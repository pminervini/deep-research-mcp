# -*- coding: utf-8 -*-

"""
Test script to verify the core deep research functionality.
This tests the underlying components that the MCP server uses.
"""

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
from deep_research_mcp.results import ResearchResult


@pytest.mark.parametrize(
    ("config", "backend_type"),
    [
        (
            ResearchConfig(
                provider="openai",
                model="gpt-5-mini",
                api_key="openai-test-key",
                base_url="https://api.openai.com/v1",
            ),
            OpenAIResearchBackend,
        ),
        (
            ResearchConfig(
                provider="gemini",
                model="deep-research-preview-04-2026",
                api_key="gemini-test-key",
                base_url="https://generativelanguage.googleapis.com",
            ),
            GeminiResearchBackend,
        ),
        (
            ResearchConfig(
                provider="openai-codex",
                model="auto",
                base_url="https://chatgpt.com/backend-api/codex",
            ),
            CodexResearchBackend,
        ),
        (
            ResearchConfig(
                provider="dr-tulu",
                model="dr-tulu",
                base_url="http://localhost:8080/",
            ),
            DrTuluResearchBackend,
        ),
    ],
    ids=["openai", "gemini", "openai-codex", "dr-tulu"],
)
def test_agent_selects_provider_backend(config, backend_type):
    """The agent factory selects the backend configured for each provider."""
    agent = DeepResearchAgent(config)

    assert agent.config is config
    assert isinstance(agent.backend, backend_type)


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
