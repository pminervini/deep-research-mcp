# -*- coding: utf-8 -*-

"""
Shared backend interface definitions.
"""

import logging
from collections.abc import Awaitable, Callable

from deep_research_mcp.config import ResearchConfig
from deep_research_mcp.results import ResearchResult, ResearchTaskStatus

TaskStartedCallback = Callable[[str], Awaitable[None]]


class ResearchBackend:
    """Common interface for provider-specific research implementations."""

    def __init__(self, config: ResearchConfig, logger: logging.Logger):
        self.config = config
        self.logger = logger

    async def research(
        self,
        query: str,
        system_prompt: str | None = None,
        include_code_interpreter: bool = True,
        on_task_started: TaskStartedCallback | None = None,
    ) -> ResearchResult:
        """Run provider-specific research."""
        raise NotImplementedError

    async def get_task_status(self, task_id: str) -> ResearchTaskStatus:
        """Return provider-specific task status details."""
        raise NotImplementedError

    async def get_task_result(self, task_id: str) -> ResearchResult | None:
        """Return the full result of a completed task, or None if unsupported."""
        return None

    @staticmethod
    def _combine_system_prompt(query: str, system_prompt: str | None) -> str:
        """Combine system instructions with the user query when present."""
        if system_prompt:
            return f"{system_prompt}\n\n{query}"
        return query
