# -*- coding: utf-8 -*-

"""
Test script to verify MCP server integration functionality.
This script tests the deep research MCP server tools without requiring
a full Claude Code MCP integration.
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import inspect
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

# Import the underlying functions directly
from deep_research_mcp import __version__
import deep_research_mcp.mcp_server as mcp_server
from deep_research_mcp.mcp_server import (
    deep_research,
    mcp,
    research_status,
)


@pytest.mark.asyncio
@pytest.mark.api
@pytest.mark.integration
async def test_deep_research_invalid_api_key_graceful_error():
    """Test deep_research handles invalid API keys gracefully."""
    old_provider = os.environ.get("PROVIDER")
    old_research_provider = os.environ.get("RESEARCH_PROVIDER")
    old_research_api_key = os.environ.get("RESEARCH_API_KEY")
    old_openai_api_key = os.environ.get("OPENAI_API_KEY")

    os.environ["PROVIDER"] = "openai"
    os.environ["RESEARCH_PROVIDER"] = "openai"
    os.environ["RESEARCH_API_KEY"] = "invalid-api-key"
    os.environ.pop("OPENAI_API_KEY", None)
    mcp_server._agents.clear()  # pylint: disable=protected-access

    try:
        result = await deep_research(
            query="Test query with invalid key",
            system_instructions="This is just a test",
            include_analysis=False,
        )
        assert isinstance(result, str)
        assert result.startswith("Unexpected error:") or result.startswith(
            "Research error:"
        )
    finally:
        if old_provider is None:
            os.environ.pop("PROVIDER", None)
        else:
            os.environ["PROVIDER"] = old_provider

        if old_research_provider is None:
            os.environ.pop("RESEARCH_PROVIDER", None)
        else:
            os.environ["RESEARCH_PROVIDER"] = old_research_provider

        if old_research_api_key is None:
            os.environ.pop("RESEARCH_API_KEY", None)
        else:
            os.environ["RESEARCH_API_KEY"] = old_research_api_key

        if old_openai_api_key is None:
            os.environ.pop("OPENAI_API_KEY", None)
        else:
            os.environ["OPENAI_API_KEY"] = old_openai_api_key

        mcp_server._agents.clear()  # pylint: disable=protected-access


@pytest.mark.asyncio
async def test_mcp_tool_schema():
    """The public MCP contract exposes the expected tools and arguments."""
    tools = {tool.name: tool for tool in await mcp.list_tools()}

    assert set(tools) == {"deep_research", "research_status", "list_backends"}
    assert set(tools["deep_research"].inputSchema["properties"]) == {
        "query",
        "system_instructions",
        "include_analysis",
        "callback_url",
        "backend",
    }
    assert set(tools["research_status"].inputSchema["properties"]) == {"task_id"}
    assert set(tools["list_backends"].inputSchema.get("properties", {})) == set()


def test_lazy_agent_applies_cancel_on_timeout_override():
    """The explicit server override wins over the configured timeout behavior."""
    server_env = dict(os.environ)
    server_env.update(
        {
            "RESEARCH_PROVIDER": "dr-tulu",
            "RESEARCH_MODEL": "dr-tulu",
            "RESEARCH_BASE_URL": "http://127.0.0.1:18080",
            "RESEARCH_CANCEL_ON_TIMEOUT": "true",
        }
    )
    script = (
        "import deep_research_mcp.mcp_server as server; "
        "server._cancel_on_timeout_override = False; "
        "print(server._ensure_research_agent().config.cancel_on_timeout)"
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        env=server_env,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "False"


NAMED_BACKENDS_TOML = (
    "[backends.codex]\n"
    'provider = "openai-codex"\n'
    "[backends.tulu-b]\n"
    'provider = "dr-tulu"\n'
    'base_url = "http://127.0.0.1:18081"\n'
)


def _named_backends_env(tmp_path: Path) -> dict[str, str]:
    """Server env with a dr-tulu default and two named backends in a temp HOME."""
    (tmp_path / ".deep_research").write_text(NAMED_BACKENDS_TOML, encoding="utf-8")
    server_env = dict(os.environ)
    server_env.update(
        {
            "HOME": str(tmp_path),
            "PROVIDER": "dr-tulu",
            "RESEARCH_PROVIDER": "dr-tulu",
            "RESEARCH_MODEL": "dr-tulu",
            "RESEARCH_BASE_URL": "http://127.0.0.1:18080",
        }
    )
    return server_env


def test_agents_are_cached_per_backend(tmp_path):
    """Each backend name gets its own agent; unknown names are rejected."""
    script = "\n".join(
        [
            "import deep_research_mcp.mcp_server as server",
            "from deep_research_mcp.errors import ConfigurationError",
            "default = server._ensure_research_agent()",
            "assert default is server._ensure_research_agent('default')",
            "tulu_b = server._ensure_research_agent('tulu-b')",
            "assert tulu_b is not default",
            "print(default.config.base_url, tulu_b.config.base_url)",
            "print(server._ensure_research_agent('codex').config.provider)",
            "print(server._split_task_id('tulu-b:a:b'))",
            "print(server._split_task_id('resp:abc'))",
            "try:",
            "    server._ensure_research_agent('nope')",
            "except ConfigurationError as error:",
            "    print(error)",
        ]
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        env=_named_backends_env(tmp_path),
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.splitlines() == [
        "http://127.0.0.1:18080 http://127.0.0.1:18081",
        "openai-codex",
        "('tulu-b', 'a:b')",
        "('default', 'resp:abc')",
        "Backend 'nope' is not defined in the [backends] table",
    ]


@pytest.mark.parametrize(
    "task_id, expected",
    [
        ("abc", ("default", "abc")),
        ("default:abc", ("default", "abc")),
        ("default:a:b", ("default", "a:b")),
    ],
)
def test_split_task_id_default_backend(task_id, expected):
    # pylint: disable=protected-access
    assert mcp_server._split_task_id(task_id) == expected


@pytest.mark.asyncio
async def test_deep_research_unknown_backend_returns_error():
    mcp_server._agents.clear()  # pylint: disable=protected-access
    try:
        result = await deep_research(query="Test query", backend="nope")
    finally:
        mcp_server._agents.clear()  # pylint: disable=protected-access

    assert result.startswith("Failed to initialize research agent:")
    assert "nope" in result


@pytest.mark.asyncio
async def test_stdio_server_initializes_and_exposes_tools(tmp_path):
    """Test stdio MCP handshake used by Claude Code, including named backends."""
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "deep_research_mcp.mcp_server"],
        env=_named_backends_env(tmp_path),
        cwd=Path(__file__).resolve().parents[1],
    )

    def rendered(result) -> str:
        assert result.isError is False
        return "\n".join(
            item.text for item in (result.content or []) if hasattr(item, "text")
        )

    async with stdio_client(server) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            tools = await session.list_tools()
            tool_names = {tool.name for tool in tools.tools}
            assert tool_names == {"deep_research", "research_status", "list_backends"}

            status_text = rendered(
                await session.call_tool("research_status", {"task_id": "fake-task-id"})
            )
            assert "Task fake-task-id status: unknown" in status_text

            named_text = rendered(
                await session.call_tool("research_status", {"task_id": "tulu-b:fake"})
            )
            assert "Task tulu-b:fake status: unknown" in named_text

            codex_text = rendered(
                await session.call_tool("research_status", {"task_id": "codex:fake"})
            )
            assert "not available for the openai-codex provider" in codex_text

            backends_text = rendered(await session.call_tool("list_backends", {}))
            assert "- default: provider=dr-tulu" in backends_text
            assert "base_url=http://127.0.0.1:18080" in backends_text
            assert "- tulu-b: provider=dr-tulu" in backends_text
            assert "base_url=http://127.0.0.1:18081" in backends_text
            assert "- codex: provider=openai-codex" in backends_text
            assert "oauth:" in backends_text


def test_mcp_server_structure():
    """Test that MCP server structure is correct"""
    # Check that the MCP instance exists
    assert mcp is not None
    assert mcp.name == f"deep-research (v{__version__})"

    # Check that the exported functions are callable
    assert callable(deep_research)
    assert callable(research_status)
    assert callable(mcp_server.main)

    deep_research_signature = inspect.signature(deep_research)
    assert "callback_url" in deep_research_signature.parameters


@pytest.mark.asyncio
async def test_research_status_recovered_report_keeps_backend_prefix(tmp_path):
    """A report recovered from a named backend renders the prefixed task ID.

    Uses a real local HTTP endpoint that speaks the Tavily task API, so the
    recovery path runs through the real agent and backend.
    """

    class TavilyTaskHandler(BaseHTTPRequestHandler):
        """Serve one completed Tavily research task for any task ID."""

        def do_GET(self):  # pylint: disable=invalid-name
            task_id = self.path.rsplit("/", 1)[-1]
            payload = json.dumps(
                {
                    "request_id": task_id,
                    "status": "completed",
                    "created_at": "2026-10-19T06:00:00Z",
                    "completed_at": "2026-10-19T06:05:00Z",
                    "content": "Recovered report body.",
                    "sources": [{"url": "https://example.com/a", "title": "Example"}],
                }
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            del args

    server = ThreadingHTTPServer(("127.0.0.1", 0), TavilyTaskHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        host, port = server.server_address
        (tmp_path / ".deep_research").write_text(
            "[backends.lab]\n"
            'provider = "tavily"\n'
            f'base_url = "http://{host}:{port}"\n'
            'api_key = "test-key"\n',
            encoding="utf-8",
        )
        server_env = dict(os.environ)
        server_env.update(
            {
                "HOME": str(tmp_path),
                "RESEARCH_PROVIDER": "dr-tulu",
                "RESEARCH_BASE_URL": "http://127.0.0.1:18080",
            }
        )
        mcp_server_params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "deep_research_mcp.mcp_server"],
            env=server_env,
            cwd=Path(__file__).resolve().parents[1],
        )

        async with stdio_client(mcp_server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(
                    "research_status", {"task_id": "lab:task-123"}
                )
                assert result.isError is False
                text = "\n".join(
                    item.text
                    for item in (result.content or [])
                    if hasattr(item, "text")
                )

        assert "Task lab:task-123 status: completed" in text
        assert "Recovered report body." in text
        assert "- **Task ID**: lab:task-123" in text
        assert "- **Task ID**: task-123" not in text
    finally:
        server.shutdown()
        thread.join()
        server.server_close()
