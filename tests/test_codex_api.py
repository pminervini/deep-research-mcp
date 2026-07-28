# -*- coding: utf-8 -*-

"""Credential-aware end-to-end check for the private Codex backend."""

from __future__ import annotations

import pytest

from deep_research_mcp.agent import DeepResearchAgent
from deep_research_mcp.codex_auth import CodexAuthManager
from deep_research_mcp.config import ResearchConfig


@pytest.mark.asyncio
@pytest.mark.api
@pytest.mark.integration
async def test_openai_codex_subscription_end_to_end():
    """Run whenever this project has a current or refreshable Codex session."""
    auth_status = CodexAuthManager().status()
    if not auth_status.logged_in:
        pytest.skip(
            "No usable OpenAI Codex session; run "
            "`uv run python cli/deep-research-cli.py auth login`"
        )

    config = ResearchConfig.from_env(
        {
            "RESEARCH_PROVIDER": "openai-codex",
            "RESEARCH_MODEL": "auto",
            "RESEARCH_TIMEOUT": "300",
        }
    )
    agent = DeepResearchAgent(config)

    result = await agent.research(
        "In two sentences, summarize one current OpenAI Codex capability and cite a source.",
        include_code_interpreter=False,
    )

    assert result.status == "completed", result.message
    assert result.final_report
    assert result.citations
    assert result.task_id
