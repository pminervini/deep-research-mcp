# -*- coding: utf-8 -*-

"""
Headless tests for the Textual deep research TUI.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest
from textual.containers import Container
from textual.widgets import Input, Markdown, Select, Static, Switch


def load_tui_module():
    module_path = (
        Path(__file__).resolve().parent.parent / "cli" / "deep-research-tui.py"
    )
    spec = importlib.util.spec_from_file_location("deep_research_tui_app", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


TUI = load_tui_module()


def build_startup_state():
    config = TUI.get_provider_defaults("openai", "responses")
    return TUI.StartupState(
        config_path=None,
        mode="agent",
        server_url="http://127.0.0.1:8080/mcp",
        query="Investigate frontier AI lab spending trends.",
        task_id="",
        save_path="reports/test-output.md",
        system_prompt=TUI.DEFAULT_SYSTEM_PROMPT,
        include_analysis=True,
        json_output=False,
        config=config,
    )


@pytest.mark.asyncio
async def test_provider_change_updates_model_and_base_url():
    app = TUI.DeepResearchTUI(build_startup_state())

    async with app.run_test(size=(140, 42)) as pilot:
        app.query_one("#provider", Select).value = "gemini"
        await pilot.pause()

        assert (
            app.query_one("#model", Input).value == "deep-research-pro-preview-12-2025"
        )
        assert (
            app.query_one("#base-url", Input).value
            == "https://generativelanguage.googleapis.com"
        )


@pytest.mark.asyncio
async def test_initial_focus_and_arrow_navigation_work_for_form_controls():
    app = TUI.DeepResearchTUI(build_startup_state())

    async with app.run_test(size=(140, 42)) as pilot:
        assert app.focused is app.query_one("#mode", Select)

        await pilot.press("right")
        await pilot.pause()
        assert app.query_one("#mode", Select).value == "mcp"

        await pilot.press("down")
        await pilot.pause()
        assert app.focused is app.query_one("#save-path", Input)

        await pilot.press("down")
        await pilot.pause()
        assert app.focused is app.query_one("#task-id", Input)


@pytest.mark.asyncio
async def test_switching_to_mcp_hides_agent_controls_and_disables_json_toggle():
    app = TUI.DeepResearchTUI(build_startup_state())

    async with app.run_test(size=(140, 42)) as pilot:
        app.query_one("#mode", Select).value = "mcp"
        await pilot.pause()

        assert not app.query_one("#agent-settings", Container).display
        assert app.query_one("#mcp-settings", Container).display
        assert app.query_one("#json-output", Switch).disabled


@pytest.mark.asyncio
async def test_left_and_right_toggle_switch_values():
    app = TUI.DeepResearchTUI(build_startup_state())

    async with app.run_test(size=(140, 42)) as pilot:
        include_analysis = app.query_one("#include-analysis", Switch)
        include_analysis.focus()
        await pilot.pause()

        await pilot.press("left")
        await pilot.pause()
        assert include_analysis.value is False

        await pilot.press("right")
        await pilot.pause()
        assert include_analysis.value is True


@pytest.mark.asyncio
async def test_clarification_panel_recomposes_answer_inputs():
    app = TUI.DeepResearchTUI(build_startup_state())

    async with app.run_test(size=(140, 42)) as pilot:
        panel = app.query_one("#clarification-answers", TUI.ClarificationAnswersPanel)
        panel.set_questions(["Scope by geography?", "Need pricing detail?"], ["Global"])
        await pilot.pause()

        answer_inputs = list(panel.query(Input))
        assert len(answer_inputs) == 2
        assert answer_inputs[0].value == "Global"
        assert answer_inputs[1].value == ""


@pytest.mark.asyncio
async def test_output_panel_toggles_markdown_and_raw_views():
    app = TUI.DeepResearchTUI(build_startup_state())

    async with app.run_test(size=(140, 42)) as pilot:
        # Exercise the internal output toggle state directly in a focused UI test.
        # pylint: disable=protected-access
        app._set_output("# Title\n\n- one\n- two")
        await pilot.pause()

        md = app.query_one("#output-markdown", Markdown)
        raw = app.query_one("#output-area", Static)
        assert md.display is True
        assert raw.display is False

        await pilot.click("#btn-output-raw")
        await pilot.pause()
        assert md.display is False
        assert raw.display is True
        assert app._output_text == "# Title\n\n- one\n- two"

        await pilot.click("#btn-output-md")
        await pilot.pause()
        assert md.display is True
        assert raw.display is False
