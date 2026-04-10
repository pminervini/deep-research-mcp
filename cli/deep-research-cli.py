#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Unified CLI for the Deep Research system.

Supports direct agent mode (default) and MCP client mode (via --server-url).
Configuration is loaded from ~/.deep_research (TOML) with every parameter
overridable via CLI flags.

USAGE EXAMPLES:

  # Basic research query (agent mode)
  uv run python cli/deep-research-cli.py research "What are the latest treatments for diabetes?"

  # Research with a specific provider and model
  uv run python cli/deep-research-cli.py --provider gemini research "Healthcare costs in the US"

  # Research with interactive clarification
  uv run python cli/deep-research-cli.py research "Quantum computing" --clarify

  # Research with a custom system prompt from file
  uv run python cli/deep-research-cli.py research "AI trends" --system-prompt-file prompts/custom.txt

  # Research via MCP server (client mode)
  uv run python cli/deep-research-cli.py research "Climate change" --server-url http://localhost:8080/mcp

  # Check task status
  uv run python cli/deep-research-cli.py status abc123-def456

  # View resolved configuration
  uv run python cli/deep-research-cli.py config --pretty

  # Override config for a single run
  uv run python cli/deep-research-cli.py --provider openai --model gpt-5-mini --timeout 600 research "Quick query"
"""

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any

# Add src to path to import the deep_research_mcp package
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

import structlog

from deep_research_mcp import (
    DeepResearchAgent,
    ResearchConfig,
    ResearchError,
    ResearchResult,
)

DEFAULT_SYSTEM_PROMPT = """
You are a professional researcher preparing a structured, data-driven report.
Your task is to analyze the research question the user poses.

Do:
- Focus on data-rich insights: include specific figures, trends, statistics,
  and measurable outcomes.
- When appropriate, summarize data in a way that could be turned into charts
  or tables, and call this out in the response.
- Prioritize reliable, up-to-date sources: peer-reviewed research, official
  organizations, regulatory agencies, or authoritative reports.
- Include inline citations and return all source metadata.

