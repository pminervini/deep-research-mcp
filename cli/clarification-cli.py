#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Clarification-focused CLI demonstrating the enhanced Deep Research pipeline.
This CLI shows how to use the clarification features in a conversational flow.

Usage: 
    python cli/clarification-cli.py "Your research question here"

Examples:
    python cli/clarification-cli.py "What are the latest developments in quantum computing?"
    python cli/clarification-cli.py "How has climate change affected Arctic ice coverage?"
    python cli/clarification-cli.py "What are the economic impacts of remote work?"
    python cli/clarification-cli.py "Compare the effectiveness of different vaccines"
"""

import os
import sys
import argparse
import structlog
import asyncio
from typing import Dict, Any, Optional, List

from deep_research_mcp.config import ResearchConfig
from deep_research_mcp.agent import DeepResearchAgent


def setup_logging():
    """Configure structured logging"""
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="ISO"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer()
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


async def run_clarification_pipeline(user_query: str) -> str:
    """
    Execute the complete clarification-enhanced research pipeline
    """
    logger = structlog.get_logger()
    logger.info("Starting Clarification-Enhanced Deep Research Pipeline")
    logger.info("=" * 70)

    try:
        # Load configuration
        config = ResearchConfig.from_env()
        config.enable_clarification = True  # Force enable for this CLI
        config.validate()
        
        logger.info(f"Configuration loaded:")
        logger.info(f"   Research Model: {config.model}")
        logger.info(f"   Triage Model: {config.triage_model}")
        logger.info(f"   Clarifier Model: {config.clarifier_model}")
        logger.info(f"   Clarification: {'Enabled' if config.enable_clarification else 'Disabled'}")
        
        # Initialize agent
        agent = DeepResearchAgent(config)
        
        # Step 1: Start clarification process
        logger.info("\n" + "=" * 70)
        logger.info("STEP 1: QUERY ANALYSIS")
        logger.info("=" * 70)
        
        clarification_result = agent.start_clarification(user_query)
        
        # Handle clarification result
        working_query = user_query
        if clarification_result.get("needs_clarification", False):
            logger.info(f"Assessment: {clarification_result.get('query_assessment', 'Query needs refinement')}")
            logger.info(f"Reasoning: {clarification_result.get('reasoning', 'Additional context would improve results')}")
            
            questions = clarification_result.get("questions", [])
            session_id = clarification_result.get("session_id", "")
            
            if questions:
                logger.info("\n" + "=" * 70)
                logger.info("STEP 2: CLARIFYING QUESTIONS")
                logger.info("=" * 70)
                logger.info("To provide the most relevant and useful research, please answer these questions:")
                
                answers = []
                for i, question in enumerate(questions, 1):
                    logger.info(f"\n{i}. {question}")
                    answer = input("Your answer (or press Enter to skip): ").strip()
                    answers.append(answer if answer else "[No specific preference]")
                    if answer:
                        logger.info(f"   → {answer}")
                    else:
                        logger.info("   → [Skipped]")
                
                # Process answers and enrich query
                logger.info("\n" + "=" * 70)
                logger.info("STEP 3: QUERY ENRICHMENT")
                logger.info("=" * 70)
                
                status_result = agent.add_clarification_answers(session_id, answers)
                if "error" not in status_result:
                    enriched_query = agent.get_enriched_query(session_id)
                    if enriched_query:
                        working_query = enriched_query
                        logger.info(f"Original Query: {user_query}")
                        logger.info(f"Enhanced Query: {working_query}")
                    else:
                        logger.warning("Could not enrich query, using original")
                else:
                    logger.error(f"Error processing answers: {status_result['error']}")
        else:
            logger.info(f"Assessment: {clarification_result.get('query_assessment', 'Query is sufficient')}")
            logger.info(f"Reasoning: {clarification_result.get('reasoning', 'No clarification needed')}")
            logger.info("Proceeding directly to research phase")
        
        # Step 4: Perform enhanced research
        logger.info("\n" + "=" * 70)
        logger.info("STEP 4: DEEP RESEARCH")
        logger.info("=" * 70)
        logger.info("Conducting comprehensive research...")
        logger.info("This may take several minutes...")
        
        system_prompt = """
        You are conducting professional research. Please provide:
        - Comprehensive analysis with specific data and statistics
        - Multiple perspectives on the topic
        - Current trends and recent developments
        - Authoritative sources and citations
        - Clear, well-structured presentation
        
        Focus on providing actionable insights backed by evidence.
        """
        
        result = await agent.research(
            query=working_query,
            system_prompt=system_prompt,
            include_code_interpreter=True,
        )
        
        # Step 5: Present results
        logger.info("\n" + "=" * 70)
        logger.info("STEP 5: RESEARCH RESULTS")
        logger.info("=" * 70)
        
        if result["status"] == "completed":
            logger.info("Research completed successfully!")
            logger.info(f"Task ID: {result.get('task_id', 'N/A')}")
            logger.info(f"Total research steps: {result.get('total_steps', 0)}")
            logger.info(f"Search queries executed: {len(result.get('search_queries', []))}")
            logger.info(f"Citations found: {len(result.get('citations', []))}")
            
            logger.info("\n" + "=" * 80)
            logger.info("FINAL RESEARCH REPORT")
            logger.info("=" * 80)
            logger.info(result.get('final_report', 'No report generated'))
            
            # Display citations
            citations = result.get('citations', [])
            if citations:
                logger.info("\n" + "=" * 80)
                logger.info("SOURCES AND CITATIONS")
                logger.info("=" * 80)
                for citation in citations:
                    logger.info(f"{citation.get('index', '?')}. {citation.get('title', 'Unknown Title')}")
                    logger.info(f"   URL: {citation.get('url', 'No URL')}")
            
            return result.get('final_report', 'Research completed but no report generated')
        
        else:
            error_message = result.get('message', 'Unknown error occurred')
            logger.error(f"Research failed: {error_message}")
            return f"Research failed: {error_message}"
    
    except Exception as e:
        logger.error(f"Pipeline failed with error: {e}")
        return f"Pipeline error: {str(e)}"


def main():
    """Main entry point"""
    setup_logging()
    logger = structlog.get_logger()
    
    parser = argparse.ArgumentParser(
        description="Clarification-Enhanced Deep Research CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cli/clarification-cli.py "What are the latest developments in quantum computing?"
  python cli/clarification-cli.py "How has climate change affected Arctic ice coverage?"
  python cli/clarification-cli.py "What are the economic impacts of remote work?"
        """
    )
    parser.add_argument("query", help="Your research question")
    parser.add_argument(
        "--no-clarification", 
        action="store_true", 
        help="Skip clarification and go directly to research"
    )
    
    args = parser.parse_args()
    
    if not args.query.strip():
        logger.error("Please provide a research query")
        parser.print_help()
        sys.exit(1)
    
    # Check for API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY environment variable not set")
        logger.error("Please set your OpenAI API key or add it to ~/.deep_research")
        sys.exit(1)
    
    # Run the pipeline
    if args.no_clarification:
        logger.info("Clarification disabled, proceeding directly to research")
        # Could implement direct research here
    
    try:
        result = asyncio.run(run_clarification_pipeline(args.query))
        logger.info("\n" + "=" * 80)
        logger.info("PIPELINE COMPLETED SUCCESSFULLY")
        logger.info("=" * 80)
    except KeyboardInterrupt:
        logger.info("\nPipeline interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()