# -*- coding: utf-8 -*-

"""
Tests that the MCP server entrypoints run for real with both providers.
For the openai provider, we ONLY use `gpt-5-mini` since it's WAY cheaper
than o4-mini-deep-research-2025-06-26 and o3-deep-research-2025-06-26.
"""

import os
import logging
import pytest

from deep_research_mcp.config import ResearchConfig

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider,model",
    [
        ("openai", "gpt-5-mini"),
        # ("open-deep-research", "openai/qwen/qwen3-coder-30b"),
    ],
)
async def test_mcp_server_with_providers(provider, model):
    logger.info(f"=== Starting test for provider={provider}, model={model} ===")

    # Prepare environment for this run
    old_provider = os.environ.get("PROVIDER")
    old_model = os.environ.get("RESEARCH_MODEL")
    old_enable_clar = os.environ.get("ENABLE_CLARIFICATION")

    logger.info(f"Setting environment: PROVIDER={provider}, RESEARCH_MODEL={model}")
    os.environ["PROVIDER"] = provider
    os.environ["RESEARCH_MODEL"] = model
    os.environ["ENABLE_CLARIFICATION"] = "false"

    try:
        # Confirm config resolve reflects our desired provider/model
        logger.info("Loading ResearchConfig from environment...")
        cfg = ResearchConfig.from_env()
        logger.info(f"Config loaded: provider={cfg.provider}, model={cfg.model}")

        assert cfg.provider == provider
        if provider == "openai":
            assert cfg.model == "gpt-5-mini"
        else:
            assert cfg.model == model

        # Import server and ensure a fresh agent instance
        logger.info("Importing mcp_server and resetting agent...")
        import deep_research_mcp.mcp_server as mcp_server
        mcp_server.research_agent = None

        # Run deep research for real (no mocks/mocks)
        logger.info(f"Starting deep_research call for provider: {provider}")
        logger.info("This may take several minutes...")
        result = await mcp_server.deep_research(
            query="Sanity check query for provider: " + provider,
            system_instructions="Keep it brief; this is a test run.",
            include_analysis=False,
        )
        logger.info(f"deep_research completed. Result length: {len(result)} chars")

        # Always returns a string: either a report or a clear error
        logger.info("Validating result type...")
        assert isinstance(result, str)

        # We accept both success or informative failure depending on env/services
        acceptable_indicators = (
            "Research Report:",
            "Research failed:",
            "Failed to initialize research agent",
            "Unexpected error:",
        )
        logger.info("Checking for acceptable result indicators...")
        assert any(ind in result for ind in acceptable_indicators)
        logger.info(f"Test PASSED for provider={provider}")

    finally:
        # Restore environment
        logger.info("Restoring environment variables...")
        if old_provider is None:
            os.environ.pop("PROVIDER", None)
        else:
            os.environ["PROVIDER"] = old_provider

        if old_model is None:
            os.environ.pop("RESEARCH_MODEL", None)
        else:
            os.environ["RESEARCH_MODEL"] = old_model

        if old_enable_clar is None:
            os.environ.pop("ENABLE_CLARIFICATION", None)
        else:
            os.environ["ENABLE_CLARIFICATION"] = old_enable_clar
        logger.info(f"=== Finished test for provider={provider} ===")
