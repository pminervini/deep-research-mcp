# -*- coding: utf-8 -*-

"""Explicitly gated end-to-end check for the private Codex backend."""

from __future__ import annotations

import os

import pytest

from deep_research_mcp.agent import DeepResearchAgent
from deep_research_mcp.config import ResearchConfig


@pytest.mark.asyncio
@pytest.mark.api
@pytest.mark.integration
async def test_openai_codex_subscription_end_to_end():
    """Run only when the maintainer deliberately opts into subscription use."""
    if os.environ.get("RUN_OPENAI_CODEX_E2E") != "1":
        pytest.skip("Set RUN_OPENAI_CODEX_E2E=1 to run the Codex subscription test")

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
    assert result.task_id
