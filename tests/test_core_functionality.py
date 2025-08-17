#!/usr/bin/env python3
"""
Test script to verify the core deep research functionality.
This tests the underlying components that the MCP server uses.
"""

import pytest
import os
from deep_research_mcp.config import ResearchConfig
from deep_research_mcp.agent import DeepResearchAgent


@pytest.fixture
def test_config():
    """Test configuration fixture"""
    os.environ["RESEARCH_MODEL"] = "gpt-5-mini"  # Use cheap model for testing
    os.environ["TRIAGE_MODEL"] = "gpt-5-mini"
    os.environ["CLARIFIER_MODEL"] = "gpt-5-mini"
    return ResearchConfig.from_env()


@pytest.fixture
def test_agent(test_config):
    """Test agent fixture"""
    return DeepResearchAgent(test_config)


def test_config_loading(test_config):
    """Test configuration loading"""
    assert test_config.model == "gpt-5-mini"
    assert test_config.timeout > 0
    assert test_config.poll_interval > 0
    assert hasattr(test_config, "enable_clarification")
    assert hasattr(test_config, "triage_model")
    assert hasattr(test_config, "clarifier_model")
    assert test_config.triage_model == "gpt-5-mini"
    assert test_config.clarifier_model == "gpt-5-mini"


def test_config_validation():
    """Test configuration validation"""
    config = ResearchConfig.from_env()
    config.validate()
    assert config.model is not None
    assert config.timeout > 0
    assert config.poll_interval > 0


def test_agent_initialization(test_config):
    """Test agent initialization"""
    agent = DeepResearchAgent(test_config)
    assert agent.config == test_config
    assert hasattr(agent, "clarification_manager")


@pytest.mark.asyncio
async def test_agent_status_check(test_agent):
    """Test agent's get_task_status method"""
    # Skip if no API key
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set - skipping real API tests")

    # Test with a fake task ID - should handle gracefully
    status = await test_agent.get_task_status("fake-task-id-123")
    assert isinstance(status, dict)
    assert "task_id" in status
    assert status["task_id"] == "fake-task-id-123"


@pytest.mark.asyncio
async def test_research_dry_run(test_agent):
    """Test research initialization (without actual API call)"""
    # Skip if no API key
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set - skipping real API tests")

    # We'll attempt to start research but expect it to fail at the API call stage
    # This tests that all the setup and parameter handling works correctly
    result = await test_agent.research(
        query="Test research query for validation",
        system_prompt="This is a test system prompt",
        include_code_interpreter=False,
    )

    # Check the result format
    assert isinstance(result, dict)
    assert "status" in result


def test_clarification_methods(test_agent):
    """Test clarification methods exist and are callable"""
    assert hasattr(test_agent, "start_clarification")
    assert hasattr(test_agent, "add_clarification_answers")
    assert hasattr(test_agent, "get_enriched_query")

    # Test basic clarification start (should work even without API key if clarification disabled)
    test_agent.config.enable_clarification = False  # Disable to avoid API calls
    result = test_agent.start_clarification("test query")
    assert isinstance(result, dict)
    assert result["needs_clarification"] == False


def test_mcp_server_imports():
    """Test that MCP server can import all required components"""
    try:
        import deep_research_mcp.mcp_server as mcp_server

        # Test that the module imports successfully
        assert hasattr(mcp_server, "deep_research")
        assert hasattr(mcp_server, "research_with_context")
        assert hasattr(mcp_server, "research_status")
        
        # Check that the FastMCP instance exists
        assert hasattr(mcp_server, "mcp"), "MCP server missing FastMCP instance"

        # Check that main function exists
        assert hasattr(mcp_server, "main"), "MCP server missing main function"
    except ImportError as e:
        pytest.fail(f"Failed to import MCP server components: {e}")


def test_config_clarification_defaults():
    """Test clarification configuration defaults"""
    # Clean environment first
    env_vars_to_clean = ["ENABLE_CLARIFICATION", "TRIAGE_MODEL", "CLARIFIER_MODEL"]
    for var in env_vars_to_clean:
        if var in os.environ:
            del os.environ[var]

    os.environ["RESEARCH_MODEL"] = "gpt-5-mini"

    # Test defaults
    config = ResearchConfig.from_env()
    assert config.enable_clarification == False  # Default is False
    assert config.triage_model == "gpt-5-mini"
    assert config.clarifier_model == "gpt-5-mini"


def test_config_clarification_enabled():
    """Test clarification configuration when enabled"""
    os.environ["RESEARCH_MODEL"] = "gpt-5-mini"
    os.environ["ENABLE_CLARIFICATION"] = "true"
    os.environ["TRIAGE_MODEL"] = "gpt-5-mini"
    os.environ["CLARIFIER_MODEL"] = "gpt-5-mini"

    config = ResearchConfig.from_env()
    assert config.enable_clarification == True
    assert config.triage_model == "gpt-5-mini"
    assert config.clarifier_model == "gpt-5-mini"

    # Clean up
    if "ENABLE_CLARIFICATION" in os.environ:
        del os.environ["ENABLE_CLARIFICATION"]
    if "TRIAGE_MODEL" in os.environ:
        del os.environ["TRIAGE_MODEL"]
    if "CLARIFIER_MODEL" in os.environ:
        del os.environ["CLARIFIER_MODEL"]

