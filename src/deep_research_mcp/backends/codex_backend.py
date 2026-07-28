# -*- coding: utf-8 -*-

"""ChatGPT subscription research through the OpenAI Codex backend."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
import json
import logging
import re
import time
from typing import Any
import uuid

import httpx

from deep_research_mcp.codex_auth import (
    CodexAuthError,
    CodexAuthManager,
    CodexTokens,
)
from deep_research_mcp.config import OPENAI_CODEX_BASE_URL, ResearchConfig
from deep_research_mcp.errors import ConfigurationError, ResearchError
from deep_research_mcp.results import (
    ResearchCitation,
    ResearchResult,
    ResearchTaskStatus,
)

from .base import ResearchBackend, TaskStartedCallback

CODEX_RESEARCH_INSTRUCTIONS = """
You are a deep research assistant. Investigate the user's question with web
search, triangulate important claims across reliable sources, distinguish facts
from inference, and produce a structured report with inline source links.
""".strip()

MARKDOWN_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
URL_PATTERN = re.compile(r"https?://[^\s<>()\]]+")

# Version of the official Codex client protocol this backend implements.
CODEX_PROTOCOL_VERSION = "0.145.0"

try:
    PACKAGE_VERSION = version("deep-research-mcp")
except PackageNotFoundError:
    PACKAGE_VERSION = "unknown"


class CodexBackendError(ResearchError):
    """The Codex backend returned an unusable response."""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


@dataclass(slots=True)
class CodexStreamState:
    """Incrementally assembled Responses API stream state."""

    task_id: str | None = None
    text_parts: list[str] = field(default_factory=list)
    fallback_text: str = ""
    citations: list[ResearchCitation] = field(default_factory=list)
    citation_urls: set[str] = field(default_factory=set)
    search_queries: list[str] = field(default_factory=list)
    search_query_set: set[str] = field(default_factory=set)
    reasoning_item_ids: set[str] = field(default_factory=set)
    total_steps: int = 0
    terminal_status: str | None = None
    failure_message: str | None = None


class CodexResearchBackend(ResearchBackend):
    """Run one-shot research against ChatGPT's Codex Responses stream."""

    def __init__(
        self,
        config: ResearchConfig,
        logger: logging.Logger,
        *,
        auth_manager: CodexAuthManager | None = None,
        base_url: str | None = None,
    ) -> None:
        super().__init__(config, logger)
        configured_url = (config.base_url or OPENAI_CODEX_BASE_URL).rstrip("/")
        if base_url is None and configured_url != OPENAI_CODEX_BASE_URL:
            raise ConfigurationError(
                "The openai-codex provider only supports " f"{OPENAI_CODEX_BASE_URL}"
            )
        self.base_url = (base_url or configured_url).rstrip("/")
        self.auth_manager = auth_manager or CodexAuthManager()
        self.logger.warning(
            "The openai-codex provider uses an undocumented ChatGPT Codex "
            "endpoint and may change without notice"
        )

    async def research(
        self,
        query: str,
        system_prompt: str | None = None,
        include_code_interpreter: bool = True,
        on_task_started: TaskStartedCallback | None = None,
    ) -> ResearchResult:
        """Run synchronous streaming research with native web search."""
        del on_task_started
        start_time = time.time()
        timeout = httpx.Timeout(
            timeout=self.config.timeout,
            connect=min(30.0, self.config.timeout),
        )

        try:
            async with asyncio.timeout(self.config.timeout):
                async with httpx.AsyncClient(timeout=timeout) as client:
                    tokens = await self.auth_manager.get_valid_tokens()
                    model, tokens = await self._resolve_model(client, tokens)
                    request_body = self._build_request(
                        model=model,
                        query=query,
                        system_prompt=system_prompt,
                    )
                    state = await self._stream_response(client, tokens, request_body)
            return self._build_result(
                state,
                include_code_interpreter=include_code_interpreter,
                execution_time=time.time() - start_time,
            )
        except TimeoutError:
            return ResearchResult.failed(
                message=(
                    "OpenAI Codex research timed out; streamed tasks cannot be "
                    "recovered with research_status"
                ),
                error_code="timeout",
                execution_time=time.time() - start_time,
            )
        except (CodexAuthError, CodexBackendError, httpx.HTTPError) as error:
            self.logger.error(f"OpenAI Codex research failed: {error}")
            return ResearchResult.failed(
                message=str(error),
                error_code=getattr(error, "code", None),
                execution_time=time.time() - start_time,
            )

    async def get_task_status(self, task_id: str) -> ResearchTaskStatus:
        """Explain that direct Codex streams do not support recovery."""
        return ResearchTaskStatus.unknown(
            task_id=task_id,
            message=(
                "Task status and completed-report recovery are not available "
                "for the openai-codex provider"
            ),
        )

    async def get_task_result(self, task_id: str) -> ResearchResult | None:
        """Direct Codex streams are not persisted for later retrieval."""
        del task_id
        return None

    async def _resolve_model(
        self, client: httpx.AsyncClient, tokens: CodexTokens
    ) -> tuple[str, CodexTokens]:
        models_data, current_tokens = await self._get_models(client, tokens)
        models = models_data.get("models")
        if not isinstance(models, list) or not models:
            raise CodexBackendError(
                "OpenAI Codex returned no models for this ChatGPT account",
                code="models_unavailable",
            )

        available = [
            model
            for model in models
            if isinstance(model, dict)
            and isinstance(model.get("slug"), str)
            and model["slug"]
        ]
        if not available:
            raise CodexBackendError(
                "OpenAI Codex returned an invalid model catalogue",
                code="invalid_models",
            )

        if self.config.model != "auto":
            for model in available:
                if model["slug"] == self.config.model:
                    return str(model["slug"]), current_tokens
            model_names = ", ".join(str(model["slug"]) for model in available)
            raise CodexBackendError(
                f"Model '{self.config.model}' is not available for this "
                f"ChatGPT account. Available models: {model_names}",
                code="model_not_available",
            )

        for model in available:
            if model.get("visibility") == "list" or model.get("show_in_picker") is True:
                return str(model["slug"]), current_tokens
        return str(available[0]["slug"]), current_tokens

    async def _get_models(
        self, client: httpx.AsyncClient, tokens: CodexTokens
    ) -> tuple[dict[str, Any], CodexTokens]:
        current = tokens
        refreshed = False
        while True:
            response = await client.get(
                f"{self.base_url}/models",
                params={"client_version": CODEX_PROTOCOL_VERSION},
                headers=self._headers(current, accept="application/json"),
            )
            if response.status_code == 401 and not refreshed:
                current = await self.auth_manager.get_valid_tokens(force_refresh=True)
                refreshed = True
                continue
            self._raise_http_error(response, "retrieve the Codex model catalogue")
            try:
                data = response.json()
            except json.JSONDecodeError as error:
                raise CodexBackendError(
                    "OpenAI Codex returned an invalid model catalogue",
                    code="invalid_models",
                ) from error
            if not isinstance(data, dict):
                raise CodexBackendError(
                    "OpenAI Codex returned an invalid model catalogue",
                    code="invalid_models",
                )
            return data, current

    def _build_request(
        self,
        *,
        model: str,
        query: str,
        system_prompt: str | None,
    ) -> dict[str, Any]:
        instructions = CODEX_RESEARCH_INSTRUCTIONS
        if system_prompt:
            instructions = f"{instructions}\n\n{system_prompt}"

        request: dict[str, Any] = {
            "model": model,
            "instructions": instructions,
            "input": [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": query}],
                }
            ],
            "tools": [{"type": "web_search"}],
            "tool_choice": "auto",
            "parallel_tool_calls": True,
            "store": False,
            "stream": True,
        }
        if self.config.enable_reasoning_summaries:
            request["reasoning"] = {"summary": "auto"}
        return request

    async def _stream_response(
        self,
        client: httpx.AsyncClient,
        tokens: CodexTokens,
        request_body: dict[str, Any],
    ) -> CodexStreamState:
        current = tokens
        refreshed = False
        while True:
            async with client.stream(
                "POST",
                f"{self.base_url}/responses",
                headers=self._headers(current),
                json=request_body,
            ) as response:
                if response.status_code == 401 and not refreshed:
                    await response.aread()
                    current = await self.auth_manager.get_valid_tokens(
                        force_refresh=True
                    )
                    refreshed = True
                    continue
                if response.is_error:
                    await response.aread()
                    self._raise_http_error(response, "start Codex research")
                return await self._consume_sse(response)

    async def _consume_sse(self, response: httpx.Response) -> CodexStreamState:
        state = CodexStreamState()
        async for data in _iter_sse_data(response):
            if data == "[DONE]":
                break
            try:
                event = json.loads(data)
            except json.JSONDecodeError as error:
                raise CodexBackendError(
                    "OpenAI Codex returned malformed streaming data",
                    code="invalid_stream",
                ) from error
            if not isinstance(event, dict):
                continue
            self._apply_stream_event(state, event)

        if state.terminal_status is None:
            raise CodexBackendError(
                "OpenAI Codex stream ended before a terminal response",
                code="truncated_stream",
            )
        if state.terminal_status != "completed":
            raise CodexBackendError(
                state.failure_message
                or f"OpenAI Codex research ended with status {state.terminal_status}",
                code=f"response_{state.terminal_status}",
            )
        return state

    def _apply_stream_event(
        self, state: CodexStreamState, event: dict[str, Any]
    ) -> None:
        event_type = str(event.get("type") or "")
        response_data = event.get("response")
        if isinstance(response_data, dict):
            if response_data.get("id"):
                state.task_id = str(response_data["id"])
            output = response_data.get("output")
            if isinstance(output, list):
                for item in output:
                    if isinstance(item, dict):
                        self._record_output_item(state, item, count_step=False)

        if event_type == "response.output_text.delta":
            delta = event.get("delta")
            if isinstance(delta, str):
                state.text_parts.append(delta)
        elif event_type == "response.output_text.done":
            text = event.get("text")
            if isinstance(text, str) and text:
                state.fallback_text = text
        elif event_type == "response.output_text.annotation.added":
            annotation = event.get("annotation")
            if isinstance(annotation, dict):
                self._record_annotation(state, annotation)
        elif event_type == "response.output_item.done":
            item = event.get("item")
            if isinstance(item, dict):
                self._record_output_item(state, item, count_step=True)
        elif "web_search_call" in event_type:
            self._record_search_action(state, event.get("action"))
        elif event_type == "response.completed":
            state.terminal_status = "completed"
        elif event_type == "response.incomplete":
            state.terminal_status = "incomplete"
            state.failure_message = _response_failure_message(response_data)
        elif event_type == "response.failed":
            state.terminal_status = "failed"
            state.failure_message = _response_failure_message(response_data)
        elif event_type == "error":
            state.terminal_status = "failed"
            state.failure_message = _event_error_message(event)

    def _record_output_item(
        self,
        state: CodexStreamState,
        item: dict[str, Any],
        *,
        count_step: bool,
    ) -> None:
        if count_step:
            state.total_steps += 1
        item_type = str(item.get("type") or "")
        item_id = str(item.get("id") or f"{item_type}:{state.total_steps}")
        if item_type == "reasoning":
            state.reasoning_item_ids.add(item_id)
        if item_type == "web_search_call":
            self._record_search_action(state, item.get("action"))
        if item_type == "message":
            content = item.get("content")
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    text = block.get("text")
                    if isinstance(text, str) and text:
                        state.fallback_text = text
                    annotations = block.get("annotations")
                    if isinstance(annotations, list):
                        for annotation in annotations:
                            if isinstance(annotation, dict):
                                self._record_annotation(state, annotation)

    def _record_search_action(self, state: CodexStreamState, action: Any) -> None:
        if not isinstance(action, dict):
            return
        query = action.get("query")
        if (
            action.get("type") == "search"
            and isinstance(query, str)
            and query
            and query not in state.search_query_set
        ):
            state.search_query_set.add(query)
            state.search_queries.append(query)

    def _record_annotation(
        self, state: CodexStreamState, annotation: dict[str, Any]
    ) -> None:
        citation = annotation.get("url_citation")
        if isinstance(citation, dict):
            annotation = citation
        url = annotation.get("url")
        if not isinstance(url, str) or not url or url in state.citation_urls:
            return
        state.citation_urls.add(url)
        title = annotation.get("title")
        state.citations.append(
            ResearchCitation(
                index=len(state.citations) + 1,
                title=str(title) if title else f"Source {len(state.citations) + 1}",
                url=url,
            )
        )

    def _build_result(
        self,
        state: CodexStreamState,
        *,
        include_code_interpreter: bool,
        execution_time: float,
    ) -> ResearchResult:
        final_report = "".join(state.text_parts).strip() or state.fallback_text.strip()
        if not final_report:
            raise CodexBackendError(
                "OpenAI Codex completed without report text",
                code="empty_response",
            )

        citations = state.citations or _extract_text_citations(final_report)
        provider_note = (
            "Code Interpreter is not available for openai-codex; "
            "research completed with web search only."
            if include_code_interpreter
            else None
        )
        return ResearchResult.completed(
            task_id=state.task_id or f"codex-{uuid.uuid4()}",
            final_report=final_report,
            citations=citations,
            reasoning_steps=len(state.reasoning_item_ids),
            search_queries=state.search_queries,
            total_steps=state.total_steps,
            message=provider_note,
            execution_time=execution_time,
        )

    @staticmethod
    def _headers(
        tokens: CodexTokens, *, accept: str = "text/event-stream"
    ) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {tokens.access_token}",
            "ChatGPT-Account-ID": tokens.account_id,
            "originator": "deep_research_mcp",
            "User-Agent": f"deep-research-mcp/{PACKAGE_VERSION}",
            "Accept": accept,
        }

    @staticmethod
    def _raise_http_error(response: httpx.Response, action: str) -> None:
        if not response.is_error:
            return
        detail = _http_error_detail(response)
        suffix = f": {detail}" if detail else ""
        if response.status_code == 403:
            raise CodexBackendError(
                "OpenAI Codex denied this third-party client. The private "
                f"endpoint may not accept its originator{suffix}",
                code="access_denied",
            )
        if response.status_code == 429:
            raise CodexBackendError(
                f"OpenAI Codex rate or subscription limit reached{suffix}",
                code="rate_limited",
            )
        if response.status_code == 401:
            raise CodexBackendError(
                f"OpenAI Codex authentication failed{suffix}",
                code="authentication_failed",
            )
        raise CodexBackendError(
            f"Could not {action}{suffix} (HTTP {response.status_code})",
            code=f"http_{response.status_code}",
        )


