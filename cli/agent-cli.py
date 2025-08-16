#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Simple CLI tool to use the Deep Research MCP server functionality.

USAGE EXAMPLES:

  # Basic research query
  python cli/agent-cli.py research "What are the latest treatments for diabetes?"

  # Research with specific model (recommended)
  python cli/agent-cli.py research "Healthcare costs in the US" --model gpt-4o-mini

  # Check configuration
  python cli/agent-cli.py config

  # List available models
  python cli/agent-cli.py models

EXAMPLE QUERIES:
  - "What are the current market trends for AI in healthcare?"
  - "Compare effectiveness of different COVID-19 vaccines"
  - "Latest research on mental health treatments"
  - "Economic impact of telemedicine adoption"
"""

import argparse
import asyncio
import sys
import structlog
from pathlib import Path

# Add src to path to import the deep_research_mcp package
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from deep_research_mcp.agent import DeepResearchAgent
from deep_research_mcp.config import ResearchConfig
from deep_research_mcp.errors import ResearchError

SYSTEM_PROMPT = """
You are a professional researcher preparing a structured, data-driven report on behalf of a global health economics team. Your task is to analyze the health question the user poses.

Do:
- Focus on data-rich insights: include specific figures, trends, statistics, and measurable outcomes (e.g., reduction in hospitalization costs, market size, pricing trends, payer adoption).
- When appropriate, summarize data in a way that could be turned into charts or tables, and call this out in the response (e.g., “this would work well as a bar chart comparing per-patient costs across regions”).
- Prioritize reliable, up-to-date sources: peer-reviewed research, health organizations (e.g., WHO, CDC), regulatory agencies, or pharmaceutical earnings reports.
- Include an internal file lookup tool to retrieve information from our own internal data sources. If you’ve already retrieved a file, do not call fetch again for that same file. Prioritize inclusion of that data.
- Include inline citations and return all source metadata.

Be analytical, avoid generalities, and ensure that each section supports data-backed reasoning that could inform healthcare policy or financial modeling.
"""


async def research(query: str, model: str = "gpt-4o-mini") -> None:
    """Use the research functionality"""
    logger = structlog.get_logger()

    logger.info(f"Starting research with query: '{query}'")
    logger.info(f"Using model: {model}")
    logger.info("-" * 50)

    try:
        # Create config with specified model
        config = ResearchConfig.from_env()
        config.model = model
        config.validate()

        # Initialize agent
        agent = DeepResearchAgent(config)

        # Perform research
        result = await agent.research(
            query=query, system_prompt=SYSTEM_PROMPT, include_code_interpreter=True
        )

        # Display results
        if result["status"] == "completed":
            logger.info("Research completed successfully!")
            logger.info(f"Task ID: {result['task_id']}")
            logger.info(f"Total steps: {result['total_steps']}")
            logger.info(f"Search queries: {len(result['search_queries'])}")
            logger.info(f"Citations: {len(result['citations'])}")
            logger.info("\n" + "=" * 60)
            logger.info("RESEARCH REPORT")
            logger.info("=" * 60)
            logger.info(result["final_report"])

            if result["citations"]:
                logger.info("\n" + "=" * 60)
                logger.info("CITATIONS")
                logger.info("=" * 60)
                for citation in result["citations"]:
                    logger.info(
                        f"{citation['index']}. [{citation['title']}]({citation['url']})"
                    )
        elif result["status"] == "failed":
            logger.error(f"Research failed: {result.get('message', 'Unknown error')}")
            if result.get("error_code"):
                logger.error(f"Error code: {result['error_code']}")
            if result.get("task_id"):
                logger.error(f"Task ID: {result['task_id']}")
        else:
            logger.error(f"Research error: {result.get('message', 'Unknown error')}")

    except ResearchError as e:
        logger.error(f"Research error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")


async def check_config() -> None:
    """Check configuration"""
    logger = structlog.get_logger()

    logger.info("Checking configuration...")
    logger.info("-" * 30)

    try:
        config = ResearchConfig.from_env()
        config.validate()

        logger.info("Configuration is valid")
        logger.info(
            f"API Key: {'*' * 20}{config.api_key[-10:] if len(config.api_key) > 10 else '*' * len(config.api_key)}"
        )
        logger.info(f"Model: {config.model}")
        logger.info(f"Timeout: {config.timeout} seconds")
        logger.info(f"Poll interval: {config.poll_interval} seconds")
        logger.info(f"Max retries: {config.max_retries}")

    except Exception as e:
        logger.error(f"Configuration error: {e}")
        logger.error("\nMake sure you have set the OPENAI_API_KEY environment variable")


def main():
    parser = argparse.ArgumentParser(description="Deep Research MCP CLI Tool")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Research command
    research_parser = subparsers.add_parser(
        "research", help="Perform research on a query"
    )
    research_parser.add_argument("query", help="Research query")
    research_parser.add_argument(
        "--model",
        default="gpt-4o-mini",
        choices=[
            "gpt-4o-mini",
            "o3-deep-research-2025-06-26",
            "o4-mini-deep-research-2025-06-26",
        ],
        help="Model to use for research",
    )

    # List models command
    subparsers.add_parser("models", help="List available models")

    # Check config command
    subparsers.add_parser("config", help="Check configuration")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == "research":
        asyncio.run(research(args.query, args.model))
    elif args.command == "config":
        asyncio.run(check_config())


if __name__ == "__main__":
    main()
