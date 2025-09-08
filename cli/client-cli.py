#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Simple HTTP-streaming MCP client for the Deep Research MCP server.

How to start the server (HTTP streaming mode):
    # Bind on 127.0.0.1:8080 and expose Streamable HTTP endpoint at /mcp
    python src/deep_research_mcp/mcp_server.py --transport http --host 127.0.0.1 --port 8080

How to connect this client to the server:
    # List available tools
    python cli/client-cli.py --url http://127.0.0.1:8080/mcp list-tools

    # Run a simple research query (streams over HTTP)
    python cli/client-cli.py --url http://127.0.0.1:8080/mcp research "What’s new in quantum computing?"

Pure curl usage (HTTP streaming):
    # 1) Initialize a session and capture the mcp-session-id response header
    SESSION_ID=$(curl -isS -X POST http://127.0.0.1:8080/mcp \
        -H 'content-type: application/json' -H 'accept: application/json' \
        --data '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{}}}' \
        | awk -F': ' 'tolower($1)=="mcp-session-id"{print $2}' | tr -d '\r')

    # 2) Send initialized notification (required by many servers)
    curl -sS -X POST http://127.0.0.1:8080/mcp \
        -H 'content-type: application/json' -H 'accept: application/json' \
        -H "mcp-session-id: $SESSION_ID" \
        --data '{"jsonrpc":"2.0","method":"notifications/initialized"}'

    # 3) List tools
    curl -sS -X POST http://127.0.0.1:8080/mcp \
        -H 'content-type: application/json' -H 'accept: application/json' \
        -H "mcp-session-id: $SESSION_ID" \
        --data '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'

    # 4) Call deep_research tool
    curl -sS -X POST http://127.0.0.1:8080/mcp \
        -H 'content-type: application/json' -H 'accept: application/json' \
        -H "mcp-session-id: $SESSION_ID" \
        --data '{
          "jsonrpc":"2.0",
          "id":3,
          "method":"tools/call",
          "params":{
            "name":"deep_research",
            "arguments":{
              "query":"What’s new in quantum computing?",
              "system_instructions":"",
              "include_analysis":true,
              "request_clarification":false
            }
          }
        }'

Notes:
    - Ensure your OpenAI credentials/config are set as described in README.md
      (e.g., OPENAI_API_KEY env var or ~/.deep_research configuration).
    - The default FastMCP Streamable HTTP path is "/mcp".
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Any, List, Optional

from fastmcp import Client as MCPClient
import mcp.types as types


async def _logging_callback(params: types.LoggingMessageNotificationParams) -> None:
    level = params.level.value if hasattr(params.level, "value") else str(params.level)
    msg = params.message
    print(f"[server-log][{level}] {msg}")


async def _progress_callback(progress: float, total: float | None, message: str | None) -> None:
    if total is not None and total > 0:
        pct = (progress / total) * 100.0
        print(f"[progress] {pct:5.1f}% {message or ''}")
    else:
        print(f"[progress] {progress} {message or ''}")


def _render_call_tool_result(result: types.CallToolResult) -> str:
    # Prefer structuredContent when present; otherwise concatenate text content items
    if result.structuredContent is not None:
        # Prefer unwrapped 'result' key if present
        sc = result.structuredContent
        if isinstance(sc, dict) and "result" in sc:
            val = sc.get("result")
            return val if isinstance(val, str) else str(val)
        return str(sc)

    parts: List[str] = []
    for item in (result.content or []):
        if isinstance(item, types.TextContent):
            parts.append(item.text)
        else:
            parts.append(str(item))
    return "\n".join(parts)


async def cmd_list_tools(url: str) -> int:
    async with MCPClient(url) as client:
        tools = await client.list_tools()
        if not tools:
            print("No tools available.")
            return 0

        print("Available tools:")
        for t in tools:
            desc = (t.description or "").strip().splitlines()[0] if t.description else ""
            print(f"- {t.name}: {desc}")
        return 0