async def _iter_sse_data(response: httpx.Response):
    data_lines: list[str] = []
    async for line in response.aiter_lines():
        if not line:
            if data_lines:
                yield "\n".join(data_lines)
                data_lines = []
            continue
        if line.startswith(":"):
            continue
        if line.startswith("data:"):
            value = line[5:]
            if value.startswith(" "):
                value = value[1:]
            data_lines.append(value)
    if data_lines:
        yield "\n".join(data_lines)


def _response_failure_message(response_data: Any) -> str | None:
    if not isinstance(response_data, dict):
        return None
    error = response_data.get("error")
    if isinstance(error, dict):
        message = error.get("message") or error.get("code")
        return str(message) if message else None
    incomplete = response_data.get("incomplete_details")
    if isinstance(incomplete, dict) and incomplete.get("reason"):
        return f"OpenAI Codex response was incomplete: {incomplete['reason']}"
    return str(error) if error else None


def _event_error_message(event: dict[str, Any]) -> str:
    error = event.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or error.get("code") or "Codex stream error")
    return str(event.get("message") or error or "Codex stream error")


def _http_error_detail(response: httpx.Response) -> str:
    try:
        data = response.json()
    except json.JSONDecodeError:
        return response.text.strip()[:300]
    if not isinstance(data, dict):
        return ""
    error = data.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or error.get("code") or "")
    return str(error or data.get("message") or "")


def _extract_text_citations(text: str) -> list[ResearchCitation]:
    citations: list[ResearchCitation] = []
    seen_urls: set[str] = set()
    for title, url in MARKDOWN_LINK_PATTERN.findall(text):
        if url not in seen_urls:
            seen_urls.add(url)
            citations.append(
                ResearchCitation(
                    index=len(citations) + 1,
                    title=title,
                    url=url,
                )
            )
    for match in URL_PATTERN.findall(text):
        url = match.rstrip(".,;:")
        if url not in seen_urls:
            seen_urls.add(url)
            citations.append(
                ResearchCitation(
                    index=len(citations) + 1,
                    title=f"Source {len(citations) + 1}",
                    url=url,
                )
            )
    return citations
