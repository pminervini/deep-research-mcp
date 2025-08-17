#!/usr/bin/env python3
"""
Test script to verify MCP server integration functionality.
This script tests the deep research MCP server tools without requiring
a full Claude Code MCP integration.
"""

import pytest
import os

# Import the underlying functions from the MCP server module
import deep_research_mcp.mcp_server as mcp_server


@pytest.mark.asyncio
async def test_research_status():
    """Test the research_status tool with a fake task ID"""
    # Access the function through the tool's fn attribute
    result = await mcp_server.research_status.fn("fake-task-id")
    assert result is not None
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_deep_research_without_api():
    """Test deep_research tool initialization (without actual API call)"""
    # Access the function through the tool's fn attribute
    result = await mcp_server.deep_research.fn(
        query="Test query for MCP integration",
        system_instructions="This is just a test",
        include_analysis=False,
    )

    assert result is not None
    assert isinstance(result, str)


def test_mcp_server():
    """Test that MCP server structure is correct"""
    # Check that the MCP instance exists
    assert hasattr(mcp_server, "mcp"), "MCP server missing FastMCP instance"
    
    # Check that the tool objects exist
    assert hasattr(mcp_server, "research_status"), "Missing research_status tool"
    assert hasattr(mcp_server, "deep_research"), "Missing deep_research tool"
    
    # Check that tools have callable functions
    assert hasattr(mcp_server.research_status, "fn"), "research_status missing fn attribute"
    assert hasattr(mcp_server.deep_research, "fn"), "deep_research missing fn attribute"
    assert callable(mcp_server.research_status.fn)
    assert callable(mcp_server.deep_research.fn)
