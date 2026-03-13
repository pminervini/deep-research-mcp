# -*- coding: utf-8 -*-

"""
Test script to verify MCP server integration functionality.
This script tests the deep research MCP server tools without requiring
a full Claude Code MCP integration.
"""

import os

import pytest

# Import the underlying functions directly
from deep_research_mcp import __version__
import deep_research_mcp.mcp_server as mcp_server
from deep_research_mcp.mcp_server import deep_research, research_status, research_with_context, mcp


@pytest.mark.asyncio
async def test_research_status():
    """Test the research_status tool with a fake task ID"""
    mcp_server.research_agent = None
    result = await research_status("fake-task-id")
    assert result is not None
    assert isinstance(result, str)
    # May return "not initialized" if agent is uninitialized,
    # or an error if the agent is initialized but task ID is invalid
    assert "Research agent not initialized" in result or "Error checking status" in result


@pytest.mark.asyncio
async def test_deep_research_without_api():
    """Test deep_research tool initialization (without actual API call)"""
    result = await deep_research(query="Test query for MCP integration", system_instructions="This is just a test", include_analysis=False)

    assert result is not None
    assert isinstance(result, str)
    # Should either work with valid config or show error without API keys
    assert "Research Report:" in result or "Failed to initialize research agent" in result or "Unexpected error:" in result


@pytest.mark.asyncio
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
        result = await deep_research(query="Test query with invalid key", system_instructions="This is just a test", include_analysis=False)
        assert isinstance(result, str)
        assert result.startswith("Unexpected error:") and "invalid_api_key" in result
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
async def test_research_with_context():
    """Test the research_with_context tool"""
    result = await research_with_context(session_id="fake-session-id", answers=["Answer 1", "Answer 2"], system_instructions="Test instructions", include_analysis=False)

    assert result is not None
    assert isinstance(result, str)
    # Should contain error about session not found or initialization failure
    assert "Session fake-session-id not found" in result or "Failed to initialize research agent" in result


def test_mcp_server_structure():
    """Test that MCP server structure is correct"""
    # Check that the MCP instance exists
    assert mcp is not None
    assert mcp.name == f"deep-research (v{__version__})"

    # Check that the exported functions are callable
    assert callable(deep_research)
    assert callable(research_status)
    assert callable(research_with_context)
