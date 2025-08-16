#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Simple command-line interface for OpenAI Deep Research API.

Usage: 
    python cli/simple-cli.py "Your research question here"
    python cli/simple-cli.py "Your research question here" --clarify

Examples:
    python cli/simple-cli.py "What are the latest developments in quantum computing?"
    python cli/simple-cli.py "How does climate change affect ocean currents?"
    python cli/simple-cli.py "Compare the economic impact of remote work policies" --clarify
    python cli/simple-cli.py "What are the current trends in artificial intelligence research?"

Note: For clarification features, ensure ENABLE_CLARIFICATION=true in ~/.deep_research
"""

import os
import sys
import argparse
import structlog
from openai import OpenAI


def main():
    parser = argparse.ArgumentParser(description="Simple OpenAI Deep Research API CLI")
    parser.add_argument("query", help="Your research question")
    parser.add_argument(
        "--clarify", 
        action="store_true", 
        help="Enable clarification mode (requires ENABLE_CLARIFICATION=true in config)"
    )
    
    args = parser.parse_args()
    
    logger = structlog.get_logger()

    query = args.query

    # Add clarification note if enabled
    if args.clarify:
        logger.info("Note: --clarify flag provided, but this simple CLI doesn't implement clarification.")
        logger.info("For full clarification features, use:")
        logger.info("  python cli/clarification-cli.py \"your query\"")
        logger.info("  python cli/agent-cli.py research \"your query\" --clarify")
        logger.info("")

    logger.info(f"Researching: {query}")
    logger.info("This may take a few minutes...")

    try:
        client = OpenAI()

        response = client.responses.create(
            model="o4-mini-deep-research-2025-06-26",
            input=[
                {"role": "user", "content": [{"type": "input_text", "text": query}]}
            ],
            reasoning={"summary": "auto"},
            tools=[{"type": "web_search_preview"}],
        )

        logger.info("\n" + "=" * 80)
        logger.info("RESEARCH RESULTS")
        logger.info("=" * 80)

        # Get the final report
        if response.output and len(response.output) > 0:
            final_output = response.output[-1]
            if hasattr(final_output, "content") and final_output.content:
                report = final_output.content[0].text
                logger.info(report)

                # Show citations if available
                if hasattr(final_output.content[0], "annotations") and final_output.content[0].annotations:
                    logger.info("\n" + "-" * 40)
                    logger.info("CITATIONS")
                    logger.info("-" * 40)
                    for i, annotation in enumerate(final_output.content[0].annotations, 1):
                        if hasattr(annotation, "citation") and annotation.citation:
                            logger.info(f"[{i}] {annotation.citation.title}")
                            logger.info(f"    {annotation.citation.url}")
        else:
            logger.warning("No results returned from the research API.")

    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
