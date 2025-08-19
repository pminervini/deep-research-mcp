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
    request_clarification: Annotated[
        bool,
        "When True, analyze the query and return clarifying questions instead of starting research. Use this to improve research quality for ambiguous queries.",
    ] = False,
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
        # Handle clarification request
        if request_clarification:
            clarification_result = research_agent.start_clarification(query)

            if not clarification_result.get("needs_clarification", False):
                return f"""# Query Analysis

**Original Query:** {query}

**Assessment:** {clarification_result.get('query_assessment', 'Query is sufficient for research')}

**Recommendation:** {clarification_result.get('reasoning', 'Proceed with research directly')}

You can proceed with the research using the same query."""

            # Format clarifying questions for Claude Code
            questions = clarification_result.get("questions", [])
            session_id = clarification_result.get("session_id", "")

            questions_formatted = "\n".join(
                [f"{i+1}. {q}" for i, q in enumerate(questions)]
            )

            return f"""# Clarifying Questions Needed

**Original Query:** {query}

**Why clarification is helpful:** {clarification_result.get('reasoning', 'Additional context will improve research quality')}

**Session ID:** `{session_id}`

**Please answer these questions to improve the research:**

{questions_formatted}

**Instructions:** Use the `research_with_context` tool with your answers and the session ID above to proceed with enhanced research."""

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


@mcp.tool()
async def research_with_context(
    session_id: Annotated[
        str,
        "Session ID from clarification request. Get this from the deep_research tool when request_clarification=True",
    ],
    answers: Annotated[
        list[str],
        "List of answers to the clarifying questions, in the same order as the questions were presented",
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
    Perform research using an enriched query based on clarification answers.

    **Use after:**
    - Calling `deep_research` with `request_clarification=True`
    - Receiving clarifying questions and a session ID
    - Gathering answers from the user

    **What it does:**
    - Takes your answers to clarifying questions
    - Creates an enriched, more specific research query
    - Performs comprehensive research with the enhanced query

    **Returns:** Complete research report with citations and metadata
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
        # Add answers to the clarification session
        status_result = research_agent.add_clarification_answers(session_id, answers)

        if "error" in status_result:
            return f"Error with clarification session: {status_result['error']}"

        # Get enriched query
        enriched_query = research_agent.get_enriched_query(session_id)

        if not enriched_query:
            return f"Could not retrieve enriched query for session {session_id}. Please check the session ID."

        logger.info(f"Using enriched query: {enriched_query}")

        # Prepare system prompt
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

        # Perform research with enriched query
        result = await research_agent.research(
            query=enriched_query,
            system_prompt=system_prompt,
            include_code_interpreter=include_analysis,
        )

        if result["status"] == "completed":
            # Format for Claude Code consumption
            formatted_result = f"""# Enhanced Research Report

**Original Query Enhanced With User Context**

**Enriched Query:** {enriched_query}

**User Clarifications Provided:** {len(answers)} answers

---

{result['final_report']}

## Research Metadata
- **Total research steps**: {result['total_steps']}
- **Search queries executed**: {len(result['search_queries'])}
- **Citations found**: {len(result['citations'])}
- **Task ID**: {result['task_id']}
- **Clarification Session**: {session_id}

## Citations
"""
            for citation in result["citations"]:
                formatted_result += (
                    f"{citation['index']}. [{citation['title']}]({citation['url']})\n"
                )

            return formatted_result
        else:
            return f"Research failed: {result.get('message', 'Unknown error')}"

    except Exception as e:
        logger.error(f"Error in research_with_context: {e}")
        return f"Error performing enhanced research: {str(e)}"


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
