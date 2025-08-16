#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MCP Server implementation for Claude Code integration.
"""

import logging
from typing import Annotated, Optional
from fastmcp import FastMCP

from deep_research_mcp.agent import DeepResearchAgent
from deep_research_mcp.config import ResearchConfig
from deep_research_mcp.errors import ResearchError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize MCP server
mcp = FastMCP("deep-research")

# Global agent instance
research_agent: Optional[DeepResearchAgent] = None


@mcp.tool()
async def deep_research(
    query: Annotated[
        str,
        "Specific research question or topic. Examples: 'Latest quantum computing breakthroughs in 2024', 'Compare renewable energy adoption rates globally', 'Analyze Tesla's financial performance vs competitors'",
    ],
    system_instructions: Annotated[
        str,
        "Custom research approach instructions. Examples: 'Focus on peer-reviewed sources only', 'Include financial data and charts', 'Prioritize recent developments from 2024-2025'. Leave empty for balanced analysis.",
    ] = "",
    include_analysis: Annotated[
        bool,
        "Enable code execution for data analysis, calculations, and visualizations. Useful for: statistical analysis, creating charts/graphs, processing datasets. Set to False for text-only research.",
    ] = True,
) -> str:
    """
    Performs autonomous deep research using OpenAI's Deep Research API with web search and analysis capabilities.

    **What it does:**
    - Decomposes complex queries into research strategies
    - Conducts real-time web searches for current information
    - Executes code for data analysis and visualization (when include_analysis=True)
    - Synthesizes findings into comprehensive reports with citations

    **Best for:**
    - Current events and recent developments
    - Data-driven analysis requiring statistics/charts
    - Complex topics needing multiple source synthesis
    - Academic-style research with proper citations

    **Returns:** Structured markdown report with citations, metadata, and research insights.

    **Note:** Uses OpenAI's Deep Research models - monitor costs as research can generate substantial tokens.
    """
    global research_agent

    if not research_agent:
        try:
            config = ResearchConfig.from_env()
            config.validate()
            research_agent = DeepResearchAgent(config)
        except Exception as e:
            return f"Failed to initialize research agent: {str(e)}"

    try:
        system_prompt = (
            system_instructions
            or """
        You are a professional researcher preparing a structured, data-driven report.
        Requirements:
        - Focus on data-rich insights with specific figures and statistics
        - Include tables and visualizations when appropriate  
        - Prioritize peer-reviewed sources and authoritative data
        - Use inline citations throughout
        - Be analytical and avoid generalities
        """
        )

        result = await research_agent.research(
            query=query,
            system_prompt=system_prompt,
            include_code_interpreter=include_analysis,
        )

        if result["status"] == "completed":
            # Format for Claude Code consumption
            formatted_result = f"""# Research Report: {query}

{result['final_report']}

## Research Metadata
- **Total research steps**: {result['total_steps']}
- **Search queries executed**: {len(result['search_queries'])}
- **Citations found**: {len(result['citations'])}
- **Task ID**: {result['task_id']}

## Citations
"""
            for citation in result["citations"]:
                formatted_result += (
                    f"{citation['index']}. [{citation['title']}]({citation['url']})\n"
                )

            return formatted_result
        else:
            return f"Research failed: {result.get('message', 'Unknown error')}"

    except ResearchError as e:
        logger.error(f"Research error: {e}")
        return f"Research error: {str(e)}"
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return f"Unexpected error: {str(e)}"


@mcp.tool()
async def research_status(
    task_id: Annotated[
        str,
        "Research task ID returned by deep_research tool. Format: UUID string like 'abc123-def456-ghi789'",
    ],
) -> str:
    """
    Check the current status and progress of a running research task.

    **Use when:**
    - Research is taking a long time (>5 minutes)
    - Want to check if a task completed successfully
    - Need creation/completion timestamps

    **Returns:** Task status ('running', 'completed', 'failed') with timestamps.
    """
    global research_agent

    if not research_agent:
        return "Research agent not initialized. Please run a research query first."

    try:
        status = await research_agent.get_task_status(task_id)

        if status["status"] == "error":
            return f"Error checking status: {status.get('error', 'Unknown error')}"

        result = f"Task {task_id} status: {status['status']}"

        if status.get("created_at"):
            result += f"\nCreated at: {status['created_at']}"

        if status.get("completed_at"):
            result += f"\nCompleted at: {status['completed_at']}"

        return result

    except Exception as e:
        logger.error(f"Error checking status: {e}")
        return f"Error checking status: {str(e)}"


def main():
    """Main entry point for MCP server"""
    logger.info("Starting Deep Research MCP server...")

    # Validate configuration on startup
    try:
        config = ResearchConfig.from_env()
        config.validate()
        logger.info(f"Configuration loaded successfully. Model: {config.model}")
    except Exception as e:
        logger.error(f"Configuration error: {e}")
        logger.error(
            "Please ensure OPENAI_API_KEY is set in your ~/.deep_research file or environment variables"
        )
        return

    # Run the MCP server
    mcp.run()


if __name__ == "__main__":
    main()
