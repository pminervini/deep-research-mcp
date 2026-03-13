# -*- coding: utf-8 -*-

"""
Deep Research MCP Agent

This module provides a provider-aware research agent that can work with multiple
research backends (OpenAI Responses API, Gemini Interactions API, and Open
Deep Research) to perform deep research tasks with optional clarification workflows.
"""

import asyncio
import logging
import time
import warnings
from typing import Any, Dict, List, Optional

import httpx
from openai import AuthenticationError, OpenAI
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential

from deep_research_mcp.clarification import ClarificationManager, build_clarification_client_kwargs
from deep_research_mcp.config import ResearchConfig
from deep_research_mcp.errors import ResearchError, TaskTimeoutError, ConfigurationError
from deep_research_mcp.prompts.prompts import PromptManager

logger = logging.getLogger(__name__)

GEMINI_DEEP_RESEARCH_AGENT = "deep-research-pro-preview-12-2025"
GEMINI_API_VERSION = "v1beta"
GEMINI_TERMINAL_STATUSES = {"completed", "failed", "cancelled", "incomplete"}


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
        elif self.config.provider in {"gemini"}:
            self._init_gemini()
        elif self.config.provider in {"open-deep-research"}:
            self._init_open_deep_research()
        else:
            raise ConfigurationError(f"Provider '{self.config.provider}' is not supported")

        self.logger = logging.getLogger(__name__)
        self.clarification_manager = ClarificationManager(config)
        self.prompt_manager = PromptManager()

        # Initialize instruction builder client only if clarification is enabled
        self.instruction_client = self._create_instruction_client() if config.enable_clarification else None

    def _init_gemini(self):
        """Initialize Gemini Interactions API client."""
        from google import genai
        from google.genai import types

        client_kwargs = {}
        http_options_kwargs = {"apiVersion": GEMINI_API_VERSION}

        if self.config.api_key:
            client_kwargs["api_key"] = self.config.api_key
        if self.config.base_url:
            http_options_kwargs["baseUrl"] = self.config.base_url

        client_kwargs["http_options"] = types.HttpOptions(**http_options_kwargs)
        self.client = genai.Client(**client_kwargs)

        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="Interactions usage is experimental.*", category=UserWarning)
            self.gemini_interactions = self.client.interactions

    def _init_open_deep_research(self):
        """Initialize open-deep-research components"""
        import os
        from dotenv import load_dotenv
        from huggingface_hub import login
        from smolagents import CodeAgent, ToolCallingAgent, LiteLLMModel, GoogleSearchTool, DuckDuckGoSearchTool, WikipediaSearchTool
        from open_deep_research.text_inspector_tool import TextInspectorTool
        from open_deep_research.text_web_browser import SimpleTextBrowser, VisitTool, PageUpTool, PageDownTool, FinderTool, FindNextTool, ArchiveSearchTool
        from open_deep_research.visual_qa import visualizer

        # Load environment variables
        load_dotenv(override=True)
        if os.getenv("HF_TOKEN"):
            login(os.getenv("HF_TOKEN"))

        # Setup browser configuration
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0"
        self.browser_config = {"viewport_size": 1024 * 5, "downloads_folder": "downloads_folder", "request_kwargs": {"headers": {"User-Agent": user_agent}, "timeout": 300}, "serpapi_key": os.getenv("SERPAPI_API_KEY")}
        os.makedirs(f"./{self.browser_config['downloads_folder']}", exist_ok=True)

        # Create model for open-deep-research
        model_params = {"model_id": self.config.model or "Qwen/Qwen2.5-Coder-32B-Instruct", "custom_role_conversions": {"tool-call": "assistant", "tool-response": "user"}, "max_completion_tokens": 8192}

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
        self.web_tools = search_tools + [VisitTool(self.browser), PageUpTool(self.browser), PageDownTool(self.browser), FinderTool(self.browser), FindNextTool(self.browser), ArchiveSearchTool(self.browser), TextInspectorTool(self.odr_model, text_limit)]

        # Create search agent
        search_agent_description = """A team member that will search the internet to answer your question.
Ask him for all your questions that require browsing the web.
Provide him as much context as possible, in particular if you need to search on a specific timeframe!
And don't hesitate to provide him with a complex search task, like finding a difference between two webpages.
Your request must be a real sentence, not a google search! Like "Find me this information (...)" rather than a few keywords.
"""
        self.search_agent = ToolCallingAgent(model=self.odr_model, tools=self.web_tools, max_steps=20, verbosity_level=2, planning_interval=4, name="search_agent", description=search_agent_description, provide_run_summary=True)

        # Add custom prompt for search agent
        self.search_agent.prompt_templates["managed_agent"]["task"] += """You can navigate to .txt online files.
If a non-html page is in another format, especially .pdf or a Youtube video, use tool 'inspect_file_as_text' to inspect it.
Additionally, if after some searching you find out that you need more information to answer the question, you can use `final_answer` with your request for clarification as argument to request for more information."""

        # Create manager agent
        self.manager_agent = CodeAgent(model=self.odr_model, tools=[visualizer, TextInspectorTool(self.odr_model, text_limit)], max_steps=12, verbosity_level=2, planning_interval=4, managed_agents=[self.search_agent], additional_authorized_imports=["*"])

    async def research(self, query: str, system_prompt: Optional[str] = None, include_code_interpreter: bool = True, callback_url: Optional[str] = None) -> Dict[str, Any]:
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

        result: Dict[str, Any]
        if self.config.provider in {"openai"}:
            # Route based on api_style
            if self.config.api_style == "chat_completions":
                result = await self._run_chat_completions_research(enhanced_query, system_prompt, include_code_interpreter)
            else:
                # Responses API path (default)
                # Prepare input messages for OpenAI
                input_messages = []
                if system_prompt:
                    input_messages.append({"role": "developer", "content": [{"type": "input_text", "text": system_prompt}]})

                input_messages.append({"role": "user", "content": [{"type": "input_text", "text": enhanced_query}]})

                # Configure tools
                tools = [{"type": "web_search_preview"}]
                if include_code_interpreter:
                    tools.append({"type": "code_interpreter", "container": {"type": "auto", "file_ids": []}})

                try:
                    response = await self._create_openai_research_task(input_messages, tools)
                    final_response = await self._wait_for_completion(response.id)
                    result = self._extract_openai_results(final_response)
                except ResearchError as e:
                    result = {"status": "failed", "message": str(e)}
        elif self.config.provider in {"gemini"}:
            try:
                result = await self._run_gemini_research(enhanced_query, system_prompt, include_code_interpreter)
            except ResearchError as e:
                result = {"status": "failed", "message": str(e)}
        elif self.config.provider in {"open-deep-research"}:
            # Use open-deep-research agent
            result = await self._run_open_deep_research(enhanced_query, system_prompt)
        else:
            raise ResearchError(f"Provider '{self.config.provider}' is not supported yet")

        # Send callback if provided
        if callback_url and result.get("status") == "completed":
            await self._send_completion_callback(callback_url, result)

        return result

    async def _run_open_deep_research(self, query: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        """Run open-deep-research agent asynchronously"""
        import uuid

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
            result = await loop.run_in_executor(None, self.manager_agent.run, augmented_query)

            # Extract citations from the agent's memory/search results
            citations = []
            search_queries = []

            # Try to extract search queries and citations from agent memory
            if hasattr(self.manager_agent, "memory") and hasattr(self.manager_agent.memory, "steps"):
                for step in self.manager_agent.memory.steps:
                    # Extract search queries
                    if hasattr(step, "tool_calls"):
                        for tool_call in step.tool_calls:
                            if "search" in tool_call.get("name", "").lower():
                                search_queries.append(tool_call.get("arguments", {}).get("query", ""))

                    # Extract citations from visited pages
                    if hasattr(step, "observations") and step.observations:
                        for obs in step.observations:
                            if isinstance(obs, str) and "http" in obs:
                                # Extract URLs from the observation
                                import re

                                urls = re.findall(r"https?://[^\s\)]+", obs)
                                for i, url in enumerate(urls):
                                    citations.append({"index": len(citations) + 1, "title": f"Source {len(citations) + 1}", "url": url.rstrip(".,;:"), "start_char": 0, "end_char": 0})

            # Get total steps
            total_steps = len(self.manager_agent.memory.steps) if hasattr(self.manager_agent, "memory") else 0

            return {"status": "completed", "final_report": str(result), "citations": citations, "reasoning_steps": total_steps, "search_queries": search_queries, "total_steps": total_steps, "task_id": task_id, "execution_time": time.time() - start_time}

        except Exception as e:
            self.logger.error(f"Open Deep Research error: {e}")
            return {"status": "failed", "message": str(e), "task_id": task_id, "execution_time": time.time() - start_time}

    async def _run_gemini_research(self, query: str, system_prompt: Optional[str] = None, include_code_interpreter: bool = True) -> Dict[str, Any]:
        """Run Gemini Deep Research via the Interactions API."""
        if include_code_interpreter:
            self.logger.debug("Gemini Deep Research does not expose a separate code_execution toggle; ignoring include_code_interpreter")

        request_input = query
        if system_prompt:
            request_input = f"{system_prompt}\n\n{query}"

        request_kwargs: Dict[str, Any] = {"agent": self.config.model or GEMINI_DEEP_RESEARCH_AGENT, "background": True, "input": request_input, "store": True}

        interaction = self.gemini_interactions.create(**request_kwargs)
        self.logger.info(f"Research task started: {interaction.id}")
        final_interaction = await self._wait_for_gemini_completion(interaction.id)
        return self._extract_gemini_results(final_interaction)

    async def _wait_for_gemini_completion(self, task_id: str):
        """Poll Gemini Interactions API for task completion with timeout."""
        start_time = time.time()

        while time.time() - start_time < self.config.timeout:
            try:
                interaction = self.gemini_interactions.get(task_id)

                if interaction.status == "completed":
                    self.logger.info(f"Research completed: {task_id}")
                    return interaction
                if interaction.status == "requires_action":
                    raise ResearchError(f"Research task {task_id} requires client tool handling, which this integration does not support")
                if interaction.status in {"failed", "cancelled", "incomplete"}:
                    raise ResearchError(self._extract_gemini_failure_message(interaction))

                self.logger.debug(f"Task {task_id} status: {interaction.status}")
                await asyncio.sleep(self.config.poll_interval)

            except ResearchError:
                raise
            except Exception as e:
                self.logger.error(f"Error polling task {task_id}: {e}")
                await asyncio.sleep(5)

        self.logger.warning(f"Task {task_id} timed out, attempting cancellation")
        try:
            self.gemini_interactions.cancel(task_id)
        except Exception:
            pass

        raise TaskTimeoutError(f"Research task {task_id} did not complete within {self.config.timeout} seconds")

    def _extract_gemini_failure_message(self, interaction) -> str:
        """Extract Gemini failure details from Interaction responses."""
        model_extra = getattr(interaction, "model_extra", None) or {}
        error_details = getattr(interaction, "error", None) or model_extra.get("error")

        if error_details:
            if isinstance(error_details, dict):
                error_message = error_details.get("message") or error_details.get("code")
                if error_message:
                    return f"Research task failed: {error_message}"
            return f"Research task failed: {error_details}"

        outputs = getattr(interaction, "outputs", None) or []
        for output in reversed(outputs):
            if getattr(output, "type", None) == "text" and getattr(output, "text", None):
                return f"Research task {interaction.status}: {output.text}"

        return f"Research task {interaction.id} ended with status {interaction.status}"

    def _extract_gemini_results(self, interaction) -> Dict[str, Any]:
        """Extract and structure final results (Gemini Interactions API)."""
        if interaction.status != "completed":
            return {"status": "failed", "message": self._extract_gemini_failure_message(interaction), "task_id": interaction.id}

        outputs = getattr(interaction, "outputs", None) or []
        if not outputs:
            return {"status": "error", "message": "No output received", "task_id": interaction.id}

        source_lookup: Dict[str, Dict[str, str]] = {}
        search_queries: List[str] = []
        reasoning_steps = 0
        final_report = ""

        for output in outputs:
            output_type = getattr(output, "type", None)
            if output_type == "text" and getattr(output, "text", None):
                final_report = output.text
            elif output_type == "thought":
                reasoning_steps += 1
            elif output_type == "google_search_call":
                queries = getattr(getattr(output, "arguments", None), "queries", None) or []
                search_queries.extend(query for query in queries if query)
            elif output_type == "google_search_result":
                for result in getattr(output, "result", None) or []:
                    if getattr(result, "url", None):
                        source_lookup[result.url] = {"title": getattr(result, "title", None) or result.url, "url": result.url}
            elif output_type == "url_context_result":
                for result in getattr(output, "result", None) or []:
                    if getattr(result, "url", None):
                        source_lookup[result.url] = {"title": result.url, "url": result.url}

        citations = []
        seen_urls = set()
        text_output = next((output for output in reversed(outputs) if getattr(output, "type", None) == "text" and getattr(output, "text", None)), None)

        if text_output and getattr(text_output, "annotations", None):
            for annotation in text_output.annotations:
                source = getattr(annotation, "source", None)
                if not source:
                    continue
                citation_info = source_lookup.get(source, {"title": source, "url": source})
                citation_url = citation_info["url"]
                if citation_url in seen_urls:
                    continue
                seen_urls.add(citation_url)
                citations.append({"index": len(citations) + 1, "title": citation_info["title"], "url": citation_url, "start_char": getattr(annotation, "start_index", 0) or 0, "end_char": getattr(annotation, "end_index", 0) or 0})

        for citation_info in source_lookup.values():
            if citation_info["url"] in seen_urls:
                continue
            seen_urls.add(citation_info["url"])
            citations.append({"index": len(citations) + 1, "title": citation_info["title"], "url": citation_info["url"], "start_char": 0, "end_char": 0})

        return {"status": "completed", "final_report": final_report, "citations": citations, "reasoning_steps": reasoning_steps, "search_queries": search_queries, "total_steps": len(outputs), "task_id": interaction.id}

    async def _run_chat_completions_research(self, query: str, system_prompt: Optional[str] = None, include_code_interpreter: bool = True) -> Dict[str, Any]:
        """Run research using the Chat Completions API (synchronous call, no polling)."""
        import uuid

        if include_code_interpreter:
            self.logger.debug("code_interpreter is not available with Chat Completions API; ignoring")

        # Build messages in Chat Completions format
        messages: List[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": query})

        start_time = time.time()

        try:
            # Create a client with an appropriate timeout for long-running requests
            client = OpenAI(api_key=self.client.api_key, base_url=str(self.client.base_url), timeout=httpx.Timeout(self.config.timeout, connect=10.0))

            # Run the synchronous API call in an executor to avoid blocking
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, lambda: self._create_chat_completions_request(client, messages))

            elapsed = time.time() - start_time
            return self._extract_chat_completions_results(response, elapsed)

        except Exception as e:
            self.logger.error(f"Chat Completions research error: {e}")
            return {"status": "failed", "message": str(e), "task_id": str(uuid.uuid4()), "execution_time": time.time() - start_time}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10), retry=retry_if_not_exception_type(AuthenticationError), reraise=True)
    def _create_chat_completions_request(self, client: OpenAI, messages: List[Dict[str, str]]):
        """Retry-wrapped Chat Completions API call."""
        return client.chat.completions.create(model=self.config.model, messages=messages)

    def _extract_chat_completions_results(self, response, elapsed_time: float) -> Dict[str, Any]:
        """Parse Chat Completions response into the standard output dict."""
        content = response.choices[0].message.content if response.choices else ""
        citations = self._extract_chat_completions_citations(response, content)

        return {"status": "completed", "final_report": content, "citations": citations, "reasoning_steps": 0, "search_queries": [], "total_steps": 1, "task_id": response.id, "execution_time": elapsed_time}

    def _extract_chat_completions_citations(self, response, text: str) -> List[Dict[str, Any]]:
        """Multi-layer citation extraction for Chat Completions responses."""
        import re

        citations: List[Dict[str, Any]] = []
        seen_urls: set = set()

        # 1. Perplexity-style: response.citations (list of URLs)
        provider_citations = getattr(response, "citations", None)
        if provider_citations and isinstance(provider_citations, list):
            for i, url in enumerate(provider_citations):
                if isinstance(url, str) and url not in seen_urls:
                    seen_urls.add(url)
                    citations.append({"index": len(citations) + 1, "title": f"Source {len(citations) + 1}", "url": url, "start_char": 0, "end_char": 0})

        # 2. Annotation-based: message.annotations
        message = response.choices[0].message if response.choices else None
        if message:
            annotations = getattr(message, "annotations", None)
            if annotations:
                for annotation in annotations:
                    url = getattr(annotation, "url", None)
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        citations.append({"index": len(citations) + 1, "title": getattr(annotation, "title", f"Source {len(citations) + 1}"), "url": url, "start_char": getattr(annotation, "start_index", 0), "end_char": getattr(annotation, "end_index", 0)})

        # 3. Regex fallback: extract URLs from response text
        if not citations and text:
            urls = re.findall(r"https?://[^\s\)\]\}>\"']+", text)
            for url in urls:
                url = url.rstrip(".,;:")
                if url not in seen_urls:
                    seen_urls.add(url)
                    citations.append({"index": len(citations) + 1, "title": f"Source {len(citations) + 1}", "url": url, "start_char": 0, "end_char": 0})

        return citations

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10), retry=retry_if_not_exception_type(AuthenticationError), reraise=True)
    async def _create_openai_research_task(self, input_messages: List[Dict], tools: List[Dict]) -> Dict[str, Any]:
        """Create research task with retry logic (OpenAI)"""
        response: Dict[str, Any] = self.client.responses.create(model=self.config.model, input=input_messages, tools=tools, reasoning={"summary": "auto"}, background=True)  # Essential for long-running tasks

        self.logger.info(f"Research task started: {response.id}")
        return response

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

            except ResearchError:
                raise
            except Exception as e:
                self.logger.error(f"Error polling task {task_id}: {e}")
                await asyncio.sleep(5)  # Brief backoff on error

        # Timeout reached, attempt cancellation
        self.logger.warning(f"Task {task_id} timed out, attempting cancellation")
        try:
            self.client.responses.cancel(task_id)
        except:
            pass

        raise TaskTimeoutError(f"Research task {task_id} did not complete within {self.config.timeout} seconds")

    async def _send_completion_callback(self, callback_url: str, response_data: Dict[str, Any]):
        """Send completion notification to callback URL"""
        try:
            async with httpx.AsyncClient() as client:
                payload = {"status": "completed", "task_id": response_data.get("task_id"), "timestamp": time.time(), "result_preview": response_data.get("final_report", "")[:500]}
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
                    return {"status": "failed", "message": error_details.get("message", "Unknown error"), "error_code": error_details.get("code"), "task_id": response.id}
                else:
                    return {"status": "failed", "message": str(error_details), "task_id": response.id}
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
                # Handle different annotation types using the type discriminator
                if annotation.type == "url_citation":
                    # Web search citation - has all fields we need
                    citations.append({"index": i + 1, "title": annotation.title, "url": annotation.url, "start_char": annotation.start_index, "end_char": annotation.end_index})
                elif annotation.type == "file_citation":
                    # File citation - use filename as title, create file:// URL
                    citations.append({"index": i + 1, "title": f"File: {annotation.filename}", "url": f"file://{annotation.file_id}/{annotation.filename}", "start_char": annotation.index, "end_char": annotation.index})
                elif annotation.type == "container_file_citation":
                    # Container file citation - use filename as title
                    citations.append({"index": i + 1, "title": f"Container File: {annotation.filename}", "url": f"container://{annotation.container_id}/{annotation.file_id}/{annotation.filename}", "start_char": annotation.start_index, "end_char": annotation.end_index})
                elif annotation.type == "file_path":
                    # File path citation - minimal info
                    citations.append({"index": i + 1, "title": f"File Path: {annotation.file_id}", "url": f"file://{annotation.file_id}", "start_char": annotation.index, "end_char": annotation.index})
                else:
                    # Unknown annotation type - log and skip
                    self.logger.warning(f"Unknown annotation type '{annotation.type}' " f"at index {i}, skipping")
                    continue

        # Extract intermediate steps for debugging
        reasoning_steps = [item.summary for item in response.output if item.type == "reasoning" and hasattr(item, "summary")]
        search_queries = [getattr(item.action, "query", "") for item in response.output if item.type == "web_search_call" and hasattr(item, "action")]

        return {"status": "completed", "final_report": final_report, "citations": citations, "reasoning_steps": len(reasoning_steps), "search_queries": search_queries, "total_steps": len(response.output), "task_id": response.id}

    async def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """Check the status of a research task"""
        if self.config.provider in {"openai"} and self.config.api_style == "chat_completions":
            return {"task_id": task_id, "status": "unknown", "message": "Task status tracking not available with Chat Completions API"}
        if self.config.provider in {"openai"}:
            try:
                response = self.client.responses.retrieve(task_id)
                return {"task_id": task_id, "status": response.status, "created_at": getattr(response, "created_at", None), "completed_at": getattr(response, "completed_at", None)}
            except Exception as e:
                self.logger.error(f"Error checking status for task {task_id}: {e}")
                return {"task_id": task_id, "status": "error", "error": str(e)}
        elif self.config.provider in {"gemini"}:
            try:
                interaction = self.gemini_interactions.get(task_id)
                completed_at = interaction.updated if interaction.status in GEMINI_TERMINAL_STATUSES else None
                return {"task_id": task_id, "status": interaction.status, "created_at": getattr(interaction, "created", None), "completed_at": completed_at}
            except Exception as e:
                self.logger.error(f"Error checking status for task {task_id}: {e}")
                return {"task_id": task_id, "status": "error", "error": str(e)}
        elif self.config.provider in {"open-deep-research"}:
            # For open-deep-research, we don't have persistent task tracking
            return {"task_id": task_id, "status": "unknown", "message": "Task status tracking not available for open-deep-research provider"}
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

    def add_clarification_answers(self, session_id: str, answers: List[str]) -> Dict[str, Any]:
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
        return OpenAI(**build_clarification_client_kwargs(self.config))

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
            instruction_prompt = self.prompt_manager.get_instruction_builder_prompt(query)

            # Call the instruction builder model
            response = self.instruction_client.chat.completions.create(model=self.config.instruction_builder_model, messages=[{"role": "user", "content": instruction_prompt}])

            enhanced_instruction = response.choices[0].message.content.strip()
            self.logger.info(f"Enhanced research instruction created for query: {query[:50]}...")

            return enhanced_instruction

        except Exception as e:
            self.logger.warning(f"Failed to build research instruction: {e}")
            # Fallback to original query if instruction building fails
            return query
