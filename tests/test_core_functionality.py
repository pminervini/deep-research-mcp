# -*- coding: utf-8 -*-

"""
Test script to verify the core deep research functionality.
This tests the underlying components that the MCP server uses.
"""

import os
from types import SimpleNamespace

import pytest

from deep_research_mcp.agent import DeepResearchAgent
from deep_research_mcp.backends import (
    CodexResearchBackend,
    DrTuluResearchBackend,
    GeminiResearchBackend,
    OpenAIResearchBackend,
)
from deep_research_mcp.config import ResearchConfig
from deep_research_mcp.results import ResearchResult, ResearchTaskStatus


@pytest.fixture
def test_config():
    """Test configuration fixture"""
    os.environ["RESEARCH_MODEL"] = "gpt-5-mini"  # Use cheap model for testing
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
    assert not hasattr(test_config, "enable_clarification")
    assert not hasattr(test_config, "triage_model")
    assert not hasattr(test_config, "clarifier_model")


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
    assert isinstance(agent.backend, OpenAIResearchBackend)
    assert hasattr(agent.backend, "client")
    assert not hasattr(agent, "clarification_manager")
    assert not hasattr(agent, "instruction_client")
    assert not hasattr(agent, "prompt_manager")


def test_gemini_agent_initialization():
    """Test Gemini agent initialization without making API calls."""
    old_provider = os.environ.get("RESEARCH_PROVIDER")
    old_model = os.environ.get("RESEARCH_MODEL")
    old_api_key = os.environ.get("RESEARCH_API_KEY")

    os.environ["RESEARCH_PROVIDER"] = "gemini"
    os.environ["RESEARCH_MODEL"] = "deep-research-preview-04-2026"
    os.environ["RESEARCH_API_KEY"] = "gemini-test-key"

    try:
        config = ResearchConfig.from_env()
        agent = DeepResearchAgent(config)
        assert agent.config.provider == "gemini"
        assert isinstance(agent.backend, GeminiResearchBackend)
        assert hasattr(agent.backend, "gemini_interactions")
    finally:
        if old_provider:
            os.environ["RESEARCH_PROVIDER"] = old_provider
        else:
            os.environ.pop("RESEARCH_PROVIDER", None)

        if old_model:
            os.environ["RESEARCH_MODEL"] = old_model
        else:
            os.environ.pop("RESEARCH_MODEL", None)

        if old_api_key:
            os.environ["RESEARCH_API_KEY"] = old_api_key
        else:
            os.environ.pop("RESEARCH_API_KEY", None)


def test_openai_codex_agent_initialization():
    """Test Codex subscription provider selection without network access."""
    config = ResearchConfig.from_env(
        {
            "RESEARCH_PROVIDER": "openai-codex",
            "RESEARCH_MODEL": "auto",
        }
    )

    agent = DeepResearchAgent(config)

    assert isinstance(agent.backend, CodexResearchBackend)
    assert agent.config.base_url == "https://chatgpt.com/backend-api/codex"


def test_gemini_extract_results_uses_current_steps_schema():
    """Gemini Interactions now return steps, not legacy outputs."""
    backend = object.__new__(GeminiResearchBackend)
    interaction = SimpleNamespace(
        id="interaction-test",
        status="completed",
        steps=[
            SimpleNamespace(
                type="user_input",
                content=[SimpleNamespace(type="text", text="Research test")],
            ),
            SimpleNamespace(type="thought", summary=[]),
            SimpleNamespace(
                type="google_search_call",
                arguments=SimpleNamespace(queries=["test query"]),
            ),
            SimpleNamespace(
                type="model_output",
                content=[
                    SimpleNamespace(
                        type="text",
                        text="Final report",
                        annotations=[
                            SimpleNamespace(
                                type="url_citation",
                                title="Example",
                                url="https://example.com",
                            )
                        ],
                    )
                ],
            ),
            SimpleNamespace(
                type="model_output",
                content=[SimpleNamespace(type="text", text="Sources block")],
            ),
        ],
    )

    result = backend.extract_results(interaction)

    assert result.status == "completed"
    assert result.final_report == "Final report\nSources block"
    assert result.reasoning_steps == 1
    assert result.search_queries == ["test query"]
    assert result.total_steps == 5
    assert [(citation.title, citation.url) for citation in result.citations] == [
        ("Example", "https://example.com")
    ]


