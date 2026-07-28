# -*- coding: utf-8 -*-

"""
Test script to verify MCP server integration functionality.
This script tests the deep research MCP server tools without requiring
a full Claude Code MCP integration.
"""

import inspect
import os
import subprocess
import sys
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
    mcp_server.research_agent = None

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

        mcp_server.research_agent = None


@pytest.mark.asyncio
async def test_mcp_tool_schema():
    """The public MCP contract exposes the expected tools and arguments."""
    tools = {tool.name: tool for tool in await mcp.list_tools()}

    assert set(tools) == {"deep_research", "research_status"}
    assert set(tools["deep_research"].inputSchema["properties"]) == {
        "query",
        "system_instructions",
        "include_analysis",
        "callback_url",
    }
    assert set(tools["research_status"].inputSchema["properties"]) == {"task_id"}


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


@pytest.mark.asyncio
async def test_stdio_server_initializes_and_exposes_tools():
    """Test stdio MCP handshake used by Claude Code."""
    server_env = dict(os.environ)
    server_env.update(
        {
            "PROVIDER": "dr-tulu",
            "RESEARCH_PROVIDER": "dr-tulu",
            "RESEARCH_MODEL": "dr-tulu",
            "RESEARCH_BASE_URL": "http://127.0.0.1:18080",
        }
    )
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "deep_research_mcp.mcp_server"],
        env=server_env,
        cwd=Path(__file__).resolve().parents[1],
    )

    async with stdio_client(server) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            tools = await session.list_tools()
            tool_names = {tool.name for tool in tools.tools}
            assert tool_names == {"deep_research", "research_status"}

            result = await session.call_tool(
                "research_status", {"task_id": "fake-task-id"}
            )
            assert result.isError is False

            text_items = [
                item.text for item in (result.content or []) if hasattr(item, "text")
            ]
            rendered_text = "\n".join(text_items)
            assert "status: unknown" in rendered_text


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
