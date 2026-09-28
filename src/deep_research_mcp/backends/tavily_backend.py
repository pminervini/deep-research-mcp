# -*- coding: utf-8 -*-

"""Tavily Research provider backend."""

import asyncio
import time
from typing import Any

import httpx

from deep_research_mcp.errors import ResearchError, TaskTimeoutError
from deep_research_mcp.results import (
    ResearchCitation,
    ResearchResult,
    ResearchTaskStatus,
)

from .base import ResearchBackend, TaskStartedCallback


class TavilyResearchBackend(ResearchBackend):
    """Run Tavily Research tasks and recover their reports by ID."""

    async def research(
        self,
        query: str,
        system_prompt: str | None = None,
        include_code_interpreter: bool = True,
        on_task_started: TaskStartedCallback | None = None,
    ) -> ResearchResult:
        """Create a research task and poll until it finishes."""
        del include_code_interpreter
        task_id: str | None = None

        try:
            task = await self._request(
                "POST",
                "/research",
                json={
                    "input": self._combine_system_prompt(query, system_prompt),
                    "model": self.config.model,
                    "stream": False,
                },
            )
            task_id = task.get("request_id")
            if not task_id:
                raise ResearchError("Tavily did not return a research task ID")
            self.logger.info(f"Research task started: {task_id}")
            if on_task_started:
                await on_task_started(task_id)

            deadline = time.monotonic() + self.config.timeout
            while time.monotonic() < deadline:
                task = await self._get_task(task_id)
                if task.get("status") == "completed":
                    return self._extract_result(task)
                if task.get("status") == "failed":
                    return ResearchResult.failed(
                        task_id=task_id,
                        message=self._failure_message(task),
                    )
                await asyncio.sleep(self.config.poll_interval)

            raise TaskTimeoutError(
                f"Tavily task {task_id} did not complete within "
                f"{self.config.timeout} seconds. The task may still be running; "
                f"use research_status with task ID {task_id} to retrieve the result later"
            )
        except (ResearchError, httpx.HTTPError) as error:
            return ResearchResult.failed(message=str(error), task_id=task_id)

    async def get_task_status(self, task_id: str) -> ResearchTaskStatus:
        """Return the current Tavily Research task status."""
        try:
            task = await self._get_task(task_id)
            return ResearchTaskStatus(
                task_id=task_id,
                status=task.get("status", "unknown"),
                created_at=task.get("created_at"),
                completed_at=task.get("completed_at"),
                message=(
                    self._failure_message(task)
                    if task.get("status") == "failed"
                    else None
                ),
            )
        except (ResearchError, httpx.HTTPError) as error:
            return ResearchTaskStatus.error_status(task_id=task_id, error=str(error))

    async def get_task_result(self, task_id: str) -> ResearchResult | None:
        """Recover the full report for a completed Tavily task."""
        task = await self._get_task(task_id)
        if task.get("status") != "completed":
            return None
        return self._extract_result(task)

    async def _get_task(self, task_id: str) -> dict[str, Any]:
        """Fetch one Tavily Research task."""
        return await self._request("GET", f"/research/{task_id}")

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        """Send a Tavily API request and return its JSON body."""
        base_url = (self.config.base_url or "https://api.tavily.com").rstrip("/")
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.request(
                method,
                f"{base_url}{path}",
                headers={"Authorization": f"Bearer {self.config.api_key}"},
                **kwargs,
            )
            response.raise_for_status()
            return response.json()

    @staticmethod
    def _failure_message(task: dict[str, Any]) -> str:
        """Extract the failure reason returned by Tavily."""
        detail = task.get("detail") or task.get("error") or task.get("message")
        if isinstance(detail, dict):
            detail = detail.get("error") or detail.get("message")
        return str(detail or "Tavily research task failed")

    @staticmethod
    def _extract_result(task: dict[str, Any]) -> ResearchResult:
        """Normalize a completed Tavily report and its sources."""
        citations: list[ResearchCitation] = []
        seen_urls: set[str] = set()
        for source in task.get("sources") or []:
            url = source.get("url")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            citations.append(
                ResearchCitation(
                    index=len(citations) + 1,
                    title=source.get("title") or url,
                    url=url,
                )
            )

        return ResearchResult.completed(
            task_id=task["request_id"],
            final_report=task.get("content") or "",
            citations=citations,
            execution_time=task.get("response_time"),
        )
