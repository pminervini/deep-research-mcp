# -*- coding: utf-8 -*-

"""
Gemini provider backend.
"""

import asyncio
import time
import warnings
from typing import Any

from deep_research_mcp.async_utils import run_blocking
from deep_research_mcp.config import ResearchConfig
from deep_research_mcp.errors import ResearchError, TaskTimeoutError
from deep_research_mcp.results import (
    ResearchCitation,
    ResearchResult,
    ResearchTaskStatus,
)

from .base import ResearchBackend

GEMINI_DEEP_RESEARCH_AGENT = "deep-research-pro-preview-12-2025"
GEMINI_API_VERSION = "v1beta"
GEMINI_TERMINAL_STATUSES = {"completed", "failed", "cancelled", "incomplete"}


class GeminiResearchBackend(ResearchBackend):
    """Gemini-backed deep research implementation."""

    def __init__(self, config: ResearchConfig, logger):
        super().__init__(config, logger)
        self._init_gemini()

    def _init_gemini(self) -> None:
        """Initialize the Gemini Interactions API client."""
        from google import genai
        from google.genai import types

        client_kwargs: dict[str, Any] = {}
        if self.config.api_key:
            client_kwargs["api_key"] = self.config.api_key
        client_kwargs["http_options"] = types.HttpOptions(
            api_version=GEMINI_API_VERSION,
            base_url=self.config.base_url,
        )
        self.client = genai.Client(**client_kwargs)

        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="Interactions usage is experimental.*",
                category=UserWarning,
            )
            self.gemini_interactions = self.client.interactions

    async def research(
        self,
        query: str,
        system_prompt: str | None = None,
        include_code_interpreter: bool = True,
    ) -> ResearchResult:
        """Run research via Gemini Deep Research."""
        try:
            return await self._run_research(
                query, system_prompt, include_code_interpreter
            )
        except ResearchError as error:
            return ResearchResult.failed(message=str(error))

    async def get_task_status(self, task_id: str) -> ResearchTaskStatus:
        """Return task status for the Gemini provider."""
        try:
            interaction = await run_blocking(self.gemini_interactions.get, task_id)
            completed_at = (
                interaction.updated
                if interaction.status in GEMINI_TERMINAL_STATUSES
                else None
            )
            return ResearchTaskStatus(
                task_id=task_id,
                status=interaction.status,
                created_at=getattr(interaction, "created", None),
                completed_at=completed_at,
            )
        except Exception as error:
            self.logger.error(f"Error checking status for task {task_id}: {error}")
            return ResearchTaskStatus.error_status(task_id=task_id, error=str(error))

    async def _run_research(
        self,
        query: str,
        system_prompt: str | None = None,
        include_code_interpreter: bool = True,
    ) -> ResearchResult:
        """Run Gemini Deep Research via the Interactions API."""
        if include_code_interpreter:
            self.logger.debug(
                "Gemini Deep Research does not expose a separate "
                "code_execution toggle; ignoring include_code_interpreter"
            )

        request_input = self._combine_system_prompt(query, system_prompt)
        interaction = await run_blocking(
            self.gemini_interactions.create,
            agent=self.config.model or GEMINI_DEEP_RESEARCH_AGENT,
            background=True,
            input=request_input,
            store=True,
        )
        self.logger.info(f"Research task started: {interaction.id}")
        final_interaction = await self._wait_for_completion(interaction.id)
        return self._extract_results(final_interaction)

    async def _wait_for_completion(self, task_id: str):
        """Poll Gemini Interactions until completion or timeout."""
        start_time = time.time()

        while time.time() - start_time < self.config.timeout:
            try:
                interaction = await run_blocking(self.gemini_interactions.get, task_id)

                if interaction.status == "completed":
                    self.logger.info(f"Research completed: {task_id}")
                    return interaction
                if interaction.status == "requires_action":
                    raise ResearchError(
                        f"Research task {task_id} requires client tool handling, "
                        "which this integration does not support"
                    )
                if interaction.status in {"failed", "cancelled", "incomplete"}:
                    raise ResearchError(self._extract_failure_message(interaction))

                self.logger.debug(f"Task {task_id} status: {interaction.status}")
                await asyncio.sleep(self.config.poll_interval)

            except ResearchError:
                raise
            except Exception as error:
                self.logger.error(f"Error polling task {task_id}: {error}")
                await asyncio.sleep(5)

        self.logger.warning(f"Task {task_id} timed out, attempting cancellation")
        try:
            await run_blocking(self.gemini_interactions.cancel, task_id)
        except Exception:
            pass

        raise TaskTimeoutError(
            f"Research task {task_id} did not complete within "
            f"{self.config.timeout} seconds"
        )

    def _extract_failure_message(self, interaction) -> str:
        """Extract Gemini failure details from Interaction responses."""
        model_extra = getattr(interaction, "model_extra", None) or {}
        error_details = getattr(interaction, "error", None) or model_extra.get("error")

        if error_details:
            if isinstance(error_details, dict):
                error_message = error_details.get("message") or error_details.get(
                    "code"
                )
                if error_message:
                    return f"Research task failed: {error_message}"
            return f"Research task failed: {error_details}"

        outputs = getattr(interaction, "outputs", None) or []
        for output in reversed(outputs):
            if getattr(output, "type", None) == "text" and getattr(
                output, "text", None
            ):
                return f"Research task {interaction.status}: {output.text}"

        return f"Research task {interaction.id} ended with status {interaction.status}"

    def _extract_results(self, interaction) -> ResearchResult:
        """Extract and normalize Gemini Interactions output."""
        if interaction.status != "completed":
            return ResearchResult.failed(
                message=self._extract_failure_message(interaction),
                task_id=interaction.id,
            )

        outputs = getattr(interaction, "outputs", None) or []
        if not outputs:
            return ResearchResult.error(
                message="No output received", task_id=interaction.id
            )

        source_lookup: dict[str, dict[str, str]] = {}
        search_queries: list[str] = []
        reasoning_steps = 0
        final_report = ""

        for output in outputs:
            output_type = getattr(output, "type", None)
            if output_type == "text" and getattr(output, "text", None):
                final_report = output.text
            elif output_type == "thought":
                reasoning_steps += 1
            elif output_type == "google_search_call":
                queries = (
                    getattr(getattr(output, "arguments", None), "queries", None) or []
                )
                search_queries.extend(query for query in queries if query)
            elif output_type == "google_search_result":
                for result in getattr(output, "result", None) or []:
                    if getattr(result, "url", None):
                        source_lookup[result.url] = {
                            "title": getattr(result, "title", None) or result.url,
                            "url": result.url,
                        }
            elif output_type == "url_context_result":
                for result in getattr(output, "result", None) or []:
                    if getattr(result, "url", None):
                        source_lookup[result.url] = {
                            "title": result.url,
                            "url": result.url,
                        }

        citations: list[ResearchCitation] = []
        seen_urls: set[str] = set()
        text_output = next(
            (
                output
                for output in reversed(outputs)
                if getattr(output, "type", None) == "text"
                and getattr(output, "text", None)
            ),
            None,
        )

        if text_output and getattr(text_output, "annotations", None):
            for annotation in text_output.annotations:
                source = getattr(annotation, "source", None)
                if not source:
                    continue
                citation_info = source_lookup.get(
                    source, {"title": source, "url": source}
                )
                citation_url = citation_info["url"]
                if citation_url in seen_urls:
                    continue
                seen_urls.add(citation_url)
                citations.append(
                    ResearchCitation(
                        index=len(citations) + 1,
                        title=citation_info["title"],
                        url=citation_url,
                        start_char=getattr(annotation, "start_index", 0) or 0,
                        end_char=getattr(annotation, "end_index", 0) or 0,
                    )
                )

        for citation_info in source_lookup.values():
            if citation_info["url"] in seen_urls:
                continue
            seen_urls.add(citation_info["url"])
            citations.append(
                ResearchCitation(
                    index=len(citations) + 1,
                    title=citation_info["title"],
                    url=citation_info["url"],
                )
            )

        return ResearchResult.completed(
            task_id=interaction.id,
            final_report=final_report,
            citations=citations,
            reasoning_steps=reasoning_steps,
            search_queries=search_queries,
            total_steps=len(outputs),
        )
