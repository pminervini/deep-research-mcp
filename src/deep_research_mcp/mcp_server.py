#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MCP Server for Deep Research Agent

This module provides an MCP (Model Context Protocol) server interface for the
Deep Research Agent. It exposes research capabilities through standardized MCP
tools that can be used by AI assistants and other MCP‑compatible clients.

Transports:
- stdio (default) — for editors/CLIs that spawn a local process
- http (streaming) — runs a local HTTP server with streaming responses so
  MCP‑over‑HTTP clients can connect over the network

Features:
- Deep research with multiple backend providers (OpenAI API, experimental OpenAI Codex subscription, Gemini Deep Research, Tavily Research, DR-Tulu, Gnosis)
- Task status monitoring for long‑running research
- Configurable research parameters and system instructions
- Support for data analysis and visualization capabilities

Exposed tools:
- deep_research: Main research tool (optionally targeting a named backend)
- research_status: Monitor task progress
- list_backends: List the default and named backends declared in the config

Quick start:
    # stdio (default)
    uv run deep-research-mcp

    # HTTP streaming (bind to 127.0.0.1:8080)
    uv run deep-research-mcp --transport http --host 127.0.0.1 --port 8080

Note: In HTTP mode, responses are streamed by the underlying FastMCP HTTP
server. The tools in this module currently return their full results when a
research task completes; clients that support streaming will still benefit from
the HTTP transport and any incremental events emitted by the server.

