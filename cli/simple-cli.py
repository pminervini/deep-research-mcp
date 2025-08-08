#!/usr/bin/env python3

"""
Simple command-line interface for OpenAI Deep Research API.
Usage: python simple-cli.py "Your research question here"
"""
import os
import sys
from openai import OpenAI


def main():
    if len(sys.argv) != 2:
        print("Usage: python simple-cli.py 'Your research question'")
        sys.exit(1)
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY environment variable not set")
        sys.exit(1)
    
    query = sys.argv[1]
    
    print(f"🔍 Researching: {query}")
    print("⏳ This may take a few minutes...")
    
    try:
        client = OpenAI(api_key=api_key)
        
        response = client.responses.create(
            model="o4-mini-deep-research-2025-06-26",
            input=[
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": query}]
                }
            ],
            reasoning={"summary": "auto"},
            tools=[
                {"type": "web_search_preview"}
            ]
        )
        
        print("\n" + "="*80)
        print("RESEARCH RESULTS")
        print("="*80)
        
        # Get the final report
        if response.output and len(response.output) > 0:
            final_output = response.output[-1]
            if hasattr(final_output, 'content') and final_output.content:
                report = final_output.content[0].text
                print(report)
                
                # Show citations if available
                if hasattr(final_output.content[0], 'annotations') and final_output.content[0].annotations:
                    print("\n" + "-"*40)
                    print("CITATIONS")
                    print("-"*40)
                    for i, annotation in enumerate(final_output.content[0].annotations, 1):
                        if hasattr(annotation, 'citation') and annotation.citation:
                            print(f"[{i}] {annotation.citation.title}")
                            print(f"    {annotation.citation.url}")
        else:
            print("No results returned from the research API.")
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()