#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Simple CLI tool to use the Deep Research MCP server functionality.
"""

import argparse
import asyncio
import sys
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

async def research(query: str, model: str = "o3-deep-research-2025-06-26") -> None:
    """Use the research functionality"""
    print(f"Starting research with query: '{query}'")
    print(f"Using model: {model}")
    print("-" * 50)

    try:
        # Create config with specified model
        config = ResearchConfig.from_env()
        config.model = model
        config.validate()
        
        # Initialize agent
        agent = DeepResearchAgent(config)
        
        # Perform research
        result = await agent.research(
            query=query,
            system_prompt=SYSTEM_PROMPT,
            include_code_interpreter=True
        )
        
        # Display results
        if result["status"] == "completed":
            print("Research completed successfully!")
            print(f"Task ID: {result['task_id']}")
            print(f"Total steps: {result['total_steps']}")
            print(f"Search queries: {len(result['search_queries'])}")
            print(f"Citations: {len(result['citations'])}")
            print("\n" + "=" * 60)
            print("RESEARCH REPORT")
            print("=" * 60)
            print(result['final_report'])
            
            if result['citations']:
                print("\n" + "=" * 60)
                print("CITATIONS")
                print("=" * 60)
                for citation in result['citations']:
                    print(f"{citation['index']}. [{citation['title']}]({citation['url']})")
        elif result["status"] == "failed":
            print(f"Research failed: {result.get('message', 'Unknown error')}")
            if result.get('error_code'):
                print(f"Error code: {result['error_code']}")
            if result.get('task_id'):
                print(f"Task ID: {result['task_id']}")
        else:
            print(f"Research error: {result.get('message', 'Unknown error')}")
            
    except ResearchError as e:
        print(f"Research error: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")


async def list_models() -> None:
    """List available models"""
    print("Available Deep Research Models:")
    print("-" * 40)
    models = [
        {
            "name": "o3-deep-research-2025-06-26",
            "description": "Highest quality model with 200K token context",
            "cost": "$40 per 1M output tokens"
        },
        {
            "name": "o4-mini-deep-research-2025-06-26",
            "description": "Faster, lower-cost alternative", 
            "cost": "Lower than o3 model"
        }
    ]
    
    for model in models:
        print(f"• {model['name']}")
        print(f"  Description: {model['description']}")
        print(f"  Cost: {model['cost']}")
        print()


async def check_config() -> None:
    """Check configuration"""
    print("Checking configuration...")
    print("-" * 30)
    
    try:
        config = ResearchConfig.from_env()
        config.validate()
        
        print("Configuration is valid")
        print(f"API Key: {'*' * 20}{config.api_key[-10:] if len(config.api_key) > 10 else '*' * len(config.api_key)}")
        print(f"Model: {config.model}")
        print(f"Timeout: {config.timeout} seconds")
        print(f"Poll interval: {config.poll_interval} seconds")
        print(f"Max retries: {config.max_retries}")
        
    except Exception as e:
        print(f"Configuration error: {e}")
        print("\nMake sure you have set the OPENAI_API_KEY environment variable")


def main():
    parser = argparse.ArgumentParser(description="Deep Research MCP CLI Tool")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Research command
    research_parser = subparsers.add_parser("research", help="Perform research on a query")
    research_parser.add_argument("query", help="Research query")
    research_parser.add_argument("--model", default="o3-deep-research-2025-06-26", 
                               choices=["o3-deep-research-2025-06-26", "o4-mini-deep-research-2025-06-26"],
                               help="Model to use for research")
    
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
    elif args.command == "models":
        asyncio.run(list_models())
    elif args.command == "config":
        asyncio.run(check_config())


if __name__ == "__main__":
    main()