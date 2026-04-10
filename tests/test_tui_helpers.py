# -*- coding: utf-8 -*-

"""
Tests for the CLI-side deep research TUI helpers.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def load_tui_module():
    module_path = (
        Path(__file__).resolve().parent.parent / "cli" / "deep-research-tui.py"
    )
    spec = importlib.util.spec_from_file_location("deep_research_tui", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


TUI = load_tui_module()


def test_provider_defaults_for_gemini():
    defaults = TUI.get_provider_defaults("gemini", "responses")

    assert defaults.provider == "gemini"
    assert defaults.model == "deep-research-pro-preview-12-2025"
    assert defaults.base_url == "https://generativelanguage.googleapis.com"


def test_provider_defaults_for_openai_chat_completions():
    defaults = TUI.get_provider_defaults("openai", "chat_completions")

    assert defaults.provider == "openai"
    assert defaults.api_style == "chat_completions"
    assert defaults.model == "gpt-5-mini"
    assert defaults.base_url == "https://api.openai.com/v1"


def test_normalize_answers_pads_missing_values():
    normalized = TUI.normalize_answers(
        ["Question 1?", "Question 2?", "Question 3?"],
        ["One", "", "  "],
    )

    assert normalized == [
        "One",
        TUI.NO_ANSWER_PLACEHOLDER,
        TUI.NO_ANSWER_PLACEHOLDER,
    ]


def test_parse_task_id_from_output_handles_markdown_and_status_text():
    markdown = """
## Research Metadata
- **Task ID**: abc-123
"""
    status_text = "Task xyz-789 status: completed"

    assert TUI.parse_task_id_from_output(markdown) == "abc-123"
    assert TUI.parse_task_id_from_output(status_text) == "xyz-789"


def test_render_agent_clarification_output_includes_session_and_questions():
    rendered = TUI.render_agent_clarification_output(
        "quantum computing",
        {
            "needs_clarification": True,
            "reasoning": "The query is broad.",
            "session_id": "session-123",
            "created_at": "2026-04-10T10:00:00Z",
            "questions": ["Hardware or software focus?", "Recent work only?"],
        },
    )

    assert "session-123" in rendered
    assert "Hardware or software focus?" in rendered
    assert "Recent work only?" in rendered


def test_write_output_file_persists_content(tmp_path):
    target = tmp_path / "reports" / "report.md"

    saved_path = TUI.write_output_file(str(target), "cyberpunk report")

    assert saved_path == str(target)
    assert target.read_text(encoding="utf-8") == "cyberpunk report"
