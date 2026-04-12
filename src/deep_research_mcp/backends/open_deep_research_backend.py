# -*- coding: utf-8 -*-

"""
Open Deep Research provider backend.
"""

import re
import time
import uuid
from typing import Any

from deep_research_mcp.async_utils import run_blocking
from deep_research_mcp.config import ResearchConfig
from deep_research_mcp.results import (
    ResearchCitation,
    ResearchResult,
    ResearchTaskStatus,
)

from .base import ResearchBackend


class OpenDeepResearchBackend(ResearchBackend):
    """Open Deep Research provider implementation."""

    def __init__(self, config: ResearchConfig, logger):
        super().__init__(config, logger)
        self._init_open_deep_research()

    def _init_open_deep_research(self) -> None:
        """Initialize open-deep-research components."""
        import os

        from dotenv import load_dotenv
        from huggingface_hub import login
        from open_deep_research.text_inspector_tool import TextInspectorTool
        from open_deep_research.text_web_browser import (
            ArchiveSearchTool,
            FindNextTool,
            FinderTool,
            PageDownTool,
            PageUpTool,
            SimpleTextBrowser,
            VisitTool,
        )
        from open_deep_research.visual_qa import visualizer
        from smolagents import CodeAgent, LiteLLMModel, ToolCallingAgent

        load_dotenv(override=True)
        if os.getenv("HF_TOKEN"):
            login(os.getenv("HF_TOKEN"))

        user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0"
        )
        self.browser_config = {
            "viewport_size": 1024 * 5,
            "downloads_folder": "downloads_folder",
            "request_kwargs": {"headers": {"User-Agent": user_agent}, "timeout": 300},
            "serpapi_key": os.getenv("SERPAPI_API_KEY"),
        }
        os.makedirs(f"./{self.browser_config['downloads_folder']}", exist_ok=True)

        model_params: dict[str, Any] = {
            "model_id": self.config.model or "Qwen/Qwen2.5-Coder-32B-Instruct",
            "custom_role_conversions": {
                "tool-call": "assistant",
                "tool-response": "user",
            },
            "max_completion_tokens": 8192,
        }
        if self.config.base_url:
            model_params["api_base"] = self.config.base_url
        if self.config.api_key:
            model_params["api_key"] = self.config.api_key

        self.odr_model = LiteLLMModel(**model_params)
        self.browser = SimpleTextBrowser(**self.browser_config)
        text_limit = 100000

        search_tools = self._build_search_tools()
        self.web_tools = search_tools + [
            VisitTool(self.browser),
            PageUpTool(self.browser),
            PageDownTool(self.browser),
            FinderTool(self.browser),
            FindNextTool(self.browser),
            ArchiveSearchTool(self.browser),
            TextInspectorTool(self.odr_model, text_limit),
        ]

        search_agent_description = """A team member that will search the internet to answer your question.
Ask him for all your questions that require browsing the web.
Provide him as much context as possible, in particular if you need to search on a specific timeframe!
And don't hesitate to provide him with a complex search task, like finding a difference between two webpages.
Your request must be a real sentence, not a google search! Like "Find me this information (...)" rather than a few keywords.
"""
        self.search_agent = ToolCallingAgent(
            model=self.odr_model,
            tools=self.web_tools,
            max_steps=20,
            verbosity_level=2,
            planning_interval=4,
            name="search_agent",
            description=search_agent_description,
            provide_run_summary=True,
        )
        self.search_agent.prompt_templates["managed_agent"][
            "task"
        ] += """You can navigate to .txt online files.
If a non-html page is in another format, especially .pdf or a Youtube video, use tool 'inspect_file_as_text' to inspect it.
Additionally, if after some searching you find out that you need more information to answer the question, you can use `final_answer` with your request for clarification as argument to request for more information."""

        self.manager_agent = CodeAgent(
            model=self.odr_model,
            tools=[visualizer, TextInspectorTool(self.odr_model, text_limit)],
            max_steps=12,
            verbosity_level=2,
            planning_interval=4,
            managed_agents=[self.search_agent],
            additional_authorized_imports=["*"],
        )

    def _build_search_tools(self) -> list[Any]:
        """Build the search tool list for Open Deep Research."""
        import os

        from smolagents import (
            DuckDuckGoSearchTool,
            GoogleSearchTool,
            WikipediaSearchTool,
        )

        search_tools: list[Any] = []
        if os.getenv("SERPAPI_API_KEY") or os.getenv("SERPER_API_KEY"):
            try:
                search_tools.append(
                    GoogleSearchTool(
                        provider="serper" if os.getenv("SERPER_API_KEY") else "serpapi"
                    )
                )
            except Exception:
                pass

        search_tools.append(DuckDuckGoSearchTool())
        search_tools.append(WikipediaSearchTool(user_agent="OpenDeepResearch/1.0"))
        return search_tools

    async def research(
        self,
        query: str,
        system_prompt: str | None = None,
        include_code_interpreter: bool = True,
    ) -> ResearchResult:
        """Run research via the Open Deep Research provider."""
        del include_code_interpreter
        return await self._run_research(query, system_prompt)

    async def get_task_status(self, task_id: str) -> ResearchTaskStatus:
        """Return task status for the Open Deep Research provider."""
        return ResearchTaskStatus.unknown(
            task_id=task_id,
            message="Task status tracking not available for open-deep-research provider",
        )

    async def _run_research(
        self, query: str, system_prompt: str | None = None
    ) -> ResearchResult:
        """Run open-deep-research asynchronously."""
        task_id = str(uuid.uuid4())
        start_time = time.time()
        augmented_query = self._combine_system_prompt(query, system_prompt)

        try:
            result = await run_blocking(self.manager_agent.run, augmented_query)
            citations, search_queries, total_steps = self._extract_memory_details()
            return ResearchResult.completed(
                task_id=task_id,
                final_report=str(result),
                citations=citations,
                reasoning_steps=total_steps,
                search_queries=search_queries,
                total_steps=total_steps,
                execution_time=time.time() - start_time,
            )
        except Exception as error:
            self.logger.error(f"Open Deep Research error: {error}")
            return ResearchResult.failed(
                message=str(error),
                task_id=task_id,
                execution_time=time.time() - start_time,
            )

    def _extract_memory_details(
        self,
    ) -> tuple[list[ResearchCitation], list[str], int]:
        """Extract citations and search queries from ODR agent memory."""
        citations: list[ResearchCitation] = []
        search_queries: list[str] = []

        memory = getattr(self.manager_agent, "memory", None)
        if memory is None or not hasattr(memory, "steps"):
            return citations, search_queries, 0

        for step in memory.steps:
            if hasattr(step, "tool_calls"):
                for tool_call in step.tool_calls:
                    if "search" in tool_call.get("name", "").lower():
                        search_queries.append(
                            tool_call.get("arguments", {}).get("query", "")
                        )

            if hasattr(step, "observations") and step.observations:
                for observation in step.observations:
                    if isinstance(observation, str) and "http" in observation:
                        urls = re.findall(r"https?://[^\s\)]+", observation)
                        for url in urls:
                            citations.append(
                                ResearchCitation(
                                    index=len(citations) + 1,
                                    title=f"Source {len(citations) + 1}",
                                    url=url.rstrip(".,;:"),
                                )
                            )

        return citations, search_queries, len(memory.steps)