@pytest.mark.asyncio
async def test_gemini_research_fails_without_task_id():
    """Gemini task creation must return an ID before polling can start."""
    backend = object.__new__(GeminiResearchBackend)
    backend.config = SimpleNamespace(model=None)
    backend.gemini_interactions = SimpleNamespace(create=lambda **_: SimpleNamespace())

    result = await backend.research("Research test", include_code_interpreter=False)

    assert result.status == "failed"
    assert result.message == "Gemini did not return a research task ID"


def test_openai_extract_results_dedupes_citations_and_joins_blocks():
    """The final message may not be last, may have several blocks, and may repeat URLs."""
    backend = object.__new__(OpenAIResearchBackend)
    response = SimpleNamespace(
        id="resp-test",
        status="completed",
        output=[
            SimpleNamespace(
                type="web_search_call",
                action=SimpleNamespace(query="canberra facts"),
            ),
            SimpleNamespace(
                type="message",
                content=[
                    SimpleNamespace(
                        type="output_text",
                        text="First block.",
                        annotations=[
                            SimpleNamespace(
                                type="url_citation",
                                title="Example",
                                url="https://example.com",
                            ),
                            SimpleNamespace(
                                type="url_citation",
                                title="Example duplicate",
                                url="https://example.com",
                            ),
                        ],
                    ),
                    SimpleNamespace(
                        type="output_text",
                        text="Second block.",
                        annotations=[
                            SimpleNamespace(
                                type="url_citation",
                                title="Other",
                                url="https://other.example.com",
                            )
                        ],
                    ),
                ],
            ),
            SimpleNamespace(type="reasoning", summary=[]),
        ],
    )

    # pylint: disable=protected-access
    result = backend._extract_openai_results(response)

    assert result.status == "completed"
    assert result.final_report == "First block.\nSecond block."
    assert result.search_queries == ["canberra facts"]
    assert [
        (citation.index, citation.title, citation.url) for citation in result.citations
    ] == [
        (1, "Example", "https://example.com"),
        (2, "Other", "https://other.example.com"),
    ]


@pytest.mark.parametrize(
    ("model", "effort"),
    [
        ("gpt-5", "high"),
        ("gpt-5-mini", "high"),
        ("gpt-5-pro", "high"),
        ("gpt-5.1", "high"),
        ("gpt-5.2", "xhigh"),
        ("gpt-5.4", "xhigh"),
        ("gpt-5.4-mini", "xhigh"),
        ("gpt-5.4-pro", "xhigh"),
        ("gpt-5.5", "xhigh"),
        ("gpt-5.5-pro", "xhigh"),
        ("gpt-5.6", "xhigh"),
        ("gpt-5.6-sol", "xhigh"),
        ("gpt-5.6-terra", "xhigh"),
        ("gpt-5.6-luna", "xhigh"),
    ],
)
def test_openai_gpt5_builds_long_research_request(model, effort):
    """Supported GPT-5 reasoning models use the long-research request shape."""
    backend = object.__new__(OpenAIResearchBackend)
    backend.config = SimpleNamespace(
        model=model,
        enable_reasoning_summaries=True,
    )
    input_messages = [{"role": "user", "content": "Research test"}]

    # pylint: disable=protected-access
    tools = backend._build_tools(include_code_interpreter=False)
    kwargs = backend._build_responses_create_kwargs(input_messages, tools)

    assert tools == [
        {
            "type": "web_search",
            "return_token_budget": "unlimited",
        }
    ]
    assert kwargs == {
        "model": model,
        "input": input_messages,
        "tools": tools,
        "background": True,
        "tool_choice": "required",
        "reasoning": {
            "effort": effort,
            "summary": "auto",
        },
    }


