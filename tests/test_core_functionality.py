# -*- coding: utf-8 -*-

"""
Test script to verify the core deep research functionality.
This tests the underlying components that the MCP server uses.
"""

import os

import pytest

import deep_research_mcp.mcp_server as mcp_server

from deep_research_mcp.agent import DeepResearchAgent
from deep_research_mcp.config import ResearchConfig


@pytest.fixture
def test_config():
    """Test configuration fixture"""
    os.environ["RESEARCH_MODEL"] = "gpt-5-mini"  # Use cheap model for testing
    os.environ["TRIAGE_MODEL"] = "gpt-5-mini"
    os.environ["CLARIFIER_MODEL"] = "gpt-5-mini"
    os.environ["INSTRUCTION_BUILDER_MODEL"] = "gpt-5-mini"
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
@pytest.mark.slow
@pytest.mark.api
@pytest.mark.integration
async def test_research_dry_run(test_agent):
    """Test full research flow (REAL API CALL - takes 2-5 minutes and costs money)"""
    # Skip if no API key
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set - skipping real API tests")

    # WARNING: This makes a REAL OpenAI Deep Research API call
    # It will take several minutes and costs real money
    # This is an integration test, not a unit test
    result = await test_agent.research(query="Test research query for validation", system_prompt="This is a test system prompt", include_code_interpreter=False)

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


def test_instruction_builder_configuration(test_config):
    """Test instruction builder configuration"""
    assert hasattr(test_config, "instruction_builder_model")
    assert test_config.instruction_builder_model == "gpt-5-mini"


def test_instruction_builder_agent_initialization(test_agent):
    """Test that agent has instruction builder components"""
    assert hasattr(test_agent, "prompt_manager")
    assert hasattr(test_agent, "instruction_client")
    assert test_agent.prompt_manager is not None
    # instruction_client should only be initialized when clarification is enabled
    if test_agent.config.enable_clarification:
        assert test_agent.instruction_client is not None
    else:
        assert test_agent.instruction_client is None


def test_instruction_builder_with_clarification_enabled():
    """Test that instruction client is initialized when clarification is enabled"""
    os.environ["RESEARCH_MODEL"] = "gpt-5-mini"
    os.environ["ENABLE_CLARIFICATION"] = "true"
    os.environ["INSTRUCTION_BUILDER_MODEL"] = "gpt-5-mini"
    
    config = ResearchConfig.from_env()
    agent = DeepResearchAgent(config)
    
    assert agent.config.enable_clarification == True
    assert agent.instruction_client is not None
    
    # Clean up environment
    del os.environ["ENABLE_CLARIFICATION"]


def test_instruction_builder_prompt_loading(test_agent):
    """Test that instruction builder prompt can be loaded"""
    test_query = "What are the latest developments in quantum computing?"

    try:
        prompt = test_agent.prompt_manager.get_instruction_builder_prompt(test_query)
        assert prompt is not None
        assert isinstance(prompt, str)
        assert "quantum computing" in prompt.lower()
        assert "research" in prompt.lower()
    except Exception as e:
        # If prompt loading fails, it should be due to missing files, not code errors
        assert "not found" in str(e).lower() or "no such file" in str(e).lower()


def test_instruction_builder_method_exists(test_agent):
    """Test that build_research_instruction method exists and is callable"""
    assert hasattr(test_agent, "build_research_instruction")
    assert callable(test_agent.build_research_instruction)


@pytest.mark.asyncio
async def test_instruction_builder_fallback(test_agent):
    """Test that instruction builder gracefully falls back to original query on error"""
    original_query = "test query for fallback"

    # This should not raise an exception even if the API call fails
    enhanced_query = test_agent.build_research_instruction(original_query)

    # Should return at least the original query
    assert enhanced_query is not None
    assert isinstance(enhanced_query, str)
    assert len(enhanced_query) > 0


def test_config_instruction_builder_env_override():
    """Test instruction builder model can be overridden via environment"""
    old_model = os.environ.get("RESEARCH_MODEL")
    old_instruction_model = os.environ.get("INSTRUCTION_BUILDER_MODEL")

    os.environ["RESEARCH_MODEL"] = "gpt-5-mini"
    os.environ["CLARIFICATION_INSTRUCTION_BUILDER_MODEL"] = "gpt-4o-mini"

    try:
        config = ResearchConfig.from_env()
        assert config.instruction_builder_model == "gpt-4o-mini"
        assert config.model == "gpt-5-mini"
    finally:
        if old_model:
            os.environ["RESEARCH_MODEL"] = old_model
        else:
            if "RESEARCH_MODEL" in os.environ:
                del os.environ["RESEARCH_MODEL"]

        if old_instruction_model:
            os.environ["CLARIFICATION_INSTRUCTION_BUILDER_MODEL"] = old_instruction_model
        else:
            if "CLARIFICATION_INSTRUCTION_BUILDER_MODEL" in os.environ:
                del os.environ["CLARIFICATION_INSTRUCTION_BUILDER_MODEL"]
