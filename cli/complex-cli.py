#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Four-Agent Deep Research Pipeline CLI
Implements the Four-Agent Deep Research Pipeline with Triage, Clarifier, Instruction Builder, and Research Agents.

Usage: 
    python complex-cli.py "Your research question here"

Examples:
    python cli/complex-cli.py "What are the latest developments in quantum computing?"
    python cli/complex-cli.py "How has climate change affected Arctic ice coverage in the last decade?"
    python cli/complex-cli.py "What are the economic impacts of remote work on urban real estate markets?"
    python cli/complex-cli.py "Compare the effectiveness of different COVID-19 vaccines"
"""
import os
import sys
import json
from typing import Dict, Any, Optional, List
from openai import OpenAI


class FourAgentPipeline:
    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key)
        self.conversation_history: List[Dict[str, Any]] = []
    
    def triage_agent(self, user_query: str) -> Dict[str, Any]:
        """
        Triage Agent: Inspects query and decides if clarification is needed
        """
        print("🔍 Triage Agent: Analyzing your query...")
        
        triage_prompt = f"""
        You are a Triage Agent. Your job is to analyze the user's research query and decide if it needs clarification.
        
        User Query: "{user_query}"
        
        Analyze this query and determine:
        1. Is the query clear and specific enough for direct research?
        2. Are there ambiguous terms that need clarification?
        3. Would additional context help improve the research?
        
        Respond with a JSON object:
        {{
            "needs_clarification": true/false,
            "reasoning": "explanation of your decision",
            "potential_clarifications": ["list of questions to ask if clarification is needed"],
            "query_assessment": "brief assessment of the query quality"
        }}
        """
        
        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": triage_prompt}],
            temperature=0.3
        )
        
        try:
            result = json.loads(response.choices[0].message.content)
            print(f"📋 Assessment: {result['query_assessment']}")
            return result
        except json.JSONDecodeError:
            # Fallback if JSON parsing fails
            return {
                "needs_clarification": False,
                "reasoning": "Could not parse triage response, proceeding with original query",
                "potential_clarifications": [],
                "query_assessment": "Unable to assess"
            }
    
    def clarifier_agent(self, user_query: str, clarifications: List[str]) -> str:
        """
        Clarifier Agent: Asks follow-up questions and enriches the query
        """
        print("\n❓ Clarifier Agent: I need some additional information...")
        
        enriched_context = []
        
        for i, question in enumerate(clarifications[:3], 1):  # Limit to 3 questions
            print(f"\nQuestion {i}: {question}")
            user_input = input("Your answer (or press Enter to skip): ").strip()
            
            if user_input:
                enriched_context.append(f"Q: {question}\nA: {user_input}")
            else:
                enriched_context.append(f"Q: {question}\nA: [No additional information provided]")
        
        # Create enriched query
        enrichment_prompt = f"""
        Original Query: "{user_query}"
        
        Additional Context from User:
        {chr(10).join(enriched_context)}
        
        Based on the original query and the additional context, create an enriched, more specific research query that incorporates the user's clarifications. Keep the core intent but make it more precise and actionable.
        
        Return only the enriched query, nothing else.
        """
        
        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": enrichment_prompt}],
            temperature=0.2
        )
        
        enriched_query = response.choices[0].message.content.strip()
        print(f"\n✅ Enriched Query: {enriched_query}")
        return enriched_query
    
    def instruction_builder_agent(self, query: str) -> str:
        """
        Instruction Builder Agent: Converts query into precise research brief
        """
        print("\n📝 Instruction Builder Agent: Creating detailed research brief...")
        
        instruction_prompt = f"""
        You are an Instruction Builder Agent. Your job is to convert a research query into a precise, comprehensive research brief that will guide a Research Agent to produce high-quality results.
        
        Query: "{query}"
        
        Create detailed research instructions that include:
        1. Clear research objectives and scope
        2. Key areas to investigate
        3. Types of sources to prioritize
        4. Specific questions to answer
        5. Expected deliverables format
        6. Quality criteria for the research
        
        Make the instructions comprehensive but focused. The Research Agent should understand exactly what is expected.
        
        Format your response as a detailed research brief.
        """
        
        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": instruction_prompt}],
            temperature=0.2
        )
        
        research_brief = response.choices[0].message.content
        print("📋 Research brief created successfully")
        return research_brief
    
    def research_agent(self, research_brief: str) -> str:
        """
        Research Agent: Performs the actual deep research
        """
        print("\n🔬 Research Agent: Conducting comprehensive research...")
        print("⏳ This may take several minutes...")
        
        try:
            response = self.client.responses.create(
                model="o4-mini-deep-research-2025-06-26",
                input=[
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": research_brief}]
                    }
                ],
                reasoning={"summary": "auto"},
                tools=[
                    {"type": "web_search_preview"}
                ]
            )
            
            # Extract the research results
            if response.output and len(response.output) > 0:
                final_output = response.output[-1]
                if hasattr(final_output, 'content') and final_output.content:
                    return final_output.content[0].text
            
            return "No research results were generated."
            
        except Exception as e:
            return f"Research failed with error: {str(e)}"
    
    def run_pipeline(self, user_query: str) -> str:
        """
        Execute the complete Four-Agent Deep Research Pipeline
        """
        print("🚀 Starting Four-Agent Deep Research Pipeline")
        print("="*60)
        
        # Step 1: Triage Agent
        triage_result = self.triage_agent(user_query)
        
        # Step 2: Clarifier Agent (if needed)
        working_query = user_query
        if triage_result["needs_clarification"] and triage_result["potential_clarifications"]:
            print(f"\n💡 Reasoning: {triage_result['reasoning']}")
            working_query = self.clarifier_agent(user_query, triage_result["potential_clarifications"])
        else:
            print(f"\n💡 Reasoning: {triage_result['reasoning']}")
            print("✅ Query is clear enough, proceeding without clarification")
        
        # Step 3: Instruction Builder Agent
        research_brief = self.instruction_builder_agent(working_query)
        
        # Step 4: Research Agent
        research_results = self.research_agent(research_brief)
        
        return research_results


def main():
    if len(sys.argv) != 2:
        print("Usage: python complex-cli.py 'Your research question'")
        print("\nExample:")
        print("python complex-cli.py 'What are the latest developments in quantum computing?'")
        sys.exit(1)
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY environment variable not set")
        sys.exit(1)
    
    user_query = sys.argv[1]
    
    try:
        pipeline = FourAgentPipeline(api_key)
        results = pipeline.run_pipeline(user_query)
        
        print("\n" + "="*80)
        print("FINAL RESEARCH RESULTS")
        print("="*80)
        print(results)
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Pipeline interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()