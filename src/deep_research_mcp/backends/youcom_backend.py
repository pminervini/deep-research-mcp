# -*- coding: utf-8 -*-

"""
You.com Research API provider backend.
"""

import json
import re
import time
import uuid

import httpx

from deep_research_mcp.config import ResearchConfig
from deep_research_mcp.errors import ResearchError
from deep_research_mcp.results import ResearchCitation, ResearchResult, ResearchTaskStatus

from .base import ResearchBackend, TaskStartedCallback


class YoucomResearchBackend(ResearchBackend):
    """You.com Research API-backed deep research implementation."""

    def __init__(self, config: ResearchConfig, logger):
        super().__init__(config, logger)
        if not config.api_key:
            raise ResearchError("YDC_API_KEY environment variable is required for You.com Research API")
        
        self.base_url = config.base_url or "https://api.you.com"
        self.api_key = config.api_key
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(config.timeout, connect=10.0),
            headers={
                "X-API-Key": self.api_key,
                "Content-Type": "application/json",
            }
        )

    async def research(
        self,
        query: str,
        system_prompt: str | None = None,
        include_code_interpreter: bool = True,
        on_task_started: TaskStartedCallback | None = None,
    ) -> ResearchResult:
        """Run research via the You.com Research API."""
        try:
            # Generate a task ID for tracking
            task_id = f"youcom-{uuid.uuid4().hex[:16]}"
            
            if on_task_started:
                await on_task_started(task_id)

            # Combine system prompt with query if provided
            combined_input = self._combine_system_prompt(query, system_prompt)
            
            # Determine research effort based on config
            effort_level = self._get_effort_level()
            
            start_time = time.time()
            
            # Call You.com Research API
            payload = {
                "input": combined_input,
                "research_effort": effort_level,
            }
            
            self.logger.info(f"Starting You.com research with effort level: {effort_level}")
            
            response = await self.client.post(
                f"{self.base_url}/v1/research",
                json=payload,
            )
            
            if not response.is_success:
                error_text = response.text
                self.logger.error(f"You.com API error {response.status_code}: {error_text}")
                raise ResearchError(f"You.com API error {response.status_code}: {error_text}")
            
            data = response.json()
            execution_time = time.time() - start_time
            
            # Extract research results
            output = data.get("output", {})
            content = output.get("content", "")
            sources = output.get("sources", [])
            
            # Parse citations from content and sources
            citations = self._parse_citations(content, sources)
            
            self.logger.info(f"You.com research completed in {execution_time:.2f}s with {len(citations)} citations")
            
            return ResearchResult.completed(
                task_id=task_id,
                final_report=content,
                citations=citations,
                execution_time=execution_time,
            )
            
        except ResearchError:
            raise
        except Exception as error:
            self.logger.error(f"Unexpected error in You.com research: {error}")
            return ResearchResult.failed(message=str(error))
        finally:
            await self.client.aclose()

    async def get_task_status(self, task_id: str) -> ResearchTaskStatus:
        """Return task status for the You.com provider."""
        # You.com Research API is synchronous, so tasks are either completed immediately
        # or failed. We don't have intermediate status tracking.
        if task_id.startswith("youcom-"):
            return ResearchTaskStatus(
                task_id=task_id,
                status="completed",
                message="You.com Research API executes synchronously",
            )
        else:
            return ResearchTaskStatus.error_status(
                task_id=task_id, 
                error="Invalid You.com task ID format"
            )

    async def get_task_result(self, task_id: str) -> ResearchResult | None:
        """Return the full result of a completed task, or None if unsupported."""
        # You.com Research API is synchronous, so results are returned immediately
        # and not stored for later retrieval
        return None

    def _get_effort_level(self) -> str:
        """Determine research effort level based on config or model name."""
        # Map model name or use default
        model = self.config.model or "standard"
        
        if "lite" in model.lower():
            return "lite"
        elif "deep" in model.lower():
            return "deep"
        elif "exhaustive" in model.lower():
            return "exhaustive"
        else:
            return "standard"

    def _parse_citations(self, content: str, sources: list[dict]) -> list[ResearchCitation]:
        """Parse citations from You.com Research API response."""
        citations = []
        
        # Create a mapping from citation numbers to sources
        citation_pattern = re.compile(r'\[(\d+)\]')
        citation_numbers = set(citation_pattern.findall(content))
        
        for i, source in enumerate(sources):
            # Use 1-based indexing to match citation format
            citation_index = i + 1
            
            # Only include sources that are actually cited in the content
            if str(citation_index) in citation_numbers:
                citations.append(ResearchCitation(
                    index=citation_index,
                    title=source.get("title", f"Source {citation_index}"),
                    url=source.get("url", ""),
                ))
        
        return citations