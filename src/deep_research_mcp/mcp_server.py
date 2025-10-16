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
- Deep research with multiple backend providers (OpenAI Responses API, Open Deep Research)
- Clarification workflows to improve research quality
- Task status monitoring for long‑running research
- Configurable research parameters and system instructions
- Support for data analysis and visualization capabilities

Exposed tools:
- deep_research: Main research tool with optional clarification
- research_with_context: Research using clarification answers
- research_status: Monitor task progress

Quick start:
    # stdio (default)
    python src/deep_research_mcp/mcp_server.py

    # HTTP streaming (bind to 127.0.0.1:8080)
    python src/deep_research_mcp/mcp_server.py --transport http --host 127.0.0.1 --port 8080

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
from typing import Annotated, Optional

from fastmcp import FastMCP
from fastmcp.server.context import Context

from deep_research_mcp.agent import DeepResearchAgent
from deep_research_mcp.config import ResearchConfig
from deep_research_mcp.errors import ResearchError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize MCP server (works with both stdio and HTTP transports) -- request timeout of 6 hours
mcp = FastMCP("deep-research", request_timeout=60 * 60 * 6)

# Global agent instance
research_agent: Optional[DeepResearchAgent] = None


async def _progress_heartbeat(ctx: Context, label: str, interval_seconds: int = 60) -> None:
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
    total: Optional[float] = None,
    message: Optional[str] = None,
) -> None:
    """Best-effort progress reporting helper."""
    try:
        await ctx.report_progress(progress=progress, total=total, message=message)
    except Exception:
        logger.debug("Failed to report progress", exc_info=True)


# Define the actual async functions that will be wrapped by FastMCP
async def _deep_research_impl(
    query: Annotated[
        str,
        "Specific research question or topic. Examples: 'Latest quantum computing breakthroughs in 2024', 'Compare renewable energy adoption rates globally', 'Analyze Tesla's financial performance vs competitors'",
    ],
    system_instructions: Annotated[
        str,
        "Custom research approach instructions. Examples: 'Focus on peer-reviewed sources only', 'Include financial data and charts', 'Prioritize recent developments from 2024-2025'. Leave empty for balanced analysis.",
    ] = "",
    include_analysis: Annotated[
        bool,
        "Enable code execution for data analysis, calculations, and visualizations. Useful for: statistical analysis, creating charts/graphs, processing datasets. Set to False for text-only research.",
    ] = True,
    request_clarification: Annotated[
        bool,
        "When True, analyze the query and return clarifying questions instead of starting research. Use this to improve research quality for ambiguous queries.",
    ] = False,
    ctx: Optional[Context] = None,
) -> str:
    """
    Performs autonomous deep research using OpenAI's Deep Research API with web search and analysis capabilities.

    **What it does:**
    - Decomposes complex queries into research strategies
    - Conducts real-time web searches for current information
    - Executes code for data analysis and visualization (when include_analysis=True)
    - Synthesizes findings into comprehensive reports with citations

    **Best for:**
    - Current events and recent developments
    - Data-driven analysis requiring statistics/charts
    - Complex topics needing multiple source synthesis
    - Academic-style research with proper citations

    **Returns:** Structured markdown report with citations, metadata, and research insights.

    **Note:** Uses OpenAI's Deep Research models - monitor costs as research can generate substantial tokens.
    """
    global research_agent

    if not research_agent:
        try:
            config = ResearchConfig.from_env()
            config.validate()
            research_agent = DeepResearchAgent(config)
        except Exception as e:
            return f"Failed to initialize research agent: {str(e)}"

    try:
        # Handle clarification request
        if request_clarification:
            clarification_result = research_agent.start_clarification(query)

            if not clarification_result.get("needs_clarification", False):
                return f"""# Query Analysis

**Original Query:** {query}

**Assessment:** {clarification_result.get('query_assessment', 'Query is sufficient for research')}

**Recommendation:** {clarification_result.get('reasoning', 'Proceed with research directly')}

You can proceed with the research using the same query."""

            # Format clarifying questions for Claude Code
            questions = clarification_result.get("questions", [])
            session_id = clarification_result.get("session_id", "")

            questions_formatted = "\n".join(
                [f"{i+1}. {q}" for i, q in enumerate(questions)]
            )

            return f"""# Clarifying Questions Needed

**Original Query:** {query}

**Why clarification is helpful:** {clarification_result.get('reasoning', 'Additional context will improve research quality')}

**Session ID:** `{session_id}`

**Please answer these questions to improve the research:**

{questions_formatted}

**Instructions:** Use the `research_with_context` tool with your answers and the session ID above to proceed with enhanced research."""

        system_prompt = (
            system_instructions
            or """
        You are a professional researcher preparing a structured, data-driven report.
        Requirements:
        - Focus on data-rich insights with specific figures and statistics
        - Include tables and visualizations when appropriate  
        - Prioritize peer-reviewed sources and authoritative data
        - Use inline citations throughout
        - Be analytical and avoid generalities
        """
        )

        heartbeat_task: Optional[asyncio.Task] = None

        if ctx:
            await _safe_report_progress(
                ctx, progress=0, message="Research started...", total=None
            )
            heartbeat_task = asyncio.create_task(
                _progress_heartbeat(ctx, "Research in progress")
            )

        try:
            result = await research_agent.research(
                query=query,
                system_prompt=system_prompt,
                include_code_interpreter=include_analysis,
            )
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
                    ctx,
                    progress=1,
                    total=1,
                    message="Research ended unexpectedly",
                )
            raise
        finally:
            if heartbeat_task:
                heartbeat_task.cancel()
                with suppress(asyncio.CancelledError):
                    await heartbeat_task

        if result["status"] == "completed":
            if ctx:
                await _safe_report_progress(
                    ctx,
                    progress=1,
                    total=1,
                    message="Research completed successfully",
                )
            formatted_result = f"""# Research Report: {query}

{result['final_report']}

## Research Metadata
- **Total research steps**: {result['total_steps']}
- **Search queries executed**: {len(result['search_queries'])}
- **Citations found**: {len(result['citations'])}
- **Task ID**: {result['task_id']}

## Citations
"""
            for citation in result["citations"]:
                formatted_result += (
                    f"{citation['index']}. [{citation['title']}]({citation['url']})\n"
                )

            return formatted_result
        else:
            failure_message = result.get("message", "Unknown error")
            if ctx:
                await _safe_report_progress(
                    ctx,
                    progress=1,
                    total=1,
                    message=f"Research failed: {failure_message}",
                )
            return f"Research failed: {failure_message}"

    except ResearchError as e:
        logger.error(f"Research error: {e}")
        return f"Research error: {str(e)}"
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return f"Unexpected error: {str(e)}"


