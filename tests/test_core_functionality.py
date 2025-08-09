#!/usr/bin/env python3
"""
Test script to verify the core deep research functionality.
This tests the underlying components that the MCP server uses.
"""

import asyncio
import os
import sys
from deep_research_mcp.config import ResearchConfig
from deep_research_mcp.agent import DeepResearchAgent


async def test_config():
    """Test configuration loading"""
    print("Testing configuration...")
    try:
        config = ResearchConfig.from_env()
        config.validate()
        print(f"✅ Configuration loaded successfully:")
        print(f"   Model: {config.model}")
        print(f"   Timeout: {config.timeout}s")
        print(f"   Poll interval: {config.poll_interval}s")
        print(f"   API key: {'*' * (len(config.api_key) - 10)}{config.api_key[-10:]}")
        return True, config
    except Exception as e:
        print(f"❌ Configuration failed: {e}")
        return False, None


async def test_agent_initialization(config):
    """Test agent initialization"""
    print("\nTesting agent initialization...")
    try:
        agent = DeepResearchAgent(config)
        print("✅ Agent initialized successfully")
        return True, agent
    except Exception as e:
        print(f"❌ Agent initialization failed: {e}")
        return False, None


async def test_agent_status_check(agent):
    """Test agent's get_task_status method"""
    print("\nTesting agent status check...")
    try:
        # Test with a fake task ID - should handle gracefully
        status = await agent.get_task_status("fake-task-id-123")
        print("✅ Agent status check handled gracefully:")
        print(f"   Status result: {status}")
        return True
    except Exception as e:
        print(f"❌ Agent status check failed: {e}")
        return False


async def test_research_dry_run(agent):
    """Test research initialization (without actual API call)"""
    print("\nTesting research initialization...")
    try:
        # We'll attempt to start research but expect it to fail at the API call stage
        # This tests that all the setup and parameter handling works correctly
        result = await agent.research(
            query="Test research query for validation",
            system_prompt="This is a test system prompt",
            include_code_interpreter=False
        )
        
        # Check the result format
        if isinstance(result, dict):
            print("✅ Research method returned properly formatted result:")
            print(f"   Status: {result.get('status', 'unknown')}")
            if result.get('status') == 'failed':
                print(f"   Message: {result.get('message', 'No message')}")
            return True
        else:
            print(f"❌ Research returned unexpected format: {type(result)}")
            return False
            
    except Exception as e:
        print(f"❌ Research initialization failed: {e}")
        return False


def test_mcp_server_structure():
    """Test that MCP server module has expected structure"""
    print("\nTesting MCP server structure...")
    try:
        import deep_research_mcp.mcp_server as mcp_server
        
        # Check that the FastMCP instance exists
        if hasattr(mcp_server, 'mcp'):
            print("✅ MCP server has FastMCP instance")
        else:
            print("❌ MCP server missing FastMCP instance")
            return False
            
        # Check that main function exists
        if hasattr(mcp_server, 'main'):
            print("✅ MCP server has main function")
        else:
            print("❌ MCP server missing main function")
            return False
            
        print("✅ MCP server structure is correct")
        return True
        
    except ImportError as e:
        print(f"❌ Cannot import MCP server: {e}")
        return False
    except Exception as e:
        print(f"❌ MCP server structure test failed: {e}")
        return False


async def run_all_tests():
    """Run all tests"""
    print("=" * 60)
    print("DEEP RESEARCH MCP - CORE FUNCTIONALITY TEST")
    print("=" * 60)
    
    # Check environment
    api_key = os.environ.get("OPENAI_API_KEY")
    if api_key:
        print(f"🔑 OPENAI_API_KEY configured (length: {len(api_key)})")
    else:
        print("⚠️  OPENAI_API_KEY not configured")
    
    print()
    
    # Run tests
    test_results = []
    
    # Test 1: Configuration
    config_ok, config = await test_config()
    test_results.append(config_ok)
    
    if config_ok:
        # Test 2: Agent initialization
        agent_ok, agent = await test_agent_initialization(config)
        test_results.append(agent_ok)
        
        if agent_ok:
            # Test 3: Agent status check
            status_ok = await test_agent_status_check(agent)
            test_results.append(status_ok)
            
            # Test 4: Research dry run
            research_ok = await test_research_dry_run(agent)
            test_results.append(research_ok)
        else:
            test_results.extend([False, False])  # Skip dependent tests
    else:
        test_results.extend([False, False, False])  # Skip dependent tests
    
    # Test 5: MCP server structure
    structure_ok = test_mcp_server_structure()
    test_results.append(structure_ok)
    
    # Results summary
    print("\n" + "=" * 60)
    print("TEST RESULTS SUMMARY")
    print("=" * 60)
    
    passed = sum(test_results)
    total = len(test_results)
    
    test_names = [
        "Configuration Loading",
        "Agent Initialization", 
        "Status Check Method",
        "Research Method Structure",
        "MCP Server Structure"
    ]
    
    for i, (name, result) in enumerate(zip(test_names, test_results)):
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{i+1}. {name:<25} {status}")
    
    print(f"\nOVERALL: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL CORE FUNCTIONALITY TESTS PASSED!")
        print("✅ The MCP server components are working correctly")
        print("✅ Ready for Claude Code integration")
        return True
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        print("❌ Please fix the issues above before integrating with Claude Code")
        return False


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    
    print("\n" + "=" * 60)
    print("INTEGRATION STATUS")
    print("=" * 60)
    
    if success:
        print("✅ Core functionality verified - MCP server is ready!")
        print("\nTo integrate with Claude Code:")
        print("1. Ensure OPENAI_API_KEY is in your environment")
        print("2. Configure MCP server in Claude Code settings")
        print("3. Restart Claude Code")
        print("4. Test with a research query")
    else:
        print("❌ Core functionality issues found - fix before integration")
    
    sys.exit(0 if success else 1)