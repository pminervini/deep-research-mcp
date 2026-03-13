# -*- coding: utf-8 -*-

"""
Structured result models for research and task status operations.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ResearchCitation:
    """Normalized citation metadata used across provider integrations."""

    index: int
    title: str
    url: str
    start_char: int = 0
    end_char: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize the citation into the legacy dictionary shape."""
        return {
            "index": self.index,
            "title": self.title,
            "url": self.url,
            "start_char": self.start_char,
            "end_char": self.end_char,
        }


@dataclass(slots=True)
class ResearchResult(Mapping[str, Any]):
    """Normalized result for every research execution path."""

    status: str
    task_id: str | None = None
    final_report: str = ""
    citations: list[ResearchCitation] = field(default_factory=list)
    reasoning_steps: int = 0
    search_queries: list[str] = field(default_factory=list)
    total_steps: int = 0
    message: str | None = None
    error_code: str | None = None
    execution_time: float | None = None

    @classmethod
    def completed(
        cls,
        *,
        task_id: str,
        final_report: str,
        citations: list[ResearchCitation] | None = None,
        reasoning_steps: int = 0,
        search_queries: list[str] | None = None,
        total_steps: int = 0,
        execution_time: float | None = None,
    ) -> "ResearchResult":
        """Build a successful research result."""
        return cls(
            status="completed",
            task_id=task_id,
            final_report=final_report,
            citations=citations or [],
            reasoning_steps=reasoning_steps,
            search_queries=search_queries or [],
            total_steps=total_steps,
            execution_time=execution_time,
        )

    @classmethod
    def failed(
        cls,
        *,
        message: str,
        task_id: str | None = None,
        error_code: str | None = None,
        execution_time: float | None = None,
    ) -> "ResearchResult":
        """Build a provider failure result."""
        return cls(
            status="failed",
            task_id=task_id,
            message=message,
            error_code=error_code,
            execution_time=execution_time,
        )

    @classmethod
    def error(
        cls,
        *,
        message: str,
        task_id: str | None = None,
        execution_time: float | None = None,
    ) -> "ResearchResult":
        """Build a non-provider execution error result."""
        return cls(
            status="error",
            task_id=task_id,
            message=message,
            execution_time=execution_time,
        )

    @property
    def is_completed(self) -> bool:
        """Return True when the research finished successfully."""
        return self.status == "completed"

    def to_dict(self) -> dict[str, Any]:
        """Serialize the result into the legacy dictionary shape."""
        return {
            "status": self.status,
            "task_id": self.task_id,
            "final_report": self.final_report,
            "citations": [citation.to_dict() for citation in self.citations],
            "reasoning_steps": self.reasoning_steps,
            "search_queries": self.search_queries,
            "total_steps": self.total_steps,
            "message": self.message,
            "error_code": self.error_code,
            "execution_time": self.execution_time,
        }

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.to_dict())

    def __len__(self) -> int:
        return len(self.to_dict())

    def get(self, key: str, default: Any = None) -> Any:
        """Provide dict-style access during the transition to attribute access."""
        return self.to_dict().get(key, default)


@dataclass(slots=True)
class ResearchTaskStatus(Mapping[str, Any]):
    """Normalized task status response across providers."""

    task_id: str
    status: str
    created_at: Any = None
    completed_at: Any = None
    message: str | None = None
    error: str | None = None

    @classmethod
    def unknown(cls, *, task_id: str, message: str) -> "ResearchTaskStatus":
        """Build a task status for providers that do not support polling."""
        return cls(task_id=task_id, status="unknown", message=message)

    @classmethod
    def error_status(cls, *, task_id: str, error: str) -> "ResearchTaskStatus":
        """Build an error task status response."""
        return cls(task_id=task_id, status="error", error=error)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the task status into the legacy dictionary shape."""
        return {
            "task_id": self.task_id,
            "status": self.status,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "message": self.message,
            "error": self.error,
        }

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.to_dict())

    def __len__(self) -> int:
        return len(self.to_dict())

    def get(self, key: str, default: Any = None) -> Any:
        """Provide dict-style access during the transition to attribute access."""
        return self.to_dict().get(key, default)