async def _research_status_impl(
    task_id: Annotated[
        str,
        "Research task ID returned by deep_research tool. Format: UUID string like 'abc123-def456-ghi789'",
    ],
) -> str:
    """
    Check the current status and progress of a running research task.

    **Use when:**
    - Research is taking a long time (>5 minutes)
    - Want to check if a task completed successfully
    - Need creation/completion timestamps

    **Returns:** Task status ('running', 'completed', 'failed') with timestamps.
    """
    global research_agent

    if not research_agent:
        return "Research agent not initialized. Please run a research query first."

    try:
        status = await research_agent.get_task_status(task_id)

        if status["status"] == "error":
            return f"Error checking status: {status.get('error', 'Unknown error')}"

        result = f"Task {task_id} status: {status['status']}"

        if status.get("created_at"):
            result += f"\nCreated at: {status['created_at']}"

        if status.get("completed_at"):
            result += f"\nCompleted at: {status['completed_at']}"

        return result

    except Exception as e:
        logger.error(f"Error checking status: {e}")
        return f"Error checking status: {str(e)}"


async def _research_with_context_impl(
    session_id: Annotated[
        str,
        "Session ID from clarification request. Get this from the deep_research tool when request_clarification=True",
    ],
    answers: Annotated[
        list[str],
        "List of answers to the clarifying questions, in the same order as the questions were presented",
    ],
    system_instructions: Annotated[
        str,
        "Custom research approach instructions. Examples: 'Focus on peer-reviewed sources only', 'Include financial data and charts', 'Prioritize recent developments from 2024-2025'. Leave empty for balanced analysis.",
    ] = "",
    include_analysis: Annotated[
        bool,
        "Enable code execution for data analysis, calculations, and visualizations. Useful for: statistical analysis, creating charts/graphs, processing datasets. Set to False for text-only research.",
    ] = True,
    ctx: Optional[Context] = None,
) -> str:
    """
    Perform research using an enriched query based on clarification answers.

    **Use after:**
    - Calling `deep_research` with `request_clarification=True`
    - Receiving clarifying questions and a session ID
    - Gathering answers from the user

    **What it does:**
    - Takes your answers to clarifying questions
    - Creates an enriched, more specific research query
    - Performs comprehensive research with the enhanced query

    **Returns:** Complete research report with citations and metadata
    """
    global research_agent

    if not research_agent:
        try:
            config = ResearchConfig.from_env()
            config.validate()
            research_agent = DeepResearchAgent(config)
        except Exception as e:
            return f"Failed to initialize research agent: {str(e)}"

    try:
        # Add answers to the clarification session
        status_result = research_agent.add_clarification_answers(session_id, answers)

        if "error" in status_result:
            return f"Error with clarification session: {status_result['error']}"

        # Get enriched query
        enriched_query = research_agent.get_enriched_query(session_id)

        if not enriched_query:
            return f"Could not retrieve enriched query for session {session_id}. Please check the session ID."

        logger.info(f"Using enriched query: {enriched_query}")

        # Prepare system prompt
        system_prompt = (
            system_instructions
            or """
        You are a professional researcher preparing a structured, data-driven report.
        Requirements:
        - Focus on data-rich insights with specific figures and statistics
        - Include tables and visualizations when appropriate  
        - Prioritize peer-reviewed sources and authoritative data
        - Use inline citations throughout
        - Be analytical and avoid generalities
        """
        )

        heartbeat_task: Optional[asyncio.Task] = None

        if ctx:
            await _safe_report_progress(
                ctx,
                progress=0,
                total=None,
                message="Research with context started...",
            )
            heartbeat_task = asyncio.create_task(
                _progress_heartbeat(ctx, "Research with context in progress")
            )

        try:
            # Perform research with enriched query
            result = await research_agent.research(
                query=enriched_query,
                system_prompt=system_prompt,
                include_code_interpreter=include_analysis,
            )
        except ResearchError:
            if ctx:
                await _safe_report_progress(
                    ctx,
                    progress=1,
                    total=1,
                    message="Contextual research ended with provider error",
                )
            raise
        except Exception:
            if ctx:
                await _safe_report_progress(
                    ctx,
                    progress=1,
                    total=1,
                    message="Contextual research ended unexpectedly",
                )
            raise
        finally:
            if heartbeat_task:
                heartbeat_task.cancel()
                with suppress(asyncio.CancelledError):
                    await heartbeat_task

        if result["status"] == "completed":
            if ctx:
                await _safe_report_progress(
                    ctx,
                    progress=1,
                    total=1,
                    message="Contextual research completed successfully",
                )
            # Format for Claude Code consumption
            formatted_result = f"""# Enhanced Research Report

**Original Query Enhanced With User Context**

**Enriched Query:** {enriched_query}

**User Clarifications Provided:** {len(answers)} answers

---

{result['final_report']}

## Research Metadata
- **Total research steps**: {result['total_steps']}
- **Search queries executed**: {len(result['search_queries'])}
- **Citations found**: {len(result['citations'])}
- **Task ID**: {result['task_id']}
- **Clarification Session**: {session_id}

## Citations
"""
            for citation in result["citations"]:
                formatted_result += (
                    f"{citation['index']}. [{citation['title']}]({citation['url']})\n"
                )

            return formatted_result
        else:
            failure_message = result.get("message", "Unknown error")
            if ctx:
                await _safe_report_progress(
                    ctx,
                    progress=1,
                    total=1,
                    message=f"Contextual research failed: {failure_message}",
                )
            return f"Research failed: {result.get('message', 'Unknown error')}"

    except Exception as e:
        logger.error(f"Error in research_with_context: {e}")
        return f"Error performing enhanced research: {str(e)}"


