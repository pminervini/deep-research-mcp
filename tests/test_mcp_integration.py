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
from deep_research_mcp.cli import _render_mcp_result
from deep_research_mcp.mcp_server import (
    deep_research,
    mcp,
    research_status,
)
from tests.tui_test_utils import load_tui_module


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
        assert result["status"] in {"failed", "error"}
        assert result["message"]
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
    output_schema = tools["list_backends"].outputSchema
    assert output_schema is not None
    assert set(output_schema["properties"]) == {"backends", "error"}
    assert output_schema["properties"]["backends"]["type"] == "array"
    backend_schema = output_schema["$defs"]["BackendInfo"]["properties"]
    assert {"name", "provider", "reasoning_effort", "api_key_present"} <= set(
        backend_schema
    )
    assert "api_key" not in backend_schema
    for name in ("deep_research", "research_status"):
        schema = tools[name].outputSchema
        assert schema is not None
        assert schema["type"] == "object"
        assert "result" not in schema.get("required", [])


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

    assert result["status"] == "error"
    assert result["message"].startswith("Failed to initialize research agent:")
    assert "nope" in result["message"]


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

            for task_id, expected_id in (
                ("fake-task-id", "default:fake-task-id"),
                ("tulu-b:fake", "tulu-b:fake"),
                ("codex:fake", "codex:fake"),
            ):
                response = await session.call_tool(
                    "research_status", {"task_id": task_id}
                )
                payload = response.structuredContent
                assert payload is not None
                assert json.loads(rendered(response)) == payload
                assert payload["task_id"] == expected_id
                assert payload["status"] == "unknown"
                assert payload["result"] is None
                if task_id.startswith("codex:"):
                    assert (
                        "not available for the openai-codex provider"
                        in payload["message"]
                    )

            listing = await session.call_tool("list_backends", {})
            assert listing.structuredContent is not None
            assert json.loads(rendered(listing)) == listing.structuredContent
            assert listing.structuredContent["error"] is None
            backends = {
                item["name"]: item for item in listing.structuredContent["backends"]
            }
            assert list(backends) == ["default", "codex", "tulu-b"]
            assert backends["default"]["provider"] == "dr-tulu"
            assert backends["default"]["base_url"] == "http://127.0.0.1:18080"
            assert backends["tulu-b"]["provider"] == "dr-tulu"
            assert backends["tulu-b"]["base_url"] == "http://127.0.0.1:18081"
            assert backends["codex"]["provider"] == "openai-codex"
            assert backends["codex"]["oauth_present"] is False
            assert backends["codex"]["api_key_present"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("global_error", [False, True])
async def test_list_backends_errors_stay_structured_over_stdio(
    tmp_path: Path, global_error: bool
) -> None:
    """Configuration changes after startup retain the advertised output schema."""
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "deep_research_mcp.mcp_server"],
        env=_named_backends_env(tmp_path),
        cwd=Path(__file__).resolve().parents[1],
    )
    async with stdio_client(server) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            (tmp_path / ".deep_research").write_text(
                (
                    "invalid TOML"
                    if global_error
                    else '[backends.broken]\nprovider = "unsupported"\n'
                ),
                encoding="utf-8",
            )
            result = await session.call_tool("list_backends", {})
            assert not result.isError
            payload = result.structuredContent
            assert payload is not None
            text = "\n".join(
                item.text for item in result.content if item.type == "text"
            )
            assert json.loads(text) == payload
            if global_error:
                assert payload["backends"] == []
                assert payload["error"]
                failure = await session.call_tool(
                    "research_status", {"task_id": "raw-id"}
                )
                assert not failure.isError
                assert failure.structuredContent is not None
                assert failure.structuredContent["status"] == "error"
                assert failure.structuredContent["task_id"] == "default:raw-id"
                assert failure.structuredContent["error"]
                assert failure.structuredContent["result"] is None
            else:
                assert payload["error"] is None
                assert payload["backends"][0]["name"] == "default"
                assert payload["backends"][0]["error"] is None
                assert payload["backends"][1]["name"] == "broken"
                assert "unsupported" in payload["backends"][1]["error"]


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
@pytest.mark.parametrize("backend", ["", "lab"])
@pytest.mark.parametrize(
    "task_id",
    ["complete", "failed", "running", "http-error", "recovery-error", "unavailable"],
)
async def test_research_status_recovered_report_keeps_backend_prefix(
    tmp_path: Path, backend: str, task_id: str
) -> None:
    """Exercise research/recovery JSON through the existing loopback provider."""
    # pylint: disable=protected-access
    report = "# Provider-authored report\n\nUnicode: café."
    citation = {"index": 1, "title": "Example", "url": "https://example.com/a"}
    reads = 0

    class TavilyTaskHandler(BaseHTTPRequestHandler):
        """Serve explicit local test data, including provider/recovery failures."""

        def do_POST(self) -> None:  # pylint: disable=invalid-name
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({"request_id": task_id}).encode())

        def do_GET(self) -> None:  # pylint: disable=invalid-name
            nonlocal reads
            assert self.path == f"/research/{task_id}"
            reads += 1
            status = task_id if task_id in {"running", "failed"} else "completed"
            if task_id == "unavailable" and reads > 1:
                status = "running"
            payload = json.dumps(
                {
                    "request_id": task_id,
                    "status": status,
                    "created_at": "2026-10-19T06:00:00Z",
                    "completed_at": "2026-10-19T06:05:00Z",
                    "content": report,
                    "detail": "Fixture provider failure",
                    "sources": [{"url": "https://example.com/a", "title": "Example"}],
                }
            ).encode("utf-8")
            self.send_response(
                500
                if task_id == "http-error"
                or (task_id == "recovery-error" and reads > 1)
                else 200
            )
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
        table = (
            'provider = "tavily"\n'
            f'base_url = "http://{host}:{port}"\n'
            'api_key = "test-key"\ntimeout = 0.02\npoll_interval = 0.02\n'
        )
        (tmp_path / ".deep_research").write_text(
            f"[research]\n{table}[backends.lab]\n{table}",
            encoding="utf-8",
        )
        mcp_server_params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "deep_research_mcp.mcp_server"],
            env={"HOME": str(tmp_path), "PATH": os.environ.get("PATH", "")},
            cwd=Path(__file__).resolve().parents[1],
        )

        async with stdio_client(mcp_server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tagged_id = f"{backend or 'default'}:{task_id}"
                if task_id not in {"recovery-error", "unavailable"}:
                    research = await session.call_tool(
                        "deep_research", {"query": task_id, "backend": backend}
                    )
                    assert not research.isError
                    data = research.structuredContent
                    assert data is not None
                    assert json.loads(_render_mcp_result(research)) == data
                    research_text = "\n".join(
                        item.text for item in research.content if item.type == "text"
                    )
                    assert json.loads(research_text) == data
                    assert "test-key" not in research_text
                    assert data["task_id"] == tagged_id
                    assert isinstance(data["execution_time"], (int, float))
                    assert data["citations"] == (
                        [citation] if task_id == "complete" else []
                    )
                    assert data["status"] == (
                        "completed" if task_id == "complete" else "failed"
                    )
                    assert data["final_report"] == (
                        report if task_id == "complete" else ""
                    )
                    assert data["status"] == "completed" or data["message"]
                    reads = 0
                result = await session.call_tool(
                    "research_status", {"task_id": tagged_id}
                )
                assert result.isError is False
                text = "\n".join(
                    item.text
                    for item in (result.content or [])
                    if hasattr(item, "text")
                )

        payload = result.structuredContent
        assert payload is not None
        assert json.loads(text) == payload
        assert payload["task_id"] == tagged_id
        assert json.loads(_render_mcp_result(result)) == payload
        assert "test-key" not in text
        if task_id == "complete":
            assert payload["status"] == "completed"
            assert payload["created_at"] == "2026-10-19T06:00:00Z"
            assert payload["result"]["final_report"] == report
            assert payload["result"]["task_id"] == tagged_id
            assert payload["completed_at"] == "2026-10-19T06:05:00Z"
            assert payload["result"]["citations"] == [citation]
            tui = load_tui_module()
            assert tui._render_mcp_result is _render_mcp_result
            assert json.loads(tui._render_mcp_result(result)) == payload
        else:
            assert payload["result"] is None
        if task_id in {"http-error", "recovery-error"}:
            assert payload["error"]
            assert payload["status"] == (
                "error" if task_id == "http-error" else "completed"
            )
    finally:
        server.shutdown()
        thread.join()
        server.server_close()
