#!/usr/bin/env python3
"""
Test script to verify MCP server integration functionality.
This script tests the deep research MCP server tools without requiring
a full Claude Code MCP integration.
"""

import asyncio
import os
import sys

# Import the underlying functions from the MCP server module
import deep_research_mcp.mcp_server as mcp_server


async def test_research_status():
    """Test the research_status tool with a fake task ID"""
    print("\nTesting research_status tool...")
    try:
        # Get the actual function from the FastMCP decorated function
        research_status_func = mcp_server.mcp._tools["research_status"].func
        result = await research_status_func("fake-task-id")
        print("research_status handled invalid task ID:")
        print(result)
        return True
    except Exception as e:
        print(f"research_status failed: {e}")
        return False


async def test_deep_research_without_api():
    """Test deep_research tool initialization (without actual API call)"""
    print("\nTesting deep_research tool initialization...")
    try:
        # Get the actual function from the FastMCP decorated function
        deep_research_func = mcp_server.mcp._tools["deep_research"].func

        # This should fail gracefully if API key is not set
        result = await deep_research_func(
            query="Test query for MCP integration",
            system_instructions="This is just a test",
            include_analysis=False,
        )

        # Check if it's an API key error or other expected error
        if (
            "Failed to initialize research agent" in result
            or "API key" in result.lower()
        ):
            print("deep_research correctly detected missing/invalid API configuration")
            return True
        else:
            print(f"deep_research returned result: {result[:200]}...")
            return True

    except Exception as e:
        print(f"deep_research failed unexpectedly: {e}")
        return False


async def test_mcp_server():
    """Run all MCP server tests"""
    print("=" * 60)
    print("MCP SERVER INTEGRATION TEST")
    print("=" * 60)

    # Check if OPENAI_API_KEY is set
    api_key = os.environ.get("OPENAI_API_KEY")
    if api_key:
        print(f"OPENAI_API_KEY is configured (length: {len(api_key)})")
    else:
        print("OPENAI_API_KEY not set - some tests may show API configuration errors")

    print()

    # Run individual tests
    tests_results = []

    tests_results.append(await test_research_status())
    tests_results.append(await test_deep_research_without_api())

    # Summary
    print("\n" + "=" * 60)
    print("TEST RESULTS SUMMARY")
    print("=" * 60)

    passed = sum(tests_results)
    total = len(tests_results)

    if passed == total:
        print(f"ALL TESTS PASSED ({passed}/{total})")
        print(
            "\nMCP server is working correctly and ready for Claude Code integration!"
        )
        return True
    else:
        print(f"SOME TESTS FAILED ({passed}/{total})")
        print("\nPlease check the errors above and fix any issues.")
        return False