@pytest.mark.parametrize("model", ["gpt-5-pro", "gpt-5.4-pro"])
def test_openai_pro_model_omits_unsupported_code_interpreter(model):
    """Legacy Pro models without Code Interpreter still receive web research."""
    backend = object.__new__(OpenAIResearchBackend)
    backend.config = SimpleNamespace(model=model)

    # pylint: disable=protected-access
    tools = backend._build_tools(include_code_interpreter=True)

    assert tools == [
        {
            "type": "web_search",
            "return_token_budget": "unlimited",
        }
    ]


def test_openai_custom_model_uses_current_web_search_without_gpt5_options():
    """Unknown model overrides avoid GPT-5-only search and reasoning options."""
    backend = object.__new__(OpenAIResearchBackend)
    backend.config = SimpleNamespace(
        model="custom-research-model",
        enable_reasoning_summaries=False,
    )
    input_messages = [{"role": "user", "content": "Research test"}]

    # pylint: disable=protected-access
    tools = backend._build_tools(include_code_interpreter=False)
    kwargs = backend._build_responses_create_kwargs(input_messages, tools)

    assert tools == [{"type": "web_search"}]
    assert kwargs == {
        "model": "custom-research-model",
        "input": input_messages,
        "tools": tools,
        "background": True,
    }


def test_render_citations_avoids_duplicating_url_only_titles():
    """Citations without a real title render the URL once, not as [url](url)."""
    from deep_research_mcp.mcp_server import _render_citations
    from deep_research_mcp.results import ResearchCitation

    result = ResearchResult.completed(
        task_id="task-test",
        final_report="Report",
        citations=[
            ResearchCitation(
                index=1,
                title="https://example.com/very-long-redirect",
                url="https://example.com/very-long-redirect",
            ),
            ResearchCitation(index=2, title="Example", url="https://example.com"),
        ],
    )

    assert _render_citations(result) == (
        "1. <https://example.com/very-long-redirect>\n"
        "2. [Example](https://example.com)"
    )


def test_render_research_markdown_includes_provider_note():
    """Completed capability warnings remain visible to MCP clients."""
    from deep_research_mcp.mcp_server import _render_research_markdown

    result = ResearchResult.completed(
        task_id="task-test",
        final_report="Report",
        message="Web search only.",
    )

    rendered = _render_research_markdown(title="Report", result=result)

    assert "- **Provider note**: Web search only." in rendered


def test_dr_tulu_agent_initialization():
    """Test Dr Tulu agent initialization without making network calls."""
    old_provider = os.environ.get("RESEARCH_PROVIDER")
    old_model = os.environ.get("RESEARCH_MODEL")
    old_base_url = os.environ.get("RESEARCH_BASE_URL")

    os.environ["RESEARCH_PROVIDER"] = "dr-tulu"
    os.environ["RESEARCH_MODEL"] = "dr-tulu"
    os.environ["RESEARCH_BASE_URL"] = "http://localhost:8080/"

    try:
        config = ResearchConfig.from_env()
        agent = DeepResearchAgent(config)
        assert agent.config.provider == "dr-tulu"
        assert isinstance(agent.backend, DrTuluResearchBackend)
        assert agent.config.base_url == "http://localhost:8080/"
    finally:
        if old_provider:
            os.environ["RESEARCH_PROVIDER"] = old_provider
        else:
            os.environ.pop("RESEARCH_PROVIDER", None)

        if old_model:
            os.environ["RESEARCH_MODEL"] = old_model
        else:
            os.environ.pop("RESEARCH_MODEL", None)

        if old_base_url:
            os.environ["RESEARCH_BASE_URL"] = old_base_url
        else:
            os.environ.pop("RESEARCH_BASE_URL", None)


@pytest.mark.asyncio
@pytest.mark.api
@pytest.mark.integration
async def test_agent_status_check(test_agent):
    """Test agent's get_task_status method"""
    # Skip if no API key
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set - skipping real API tests")

    # Test with a fake task ID - should handle gracefully
    status = await test_agent.get_task_status("fake-task-id-123")
    assert isinstance(status, ResearchTaskStatus)
    assert status.task_id == "fake-task-id-123"


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
    result = await test_agent.research(
        query="Test research query for validation",
        system_prompt="This is a test system prompt",
        include_code_interpreter=False,
    )

    # Check the result format
    assert isinstance(result, ResearchResult)
    assert result.status in {"completed", "failed", "error"}
