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
    query: Annotated[str, "Research query or question to investigate"],
    system_instructions: Annotated[
        str, "Optional system prompt for research approach"
    ] = "",
    include_analysis: Annotated[
        bool, "Whether to include code analysis capabilities"
    ] = True,
) -> str:
    """
    Perform comprehensive research using OpenAI's Deep Research API.
    Returns a detailed report with citations and analysis.
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
    task_id: Annotated[str, "Task ID to check status for"],
) -> str:
    """Check the status of a research task by ID"""
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


@mcp.tool()
async def list_models() -> str:
    """List available Deep Research models"""
    models = [
        {
            "name": "gpt-4o",
            "description": "GPT-4o is a model from OpenAI. It is a general-purpose model that can be used for a variety of tasks.",
            "cost": "$0.15 per 1M input tokens, $0.60 per 1M output tokens"
        },
        {
            "name": "o3-deep-research-2025-06-26",
            "description": "Highest quality model with 200K token context",
            "cost": "$40 per 1M output tokens",
        },
        {
            "name": "o4-mini-deep-research-2025-06-26",
            "description": "Faster, lower-cost alternative",
            "cost": "Lower than o3 model",
        },
    ]

    result = "## Available Deep Research Models\n\n"
    for model in models:
        result += f"### {model['name']}\n"
        result += f"- Description: {model['description']}\n"
        result += f"- Cost: {model['cost']}\n\n"

    return result


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
            "Please ensure OPENAI_API_KEY is set in your environment or .env file"
        )
        return

    # Run the MCP server
    mcp.run()


if __name__ == "__main__":
    main()
