# -*- coding: utf-8 -*-

"""
Structured result models for research and task status operations.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ResearchCitation:
    """Normalized citation metadata used across provider integrations."""

    index: int
    title: str
    url: str


@dataclass(slots=True)
class ResearchResult:
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


@dataclass(slots=True)
class ResearchTaskStatus:
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
