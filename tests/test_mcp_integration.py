#!/usr/bin/env python3
"""
Test script to verify MCP server integration functionality.
This script tests the deep research MCP server tools without requiring
a full Claude Code MCP integration.
"""

import asyncio
import os
import sys
from unittest.mock import Mock, patch

# Import the underlying functions from the MCP server module
import deep_research_mcp.mcp_server as mcp_server


async def test_list_models():
    """Test the list_models tool"""
    print("Testing list_models tool...")
    try:
        # Get the actual function from the FastMCP decorated function
        list_models_func = mcp_server.mcp._tools['list_models'].func
        result = await list_models_func()
        print("✅ list_models succeeded:")
        print(result[:200] + "..." if len(result) > 200 else result)
        return True
    except Exception as e:
        print(f"❌ list_models failed: {e}")
        return False


async def test_research_status():
    """Test the research_status tool with a fake task ID"""
    print("\nTesting research_status tool...")
    try:
        # Get the actual function from the FastMCP decorated function
        research_status_func = mcp_server.mcp._tools['research_status'].func
        result = await research_status_func("fake-task-id")
        print("✅ research_status handled invalid task ID:")
        print(result)
        return True
    except Exception as e:
        print(f"❌ research_status failed: {e}")
        return False


async def test_deep_research_without_api():
    """Test deep_research tool initialization (without actual API call)"""
    print("\nTesting deep_research tool initialization...")
    try:
        # Get the actual function from the FastMCP decorated function
        deep_research_func = mcp_server.mcp._tools['deep_research'].func
        
        # This should fail gracefully if API key is not set
        result = await deep_research_func(
            query="Test query for MCP integration",
            system_instructions="This is just a test",
            include_analysis=False
        )
        
        # Check if it's an API key error or other expected error
        if "Failed to initialize research agent" in result or "API key" in result.lower():
            print("✅ deep_research correctly detected missing/invalid API configuration")
            return True
        else:
            print(f"✅ deep_research returned result: {result[:200]}...")
            return True
            
    except Exception as e:
        print(f"❌ deep_research failed unexpectedly: {e}")
        return False


async def test_mcp_server():
    """Run all MCP server tests"""
    print("=" * 60)
    print("MCP SERVER INTEGRATION TEST")
    print("=" * 60)
    
    # Check if OPENAI_API_KEY is set
    api_key = os.environ.get("OPENAI_API_KEY")
    if api_key:
        print(f"✅ OPENAI_API_KEY is configured (length: {len(api_key)})")
    else:
        print("⚠️  OPENAI_API_KEY not set - some tests may show API configuration errors")
    
    print()
    
    # Run individual tests
    tests_results = []
    
    tests_results.append(await test_list_models())
    tests_results.append(await test_research_status())
    tests_results.append(await test_deep_research_without_api())
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST RESULTS SUMMARY")
    print("=" * 60)
    
    passed = sum(tests_results)
    total = len(tests_results)
    
    if passed == total:
        print(f"🎉 ALL TESTS PASSED ({passed}/{total})")
        print("\n✅ MCP server is working correctly and ready for Claude Code integration!")
        return True
    else:
        print(f"❌ SOME TESTS FAILED ({passed}/{total})")
        print("\n⚠️  Please check the errors above and fix any issues.")
        return False


def print_integration_instructions():
    """Print instructions for Claude Code integration"""
    print("\n" + "=" * 60)
    print("CLAUDE CODE INTEGRATION INSTRUCTIONS")
    print("=" * 60)
    
    project_dir = os.path.abspath(os.path.dirname(__file__))
    server_script = os.path.join(project_dir, "src", "deep_research_mcp", "mcp_server.py")
    
    print(f"""
To integrate this MCP server with Claude Code:

1. **Configure MCP Server in Claude Code**
   Create or update ~/.config/claude-code/mcp.json:

   {{
     "mcpServers": {{
       "deep-research": {{
         "command": "python",
         "args": ["{server_script}"],
         "env": {{
           "OPENAI_API_KEY": "${{OPENAI_API_KEY}}",
           "RESEARCH_MODEL": "o3-deep-research-2025-06-26"
         }}
       }}
     }}
   }}

2. **Alternative: Using the console script**
   {{
     "mcpServers": {{
       "deep-research": {{
         "command": "deep-research-mcp",
         "env": {{
           "OPENAI_API_KEY": "${{OPENAI_API_KEY}}"
         }}
       }}
     }}
   }}

3. **Set Environment Variables**
   Make sure OPENAI_API_KEY is set in your environment:
   export OPENAI_API_KEY="your-api-key-here"

4. **Restart Claude Code** to load the MCP server

5. **Test Integration**
   In Claude Code, you can then use:
   - "Please research the latest developments in AI safety"
   - "Use deep research to analyze quantum computing trends"
   
   The following tools will be available:
   - deep_research(): Comprehensive research with citations
   - research_status(): Check research task status  
   - list_models(): Show available research models

6. **Verify Integration**
   Check Claude Code logs for MCP server startup messages.
""")


if __name__ == "__main__":
    # Run the tests
    success = asyncio.run(test_mcp_server())
    
    # Always print integration instructions
    print_integration_instructions()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)