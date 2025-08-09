#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Simple debug CLI for testing DeepResearchAgent
"""

import asyncio
import json
import logging
import sys
from src.deep_research_mcp.config import ResearchConfig
from src.deep_research_mcp.agent import DeepResearchAgent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

async def main():
    """Run a simple deep research task"""
    try:
        # Create config with gpt-4o model
        config = ResearchConfig.from_env()
        config.model = "gpt-4o"  # Override to use gpt-4o
        config.timeout = 300.0   # 5 minutes for debugging
        config.validate()
        
        # Create agent
        agent = DeepResearchAgent(config)
        
        # Test query - something that requires web search
        query = "What are the latest developments in artificial intelligence announced in January 2025?"
        
        print(f"Starting research with query: {query}")
        print(f"Using model: {config.model}")
        print("=" * 60)
        
        # Perform research
        result = await agent.research(
            query=query,
            system_prompt="Please provide a comprehensive but concise analysis.",
            include_code_interpreter=False
        )
        
        # Print results
        print("\nRESULT:")
        print("=" * 60)
        print(json.dumps(result, indent=2))
        
        if result.get("status") == "completed":
            print("\nFINAL REPORT:")
            print("=" * 60)
            print(result.get("final_report", "No report available"))
            
            if result.get("citations"):
                print(f"\nCITATIONS ({len(result['citations'])}):")
                print("=" * 60)
                for citation in result["citations"]:
                    print(f"[{citation['index']}] {citation['title']}")
                    print(f"    {citation['url']}")
        else:
            print(f"\nTask failed with status: {result.get('status')}")
            print(f"Message: {result.get('message')}")
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())