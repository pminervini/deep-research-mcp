# -*- coding: utf-8 -*-

"""
Example: Using Anthropic Claude for Deep Research

This example demonstrates how to configure and use the Anthropic provider
for deep research tasks.
"""

import asyncio
import os
from deep_research_mcp.config import ResearchConfig
from deep_research_mcp.agent import DeepResearchAgent


async def main():
    """Example of using Anthropic Claude for research"""
    
    # Set up environment variables for Anthropic
    os.environ["PROVIDER"] = "anthropic"
    os.environ["RESEARCH_MODEL"] = "claude-3-5-sonnet-20241022"
    os.environ["ANTHROPIC_API_KEY"] = "your-anthropic-api-key-here"
    
    # Create configuration from environment
    config = ResearchConfig.from_env()
    
    # Initialize the research agent
    agent = DeepResearchAgent(config)
    
    # Perform research
    query = "What are the latest developments in quantum computing in 2024?"
    system_prompt = "Focus on recent breakthroughs and their practical applications."
    
    try:
        result = await agent.research(
            query=query,
            system_prompt=system_prompt,
            include_code_interpreter=False  # Anthropic doesn't use code interpreter
        )
        
        print("Research Results:")
        print("================")
        print(f"Status: {result['status']}")
        print(f"Task ID: {result['task_id']}")
        print(f"Total Steps: {result['total_steps']}")
        print(f"Citations: {len(result.get('citations', []))}")
        print(f"Search Queries: {result.get('search_queries', [])}")
        print("\nFinal Report:")
        print("-" * 50)
        print(result['final_report'])
        
        if result.get('citations'):
            print("\nSources:")
            print("-" * 50)
            for citation in result['citations']:
                print(f"{citation['index']}. {citation['title']}: {citation['url']}")
    
    except Exception as e:
        print(f"Research failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())