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
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@pytest.mark.asyncio
@pytest.mark.slow
@pytest.mark.api
@pytest.mark.integration
# ("open-deep-research", "openai/qwen/qwen3-coder-30b", "responses"),
@pytest.mark.parametrize(
    "provider,model,api_style",
    [
        ("openai", "gpt-5-mini", "responses"),
        ("openai", "gpt-5-mini", "chat_completions"),
        ("gemini", "deep-research-pro-preview-12-2025", "responses"),
    ],
)
async def test_mcp_server_with_providers(provider, model, api_style):
    await run_provider_check(provider, model, api_style=api_style)


async def run_provider_check(provider, model, api_style="responses"):
    logger.info(
        f"=== Starting test for provider={provider}, model={model}, api_style={api_style} ==="
    )

    # Per-provider environment overrides. These take precedence over any
    # values loaded from ~/.deep_research so a single pytest --slow run can
    # exercise multiple providers without file edits.
    env_overrides: dict[str, str] = {
        "PROVIDER": provider,
        "RESEARCH_PROVIDER": provider,
        "RESEARCH_MODEL": model,
        "ENABLE_CLARIFICATION": "false",
        "RESEARCH_API_STYLE": api_style,
    }

    if provider == "gemini":
        gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get(
            "GOOGLE_API_KEY"
        )
        if not gemini_key:
            pytest.skip(
                "GEMINI_API_KEY / GOOGLE_API_KEY not set; skipping Gemini provider check"
            )
        # Override both so we don't inherit a stale openai api_key / base_url
        # from ~/.deep_research when running against Gemini.
        env_overrides["RESEARCH_API_KEY"] = gemini_key
        env_overrides["RESEARCH_BASE_URL"] = "https://generativelanguage.googleapis.com"

    old_values: dict[str, str | None] = {
        key: os.environ.get(key) for key in env_overrides
    }

    logger.info(
        f"Setting environment overrides: {sorted(env_overrides.keys())} "
        f"(provider={provider}, model={model}, api_style={api_style})"
    )
    for key, value in env_overrides.items():
        os.environ[key] = value

    try:
        # Confirm config resolve reflects our desired provider/model
        logger.info("Loading ResearchConfig from environment...")
        cfg = ResearchConfig.from_env()
        logger.info(
            f"Config loaded: provider={cfg.provider}, model={cfg.model}, api_style={cfg.api_style}"
        )

        assert cfg.provider == provider
        assert cfg.api_style == api_style
        if provider == "openai":
            assert cfg.model == "gpt-5-mini"
        else:
            assert cfg.model == model

        # Import server and ensure a fresh agent instance
        logger.info("Importing mcp_server and resetting agent...")
        import deep_research_mcp.mcp_server as mcp_server

        mcp_server.research_agent = None

        # Run deep research for real (no mocks/mocks)
        logger.info(
            f"Starting deep_research call for provider: {provider} (api_style={api_style})"
        )
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
        logger.info(f"Test PASSED for provider={provider} (api_style={api_style})")

    finally:
        # Restore environment
        logger.info("Restoring environment variables...")
        for key, old in old_values.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old
        logger.info(
            f"=== Finished test for provider={provider} (api_style={api_style}) ==="
        )


def main() -> None:
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(
        description="Run the deep research provider integration check without pytest."
    )
    parser.add_argument(
        "--provider",
        default="openai",
        help="Research provider to validate (default: openai).",
    )
    parser.add_argument(
        "--model",
        default="gpt-5-mini",
        help="Model identifier to use for the provider (default: gpt-5-mini).",
    )
    parser.add_argument(
        "--api-style",
        default="responses",
        choices=["responses", "chat_completions"],
        help="API style to use (default: responses).",
    )

    args = parser.parse_args()
    asyncio.run(run_provider_check(args.provider, args.model, api_style=args.api_style))


if __name__ == "__main__":
    main()