async def cmd_research(
    url: str,
    query: str,
    system_instructions: str,
    include_analysis: bool,
    request_clarification: bool,
) -> int:
    async with MCPClient(url) as client:
        print("Connected.")

        args = {
            "query": query,
            "system_instructions": system_instructions,
            "include_analysis": include_analysis,
            "request_clarification": request_clarification,
        }

        print("Calling tool: deep_research ...")
        result = await client.call_tool_mcp("_deep_research_impl", args, progress_handler=_progress_callback)
        if result.isError:
            print("Tool error:")
            print(_render_call_tool_result(result))
            return 2

        output = _render_call_tool_result(result)
        print(output)
        return 0


async def cmd_status(url: str, task_id: str) -> int:
    async with MCPClient(url) as client:
        print("Connected.")

        print("Calling tool: research_status ...")
        result = await client.call_tool_mcp("_research_status_impl", {"task_id": task_id}, progress_handler=_progress_callback)
        if result.isError:
            print("Tool error:")
            print(_render_call_tool_result(result))
            return 2

        print(_render_call_tool_result(result))
        return 0


async def cmd_research_with_context(
    url: str,
    session_id: str,
    answers: List[str],
    system_instructions: str,
    include_analysis: bool,
) -> int:
    async with MCPClient(url) as client:
        print("Connected.")

        print("Calling tool: research_with_context ...")
        result = await client.call_tool_mcp(
            "_research_with_context_impl",
            {
                "session_id": session_id,
                "answers": answers,
                "system_instructions": system_instructions,
                "include_analysis": include_analysis,
            },
            progress_handler=_progress_callback,
        )
        if result.isError:
            print("Tool error:")
            print(_render_call_tool_result(result))
            return 2

        print(_render_call_tool_result(result))
        return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Simple HTTP-streaming MCP client for Deep Research MCP server",
    )
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8080/mcp",
        help="Server URL (FastMCP Streamable HTTP endpoint). Default: http://127.0.0.1:8080/mcp",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list-tools", help="List available MCP tools")

    p_research = sub.add_parser("research", help="Run the deep_research tool")
    p_research.add_argument("query", help="Research query text")
    p_research.add_argument(
        "-s",
        "--system-instructions",
        default="",
        help="Optional system instructions for the research agent",
    )
    p_research.add_argument(
        "--no-analysis",
        action="store_true",
        help="Disable code/analysis tools during research",
    )
    p_research.add_argument(
        "--clarify",
        action="store_true",
        help="Request clarifying questions instead of starting research",
    )

    p_status = sub.add_parser("status", help="Check status of a research task")
    p_status.add_argument("task_id", help="Task ID returned by deep_research")

    p_ctx = sub.add_parser("research-with-context", help="Run research_with_context with answers")
    p_ctx.add_argument("session_id", help="Session ID returned by deep_research when requesting clarification")
    p_ctx.add_argument(
        "--answer",
        action="append",
        dest="answers",
        default=[],
        help="Answer to a clarifying question (repeat for multiple)",
    )
    p_ctx.add_argument(
        "-s",
        "--system-instructions",
        default="",
        help="Optional system instructions for the research agent",
    )
    p_ctx.add_argument(
        "--no-analysis",
        action="store_true",
        help="Disable code/analysis tools during research",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.command == "list-tools":
        rc = asyncio.run(cmd_list_tools(args.url))
        raise SystemExit(rc)

    if args.command == "research":
        rc = asyncio.run(
            cmd_research(
                url=args.url,
                query=args.query,
                system_instructions=args.system_instructions,
                include_analysis=not args.no_analysis,
                request_clarification=args.clarify,
            )
        )
        raise SystemExit(rc)

    if args.command == "status":
        rc = asyncio.run(cmd_status(args.url, args.task_id))
        raise SystemExit(rc)

    if args.command == "research-with-context":
        rc = asyncio.run(
            cmd_research_with_context(
                url=args.url,
                session_id=args.session_id,
                answers=args.answers,
                system_instructions=args.system_instructions,
                include_analysis=not args.no_analysis,
            )
        )
        raise SystemExit(rc)

    raise SystemExit(2)


if __name__ == "__main__":
    main()
