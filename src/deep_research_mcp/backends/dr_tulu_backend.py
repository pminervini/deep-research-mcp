# -*- coding: utf-8 -*-

"""
Dr Tulu provider backend.
"""

import time
import uuid

import httpx

from deep_research_mcp.results import (
    ResearchCitation,
    ResearchResult,
    ResearchTaskStatus,
)

from .base import ResearchBackend


class DrTuluResearchBackend(ResearchBackend):
    """Dr Tulu-backed deep research implementation."""

    async def research(
        self,
        query: str,
        system_prompt: str | None = None,
        include_code_interpreter: bool = True,
    ) -> ResearchResult:
        """Run research via the Dr Tulu /chat endpoint."""
        del include_code_interpreter

        task_id = str(uuid.uuid4())
        start_time = time.time()
        payload = {"content": self._combine_system_prompt(query, system_prompt)}
        base_url = (self.config.base_url or "http://10.8.0.42/").rstrip("/")
        endpoint = f"{base_url}/chat"

        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.post(endpoint, json=payload)
                response.raise_for_status()
                data = response.json()

            metadata = data.get("metadata", {}) if isinstance(data, dict) else {}
            searched_links = metadata.get("searched_links", []) or []

            return ResearchResult.completed(
                task_id=task_id,
                final_report=str(data.get("response", "")),
                citations=self._build_citations(searched_links),
                total_steps=int(metadata.get("total_tool_calls", 0) or 0),
                execution_time=time.time() - start_time,
            )
        except Exception as error:
            self.logger.error(f"Dr Tulu research error: {error}")
            return ResearchResult.failed(
                message=str(error),
                task_id=task_id,
                execution_time=time.time() - start_time,
            )

    async def get_task_status(self, task_id: str) -> ResearchTaskStatus:
        """Return task status for the Dr Tulu provider."""
        return ResearchTaskStatus.unknown(
            task_id=task_id,
            message="Task status tracking not available for dr-tulu provider",
        )

    @staticmethod
    def _build_citations(urls: list[str]) -> list[ResearchCitation]:
        """Normalize Dr Tulu searched links into citations."""
        citations: list[ResearchCitation] = []
        seen_urls: set[str] = set()

        for url in urls:
            if not isinstance(url, str) or not url or url in seen_urls:
                continue
            seen_urls.add(url)
            citations.append(
                ResearchCitation(
                    index=len(citations) + 1,
                    title=f"Source {len(citations) + 1}",
                    url=url,
                )
            )

        return citations