Be analytical, avoid generalities, and ensure that each section supports
data-backed reasoning.
""".strip()


# ---------------------------------------------------------------------------
# Config override helpers
# ---------------------------------------------------------------------------


def build_cli_env(args: argparse.Namespace) -> dict[str, str]:
    """Build an env dict with CLI flag overrides injected.

    CLI flags are mapped to the same env-var keys that ResearchConfig._from_settings_map
    consumes, so provider-specific defaults are computed correctly.
    """
    mapping: dict[str, str] = {
        "provider": "RESEARCH_PROVIDER",
        "model": "RESEARCH_MODEL",
        "api_key": "RESEARCH_API_KEY",
        "base_url": "RESEARCH_BASE_URL",
        "api_style": "RESEARCH_API_STYLE",
        "timeout": "RESEARCH_TIMEOUT",
        "poll_interval": "RESEARCH_POLL_INTERVAL",
        "log_level": "LOGGING_LEVEL",
        "triage_model": "CLARIFICATION_TRIAGE_MODEL",
        "clarifier_model": "CLARIFICATION_CLARIFIER_MODEL",
        "clarification_base_url": "CLARIFICATION_BASE_URL",
        "clarification_api_key": "CLARIFICATION_API_KEY",
        "instruction_builder_model": "CLARIFICATION_INSTRUCTION_BUILDER_MODEL",
    }

    env = dict(os.environ)

    for attr_name, env_key in mapping.items():
        value = getattr(args, attr_name, None)
        if value is not None:
            env[env_key] = str(value)

    if getattr(args, "enable_clarification", False):
        env["ENABLE_CLARIFICATION"] = "true"
    if getattr(args, "enable_reasoning_summaries", False):
        env["ENABLE_REASONING_SUMMARIES"] = "true"

    return env


def load_config(args: argparse.Namespace) -> ResearchConfig:
    """Load config from file + env, then layer CLI overrides on top."""
    cli_env = build_cli_env(args)
    config_path = getattr(args, "config", None)
    return ResearchConfig.load(config_path=config_path, env=cli_env)


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


def mask_secret(value: str | None, keep: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= keep:
        return "*" * len(value)
    return ("*" * (len(value) - keep)) + value[-keep:]


def format_config(config: ResearchConfig, pretty: bool, show_secrets: bool) -> str:
    data: dict[str, Any] = asdict(config)
    if not show_secrets:
        if "api_key" in data:
            data["api_key"] = mask_secret(data["api_key"])
        if "clarification_api_key" in data:
            data["clarification_api_key"] = mask_secret(data["clarification_api_key"])

    if pretty:
        lines = [f"{k}: {data[k]}" for k in sorted(data.keys())]
        return "\n".join(lines)
    return json.dumps(data, indent=2, ensure_ascii=False)


def format_report(result: ResearchResult) -> str:
    """Format a ResearchResult as a human-readable report."""
    parts: list[str] = []

    parts.append("=" * 60)
    parts.append("RESEARCH REPORT")
    parts.append("=" * 60)

    if result.task_id:
        parts.append(f"Task ID: {result.task_id}")
    if result.total_steps:
        parts.append(f"Total steps: {result.total_steps}")
    if result.search_queries:
        parts.append(f"Search queries: {len(result.search_queries)}")
    if result.citations:
        parts.append(f"Citations: {len(result.citations)}")
    if isinstance(result.execution_time, (int, float)):
        parts.append(f"Execution time: {result.execution_time:.2f}s")

    parts.append("")
    parts.append(result.final_report)

    if result.citations:
        parts.append("")
        parts.append("=" * 60)
        parts.append("CITATIONS")
        parts.append("=" * 60)
        for citation in result.citations:
            parts.append(f"{citation.index}. [{citation.title}]({citation.url})")

    return "\n".join(parts)


def format_result_json(result: ResearchResult) -> str:
    """Format a ResearchResult as JSON."""
    data = asdict(result)
    return json.dumps(data, indent=2, ensure_ascii=False)


def format_status(task_id: str, status_data: dict[str, Any]) -> str:
    """Format a task status response."""
    parts = [f"Task ID: {task_id}"]
    for key in ("status", "created_at", "completed_at", "message", "error"):
        value = status_data.get(key)
        if value is not None:
            parts.append(f"{key}: {value}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# MCP client helpers
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _mcp_connect(url: str) -> AsyncIterator:
    """Connect to an MCP server over Streamable HTTP."""
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async with streamablehttp_client(url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            yield session


async def _mcp_progress_callback(
    progress: float, total: float | None, message: str | None
) -> None:
    if total is not None and total > 0:
        pct = (progress / total) * 100.0
        print(f"[progress] {pct:5.1f}% {message or ''}")
    else:
        print(f"[progress] {progress} {message or ''}")


def _render_mcp_result(result: Any) -> str:
    """Extract text from an MCP CallToolResult."""
    from mcp import types

    if result.structuredContent is not None:
        sc = result.structuredContent
        if isinstance(sc, dict) and "result" in sc:
            val = sc.get("result")
            return val if isinstance(val, str) else str(val)
        return str(sc)

    parts: list[str] = []
    for item in result.content or []:
        if isinstance(item, types.TextContent):
            parts.append(item.text)
        else:
            parts.append(str(item))
    return "\n".join(parts)


async def mcp_research(
    url: str,
    query: str,
    system_instructions: str,
    include_analysis: bool,
    request_clarification: bool,
    callback_url: str,
) -> tuple[int, str]:
    """Call the deep_research MCP tool. Returns (exit_code, output_text)."""
    async with _mcp_connect(url) as session:
        result = await session.call_tool(
            "deep_research",
            {
                "query": query,
                "system_instructions": system_instructions,
                "include_analysis": include_analysis,
                "request_clarification": request_clarification,
                "callback_url": callback_url,
            },
            progress_callback=_mcp_progress_callback,
        )
        output = _render_mcp_result(result)
        return (2 if result.isError else 0, output)


async def mcp_research_with_context(
    url: str,
    session_id: str,
    answers: list[str],
    system_instructions: str,
    include_analysis: bool,
    callback_url: str,
) -> tuple[int, str]:
    """Call the research_with_context MCP tool."""
    async with _mcp_connect(url) as session:
        result = await session.call_tool(
            "research_with_context",
            {
                "session_id": session_id,
                "answers": answers,
                "system_instructions": system_instructions,
                "include_analysis": include_analysis,
                "callback_url": callback_url,
            },
            progress_callback=_mcp_progress_callback,
        )
        output = _render_mcp_result(result)
        return (2 if result.isError else 0, output)


async def mcp_status(url: str, task_id: str) -> tuple[int, str]:
    """Call the research_status MCP tool."""
    async with _mcp_connect(url) as session:
        result = await session.call_tool(
            "research_status",
            {"task_id": task_id},
            progress_callback=_mcp_progress_callback,
        )
        output = _render_mcp_result(result)
        return (2 if result.isError else 0, output)


def _parse_mcp_clarification(text: str) -> tuple[str | None, list[str]]:
    """Parse session ID and questions from MCP clarification markdown output."""
    session_match = re.search(r"Session ID:\s*`([^`]+)`", text)
    session_id = session_match.group(1) if session_match else None
    questions = re.findall(r"^\d+\.\s+(.+)$", text, re.MULTILINE)
    return session_id, questions


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------


def _resolve_system_prompt(args: argparse.Namespace) -> str:
    """Resolve the system prompt from CLI flags or fall back to the default."""
    if getattr(args, "system_prompt_file", None):
        path = Path(args.system_prompt_file)
        return path.read_text(encoding="utf-8").strip()
    if getattr(args, "system_prompt", None):
        return args.system_prompt
    return DEFAULT_SYSTEM_PROMPT


async def _agent_clarification_flow(agent: DeepResearchAgent, query: str) -> str:
    """Run the interactive clarification flow. Returns the (possibly enriched) query."""
    logger = structlog.get_logger()
    logger.info("Starting clarification process...")

    clarification_result = agent.start_clarification(query)

    if not clarification_result.get("needs_clarification", False):
        logger.info(
            f"Assessment: {clarification_result.get('reasoning', 'Query is sufficient')}"
        )
        logger.info("Proceeding with original query")
        return query

    logger.info(
        f"Reasoning: {clarification_result.get('reasoning', 'No reasoning provided')}"
    )
    print("\nPlease answer the following clarifying questions:")

    questions = clarification_result.get("questions", [])
    answers: list[str] = []

    for i, question in enumerate(questions, 1):
        print(f"\n{i}. {question}")
        try:
            answer = input("Your answer (or press Enter to skip): ").strip()
        except EOFError:
            answer = ""
        answers.append(answer if answer else "[No answer provided]")

    session_id = clarification_result.get("session_id")
    if session_id:
        agent.add_clarification_answers(session_id, answers)
        enriched_query = agent.get_enriched_query(session_id)
        if enriched_query:
            logger.info(f"Enriched query: {enriched_query}")
            return enriched_query

    return query


async def cmd_research(args: argparse.Namespace) -> int:
    """Execute the research command."""
    logger = structlog.get_logger()
    system_prompt = _resolve_system_prompt(args)
    include_analysis = not getattr(args, "no_analysis", False)
    clarify = getattr(args, "clarify", False)
    callback_url = getattr(args, "callback_url", "") or ""
    server_url = getattr(args, "server_url", None)
    output_file = getattr(args, "output_file", None)
    json_output = getattr(args, "json_output", False)
    query = args.query

    # --- MCP client mode ---
    if server_url:
        logger.info(f"Connecting to MCP server at {server_url}")

        if clarify:
            rc, text = await mcp_research(
                url=server_url,
                query=query,
                system_instructions=system_prompt,
                include_analysis=include_analysis,
                request_clarification=True,
                callback_url="",
            )
            if rc != 0:
                print(text, file=sys.stderr)
                return rc

            session_id, questions = _parse_mcp_clarification(text)
            if not session_id or not questions:
                # No clarification needed, server returned assessment
                print(text)
                return 0

            print("\nPlease answer the following clarifying questions:")
            answers: list[str] = []
            for i, question in enumerate(questions, 1):
                print(f"\n{i}. {question}")
                try:
                    answer = input("Your answer (or press Enter to skip): ").strip()
                except EOFError:
                    answer = ""
                answers.append(answer if answer else "[No answer provided]")

            rc, text = await mcp_research_with_context(
                url=server_url,
                session_id=session_id,
                answers=answers,
                system_instructions=system_prompt,
                include_analysis=include_analysis,
                callback_url=callback_url,
            )
        else:
            rc, text = await mcp_research(
                url=server_url,
                query=query,
                system_instructions=system_prompt,
                include_analysis=include_analysis,
                request_clarification=False,
                callback_url=callback_url,
            )

        if rc != 0:
            print(text, file=sys.stderr)
        elif output_file:
            Path(output_file).write_text(text, encoding="utf-8")
            logger.info(f"Report written to {output_file}")
        else:
            print(text)
        return rc

    # --- Agent mode ---
    try:
        config = load_config(args)
        if clarify:
            config.enable_clarification = True
        config.validate()

        logger.info(f"Starting research with query: '{query}'")
        logger.info(f"Provider: {config.provider}, Model: {config.model}")

        agent = DeepResearchAgent(config)

        working_query = query
        if clarify:
            working_query = await _agent_clarification_flow(agent, query)

        result = await agent.research(
            query=working_query,
            system_prompt=system_prompt,
            include_code_interpreter=include_analysis,
            callback_url=callback_url or None,
        )

        if result.status == "completed":
            if json_output:
                output = format_result_json(result)
            else:
                output = format_report(result)

            if output_file:
                Path(output_file).write_text(output, encoding="utf-8")
                logger.info(f"Report written to {output_file}")
            else:
                print(output)
            return 0

        # Failed or error
        msg = result.message or "Unknown error"
        if result.error_code:
            msg = f"{msg} (code: {result.error_code})"
        logger.error(f"Research failed: {msg}")
        return 1

    except ResearchError as e:
        logger.error(f"Research error: {e}")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return 3


async def cmd_status(args: argparse.Namespace) -> int:
    """Execute the status command."""
    logger = structlog.get_logger()
    task_id = args.task_id
    server_url = getattr(args, "server_url", None)

    if server_url:
        logger.info(f"Connecting to MCP server at {server_url}")
        rc, text = await mcp_status(server_url, task_id)
        if rc != 0:
            print(text, file=sys.stderr)
        else:
            print(text)
        return rc

    try:
        config = load_config(args)
        config.validate()
        agent = DeepResearchAgent(config)
        status = await agent.get_task_status(task_id)

        parts = [f"Task ID: {status.task_id}", f"Status: {status.status}"]
        if status.created_at is not None:
            parts.append(f"Created: {status.created_at}")
        if status.completed_at is not None:
            parts.append(f"Completed: {status.completed_at}")
        if status.message:
            parts.append(f"Message: {status.message}")
        if status.error:
            parts.append(f"Error: {status.error}")
        print("\n".join(parts))
        return 0

    except ResearchError as e:
        logger.error(f"Status error: {e}")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return 3


def cmd_config(args: argparse.Namespace) -> int:
    """Execute the config command."""
    try:
        config = load_config(args)
        if not getattr(args, "no_validate", False):
            config.validate()
        output = format_config(
            config,
            pretty=getattr(args, "pretty", False),
            show_secrets=getattr(args, "show_secrets", False),
        )
        print(output)
        return 0
    except Exception as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="deep-research-cli",
        description="Unified CLI for the Deep Research system. "
        "Supports direct agent mode and MCP client mode (via --server-url).",
        epilog=(
            "examples:\n"
            "  %(prog)s research 'What are the latest AI trends?'\n"
            "  %(prog)s --provider gemini research 'Quantum computing'\n"
            "  %(prog)s research 'Climate change' --server-url http://localhost:8080/mcp\n"
            "  %(prog)s status abc123-def456\n"
            "  %(prog)s config --pretty\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # -- Global config overrides --
    cfg = parser.add_argument_group("configuration overrides")
    cfg.add_argument(
        "--config",
        default=None,
        metavar="PATH",
        help="Path to TOML config file (default: ~/.deep_research)",
    )
    cfg.add_argument(
        "--provider",
        default=None,
        choices=["openai", "gemini", "open-deep-research"],
        help="Research provider",
    )
    cfg.add_argument("--model", default=None, help="Model or agent ID")
    cfg.add_argument("--api-key", default=None, help="Provider API key")
    cfg.add_argument("--base-url", default=None, help="Provider API base URL")
    cfg.add_argument(
        "--api-style",
        default=None,
        choices=["responses", "chat_completions"],
        help="OpenAI API style",
    )
    cfg.add_argument(
        "--timeout",
        default=None,
        type=float,
        help="Max research timeout in seconds",
    )
    cfg.add_argument(
        "--poll-interval",
        default=None,
        type=float,
        help="Task poll interval in seconds",
    )
    cfg.add_argument(
        "--log-level",
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level",
    )
    cfg.add_argument(
        "--enable-clarification",
        action="store_true",
        default=False,
        help="Enable the clarification pipeline",
    )
    cfg.add_argument(
        "--enable-reasoning-summaries",
        action="store_true",
        default=False,
        help="Enable reasoning summaries",
    )
    cfg.add_argument("--triage-model", default=None, help="Model for query triage")
    cfg.add_argument(
        "--clarifier-model", default=None, help="Model for query enrichment"
    )
    cfg.add_argument(
        "--clarification-base-url",
        default=None,
        help="Base URL for clarification models",
    )
    cfg.add_argument(
        "--clarification-api-key",
        default=None,
        help="API key for clarification models",
    )
    cfg.add_argument(
        "--instruction-builder-model",
        default=None,
        help="Model for instruction building",
    )

    # -- Subcommands --
    subparsers = parser.add_subparsers(dest="command", help="available commands")

    # research
    p_research = subparsers.add_parser(
        "research", help="Perform deep research on a query"
    )
    p_research.add_argument("query", help="Research query")
    p_research.add_argument(
        "--clarify",
        action="store_true",
        help="Enable interactive clarification before research",
    )
    prompt_group = p_research.add_mutually_exclusive_group()
    prompt_group.add_argument(
        "--system-prompt", default=None, help="Inline system prompt text"
    )
    prompt_group.add_argument(
        "--system-prompt-file",
        default=None,
        metavar="PATH",
        help="Read system prompt from a file",
    )
    p_research.add_argument(
        "--no-analysis",
        action="store_true",
        help="Disable code interpreter / analysis tools",
    )
    p_research.add_argument(
        "--callback-url",
        default="",
        help="Webhook URL to notify on completion",
    )
    p_research.add_argument(
        "--server-url",
        default=None,
        help="MCP server URL (enables client mode, e.g. http://localhost:8080/mcp)",
    )
    p_research.add_argument(
        "--output-file",
        default=None,
        metavar="PATH",
        help="Write report to file instead of stdout",
    )
    p_research.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output full result as JSON (agent mode only)",
    )

    # status
    p_status = subparsers.add_parser("status", help="Check research task status")
    p_status.add_argument("task_id", help="Task ID returned by a research run")
    p_status.add_argument(
        "--server-url",
        default=None,
        help="MCP server URL (enables client mode)",
    )

    # config
    p_config = subparsers.add_parser("config", help="Display resolved configuration")
    p_config.add_argument(
        "--pretty",
        action="store_true",
        help="Human-readable output (default: JSON)",
    )
    p_config.add_argument(
        "--show-secrets",
        action="store_true",
        help="Show full API keys (default: masked)",
    )
    p_config.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip configuration validation",
    )

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        raise SystemExit(0)

    # Configure logging
    level_name = (getattr(args, "log_level", None) or "INFO").upper()
    log_level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(level=log_level, format="%(message)s")
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
    )

    if args.command == "research":
        rc = asyncio.run(cmd_research(args))
    elif args.command == "status":
        rc = asyncio.run(cmd_status(args))
    elif args.command == "config":
        rc = cmd_config(args)
    else:
        parser.print_help()
        rc = 1

    raise SystemExit(rc)


if __name__ == "__main__":
    main()
