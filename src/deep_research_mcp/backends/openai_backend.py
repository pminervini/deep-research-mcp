# -*- coding: utf-8 -*-

"""
OpenAI provider backend.
"""

import asyncio
import re
import time
import uuid
from typing import Any

import httpx
from openai import AuthenticationError, OpenAI
from openai.types.chat import ChatCompletionMessageParam
from tenacity import (
    retry,
    retry_if_not_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from deep_research_mcp.async_utils import run_blocking
from deep_research_mcp.clarification import MISSING_OPENAI_API_KEY_PLACEHOLDER
from deep_research_mcp.config import ResearchConfig
from deep_research_mcp.errors import ResearchError, TaskTimeoutError
from deep_research_mcp.results import (
    ResearchCitation,
    ResearchResult,
    ResearchTaskStatus,
)

from .base import ResearchBackend


class OpenAIResearchBackend(ResearchBackend):
    """OpenAI-backed deep research implementation."""

    def __init__(self, config: ResearchConfig, logger):
        super().__init__(config, logger)
        client_kwargs: dict[str, Any] = {}
        client_kwargs["api_key"] = config.api_key or MISSING_OPENAI_API_KEY_PLACEHOLDER
        if config.base_url:
            client_kwargs["base_url"] = config.base_url
        self.client = OpenAI(**client_kwargs)

    async def research(
        self,
        query: str,
        system_prompt: str | None = None,
        include_code_interpreter: bool = True,
    ) -> ResearchResult:
        """Run research via the OpenAI provider."""
        if self.config.api_style == "chat_completions":
            return await self._run_chat_completions_research(
                query, system_prompt, include_code_interpreter
            )

        try:
            response = await self._create_research_task(
                self._build_input_messages(query, system_prompt),
                self._build_tools(include_code_interpreter),
            )
            final_response = await self._wait_for_completion(response.id)
            return self._extract_openai_results(final_response)
        except ResearchError as error:
            return ResearchResult.failed(message=str(error))

    async def get_task_status(self, task_id: str) -> ResearchTaskStatus:
        """Return task status for the OpenAI provider."""
        if self.config.api_style == "chat_completions":
            return ResearchTaskStatus.unknown(
                task_id=task_id,
                message="Task status tracking not available with Chat Completions API",
            )

        try:
            response = await run_blocking(self.client.responses.retrieve, task_id)
            return ResearchTaskStatus(
                task_id=task_id,
                status=response.status or "unknown",
                created_at=getattr(response, "created_at", None),
                completed_at=getattr(response, "completed_at", None),
            )
        except Exception as error:
            self.logger.error(f"Error checking status for task {task_id}: {error}")
            return ResearchTaskStatus.error_status(task_id=task_id, error=str(error))

    def _build_input_messages(
        self, query: str, system_prompt: str | None
    ) -> list[dict[str, Any]]:
        """Build Responses API input messages."""
        input_messages: list[dict[str, Any]] = []
        if system_prompt:
            input_messages.append(
                {
                    "role": "developer",
                    "content": [{"type": "input_text", "text": system_prompt}],
                }
            )

        input_messages.append(
            {
                "role": "user",
                "content": [{"type": "input_text", "text": query}],
            }
        )
        return input_messages

    def _build_tools(self, include_code_interpreter: bool) -> list[dict[str, Any]]:
        """Build Responses API tool configuration."""
        tools: list[dict[str, Any]] = [{"type": "web_search_preview"}]
        if include_code_interpreter:
            tools.append(
                {
                    "type": "code_interpreter",
                    "container": {"type": "auto", "file_ids": []},
                }
            )
        return tools

    async def _run_chat_completions_research(
        self,
        query: str,
        system_prompt: str | None = None,
        include_code_interpreter: bool = True,
    ) -> ResearchResult:
        """Run research using the Chat Completions API."""
        if include_code_interpreter:
            self.logger.debug(
                "code_interpreter is not available with Chat Completions API; ignoring"
            )

        messages: list[ChatCompletionMessageParam] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": query})

        start_time = time.time()

        try:
            client = OpenAI(
                api_key=self.client.api_key,
                base_url=str(self.client.base_url),
                timeout=httpx.Timeout(self.config.timeout, connect=10.0),
            )
            response = await run_blocking(
                self._create_chat_completions_request, client, messages
            )
            return self._extract_chat_completions_results(
                response, time.time() - start_time
            )
        except Exception as error:
            self.logger.error(f"Chat Completions research error: {error}")
            return ResearchResult.failed(
                message=str(error),
                task_id=str(uuid.uuid4()),
                execution_time=time.time() - start_time,
            )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_not_exception_type(AuthenticationError),
        reraise=True,
    )
    def _create_chat_completions_request(
        self, client: OpenAI, messages: list[ChatCompletionMessageParam]
    ):
        """Retry-wrapped Chat Completions API call."""
        return client.chat.completions.create(
            model=self.config.model, messages=messages
        )

    def _extract_chat_completions_results(
        self, response, elapsed_time: float
    ) -> ResearchResult:
        """Parse Chat Completions responses into the shared result model."""
        content = response.choices[0].message.content if response.choices else ""
        citations = self._extract_chat_completions_citations(response, content)

        return ResearchResult.completed(
            task_id=response.id,
            final_report=content,
            citations=citations,
            total_steps=1,
            execution_time=elapsed_time,
        )

    def _extract_chat_completions_citations(
        self, response, text: str
    ) -> list[ResearchCitation]:
        """Extract citations from a Chat Completions response."""
        citations: list[ResearchCitation] = []
        seen_urls: set[str] = set()

        provider_citations = getattr(response, "citations", None)
        if provider_citations and isinstance(provider_citations, list):
            for url in provider_citations:
                if isinstance(url, str) and url not in seen_urls:
                    seen_urls.add(url)
                    citations.append(
                        ResearchCitation(
                            index=len(citations) + 1,
                            title=f"Source {len(citations) + 1}",
                            url=url,
                        )
                    )

        message = response.choices[0].message if response.choices else None
        if message:
            annotations = getattr(message, "annotations", None)
            if annotations:
                for annotation in annotations:
                    url = getattr(annotation, "url", None)
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        citations.append(
                            ResearchCitation(
                                index=len(citations) + 1,
                                title=getattr(
                                    annotation, "title", f"Source {len(citations) + 1}"
                                ),
                                url=url,
                            )
                        )

        if not citations and text:
            urls = re.findall(r"https?://[^\s\)\]\}>\"']+", text)
            for url in urls:
                normalized_url = url.rstrip(".,;:")
                if normalized_url not in seen_urls:
                    seen_urls.add(normalized_url)
                    citations.append(
                        ResearchCitation(
                            index=len(citations) + 1,
                            title=f"Source {len(citations) + 1}",
                            url=normalized_url,
                        )
                    )

        return citations

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_not_exception_type(AuthenticationError),
        reraise=True,
    )
    async def _create_research_task(
        self, input_messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ):
        """Create a background Responses API research task."""
        response = await run_blocking(
            self.client.responses.create,
            model=self.config.model,
            input=input_messages,
            tools=tools,
            reasoning={"summary": "auto"},
            background=True,
        )
        self.logger.info(f"Research task started: {response.id}")
        return response

    async def _wait_for_completion(self, task_id: str):
        """Poll for an OpenAI Responses task to complete."""
        start_time = time.time()

        while time.time() - start_time < self.config.timeout:
            try:
                response = await run_blocking(self.client.responses.retrieve, task_id)

                if response.status == "completed":
                    self.logger.info(f"Research completed: {task_id}")
                    return response
                if response.status == "failed":
                    error_details = getattr(response, "error", None)
                    if error_details:
                        if hasattr(error_details, "get"):
                            error_message = (
                                "Research task failed: "
                                f"{error_details.get('message', 'Unknown error')}"
                            )
                            if error_details.get("code"):
                                error_message += f" (Code: {error_details['code']})"
                        else:
                            error_message = f"Research task failed: {error_details}"
                    else:
                        error_message = f"Research task failed: {task_id}"
                    raise ResearchError(error_message)

                self.logger.debug(f"Task {task_id} status: {response.status}")
                await asyncio.sleep(self.config.poll_interval)

            except ResearchError:
                raise
            except Exception as error:
                self.logger.error(f"Error polling task {task_id}: {error}")
                await asyncio.sleep(5)

        self.logger.warning(f"Task {task_id} timed out, attempting cancellation")
        try:
            await run_blocking(self.client.responses.cancel, task_id)
        except Exception:
            pass

        raise TaskTimeoutError(
            f"Research task {task_id} did not complete within "
            f"{self.config.timeout} seconds"
        )

    def _extract_openai_results(self, response) -> ResearchResult:
        """Extract and normalize OpenAI Responses API output."""
        if response.status == "failed":
            error_details = getattr(response, "error", None)
            if error_details:
                if hasattr(error_details, "get"):
                    return ResearchResult.failed(
                        message=error_details.get("message", "Unknown error"),
                        task_id=response.id,
                        error_code=error_details.get("code"),
                    )
                return ResearchResult.failed(
                    message=str(error_details), task_id=response.id
                )
            return ResearchResult.failed(
                message=f"Task failed: {response.id}", task_id=response.id
            )

        if not response.output:
            return ResearchResult.error(
                message="No output received", task_id=response.id
            )

        final_output = response.output[-1]
        final_report = final_output.content[0].text if final_output.content else ""

        citations: list[ResearchCitation] = []
        if final_output.content and final_output.content[0].annotations:
            for index, annotation in enumerate(final_output.content[0].annotations):
                if annotation.type == "url_citation":
                    citations.append(
                        ResearchCitation(
                            index=index + 1,
                            title=annotation.title,
                            url=annotation.url,
                        )
                    )
                elif annotation.type == "file_citation":
                    citations.append(
                        ResearchCitation(
                            index=index + 1,
                            title=f"File: {annotation.filename}",
                            url=f"file://{annotation.file_id}/{annotation.filename}",
                        )
                    )
                elif annotation.type == "container_file_citation":
                    citations.append(
                        ResearchCitation(
                            index=index + 1,
                            title=f"Container File: {annotation.filename}",
                            url=(
                                "container://"
                                f"{annotation.container_id}/"
                                f"{annotation.file_id}/"
                                f"{annotation.filename}"
                            ),
                        )
                    )
                elif annotation.type == "file_path":
                    citations.append(
                        ResearchCitation(
                            index=index + 1,
                            title=f"File Path: {annotation.file_id}",
                            url=f"file://{annotation.file_id}",
                        )
                    )
                else:
                    self.logger.warning(
                        f"Unknown annotation type '{annotation.type}' "
                        f"at index {index}, skipping"
                    )

        reasoning_steps = [
            item.summary
            for item in response.output
            if item.type == "reasoning" and hasattr(item, "summary")
        ]
        search_queries = [
            getattr(item.action, "query", "")
            for item in response.output
            if item.type == "web_search_call" and hasattr(item, "action")
        ]

        return ResearchResult.completed(
            task_id=response.id,
            final_report=final_report,
            citations=citations,
            reasoning_steps=len(reasoning_steps),
            search_queries=search_queries,
            total_steps=len(response.output),
        )
