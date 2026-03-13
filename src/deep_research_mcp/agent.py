# -*- coding: utf-8 -*-

"""
Deep Research MCP Agent

This module keeps orchestration concerns in `DeepResearchAgent` while delegating
provider-specific execution to dedicated backend implementations.
"""

import logging
import time
from typing import Any

import httpx
from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam

from deep_research_mcp.async_utils import run_blocking
from deep_research_mcp.backends import ResearchBackend, build_research_backend
from deep_research_mcp.clarification import (
    ClarificationManager,
    build_clarification_client_kwargs,
)
from deep_research_mcp.config import ResearchConfig
from deep_research_mcp.prompts.prompts import PromptManager
from deep_research_mcp.results import ResearchResult, ResearchTaskStatus

logger = logging.getLogger(__name__)


class DeepResearchAgent:
    """Provider-aware orchestrator for research, clarification, and callbacks."""

    def __init__(self, config: ResearchConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.backend: ResearchBackend = build_research_backend(config, self.logger)
        self.clarification_manager = ClarificationManager(config)
        self.prompt_manager = PromptManager()
        self.instruction_client = (
            self._create_instruction_client() if config.enable_clarification else None
        )

    def __getattr__(self, name: str) -> Any:
        """Expose backend attributes for compatibility with existing callers/tests."""
        backend = self.__dict__.get("backend")
        if backend is not None and hasattr(backend, name):
            return getattr(backend, name)
        raise AttributeError(
            f"{self.__class__.__name__!s} object has no attribute {name!r}"
        )

    async def research(
        self,
        query: str,
        system_prompt: str | None = None,
        include_code_interpreter: bool = True,
        callback_url: str | None = None,
    ) -> ResearchResult:
        """
        Perform deep research on a query with full async handling.

        Args:
            query: Research question or topic
            system_prompt: Optional system instructions for research approach
            include_code_interpreter: Whether to enable code execution
            callback_url: Optional webhook URL for completion notification

        Returns:
            Dictionary with final report, citations, and metadata
        """
        start_time = time.time()

        if self.config.enable_clarification:
            enhanced_query = await self.build_research_instruction_async(query)
        else:
            enhanced_query = query

        result = await self.backend.research(
            query=enhanced_query,
            system_prompt=system_prompt,
            include_code_interpreter=include_code_interpreter,
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

    def start_clarification(self, user_query: str) -> dict[str, Any]:
        """
        Start clarification process for a query.

        Args:
            user_query: The original research query

        Returns:
            Dictionary with clarification status and questions, or indication to proceed
        """
        return self.clarification_manager.start_clarification(user_query)

    async def start_clarification_async(self, user_query: str) -> dict[str, Any]:
        """Start clarification without blocking the event loop."""
        return await self.clarification_manager.start_clarification_async(user_query)

    def add_clarification_answers(
        self, session_id: str, answers: list[str]
    ) -> dict[str, Any]:
        """
        Add answers to clarification questions.

        Args:
            session_id: Session identifier from start_clarification
            answers: List of answers to the clarification questions

        Returns:
            Dictionary with session status
        """
        return self.clarification_manager.add_answers(session_id, answers)

    def get_enriched_query(self, session_id: str) -> str | None:
        """
        Get enriched query from clarification session.

        Args:
            session_id: Session identifier

        Returns:
            Enriched query string or None if session not found
        """
        return self.clarification_manager.get_enriched_query(session_id)

    async def get_enriched_query_async(self, session_id: str) -> str | None:
        """Get an enriched query without blocking the event loop."""
        return await self.clarification_manager.get_enriched_query_async(session_id)

    def _create_instruction_client(self) -> OpenAI:
        """
        Create the OpenAI client for instruction building.
        """
        return OpenAI(**build_clarification_client_kwargs(self.config))

    def build_research_instruction(self, query: str) -> str:
        """
        Convert a research query into a more precise research brief.

        Args:
            query: Original research query to enhance

        Returns:
            Enhanced research instruction string
        """
        if not self.instruction_client:
            return query

        try:
            instruction_prompt = self.prompt_manager.get_instruction_builder_prompt(
                query
            )
            messages: list[ChatCompletionMessageParam] = [
                {"role": "user", "content": instruction_prompt}
            ]
            response = self.instruction_client.chat.completions.create(
                model=self.config.instruction_builder_model,
                messages=messages,
            )
            enhanced_instruction = (response.choices[0].message.content or "").strip()
            if not enhanced_instruction:
                return query
            self.logger.info(
                f"Enhanced research instruction created for query: {query[:50]}..."
            )
            return enhanced_instruction
        except Exception as error:
            self.logger.warning(f"Failed to build research instruction: {error}")
            return query

    async def build_research_instruction_async(self, query: str) -> str:
        """Build research instructions without blocking the event loop."""
        return await run_blocking(self.build_research_instruction, query)
