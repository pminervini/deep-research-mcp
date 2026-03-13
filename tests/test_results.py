# -*- coding: utf-8 -*-

"""
Tests for structured result models.
"""

from deep_research_mcp.results import (
    ResearchCitation,
    ResearchResult,
    ResearchTaskStatus,
)


def test_research_result_completed_contract():
    """Test the structured research result helpers."""
    result = ResearchResult.completed(
        task_id="task-123",
        final_report="Structured report",
        citations=[
            ResearchCitation(index=1, title="Example", url="https://example.com")
        ],
        search_queries=["example query"],
        total_steps=3,
        execution_time=1.5,
    )

    assert result.is_completed == True
    assert result.status == "completed"
    assert result.task_id == "task-123"
    assert result.final_report == "Structured report"
    assert result.to_dict()["citations"][0]["url"] == "https://example.com"


def test_research_task_status_helpers():
    """Test the structured task status helpers."""
    unknown_status = ResearchTaskStatus.unknown(
        task_id="task-123", message="Polling not supported"
    )
    error_status = ResearchTaskStatus.error_status(task_id="task-456", error="Boom")

    assert unknown_status.status == "unknown"
    assert unknown_status.message == "Polling not supported"
    assert unknown_status.task_id == "task-123"
    assert error_status.status == "error"
    assert error_status.error == "Boom"
