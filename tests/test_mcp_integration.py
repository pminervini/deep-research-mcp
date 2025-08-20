# -*- coding: utf-8 -*-

"""
Test script to verify MCP server integration functionality.
This script tests the deep research MCP server tools without requiring
a full Claude Code MCP integration.
"""

import pytest

# Import the underlying functions directly
from deep_research_mcp.mcp_server import deep_research, research_status, research_with_context, mcp


@pytest.mark.asyncio
async def test_research_status():
    """Test the research_status tool with a fake task ID"""
    result = await research_status.fn("fake-task-id")
    assert result is not None
    assert isinstance(result, str)
    assert "Research agent not initialized" in result


@pytest.mark.asyncio  
async def test_deep_research_without_api():
    """Test deep_research tool initialization (without actual API call)"""
    result = await deep_research.fn(
        query="Test query for MCP integration",
        system_instructions="This is just a test",
        include_analysis=False,
    )

    assert result is not None
    assert isinstance(result, str)
    # Should either work with valid config or show error without API keys
    assert ("Research Report:" in result or "Failed to initialize research agent" in result)


@pytest.mark.asyncio
async def test_research_with_context():
    """Test the research_with_context tool"""
    result = await research_with_context.fn(
        session_id="fake-session-id",
        answers=["Answer 1", "Answer 2"],
        system_instructions="Test instructions",
        include_analysis=False,
    )
    
    assert result is not None
    assert isinstance(result, str)
    # Should contain error about session not found or initialization failure
    assert ("Session fake-session-id not found" in result or "Failed to initialize research agent" in result)


def test_mcp_server_structure():
    """Test that MCP server structure is correct"""
    # Check that the MCP instance exists
    assert mcp is not None
    assert mcp.name == "deep-research"
    
    # Check that the tool wrapper functions exist and have callable .fn attributes
    assert hasattr(deep_research, 'fn')
    assert hasattr(research_status, 'fn')
    assert hasattr(research_with_context, 'fn')
    assert callable(deep_research.fn)
    assert callable(research_status.fn)
    assert callable(research_with_context.fn)
