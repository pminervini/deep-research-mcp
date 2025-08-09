#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Simple command-line interface for OpenAI Deep Research API.

Usage: python cli/simple-cli.py "Your research question here"

Examples:
    python cli/simple-cli.py "What are the latest developments in quantum computing?"
    python cli/simple-cli.py "How does climate change affect ocean currents?"
    python cli/simple-cli.py "Compare the economic impact of remote work policies"
    python cli/simple-cli.py "What are the current trends in artificial intelligence research?"
"""

import os
import sys
import structlog
from openai import OpenAI


def main():
    logger = structlog.get_logger()

    if len(sys.argv) != 2:
        logger.error("Usage: python simple-cli.py 'Your research question'")
        sys.exit(1)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("Error: OPENAI_API_KEY environment variable not set")
        sys.exit(1)

    query = sys.argv[1]

    logger.info(f"Researching: {query}")
    logger.info("This may take a few minutes...")

    try:
        client = OpenAI(api_key=api_key)

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