# Register the functions with FastMCP
_deep_research_tool = mcp.tool()(_deep_research_impl)
_research_status_tool = mcp.tool()(_research_status_impl)
_research_with_context_tool = mcp.tool()(_research_with_context_impl)

# Export the actual callable functions for direct use (Claude Code expects these to be callable)
deep_research = _deep_research_impl
research_status = _research_status_impl
research_with_context = _research_with_context_impl


def main():
    """Main entry point for MCP server.

    Use ``--transport`` to select between stdio and HTTP streaming modes.
    In HTTP mode you can customize ``--host`` and ``--port``.
    """
    parser = argparse.ArgumentParser(description="Deep Research MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport type for MCP server (default: stdio)"
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind for HTTP transport (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port to bind for HTTP transport (default: 8080)"
    )
    
    args = parser.parse_args()
    
    logger.info(f"Starting Deep Research MCP server with {args.transport} transport...")

    # Validate configuration on startup
    try:
        config = ResearchConfig.from_env()
        config.validate()
        logger.info(f"Configuration loaded successfully. Model: {config.model}")
    except Exception as e:
        logger.error(f"Configuration error: {e}")
        logger.error(
            "Please ensure OPENAI_API_KEY is set in your ~/.deep_research file or environment variables"
        )
        return

    # Run the MCP server with selected transport
    if args.transport in {"http"}:
        logger.info(f"Starting HTTP (streaming) server on {args.host}:{args.port}")
        mcp.run(transport="http", host=args.host, port=args.port)
    elif args.transport in {"stdio"}:
        logger.info("Starting stdio server")
        mcp.run()
    else:
        raise ValueError(f"Invalid transport: {args.transport}")


if __name__ == "__main__":
    main()
