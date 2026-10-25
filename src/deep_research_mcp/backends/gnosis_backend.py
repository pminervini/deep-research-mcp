# -*- coding: utf-8 -*-

"""Gnosis state-space search through openJiuwen's run API and shared output."""

import asyncio
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import quote
import uuid

import httpx

from deep_research_mcp.errors import ResearchError
from deep_research_mcp.results import (
    ResearchCitation,
    ResearchResult,
    ResearchTaskStatus,
)

from .base import ResearchBackend, TaskStartedCallback


class GnosisResearchBackend(ResearchBackend):
    """Submit search runs and recover full answers from the shared output mount."""

    async def research(
        self,
        query: str,
        system_prompt: str | None = None,
        include_code_interpreter: bool = True,
        on_task_started: TaskStartedCallback | None = None,
    ) -> ResearchResult:
        """Run Gnosis search; completion telemetry alone never counts as an answer."""
        del include_code_interpreter
        task_id: str | None = None
        try:
            options = self._load_options()
            task_id = str(uuid.uuid4())
            options.update(
                query=self._combine_system_prompt(query, system_prompt),
                run_id=task_id,
                search_mode="search",
                enable_question_router=False,
            )
            async with asyncio.timeout(self.config.timeout):
                task = await self._request("POST", "/runs", json=options)
                if task.get("run_id") != task_id:
                    raise ResearchError(
                        "Gnosis returned a missing or mismatched run ID"
                    )
                self.logger.info(f"Research task started: {task_id}")
                if on_task_started:
                    await on_task_started(task_id)
                while True:
                    status, result = await self._get_run(task_id)
                    if result is not None:
                        return result
                    if status.status in {"failed", "cancelled"}:
                        return ResearchResult.failed(
                            task_id=task_id,
                            message=status.message or f"Gnosis run {status.status}",
                        )
                    await asyncio.sleep(self.config.poll_interval)
        except TimeoutError:
            disposition = "The run may still be running"
            if self.config.cancel_on_timeout and task_id:
                try:
                    await self._request(
                        "POST", f"/runs/{quote(task_id, safe='')}/cancel"
                    )
                    disposition = "Cancellation was requested"
                except (ResearchError, httpx.HTTPError) as error:
                    disposition = f"Cancellation could not be confirmed: {error}"
            return ResearchResult.failed(
                task_id=task_id,
                error_code="timeout",
                message=(
                    f"Gnosis did not return a full answer within {self.config.timeout} "
                    f"seconds. {disposition}; use research_status with task ID "
                    f"{task_id} to check persisted results"
                ),
            )
        except (ResearchError, httpx.HTTPError, OSError, ValueError) as error:
            return ResearchResult.failed(task_id=task_id, message=str(error))

    def _load_options(self) -> dict[str, Any]:
        """Load native request options without exposing LLM credentials in config output."""
        if not self.config.gnosis_config_path:
            raise ResearchError(
                "Gnosis requires gnosis_config_path (native /runs options JSON)"
            )
        if not self.config.gnosis_output_dir:
            raise ResearchError(
                "Gnosis requires gnosis_output_dir for full-answer recovery"
            )
        if not Path(self.config.gnosis_output_dir).expanduser().is_dir():
            raise ResearchError("Gnosis shared output directory does not exist")
        path = Path(self.config.gnosis_config_path).expanduser()
        try:
            options = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ResearchError(
                "Gnosis request-options file is not valid JSON"
            ) from error
        if not isinstance(options, dict):
            raise ResearchError("Gnosis request options must be a JSON object")
        if any(key in options for key in ("query", "run_id", "conversation_id")):
            raise ResearchError(
                "Gnosis request options must not set query, run_id or conversation_id"
            )
        llm = options.get("llm")
        if not isinstance(llm, dict) or any(
            not isinstance(llm.get(key), str) or not llm[key].strip()
            for key in ("model_name", "base_url", "api_key")
        ):
            raise ResearchError(
                "Gnosis request options require llm.model_name, base_url and api_key"
            )
        return options

    async def get_task_status(self, task_id: str) -> ResearchTaskStatus:
        """Read persisted status; nonterminal telemetry cannot prove a task is alive."""
        try:
            status, _ = await self._get_run(task_id)
            return status
        except (ResearchError, httpx.HTTPError, OSError, ValueError) as error:
            return ResearchTaskStatus.error_status(task_id=task_id, error=str(error))

    async def get_task_result(self, task_id: str) -> ResearchResult | None:
        """Recover a saved answer without resubmitting or loading LLM credentials."""
        _, result = await self._get_run(task_id)
        return result

    async def _get_run(
        self, task_id: str
    ) -> tuple[ResearchTaskStatus, ResearchResult | None]:
        """Read the full run history because telemetry can arrive out of sequence."""
        response = await self._request(
            "GET",
            "/telemetry/range",
            params={"run_id": task_id, "start_seq": 0, "end_seq": 2**63 - 1},
        )
        events = response.get("items")
        if not isinstance(events, list) or any(
            not isinstance(event, dict) for event in events
        ):
            raise ResearchError("Gnosis returned invalid telemetry")
        events = [event for event in events if event.get("run_id") == task_id]
        for event in reversed(events):
            kind = event.get("event")
            payload = event.get("payload") or {}
            if kind in {"run_failed", "run_cancelled"}:
                status = "failed" if kind == "run_failed" else "cancelled"
                return (
                    ResearchTaskStatus(
                        task_id=task_id,
                        status=status,
                        message=str(
                            payload.get("error") or payload.get("reason") or kind
                        ),
                    ),
                    None,
                )
        if any(
            event.get("event") in {"search_final_result", "run_completed"}
            for event in events
        ):
            result = await asyncio.to_thread(self._read_result, task_id, events)
            if result is not None:
                return (
                    ResearchTaskStatus(
                        task_id=task_id, status=result.status, message=result.message
                    ),
                    result,
                )
        return (
            ResearchTaskStatus.unknown(
                task_id=task_id,
                message=(
                    "No full persisted result is available. Telemetry does not confirm "
                    "whether a run is still alive after a server restart."
                    if events
                    else "No telemetry found for this Gnosis run ID"
                ),
            ),
            None,
        )

    def _read_result(
        self, task_id: str, events: list[dict[str, Any]]
    ) -> ResearchResult | None:
        """Locate the algorithm's internal conversation ID, never a caller-supplied path."""
        if not self.config.gnosis_output_dir:
            raise ResearchError(
                "Gnosis requires gnosis_output_dir for full-answer recovery"
            )
        root = Path(self.config.gnosis_output_dir).expanduser().resolve()
        for event in events:
            if event.get("event") != "run_started":
                continue
            conversation_id = (event.get("payload") or {}).get("conversation_id")
            if not isinstance(conversation_id, str) or not re.fullmatch(
                r"[A-Za-z0-9_-]{1,128}", conversation_id, flags=re.ASCII
            ):
                raise ResearchError(
                    "Gnosis returned an invalid internal conversation ID"
                )
            path = (
                root / "logs" / f"result_{conversation_id}" / "final_result.json"
            ).resolve()
            if not path.is_relative_to(root):
                raise ResearchError(
                    "Gnosis result path escapes the shared output directory"
                )
            if not path.is_file():
                continue
            try:
                saved = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                # A server writes this file in place; a later poll can see the completed write.
                continue
            if not isinstance(saved, dict):
                raise ResearchError("Gnosis saved result must be a JSON object")
            return self._extract_result(task_id, saved)
        return None

    @staticmethod
    def _extract_result(task_id: str, saved: dict[str, Any]) -> ResearchResult:
        """Normalize the selected answer, not action previews or guessed candidates."""
        prediction = saved.get("prediction")
        termination = saved.get("termination")
        if (
            termination not in {"answer", "timeout_answer"}
            or not isinstance(prediction, str)
            or not prediction.strip()
        ):
            return ResearchResult.failed(
                task_id=task_id,
                message=f"Gnosis finished without a confirmed answer (termination={termination})",
            )
        citations: list[ResearchCitation] = []
        seen: set[str] = set()
        for title, url in re.findall(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", prediction):
            if url not in seen:
                seen.add(url)
                citations.append(
                    ResearchCitation(index=len(citations) + 1, title=title, url=url)
                )
        return ResearchResult.completed(
            task_id=task_id,
            final_report=prediction,
            citations=citations,
            execution_time=saved.get("completion_time"),
            message=f"Gnosis termination: {termination}",
        )

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        """Call the run service without retrying ambiguous task submissions."""
        base_url = (self.config.base_url or "http://127.0.0.1:8089").rstrip("/")
        headers = (
            {"Authorization": f"Bearer {self.config.api_key}"}
            if self.config.api_key
            else {}
        )
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.request(
                method, f"{base_url}{path}", headers=headers, **kwargs
            )
            response.raise_for_status()
            if response.status_code == 204:
                return {}
            value = response.json()
            if not isinstance(value, dict):
                raise ResearchError("Gnosis returned a non-object JSON response")
            return value
