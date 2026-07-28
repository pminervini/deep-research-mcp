# -*- coding: utf-8 -*-

"""
Deep Research MCP Agent

This module keeps orchestration concerns in `DeepResearchAgent` while delegating
provider-specific execution to dedicated backend implementations.
"""

import logging
import time

import httpx

from deep_research_mcp.backends import ResearchBackend, build_research_backend
from deep_research_mcp.backends.base import TaskStartedCallback
from deep_research_mcp.config import ResearchConfig
from deep_research_mcp.results import ResearchResult, ResearchTaskStatus

logger = logging.getLogger(__name__)


class DeepResearchAgent:
    """Provider-aware orchestrator for research and callbacks."""

    def __init__(self, config: ResearchConfig):
        self.config = config
        self.logger = logger
        self.backend: ResearchBackend = build_research_backend(config, self.logger)

    async def research(
        self,
        query: str,
        system_prompt: str | None = None,
        include_code_interpreter: bool = True,
        callback_url: str | None = None,
        on_task_started: TaskStartedCallback | None = None,
    ) -> ResearchResult:
        """
        Perform deep research on a query with full async handling.

        Args:
            query: Research question or topic
            system_prompt: Optional system instructions for research approach
            include_code_interpreter: Whether to enable code execution
            callback_url: Optional webhook URL for completion notification
            on_task_started: Optional async callback invoked with the provider
                task ID as soon as the research task is created

        Returns:
            Dictionary with final report, citations, and metadata
        """
        start_time = time.time()

        result = await self.backend.research(
            query=query,
            system_prompt=system_prompt,
            include_code_interpreter=include_code_interpreter,
            on_task_started=on_task_started,
        )

        if result.execution_time is None:
            result.execution_time = time.time() - start_time

        if callback_url and result.is_completed:
            await self._send_completion_callback(callback_url, result)

        return result

    async def _send_completion_callback(
        self, callback_url: str, response_data: ResearchResult
    ) -> None:
        """Send completion notification to callback URL."""
        try:
            async with httpx.AsyncClient() as client:
                payload = {
                    "status": "completed",
                    "task_id": response_data.task_id,
                    "timestamp": time.time(),
                    "result_preview": response_data.final_report[:500],
                }
                await client.post(callback_url, json=payload, timeout=30)
        except Exception as error:
            self.logger.error(f"Failed to send callback to {callback_url}: {error}")

    async def get_task_status(self, task_id: str) -> ResearchTaskStatus:
        """Check the status of a provider-specific research task."""
        return await self.backend.get_task_status(task_id)

    async def get_task_result(self, task_id: str) -> ResearchResult | None:
        """Fetch the full result of a completed task, or None if unsupported."""
        return await self.backend.get_task_result(task_id)
