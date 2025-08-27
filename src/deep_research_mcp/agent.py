# -*- coding: utf-8 -*-

"""
Deep Research MCP Agent

This module provides a provider-aware research agent that can work with multiple
research backends (OpenAI Responses API and Open Deep Research) to perform
deep research tasks with optional clarification workflows.
"""


import asyncio
import time
from typing import Dict, Any, Optional, List
import logging
from openai import OpenAI
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from deep_research_mcp.config import ResearchConfig
from deep_research_mcp.errors import ResearchError, TaskTimeoutError, ConfigurationError
from deep_research_mcp.clarification import ClarificationManager
from deep_research_mcp.prompts.prompts import PromptManager

logger = logging.getLogger(__name__)


class DeepResearchAgent:
    """Deep Research agent with full async support"""

    def __init__(self, config: ResearchConfig):
        self.config = config

        if self.config.provider in {"openai"}:
            # Initialize OpenAI client with custom endpoint if provided
            kwargs = {}
            if config.api_key:
                kwargs["api_key"] = config.api_key
            if config.base_url:
                kwargs["base_url"] = config.base_url
            self.client = OpenAI(**kwargs)

        elif self.config.provider in {"open-deep-research"}:
            self._init_open_deep_research()
        
        elif self.config.provider in {"anthropic"}:
            self._init_anthropic()
            
        else:
            raise ConfigurationError(f"Provider '{self.config.provider}' is not supported")

        self.logger = logging.getLogger(__name__)
        self.clarification_manager = ClarificationManager(config)
        self.prompt_manager = PromptManager()

        # Initialize instruction builder client only if clarification is enabled
        self.instruction_client = self._create_instruction_client() if config.enable_clarification else None

    def _init_open_deep_research(self):
        """Initialize open-deep-research components"""
        import os
        from dotenv import load_dotenv
        from huggingface_hub import login
        from smolagents import (
            CodeAgent,
            ToolCallingAgent,
            LiteLLMModel,
            GoogleSearchTool,
            DuckDuckGoSearchTool,
            WikipediaSearchTool,
        )
        from open_deep_research.text_inspector_tool import TextInspectorTool
        from open_deep_research.text_web_browser import (
            SimpleTextBrowser,
            VisitTool,
            PageUpTool,
            PageDownTool,
            FinderTool,
            FindNextTool,
            ArchiveSearchTool,
        )
        from open_deep_research.visual_qa import visualizer
        
        # Load environment variables
        load_dotenv(override=True)
        if os.getenv("HF_TOKEN"):
            login(os.getenv("HF_TOKEN"))
        
        # Setup browser configuration
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0"
        self.browser_config = {
            "viewport_size": 1024 * 5,
            "downloads_folder": "downloads_folder",
            "request_kwargs": {
                "headers": {"User-Agent": user_agent},
                "timeout": 300,
            },
            "serpapi_key": os.getenv("SERPAPI_API_KEY"),
        }
        os.makedirs(f"./{self.browser_config['downloads_folder']}", exist_ok=True)
        
        # Create model for open-deep-research
        model_params = {
            "model_id": self.config.model or "Qwen/Qwen2.5-Coder-32B-Instruct",
            "custom_role_conversions": {"tool-call": "assistant", "tool-response": "user"},
            "max_completion_tokens": 8192,
        }
        
        if self.config.base_url:
            model_params["api_base"] = self.config.base_url
        if self.config.api_key:
            model_params["api_key"] = self.config.api_key
        
        self.odr_model = LiteLLMModel(**model_params)
        
        # Initialize browser and tools
        self.browser = SimpleTextBrowser(**self.browser_config)
        text_limit = 100000
        
        # Setup web tools
        search_tools = []
        
        # Try to add Google search if API key is available
        if os.getenv("SERPAPI_API_KEY") or os.getenv("SERPER_API_KEY"):
            try:
                search_tools.append(GoogleSearchTool(provider="serper" if os.getenv("SERPER_API_KEY") else "serpapi"))
            except:
                pass
        
        # Always add DuckDuckGo as fallback
        search_tools.append(DuckDuckGoSearchTool())
        
        # Add Wikipedia search
        search_tools.append(WikipediaSearchTool(user_agent="OpenDeepResearch/1.0"))
        
        # Build complete web tools list
        self.web_tools = search_tools + [
            VisitTool(self.browser),
            PageUpTool(self.browser),
            PageDownTool(self.browser),
            FinderTool(self.browser),
            FindNextTool(self.browser),
            ArchiveSearchTool(self.browser),
            TextInspectorTool(self.odr_model, text_limit),
        ]
        
        # Create search agent
        self.search_agent = ToolCallingAgent(
            model=self.odr_model,
            tools=self.web_tools,
            max_steps=20,
            verbosity_level=2,
            planning_interval=4,
            name="search_agent",
            description="""A team member that will search the internet to answer your question.
Ask him for all your questions that require browsing the web.
Provide him as much context as possible, in particular if you need to search on a specific timeframe!
And don't hesitate to provide him with a complex search task, like finding a difference between two webpages.
Your request must be a real sentence, not a google search! Like "Find me this information (...)" rather than a few keywords.
""",
            provide_run_summary=True,
        )
        
        # Add custom prompt for search agent
        self.search_agent.prompt_templates["managed_agent"]["task"] += """You can navigate to .txt online files.
If a non-html page is in another format, especially .pdf or a Youtube video, use tool 'inspect_file_as_text' to inspect it.
Additionally, if after some searching you find out that you need more information to answer the question, you can use `final_answer` with your request for clarification as argument to request for more information."""
        
        # Create manager agent
        self.manager_agent = CodeAgent(
            model=self.odr_model,
            tools=[visualizer, TextInspectorTool(self.odr_model, text_limit)],
            max_steps=12,
            verbosity_level=2,
            planning_interval=4,
            managed_agents=[self.search_agent],
            additional_authorized_imports=["*"],
        )

    def _init_anthropic(self):
        """Initialize Anthropic client and tools"""
        try:
            import anthropic
        except ImportError:
            raise ConfigurationError(
                "Anthropic client not installed. Install with: pip install anthropic"
            )
        
        # Initialize Anthropic client
        kwargs = {}
        if self.config.api_key:
            kwargs["api_key"] = self.config.api_key
        if self.config.base_url:
            kwargs["base_url"] = self.config.base_url
        
        self.anthropic_client = anthropic.Anthropic(**kwargs)
        
        # Configure web search tools for Anthropic
        self.search_tools = self._init_web_search_tools()
    
    def _init_web_search_tools(self):
        """Initialize web search tools for Anthropic backend"""
        import os
        
        tools = []
        
        # Add search capability descriptions for function calling
        search_tool = {
            "name": "web_search",
            "description": "Search the web for information on a given query",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query to execute"
                    }
                },
                "required": ["query"]
            }
        }
        
        browse_tool = {
            "name": "browse_webpage",
            "description": "Browse and extract content from a specific webpage",
            "input_schema": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to browse and extract content from"
                    }
                },
                "required": ["url"]
            }
        }
        
        tools.extend([search_tool, browse_tool])
        return tools

    async def research(
        self,
        query: str,
        system_prompt: Optional[str] = None,
        include_code_interpreter: bool = True,
        callback_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Perform deep research on a query with full async handling

        Args:
            query: Research question or topic
            system_prompt: Optional system instructions for research approach
            include_code_interpreter: Whether to enable code execution
            callback_url: Optional webhook URL for completion notification

        Returns:
            Dictionary with final report, citations, and metadata
        """

        # Build enhanced research instruction using instruction builder model only if clarification is enabled
        if self.config.enable_clarification:
            enhanced_query = self.build_research_instruction(query)
        else:
            enhanced_query = query

        if self.config.provider in {"openai"}:
            # Prepare input messages for OpenAI
            input_messages = []
            if system_prompt:
                input_messages.append(
                    {
                        "role": "developer",
                        "content": [{"type": "input_text", "text": system_prompt}],
                    }
                )

            input_messages.append(
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": enhanced_query}],
                }
            )
        
            # Configure tools
            tools = [{"type": "web_search_preview"}]
            if include_code_interpreter:
                tools.append(
                    {
                        "type": "code_interpreter",
                        "container": {"type": "auto", "file_ids": []},
                    }
                )

            # Start background research task
            response = await self._create_openai_research_task(input_messages, tools)
        elif self.config.provider in {"open-deep-research"}:
            # Use open-deep-research agent
            return await self._run_open_deep_research(enhanced_query, system_prompt)
        elif self.config.provider in {"anthropic"}:
            # Use Anthropic agent
            return await self._run_anthropic_research(enhanced_query, system_prompt, include_code_interpreter)
        else:
            raise ResearchError(f"Provider '{self.config.provider}' is not supported yet")

        # Poll for completion with timeout
        try:
            final_response = await self._wait_for_completion(response.id)
        except ResearchError as e:
            # Return error details instead of raising
            return {"status": "failed", "message": str(e)}

        # Send callback if provided
        if callback_url and final_response.get("status") == "completed":
            await self._send_completion_callback(callback_url, final_response)

        return self._extract_openai_results(final_response)

    async def _run_open_deep_research(self, query: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        """Run open-deep-research agent asynchronously"""
        import uuid
        from datetime import datetime
        
        # Combine system prompt with query if provided
        augmented_query = query
        if system_prompt:
            augmented_query = f"{system_prompt}\n\n{query}"
        
        # Record start time
        task_id = str(uuid.uuid4())
        start_time = time.time()
        
        try:
            # Run the agent synchronously in an executor to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self.manager_agent.run,
                augmented_query
            )
            
            # Extract citations from the agent's memory/search results
            citations = []
            search_queries = []
            
            # Try to extract search queries and citations from agent memory
            if hasattr(self.manager_agent, 'memory') and hasattr(self.manager_agent.memory, 'steps'):
                for step in self.manager_agent.memory.steps:
                    # Extract search queries
                    if hasattr(step, 'tool_calls'):
                        for tool_call in step.tool_calls:
                            if 'search' in tool_call.get('name', '').lower():
                                search_queries.append(tool_call.get('arguments', {}).get('query', ''))
                    
                    # Extract citations from visited pages
                    if hasattr(step, 'observations') and step.observations:
                        for obs in step.observations:
                            if isinstance(obs, str) and 'http' in obs:
                                # Extract URLs from the observation
                                import re
                                urls = re.findall(r'https?://[^\s\)]+', obs)
                                for i, url in enumerate(urls):
                                    citations.append({
                                        "index": len(citations) + 1,
                                        "title": f"Source {len(citations) + 1}",
                                        "url": url.rstrip('.,;:'),
                                        "start_char": 0,
                                        "end_char": 0
                                    })
            
            # Get total steps
            total_steps = len(self.manager_agent.memory.steps) if hasattr(self.manager_agent, 'memory') else 0
            
            return {
                "status": "completed",
                "final_report": str(result),
                "citations": citations,
                "reasoning_steps": total_steps,
                "search_queries": search_queries,
                "total_steps": total_steps,
                "task_id": task_id,
                "execution_time": time.time() - start_time
            }
            
        except Exception as e:
            self.logger.error(f"Open Deep Research error: {e}")
            return {
                "status": "failed",
                "message": str(e),
                "task_id": task_id,
                "execution_time": time.time() - start_time
            }

    async def _run_anthropic_research(
        self, query: str, system_prompt: Optional[str] = None, include_code_interpreter: bool = True
    ) -> Dict[str, Any]:
        """Run Anthropic research agent asynchronously"""
        import uuid
        import requests
        from datetime import datetime
        from bs4 import BeautifulSoup
        import json
        import os
        
        # Record start time
        task_id = str(uuid.uuid4())
        start_time = time.time()
        
        try:
            # Prepare system message with research instructions
            system_message = """You are a deep research agent. Your task is to conduct comprehensive research on the given query using web search and content analysis.

For each research task:
1. Break down the query into searchable components
2. Search for relevant information using web_search
3. Browse important pages using browse_webpage to get detailed content
4. Synthesize findings into a comprehensive report
5. Include proper citations and sources

Always provide detailed, well-sourced information with references to your sources."""
            
            if system_prompt:
                system_message = f"{system_prompt}\n\n{system_message}"
            
            # Combine system prompt with query if provided
            user_message = query
            
            messages = [
                {"role": "user", "content": user_message}
            ]
            
            # Execute research with function calling
            search_queries = []
            citations = []
            reasoning_steps = []
            total_steps = 0
            
            # Initialize conversation loop for iterative research
            max_iterations = 10
            iteration = 0
            
            while iteration < max_iterations:
                total_steps += 1
                
                try:
                    # Call Anthropic API with function calling
                    response = self.anthropic_client.messages.create(
                        model=self.config.model,
                        max_tokens=4096,
                        system=system_message,
                        messages=messages,
                        tools=self.search_tools,
                        tool_choice={"type": "auto"}
                    )
                    
                    # Process response
                    assistant_message = {"role": "assistant", "content": []}
                    
                    for content_block in response.content:
                        if content_block.type == "text":
                            assistant_message["content"].append({
                                "type": "text", 
                                "text": content_block.text
                            })
                            reasoning_steps.append(content_block.text[:200] + "..." if len(content_block.text) > 200 else content_block.text)
                            
                        elif content_block.type == "tool_use":
                            # Handle tool calls
                            tool_name = content_block.name
                            tool_input = content_block.input
                            tool_use_id = content_block.id
                            
                            assistant_message["content"].append({
                                "type": "tool_use",
                                "id": tool_use_id,
                                "name": tool_name,
                                "input": tool_input
                            })
                            
                            # Execute the tool
                            tool_result = await self._execute_anthropic_tool(tool_name, tool_input)
                            
                            # Track search queries and citations
                            if tool_name == "web_search":
                                search_queries.append(tool_input.get("query", ""))
                            elif tool_name == "browse_webpage":
                                url = tool_input.get("url", "")
                                if url:
                                    citations.append({
                                        "index": len(citations) + 1,
                                        "title": f"Source {len(citations) + 1}",
                                        "url": url,
                                        "start_char": 0,
                                        "end_char": 0
                                    })
                            
                            # Add tool result to messages
                            messages.append(assistant_message)
                            messages.append({
                                "role": "user",
                                "content": [{
                                    "type": "tool_result",
                                    "tool_use_id": tool_use_id,
                                    "content": tool_result
                                }]
                            })
                            
                            break  # Continue to next iteration
                    else:
                        # No tool calls, we're done
                        final_response_text = ""
                        for content_block in response.content:
                            if content_block.type == "text":
                                final_response_text += content_block.text
                        
                        return {
                            "status": "completed",
                            "final_report": final_response_text,
                            "citations": citations,
                            "reasoning_steps": len(reasoning_steps),
                            "search_queries": search_queries,
                            "total_steps": total_steps,
                            "task_id": task_id,
                            "execution_time": time.time() - start_time
                        }
                
                except Exception as e:
                    self.logger.error(f"Error in Anthropic research iteration {iteration}: {e}")
                    if iteration == 0:
                        # If first iteration fails, return error
                        raise e
                    else:
                        # If later iteration fails, return what we have so far
                        break
                
                iteration += 1
                
                # Prevent infinite loops
                if iteration >= max_iterations:
                    break
            
            # If we exit the loop, compile final response from last assistant message
            final_report = "Research completed with available information."
            if messages and messages[-2]["role"] == "assistant":
                for content in messages[-2]["content"]:
                    if content.get("type") == "text":
                        final_report = content["text"]
                        break
            
            return {
                "status": "completed",
                "final_report": final_report,
                "citations": citations,
                "reasoning_steps": len(reasoning_steps),
                "search_queries": search_queries,
                "total_steps": total_steps,
                "task_id": task_id,
                "execution_time": time.time() - start_time
            }
            
        except Exception as e:
            self.logger.error(f"Anthropic research error: {e}")
            return {
                "status": "failed",
                "message": str(e),
                "task_id": task_id,
                "execution_time": time.time() - start_time
            }
    
    async def _execute_anthropic_tool(self, tool_name: str, tool_input: Dict[str, Any]) -> str:
        """Execute a tool call for Anthropic research"""
        import requests
        from bs4 import BeautifulSoup
        
        try:
            if tool_name == "web_search":
                query = tool_input.get("query", "")
                # Use DuckDuckGo search as a simple implementation
                return await self._simple_web_search(query)
                
            elif tool_name == "browse_webpage":
                url = tool_input.get("url", "")
                # Simple webpage content extraction
                return await self._simple_webpage_browse(url)
                
            else:
                return f"Unknown tool: {tool_name}"
                
        except Exception as e:
            self.logger.error(f"Tool execution error: {e}")
            return f"Tool execution failed: {str(e)}"
    
    async def _simple_web_search(self, query: str) -> str:
        """Simple DuckDuckGo search implementation"""
        import requests
        from bs4 import BeautifulSoup
        
        try:
            # Use DuckDuckGo instant answers API
            search_url = f"https://api.duckduckgo.com/?q={query}&format=json&no_html=1"
            
            async with httpx.AsyncClient() as client:
                response = await client.get(search_url, timeout=10)
                data = response.json()
                
                results = []
                
                # Get instant answer if available
                if data.get("Abstract"):
                    results.append(f"Summary: {data['Abstract']}")
                
                # Get related topics
                if data.get("RelatedTopics"):
                    results.append("Related information:")
                    for topic in data["RelatedTopics"][:3]:
                        if isinstance(topic, dict) and topic.get("Text"):
                            results.append(f"- {topic['Text']}")
                            if topic.get("FirstURL"):
                                results.append(f"  Source: {topic['FirstURL']}")
                
                if not results:
                    results.append(f"Search performed for: {query}")
                    results.append("Please try browsing specific URLs for more detailed information.")
                
                return "\n".join(results)
                
        except Exception as e:
            return f"Search failed: {str(e)}"
    
    async def _simple_webpage_browse(self, url: str) -> str:
        """Simple webpage content extraction"""
        from bs4 import BeautifulSoup
        
        try:
            async with httpx.AsyncClient() as client:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                }
                response = await client.get(url, headers=headers, timeout=15)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Remove script and style elements
                for script in soup(["script", "style"]):
                    script.decompose()
                
                # Get text content
                text = soup.get_text()
                
                # Clean up text
                lines = (line.strip() for line in text.splitlines())
                chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                text = ' '.join(chunk for chunk in chunks if chunk)
                
                # Limit text length
                if len(text) > 5000:
                    text = text[:5000] + "...\n[Content truncated]"
                
                return f"Content from {url}:\n\n{text}"
                
        except Exception as e:
            return f"Failed to browse {url}: {str(e)}"

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    async def _create_openai_research_task(
        self, input_messages: List[Dict], tools: List[Dict]
    ) -> Dict[str, Any]:
        """Create research task with retry logic (OpenAI)"""
        try:
            response: Dict[str, Any] = self.client.responses.create(
                model=self.config.model,
                input=input_messages,
                tools=tools,
                reasoning={"summary": "auto"},
                background=True,
            )  # Essential for long-running tasks

            self.logger.info(f"Research task started: {response.id}")
            return response
        except Exception as e:
            self.logger.error(f"Failed to create research task: {e}")
            raise

    async def _wait_for_completion(self, task_id: str) -> Dict[str, Any]:
        """Poll for task completion with timeout"""
        start_time = time.time()

        while time.time() - start_time < self.config.timeout:
            try:
                response: Dict[str, Any] = self.client.responses.retrieve(task_id)

                if response.status == "completed":
                    self.logger.info(f"Research completed: {task_id}")
                    return response
                elif response.status == "failed":
                    error_details = getattr(response, "error", None)
                    if error_details:
                        # Handle different error object types
                        if hasattr(error_details, "get"):
                            error_msg = f"Research task failed: {error_details.get('message', 'Unknown error')}"
                            if error_details.get("code"):
                                error_msg += f" (Code: {error_details['code']})"
                        else:
                            error_msg = f"Research task failed: {str(error_details)}"
                    else:
                        error_msg = f"Research task failed: {task_id}"
                    raise ResearchError(error_msg)

                # Continue polling
                self.logger.debug(f"Task {task_id} status: {response.status}")
                await asyncio.sleep(self.config.poll_interval)

            except Exception as e:
                self.logger.error(f"Error polling task {task_id}: {e}")
                await asyncio.sleep(5)  # Brief backoff on error

        # Timeout reached, attempt cancellation
        self.logger.warning(f"Task {task_id} timed out, attempting cancellation")
        try:
            self.client.responses.cancel(task_id)
        except:
            pass

        raise TaskTimeoutError(
            f"Research task {task_id} did not complete within {self.config.timeout} seconds"
        )

    async def _send_completion_callback(
        self, callback_url: str, response_data: Dict[str, Any]
    ):
        """Send completion notification to callback URL"""
        try:
            async with httpx.AsyncClient() as client:
                payload = {
                    "status": "completed",
                    "task_id": response_data.get("id"),
                    "timestamp": time.time(),
                    "result_preview": response_data.get("output", [])[-1]
                    .get("content", [{}])[0]
                    .get("text", "")[:500],
                }
                await client.post(callback_url, json=payload, timeout=30)
        except Exception as e:
            self.logger.error(f"Failed to send callback to {callback_url}: {e}")

    def _extract_openai_results(self, response) -> Dict[str, Any]:
        """Extract and structure final results (OpenAI)"""
        # Handle failed responses
        if response.status == "failed":
            error_details = getattr(response, "error", None)
            if error_details:
                # Handle different error object types
                if hasattr(error_details, "get"):
                    return {
                        "status": "failed",
                        "message": error_details.get("message", "Unknown error"),
                        "error_code": error_details.get("code"),
                        "task_id": response.id,
                    }
                else:
                    return {
                        "status": "failed",
                        "message": str(error_details),
                        "task_id": response.id,
                    }
            else:
                return {"status": "failed", "message": f"Task failed: {response.id}"}

        if not response.output:
            return {"status": "error", "message": "No output received"}

        # Get final report (last output item)
        final_output = response.output[-1]
        final_report = final_output.content[0].text if final_output.content else ""

        # Extract citations
        citations = []
        if final_output.content and final_output.content[0].annotations:
            for i, annotation in enumerate(final_output.content[0].annotations):
                citations.append(
                    {
                        "index": i + 1,
                        "title": annotation.title,
                        "url": annotation.url,
                        "start_char": annotation.start_index,
                        "end_char": annotation.end_index,
                    }
                )

        # Extract intermediate steps for debugging
        reasoning_steps = [
            item.summary
            for item in response.output
            if item.type == "reasoning" and hasattr(item, "summary")
        ]
        search_queries = [
            getattr(item.action, "query", "")
            for item in response.output
            if item.type == "web_search_call" and hasattr(item, "action")
        ]

        return {
            "status": "completed",
            "final_report": final_report,
            "citations": citations,
            "reasoning_steps": len(reasoning_steps),
            "search_queries": search_queries,
            "total_steps": len(response.output),
            "task_id": response.id,
        }

    async def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """Check the status of a research task"""
        if self.config.provider in {"openai"}:
            try:
                response = self.client.responses.retrieve(task_id)
                return {
                    "task_id": task_id,
                    "status": response.status,
                    "created_at": getattr(response, "created_at", None),
                    "completed_at": getattr(response, "completed_at", None),
                }
            except Exception as e:
                self.logger.error(f"Error checking status for task {task_id}: {e}")
                return {"task_id": task_id, "status": "error", "error": str(e)}
        elif self.config.provider in {"open-deep-research"}:
            # For open-deep-research, we don't have persistent task tracking
            return {
                "task_id": task_id,
                "status": "unknown",
                "message": "Task status tracking not available for open-deep-research provider"
            }
        elif self.config.provider in {"anthropic"}:
            # For Anthropic, we don't have persistent task tracking
            return {
                "task_id": task_id,
                "status": "unknown",
                "message": "Task status tracking not available for anthropic provider"
            }
        else:
            return {"task_id": task_id, "status": "error", "error": f"Provider {self.config.provider} not supported"}

    def start_clarification(self, user_query: str) -> Dict[str, Any]:
        """
        Start clarification process for a query

        Args:
            user_query: The original research query

        Returns:
            Dictionary with clarification status and questions, or indication to proceed
        """
        return self.clarification_manager.start_clarification(user_query)

    def add_clarification_answers(
        self, session_id: str, answers: List[str]
    ) -> Dict[str, Any]:
        """
        Add answers to clarification questions

        Args:
            session_id: Session identifier from start_clarification
            answers: List of answers to the clarification questions

        Returns:
            Dictionary with session status
        """
        return self.clarification_manager.add_answers(session_id, answers)

    def get_enriched_query(self, session_id: str) -> Optional[str]:
        """
        Get enriched query from clarification session

        Args:
            session_id: Session identifier

        Returns:
            Enriched query string or None if session not found
        """
        return self.clarification_manager.get_enriched_query(session_id)

    def _create_instruction_client(self) -> OpenAI:
        """
        Create OpenAI client for instruction builder using clarification settings or default config
        """
        kwargs = {}

        # Use clarification API key if available, otherwise fall back to main API key
        if self.config.clarification_api_key:
            kwargs["api_key"] = self.config.clarification_api_key
        elif self.config.api_key:
            kwargs["api_key"] = self.config.api_key

        # Use clarification base URL if available, otherwise fall back to main base URL
        if self.config.clarification_base_url:
            kwargs["base_url"] = self.config.clarification_base_url
        elif self.config.base_url:
            kwargs["base_url"] = self.config.base_url

        return OpenAI(**kwargs)

    def build_research_instruction(self, query: str) -> str:
        """
        Convert a research query into a precise, comprehensive research brief using instruction builder model

        Args:
            query: Original research query to enhance

        Returns:
            Enhanced research instruction string
        """
        # If instruction client is not available (clarification disabled), return original query
        if not self.instruction_client:
            return query
            
        try:
            # Get the instruction builder prompt template
            instruction_prompt = self.prompt_manager.get_instruction_builder_prompt(
                query
            )

            # Call the instruction builder model
            response = self.instruction_client.chat.completions.create(
                model=self.config.instruction_builder_model,
                messages=[{"role": "user", "content": instruction_prompt}]
            )

            enhanced_instruction = response.choices[0].message.content.strip()
            self.logger.info(
                f"Enhanced research instruction created for query: {query[:50]}..."
            )

            return enhanced_instruction

        except Exception as e:
            self.logger.warning(f"Failed to build research instruction: {e}")
            # Fallback to original query if instruction building fails
            return query