Based on the deep research patterns from:
https://cookbook.openai.com/examples/deep_research_api/introduction_to_deep_research_api_agents
"""

import argparse
import asyncio
import logging
from contextlib import suppress
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Any, Literal, cast

from mcp.server.fastmcp import Context, FastMCP

from deep_research_mcp import __version__
from deep_research_mcp.agent import DeepResearchAgent
from deep_research_mcp.auth import load_http_auth
from deep_research_mcp.codex_auth import DEFAULT_CODEX_AUTH_PATH
from deep_research_mcp.config import (
    DEFAULT_BACKEND_NAME,
    ResearchConfig,
    load_backend_names,
    split_backend_task_id,
)
from deep_research_mcp.errors import ResearchError
from deep_research_mcp.results import (
    BackendInfo,
    BackendListResult,
    ResearchResult,
    ResearchTaskStatus,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
LogLevelName = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
VALID_LOG_LEVELS: set[str] = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

DEFAULT_RESEARCH_SYSTEM_PROMPT = """You are a professional researcher preparing a structured, data-driven report.
Requirements:
- Focus on data-rich insights with specific figures and statistics
- Include tables and visualizations when appropriate
- Prioritize peer-reviewed sources and authoritative data
- Use inline citations throughout
- Be analytical and avoid generalities
"""

# Lazily built agents keyed by backend name ("default" for the [research] table).
_agents: dict[str, DeepResearchAgent] = {}

# Command-line override applied when the agent is created lazily.
_cancel_on_timeout_override: bool | None = None

# Claude Code persists tool results above its default size threshold to disk
# unless the tool declares a higher limit; research reports are inherently
# large, so request the maximum allowed (500k chars).
RESEARCH_TOOL_META = {"anthropic/maxResultSizeChars": 500_000}

# Initialize FastMCP server at module level with metadata
token_verifier, auth_settings = load_http_auth()
mcp = FastMCP(
    name=f"deep-research (v{__version__})",
    instructions=(
        "Deep Research MCP Server - Autonomous research agent with web search, "
        "data analysis, and citation capabilities. Supports OpenAI Responses API, "
        "OpenAI Chat Completions API (compatible with Perplexity, Groq, Ollama, "
        "and other providers), experimental OpenAI Codex subscription access, "
        "Gemini Deep Research via the Interactions API, Tavily Research, "
        "and DR-Tulu. Use deep_research for comprehensive "
        "research queries, list_backends to see the named backends the server "
        "operator has configured (pass one as the backend argument), and "
        "research_status where the provider supports task recovery."
    ),
    website_url="https://github.com/pminervini/deep-research-mcp",
    debug=False,
    log_level="INFO",
    token_verifier=token_verifier,
    auth=auth_settings,
)


def _apply_logging_config(log_level: str) -> None:
    """Apply configured log level to the root logger and FastMCP settings."""
    normalized_log_level = log_level.upper()
    if normalized_log_level not in VALID_LOG_LEVELS:
        normalized_log_level = "INFO"
    typed_log_level = cast(LogLevelName, normalized_log_level)
    logging.getLogger().setLevel(typed_log_level)
    logger.setLevel(typed_log_level)
    mcp.settings.log_level = typed_log_level


def _ensure_research_agent(backend: str = "") -> DeepResearchAgent:
    """Reuse the agent for a backend name, creating it on demand."""
    name = backend or DEFAULT_BACKEND_NAME
    agent = _agents.get(name)

    if agent is None:
        config = ResearchConfig.load(backend=name)
        if _cancel_on_timeout_override is not None:
            config.cancel_on_timeout = _cancel_on_timeout_override
        config.validate()
        _apply_logging_config(config.log_level)
        agent = DeepResearchAgent(config)
        _agents[name] = agent

    return agent


def _tag_task_id(backend: str, task_id: str) -> str:
    """Prefix a provider task ID with the backend name so it can be routed back."""
    return f"{backend}:{task_id}"


def _split_task_id(task_id: str) -> tuple[str, str]:
    """Split '<backend>:<id>' into its parts; un-prefixed IDs use the default."""
    backend, raw_task_id = split_backend_task_id(task_id)
    return backend or DEFAULT_BACKEND_NAME, raw_task_id


async def _progress_heartbeat(
    ctx: Context, label: str, interval_seconds: int = 60
) -> None:
    """Send periodic heartbeat updates to keep long jobs alive."""
    minutes = 1
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await ctx.report_progress(
                progress=minutes,
                message=f"{label} ({minutes} minute{'s' if minutes != 1 else ''})",
            )
        except Exception:
            logger.debug("Progress heartbeat failed", exc_info=True)
            return
        minutes += 1


async def _safe_report_progress(
    ctx: Context,
    *,
    progress: float,
    total: float | None = None,
    message: str | None = None,
) -> None:
    """Best-effort progress reporting helper."""
    try:
        await ctx.report_progress(progress=progress, total=total, message=message)
    except Exception:
        logger.debug("Failed to report progress", exc_info=True)


async def _run_research_with_progress(
    *,
    agent: DeepResearchAgent,
    backend: str,
    query: str,
    system_instructions: str,
    include_analysis: bool,
    callback_url: str,
    ctx: Context | None,
) -> ResearchResult:
    """Run research while managing progress reporting and heartbeats.

    The returned result carries a backend-tagged task ID (see _tag_task_id).
    """
    heartbeat_task: asyncio.Task[None] | None = None
    started_task_id: str | None = None

    if ctx:
        await _safe_report_progress(
            ctx, progress=0, message="Research started...", total=None
        )
        heartbeat_task = asyncio.create_task(
            _progress_heartbeat(ctx, "Research in progress")
        )

    async def report_task_started(task_id: str) -> None:
        nonlocal started_task_id
        started_task_id = task_id
        if ctx:
            await _safe_report_progress(
                ctx,
                progress=0,
                message=(
                    f"Research task started (task ID: {_tag_task_id(backend, task_id)}). "
                    "If this call is lost, recover the result with research_status."
                ),
            )

    try:
        result = await agent.research(
            query=query,
            system_prompt=system_instructions or DEFAULT_RESEARCH_SYSTEM_PROMPT,
            include_code_interpreter=include_analysis,
            callback_url=callback_url or None,
            on_task_started=report_task_started,
        )
        # Timeout paths may return a failed result without the provider task ID.
        if result.task_id is None and started_task_id is not None:
            result.task_id = started_task_id
        if result.task_id is not None:
            result.task_id = _tag_task_id(backend, result.task_id)
        return result
    except ResearchError:
        if ctx:
            await _safe_report_progress(
                ctx,
                progress=1,
                total=1,
                message="Research ended with provider error",
            )
        raise
    except Exception:
        if ctx:
            await _safe_report_progress(
                ctx, progress=1, total=1, message="Research ended unexpectedly"
            )
        raise
    finally:
        if heartbeat_task:
            heartbeat_task.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat_task


# Define the actual async functions that will be wrapped by FastMCP
@mcp.tool(meta=RESEARCH_TOOL_META, structured_output=True)
async def deep_research(
    query: Annotated[
        str,
        "Complete research question or topic, including any user-provided context "
        "needed to answer it. Examples: 'Latest quantum computing breakthroughs "
        "in 2024', 'Compare renewable energy adoption rates globally', "
        "'Analyze Tesla's financial performance vs competitors'",
    ],
    system_instructions: Annotated[
        str,
        "Custom research approach instructions. Examples: 'Focus on peer-reviewed sources only', 'Include financial data and charts', 'Prioritize recent developments from 2024-2025'. Leave empty for balanced analysis.",
    ] = "",
    include_analysis: Annotated[
        bool,
        "Enable code execution for data analysis, calculations, and visualizations. Useful for: statistical analysis, creating charts/graphs, processing datasets. Set to False for text-only research.",
    ] = True,
    callback_url: Annotated[
        str,
        "Optional webhook URL notified with a completion payload when the research finishes. Leave empty to disable callbacks.",
    ] = "",
    backend: Annotated[
        str,
        "Name of a backend declared in the server's [backends] config table. Leave empty for the default backend. Use list_backends to see what is available.",
    ] = "",
    ctx: Context | None = None,
) -> dict[str, Any]:
    """
    Performs autonomous deep research using the configured provider with web search and analysis capabilities.

    **What it does:**
    - Decomposes complex queries into research strategies
    - Conducts real-time web searches for current information
    - Executes code for data analysis and visualization when the provider supports it
    - Synthesizes findings into comprehensive reports with citations

    **Best for:**
    - Current events and recent developments
    - Data-driven analysis requiring statistics/charts
    - Complex topics needing multiple source synthesis
    - Academic-style research with proper citations

    **Returns:** A structured research result with status, task_id, final_report,
    citations, reasoning_steps, search_queries, total_steps, message, error_code,
    and execution_time. Provider-written report text is preserved unchanged.
    Failures use the same fields with status='failed' or 'error'.

    **Note:** Uses provider-native research backends - monitor costs as research can generate substantial tokens.
    """
    try:
        agent = _ensure_research_agent(backend)
    except Exception as e:
        return asdict(
            ResearchResult.error(message=f"Failed to initialize research agent: {e}")
        )

    try:
        result = await _run_research_with_progress(
            agent=agent,
            backend=backend or DEFAULT_BACKEND_NAME,
            query=query,
            system_instructions=system_instructions,
            include_analysis=include_analysis,
            callback_url=callback_url,
            ctx=ctx,
        )
        if result.is_completed:
            if ctx:
                await _safe_report_progress(
                    ctx,
                    progress=1,
                    total=1,
                    message="Research completed successfully",
                )
        elif ctx:
            await _safe_report_progress(
                ctx,
                progress=1,
                total=1,
                message=f"Research failed: {result.message or 'Unknown error'}",
            )
        return asdict(result)

    except ResearchError as e:
        logger.error(f"Research error: {e}")
        return asdict(ResearchResult.error(message=f"Research error: {e}"))
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return asdict(ResearchResult.error(message=f"Unexpected error: {e}"))


@mcp.tool(meta=RESEARCH_TOOL_META, structured_output=True)
async def research_status(
    task_id: Annotated[
        str,
        "Research task ID returned by deep_research tool, passed back verbatim. Format: '<backend>:<provider task id>' like 'default:abc123-def456-ghi789'; an un-prefixed ID is looked up on the default backend.",
    ],
) -> dict[str, Any]:
    """
    Check the current status and progress of a running research task.

    **Use when:**
    - Research is taking a long time (>5 minutes)
    - Want to check if a task completed successfully
    - Need to recover the report from a task whose original call was lost

    **Returns:** A structured object with task_id, status, created_at,
    completed_at, message, error, and result. Task IDs are backend-prefixed.
    The result is a full research result when recovered, otherwise null.
    Status/initialization failures use status='error'; a recovery failure
    preserves the provider status and sets error. Report text is not reformatted.
    """
    try:
        backend, raw_task_id = _split_task_id(task_id)
        task_id = _tag_task_id(backend, raw_task_id)
        agent = _ensure_research_agent(backend)
    except Exception as e:
        return {
            **asdict(ResearchTaskStatus.error_status(task_id=task_id, error=str(e))),
            "result": None,
        }

    try:
        status = await agent.get_task_status(raw_task_id)
        status.task_id = task_id
        result: ResearchResult | None = None
        if status.status == "completed":
            try:
                task_result = await agent.get_task_result(raw_task_id)
            except Exception as error:
                logger.error(f"Error fetching result for task {task_id}: {error}")
                status.error = str(error)
                task_result = None
            if task_result and task_result.is_completed:
                task_result.task_id = _tag_task_id(
                    backend, task_result.task_id or raw_task_id
                )
                result = task_result
        return {**asdict(status), "result": asdict(result) if result else None}

    except Exception as e:
        logger.error(f"Error checking status: {e}")
        return {
            **asdict(ResearchTaskStatus.error_status(task_id=task_id, error=str(e))),
            "result": None,
        }


@mcp.tool(structured_output=True)
def list_backends() -> BackendListResult:
    """
    List the research backends this server can use with the deep_research tool.

    **Returns:** A structured object with a backends array and an error field.
    Entries include name, provider, model, base_url, api_style, reasoning_effort,
    and provider-specific presence flags: api_key_present, oauth_present,
    run_options_present, shared_output_present. Inapplicable fields are null.
    No credential values or Gnosis file contents are returned. Presence does
    not prove valid authentication or service health; local services may not
    need an API key. 'default' describes [research]; other names describe
    [backends.<name>]. Configuration failures appear in the top-level error
    or the affected entry's error. Successful error fields are null.
    """
    try:
        names = [DEFAULT_BACKEND_NAME, *load_backend_names()]
    except Exception as e:
        return BackendListResult(error=f"Failed to load configuration: {str(e)}")

    backends: list[BackendInfo] = []
    for name in names:
        try:
            config = ResearchConfig.load(backend=name)
        except Exception as error:
            backends.append(BackendInfo(name=name, error=str(error)))
            continue
        backend = BackendInfo(
            name=name,
            provider=config.provider,
            model=config.model,
            base_url=config.base_url,
            api_style=config.api_style if config.provider == "openai" else None,
            reasoning_effort=config.reasoning_effort,
        )
        if config.provider == "openai-codex":
            backend.oauth_present = DEFAULT_CODEX_AUTH_PATH.exists()
        else:
            backend.api_key_present = bool(config.api_key)
        if config.provider == "gnosis":
            backend.run_options_present = bool(
                config.gnosis_config_path
                and Path(config.gnosis_config_path).expanduser().is_file()
            )
            backend.shared_output_present = bool(
                config.gnosis_output_dir
                and Path(config.gnosis_output_dir).expanduser().is_dir()
            )
        backends.append(backend)
    return BackendListResult(backends=backends)


def main():
    """Main entry point for MCP server.

    Use ``--transport`` to select between stdio and HTTP streaming modes.
    In HTTP mode you can customize ``--host`` and ``--port``.
    """
    global _cancel_on_timeout_override

    parser = argparse.ArgumentParser(description="Deep Research MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport type for MCP server (default: stdio)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind for HTTP transport (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port to bind for HTTP transport (default: 8080)",
    )
    parser.add_argument(
        "--cancel-on-timeout",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Cancel the provider research task when it exceeds the configured "
            "timeout. Defaults to the cancel_on_timeout config value (false), "
            "which leaves the task running so the result can be recovered "
            "with research_status."
        ),
    )

    args = parser.parse_args()

    _cancel_on_timeout_override = args.cancel_on_timeout

    logger.info(f"Starting Deep Research MCP server with {args.transport} transport...")

    # Validate configuration on startup
    try:
        config = ResearchConfig.load()
        config.validate()
        _apply_logging_config(config.log_level)
        logger.info(f"Configuration loaded successfully. Model: {config.model}")
        for name in load_backend_names():
            backend_config = ResearchConfig.load(backend=name)
            backend_config.validate()
            logger.info(
                f"Backend '{name}' configured. Provider: {backend_config.provider}, "
                f"Model: {backend_config.model}"
            )
    except Exception as e:
        logger.error(f"Configuration error: {e}")
        logger.error(
            "Please ensure provider credentials are set in your ~/.deep_research file or environment variables"
        )
        return

    # Update host and port settings for HTTP transport
    mcp.settings.host = args.host
    mcp.settings.port = args.port

    # Run the MCP server with selected transport
    if args.transport == "http":
        logger.info(f"Starting HTTP (streaming) server on {args.host}:{args.port}")
        mcp.run(transport="streamable-http")
    else:
        logger.info("Starting stdio server")
        mcp.run()


if __name__ == "__main__":
    main()
