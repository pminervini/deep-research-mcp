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

from .base import ResearchBackend, TaskStartedCallback

GEMINI_DEEP_RESEARCH_AGENT = "deep-research-preview-04-2026"
GEMINI_API_VERSION = "v1beta"
GEMINI_API_REVISION = "2026-05-20"
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
        on_task_started: TaskStartedCallback | None = None,
    ) -> ResearchResult:
        """Run research via Gemini Deep Research."""
        try:
            return await self._run_research(
                query, system_prompt, include_code_interpreter, on_task_started
            )
        except ResearchError as error:
            return ResearchResult.failed(message=str(error))

    async def get_task_status(self, task_id: str) -> ResearchTaskStatus:
        """Return task status for the Gemini provider."""
        try:
            interaction = await run_blocking(
                self.gemini_interactions.get,
                task_id,
                extra_headers=self._api_revision_headers(),
            )
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

    async def get_task_result(self, task_id: str) -> ResearchResult | None:
        """Fetch the full result of a completed Gemini interaction."""
        interaction = await run_blocking(
            self.gemini_interactions.get,
            task_id,
            extra_headers=self._api_revision_headers(),
        )
        if interaction.status != "completed":
            return None
        return self.extract_results(interaction)

    async def _run_research(
        self,
        query: str,
        system_prompt: str | None = None,
        include_code_interpreter: bool = True,
        on_task_started: TaskStartedCallback | None = None,
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
            extra_headers=self._api_revision_headers(),
        )
        self.logger.info(f"Research task started: {interaction.id}")
        if on_task_started:
            await on_task_started(interaction.id)
        final_interaction = await self._wait_for_completion(interaction.id)
        return self.extract_results(final_interaction)

    async def _wait_for_completion(self, task_id: str):
        """Poll Gemini Interactions until completion or timeout."""
        start_time = time.time()

        while time.time() - start_time < self.config.timeout:
            try:
                interaction = await run_blocking(
                    self.gemini_interactions.get,
                    task_id,
                    extra_headers=self._api_revision_headers(),
                )

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

        if self.config.cancel_on_timeout:
            self.logger.warning(f"Task {task_id} timed out, attempting cancellation")
            try:
                await run_blocking(
                    self.gemini_interactions.cancel,
                    task_id,
                    extra_headers=self._api_revision_headers(),
                )
            except Exception:
                pass
            raise TaskTimeoutError(
                f"Research task {task_id} did not complete within "
                f"{self.config.timeout} seconds and was cancelled"
            )

        self.logger.warning(f"Task {task_id} timed out, leaving it running")
        raise TaskTimeoutError(
            f"Research task {task_id} did not complete within "
            f"{self.config.timeout} seconds. The task is still running; "
            f"use research_status with task ID {task_id} to retrieve the "
            "result later"
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

        for step in reversed(self._get_interaction_steps(interaction)):
            output_text = self._extract_step_text(step)
            if output_text:
                return f"Research task {interaction.status}: {output_text}"

        return f"Research task {interaction.id} ended with status {interaction.status}"

    def extract_results(self, interaction) -> ResearchResult:
        """Extract and normalize Gemini Interactions output."""
        if interaction.status != "completed":
            return ResearchResult.failed(
                message=self._extract_failure_message(interaction),
                task_id=interaction.id,
            )

        steps = self._get_interaction_steps(interaction)
        if not steps:
            return ResearchResult.error(
                message="No output received", task_id=interaction.id
            )

        source_lookup: dict[str, dict[str, str]] = {}
        search_queries: list[str] = []
        reasoning_steps = 0
        final_report_parts: list[str] = []

        for step in steps:
            step_type = getattr(step, "type", None)
            output_text = self._extract_step_text(step)
            if output_text:
                final_report_parts.append(output_text)
            elif step_type == "thought":
                reasoning_steps += 1
            elif step_type == "google_search_call":
                queries = (
                    getattr(getattr(step, "arguments", None), "queries", None) or []
                )
                search_queries.extend(query for query in queries if query)
            elif step_type == "url_context_result":
                for result in getattr(step, "result", None) or []:
                    if getattr(result, "url", None):
                        source_lookup[result.url] = {
                            "title": getattr(result, "title", None) or result.url,
                            "url": result.url,
                        }

        citations: list[ResearchCitation] = []
        seen_urls: set[str] = set()

        for step in steps:
            for annotation in self._extract_step_annotations(step):
                citation_url = (
                    getattr(annotation, "url", None)
                    or getattr(annotation, "source", None)
                    or getattr(annotation, "document_uri", None)
                )
                if not citation_url:
                    continue
                citation_title = (
                    getattr(annotation, "title", None)
                    or getattr(annotation, "file_name", None)
                    or getattr(annotation, "name", None)
                    or citation_url
                )
                citation_info = source_lookup.get(
                    citation_url, {"title": citation_title, "url": citation_url}
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
            final_report="\n".join(final_report_parts).strip(),
            citations=citations,
            reasoning_steps=reasoning_steps,
            search_queries=search_queries,
            total_steps=len(steps),
        )

    @staticmethod
    def _api_revision_headers() -> dict[str, str]:
        """Request the current Interactions API steps schema explicitly."""
        return {"Api-Revision": GEMINI_API_REVISION}

    @staticmethod
    def _get_interaction_steps(interaction) -> list[Any]:
        """Return Gemini Interaction steps from the current SDK schema."""
        steps = getattr(interaction, "steps", None)
        if steps:
            return list(steps)
        return []

    @staticmethod
    def _extract_step_text(step) -> str:
        """Extract text from a current-schema model output step."""
        if getattr(step, "type", None) != "model_output":
            return ""

        text_parts: list[str] = []
        for content in getattr(step, "content", None) or []:
            content_text = getattr(content, "text", None)
            if content_text:
                text_parts.append(content_text)
        return "\n".join(text_parts).strip()

    @staticmethod
    def _extract_step_annotations(step) -> list[Any]:
        """Extract citation annotations from a current-schema model output step."""
        annotations: list[Any] = []
        for content in getattr(step, "content", None) or []:
            content_annotations = getattr(content, "annotations", None)
            if content_annotations:
                annotations.extend(content_annotations)
        return annotations
