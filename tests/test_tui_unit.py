# -*- coding: utf-8 -*-

"""
Tests for the CLI-side deep research TUI helpers.
"""

from __future__ import annotations

from tests.tui_test_utils import load_tui_module

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


def test_provider_defaults_for_dr_tulu():
    defaults = TUI.get_provider_defaults("dr-tulu", "responses")

    assert defaults.provider == "dr-tulu"
    assert defaults.api_style == "responses"
    assert defaults.model == "dr-tulu"
    assert defaults.base_url == "http://localhost:8080/"


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
