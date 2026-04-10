#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Interactive full-screen terminal UI for Deep Research.

A dark, keyboard-driven interface for running clarification, deep research,
task status checks, and saving output to disk.

USAGE:
    # Start in direct agent mode
    uv run python cli/deep-research-tui.py

    # Start in MCP client mode
    uv run python cli/deep-research-tui.py --mode mcp --server-url http://127.0.0.1:8080/mcp

    # Start with Gemini selected
    uv run python cli/deep-research-tui.py --provider gemini
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.theme import Theme
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    Rule,
    Select,
    Static,
    Switch,
    TextArea,
)

from deep_research_mcp import (
    DeepResearchAgent,
    ResearchConfig,
    ResearchError,
    ResearchResult,
)

DEFAULT_SYSTEM_PROMPT = """
You are a professional researcher preparing a structured, data-driven report.
Your task is to analyze the research question the user poses.

Do:
- Focus on data-rich insights: include specific figures, trends, statistics,
  and measurable outcomes.
- When appropriate, summarize data in a way that could be turned into charts
  or tables, and call this out in the response.
- Prioritize reliable, up-to-date sources: peer-reviewed research, official
  organizations, regulatory agencies, or authoritative reports.
- Include inline citations and return all source metadata.

Be analytical, avoid generalities, and ensure that each section supports
data-backed reasoning.
""".strip()


CODEX_THEME = Theme(
    name="codex",
    primary="#a78bfa",
    secondary="#818cf8",
    accent="#c4b5fd",
    foreground="#e2e8f0",
    background="#0f0f14",
    success="#a78bfa",
    warning="#f59e0b",
    error="#ef4444",
    surface="#1a1a24",
    panel="#252532",
    dark=True,
)


@dataclass
class ProviderDefaults:
    """Provider-specific default settings."""

    model: str
    base_url: str


def get_provider_defaults(
    provider: str, api_style: str = "responses"
) -> ProviderDefaults:
    """Return provider-specific default model and base URL."""
    if provider == "openai":
        if api_style == "chat_completions":
            return ProviderDefaults(
                model="gpt-5-mini",
                base_url="https://api.openai.com/v1",
            )
        return ProviderDefaults(
            model="o4-mini-deep-research-2025-06-26",
            base_url="https://api.openai.com/v1",
        )
    if provider == "gemini":
        return ProviderDefaults(
            model="deep-research-pro-preview-12-2025",
            base_url="https://generativelanguage.googleapis.com",
        )
    if provider == "open-deep-research":
        return ProviderDefaults(
            model="openai/qwen/qwen3-coder-30b",
            base_url="http://localhost:1234/v1",
        )
    return ProviderDefaults(model="gpt-5-mini", base_url="https://api.openai.com/v1")


@dataclass
class StartupState:
    """Initial state passed to the TUI at startup."""

    config_path: str | None = None
    mode: str = "agent"
    server_url: str = "http://127.0.0.1:8080/mcp"
    query: str = ""
    task_id: str = ""
    save_path: str = "output.md"
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    include_analysis: bool = True
    json_output: bool = False
    config: ProviderDefaults = field(
        default_factory=lambda: get_provider_defaults("openai")
    )


class ClarificationAnswersPanel(Container):
    """Dynamic panel for clarification question answers."""

    DEFAULT_CSS = """
    ClarificationAnswersPanel {
        height: auto;
        padding: 0 1;
    }

    ClarificationAnswersPanel .question-label {
        margin-top: 1;
        color: $accent;
    }

    ClarificationAnswersPanel Input {
        margin-bottom: 1;
    }
    """

    questions = reactive(list, recompose=True)
    answers = reactive(list, recompose=True)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._questions: list[str] = []
        self._answers: list[str] = []

    def compose(self) -> ComposeResult:
        if not self._questions:
            yield Label("No clarification questions yet.", classes="question-label")
            return
        for i, question in enumerate(self._questions):
            yield Label(f"{i + 1}. {question}", classes="question-label")
            answer_value = self._answers[i] if i < len(self._answers) else ""
            yield Input(
                value=answer_value,
                placeholder="Your answer...",
                id=f"clarification-answer-{i}",
            )

    def set_questions(
        self, questions: list[str], answers: list[str] | None = None
    ) -> None:
        """Set questions and optionally prefill answers, then recompose."""
        self._questions = list(questions)
        self._answers = list(answers) if answers else []
        self.questions = self._questions
        self.answers = self._answers

    def get_answers(self) -> list[str]:
        """Collect current answer values from input widgets."""
        answers: list[str] = []
        for i in range(len(self._questions)):
            try:
                inp = self.query_one(f"#clarification-answer-{i}", Input)
                answers.append(inp.value.strip() or "[No answer provided]")
            except Exception:
                answers.append("[No answer provided]")
        return answers

    def clear(self) -> None:
        """Clear all questions and answers."""
        self._questions = []
        self._answers = []
        self.questions = []
        self.answers = []


class OutputPanel(Static):
    """Panel for displaying research output."""

    DEFAULT_CSS = """
    OutputPanel {
        height: 100%;
        border: round $panel;
        padding: 1 2;
        background: $surface;
        overflow-y: auto;
    }

    OutputPanel .output-content {
        width: 100%;
    }
    """

    output_text = reactive("")

    def compose(self) -> ComposeResult:
        yield Static(self.output_text, classes="output-content", id="output-content")

    def watch_output_text(self, value: str) -> None:
        try:
            self.query_one("#output-content", Static).update(value)
        except Exception:
            pass

    def set_output(self, text: str) -> None:
        self.output_text = text

    def append_output(self, text: str) -> None:
        self.output_text = self.output_text + text


class DeepResearchTUI(App):
    """Interactive TUI for Deep Research."""

    TITLE = "Deep Research"
    SUB_TITLE = "Interactive Research Terminal"

    CSS = """
    Screen {
        background: $background;
    }

    Header {
        background: $surface;
        color: $primary;
    }

    Footer {
        background: $surface;
    }

    #main-container {
        layout: horizontal;
        height: 100%;
    }

    #left-panel {
        width: 45;
        min-width: 40;
        height: 100%;
        border: round $panel;
        background: $surface;
        padding: 1;
    }

    #right-panel {
        width: 1fr;
        height: 100%;
        padding: 0 1;
    }

    .section-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    .field-label {
        color: $secondary;
        margin-top: 1;
    }

    #agent-settings, #mcp-settings {
        height: auto;
        padding: 0;
    }

    #agent-settings.hidden, #mcp-settings.hidden {
        display: none;
    }

    Select {
        width: 100%;
        margin-bottom: 1;
    }

    Input {
        width: 100%;
        margin-bottom: 1;
    }

    Switch {
        margin-bottom: 1;
    }

    .switch-row {
        height: auto;
        margin-bottom: 1;
    }

    .switch-row Label {
        width: 1fr;
        padding-top: 1;
    }

    .switch-row Switch {
        width: auto;
    }

    TextArea {
        height: 6;
        margin-bottom: 1;
        border: round $panel;
    }

    #query-area {
        height: 4;
    }

    #system-prompt-area {
        height: 6;
    }

    #button-row {
        height: auto;
        margin-top: 1;
        align: center middle;
    }

    #button-row Button {
        margin: 0 1;
    }

    Button {
        background: $panel;
        color: $foreground;
        border: round $accent;
    }

    Button:hover {
        background: $accent;
        color: $background;
    }

    Button:focus {
        border: round $primary;
    }

    Button.-primary {
        background: $primary;
        color: $background;
    }

    Button.-primary:hover {
        background: $accent;
    }

    #output-scroll {
        height: 100%;
        border: round $panel;
        background: $surface;
    }

    #output-area {
        padding: 1 2;
        width: 100%;
    }

    Rule {
        margin: 1 0;
        color: $panel;
    }

    #clarification-section {
        height: auto;
        margin-top: 1;
        border: round $panel;
        padding: 1;
        background: $surface;
    }

    #clarification-section.hidden {
        display: none;
    }

    #status-bar {
        dock: bottom;
        height: 1;
        background: $surface;
        color: $secondary;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("c", "run_clarification", "Clarify", show=True),
        Binding("r", "run_research", "Research", show=True),
        Binding("t", "check_status", "Status", show=True),
        Binding("s", "save_output", "Save", show=True),
    ]

    mode = reactive("agent")
    provider = reactive("openai")
    api_style = reactive("responses")
    current_session_id: str | None = None
    clarification_questions: list[str] = []

    _focusable_ids: list[str] = [
        "#mode",
        "#save-path",
        "#task-id",
        "#server-url",
        "#provider",
        "#api-style",
        "#model",
        "#base-url",
        "#include-analysis",
        "#json-output",
        "#query-area",
        "#system-prompt-area",
        "#btn-clarify",
        "#btn-research",
        "#btn-status",
        "#btn-save",
    ]

    def __init__(self, startup_state: StartupState | None = None) -> None:
        super().__init__()
        self._startup_state = startup_state or StartupState()
        self._output_text = ""
        self._status_message = "Ready"

    def on_mount(self) -> None:
        self.register_theme(CODEX_THEME)
        self.theme = "codex"

        state = self._startup_state
        self.mode = state.mode
        self.provider = "openai"

        self.query_one("#mode", Select).value = state.mode
        self.query_one("#save-path", Input).value = state.save_path
        self.query_one("#task-id", Input).value = state.task_id
        self.query_one("#server-url", Input).value = state.server_url
        self.query_one("#provider", Select).value = "openai"
        self.query_one("#api-style", Select).value = (
            state.config.model.startswith("gpt") and "chat_completions" or "responses"
        )
        self.query_one("#model", Input).value = state.config.model
        self.query_one("#base-url", Input).value = state.config.base_url
        self.query_one("#include-analysis", Switch).value = state.include_analysis
        self.query_one("#json-output", Switch).value = state.json_output
        self.query_one("#query-area", TextArea).text = state.query
        self.query_one("#system-prompt-area", TextArea).text = state.system_prompt

        self._update_mode_visibility()
        self.query_one("#mode", Select).focus()

    def compose(self) -> ComposeResult:
        yield Header()

        with Horizontal(id="main-container"):
            with Vertical(id="left-panel"):
                yield Label("Configuration", classes="section-title")

                yield Label("Mode", classes="field-label")
                yield Select(
                    [("Agent (Direct)", "agent"), ("MCP Client", "mcp")],
                    value="agent",
                    id="mode",
                    allow_blank=False,
                )

                yield Label("Save Path", classes="field-label")
                yield Input(placeholder="output.md", id="save-path")

                yield Label("Task ID (for status)", classes="field-label")
                yield Input(placeholder="task-id-here", id="task-id")

                with Container(id="mcp-settings"):
                    yield Label("MCP Server URL", classes="field-label")
                    yield Input(
                        placeholder="http://127.0.0.1:8080/mcp",
                        id="server-url",
                    )

                with Container(id="agent-settings"):
                    yield Label("Provider", classes="field-label")
                    yield Select(
                        [
                            ("OpenAI", "openai"),
                            ("Gemini", "gemini"),
                            ("Open Deep Research", "open-deep-research"),
                        ],
                        value="openai",
                        id="provider",
                        allow_blank=False,
                    )

                    yield Label("API Style", classes="field-label")
                    yield Select(
                        [
                            ("Responses", "responses"),
                            ("Chat Completions", "chat_completions"),
                        ],
                        value="responses",
                        id="api-style",
                        allow_blank=False,
                    )

                    yield Label("Model", classes="field-label")
                    yield Input(placeholder="model-id", id="model")

                    yield Label("Base URL", classes="field-label")
                    yield Input(placeholder="https://api.openai.com/v1", id="base-url")

                    with Horizontal(classes="switch-row"):
                        yield Label("Include Analysis")
                        yield Switch(value=True, id="include-analysis")

                    with Horizontal(classes="switch-row"):
                        yield Label("JSON Output")
                        yield Switch(value=False, id="json-output")

                yield Rule()

                yield Label("Query", classes="field-label")
                yield TextArea(id="query-area")

                yield Label("System Prompt", classes="field-label")
                yield TextArea(id="system-prompt-area")

                with Container(id="clarification-section", classes="hidden"):
                    yield Label("Clarification Answers", classes="section-title")
                    yield ClarificationAnswersPanel(id="clarification-answers")

                with Horizontal(id="button-row"):
                    yield Button("Clarify", id="btn-clarify", variant="default")
                    yield Button("Research", id="btn-research", variant="primary")
                    yield Button("Status", id="btn-status", variant="default")
                    yield Button("Save", id="btn-save", variant="default")

            with Vertical(id="right-panel"):
                yield Label("Output", classes="section-title")
                with VerticalScroll(id="output-scroll"):
                    yield Static("", id="output-area")

        yield Static("Ready", id="status-bar")
        yield Footer()

    def _update_mode_visibility(self) -> None:
        """Show/hide agent vs MCP settings based on mode."""
        agent_settings = self.query_one("#agent-settings", Container)
        mcp_settings = self.query_one("#mcp-settings", Container)
        json_switch = self.query_one("#json-output", Switch)

        if self.mode == "mcp":
            agent_settings.display = False
            mcp_settings.display = True
            json_switch.disabled = True
        else:
            agent_settings.display = True
            mcp_settings.display = False
            json_switch.disabled = False

    def _update_provider_defaults(self) -> None:
        """Update model and base URL based on provider and api_style."""
        defaults = get_provider_defaults(self.provider, self.api_style)
        self.query_one("#model", Input).value = defaults.model
        self.query_one("#base-url", Input).value = defaults.base_url

        api_style_select = self.query_one("#api-style", Select)
        if self.provider == "openai":
            api_style_select.disabled = False
        else:
            api_style_select.disabled = True

    def _set_status(self, message: str) -> None:
        """Update the status bar message."""
        self._status_message = message
        self.query_one("#status-bar", Static).update(message)

    def _set_output(self, text: str) -> None:
        """Set the output panel text."""
        self._output_text = text
        self.query_one("#output-area", Static).update(text)

    def _append_output(self, text: str) -> None:
        """Append text to the output panel."""
        self._output_text += text
        self.query_one("#output-area", Static).update(self._output_text)

    def _show_clarification_section(self, questions: list[str]) -> None:
        """Show the clarification section with questions."""
        self.clarification_questions = questions
        section = self.query_one("#clarification-section", Container)
        section.remove_class("hidden")
        panel = self.query_one("#clarification-answers", ClarificationAnswersPanel)
        panel.set_questions(questions)

    def _hide_clarification_section(self) -> None:
        """Hide the clarification section."""
        section = self.query_one("#clarification-section", Container)
        section.add_class("hidden")
        panel = self.query_one("#clarification-answers", ClarificationAnswersPanel)
        panel.clear()
        self.clarification_questions = []
        self.current_session_id = None

    def on_key(self, event) -> None:
        """Handle arrow key navigation for form controls."""
        focused = self.focused

        if isinstance(focused, TextArea):
            return

        if event.key in ("up", "down"):
            self._navigate_focus(event.key)
            event.prevent_default()
            event.stop()
        elif event.key in ("left", "right"):
            if isinstance(focused, Select):
                self._cycle_select(focused, event.key)
                event.prevent_default()
                event.stop()
            elif isinstance(focused, Switch):
                focused.value = event.key == "right"
                event.prevent_default()
                event.stop()

    def _navigate_focus(self, direction: str) -> None:
        """Move focus up or down through form controls."""
        focused = self.focused
        if focused is None:
            return

        visible_ids: list[str] = []
        for widget_id in self._focusable_ids:
            try:
                widget = self.query_one(widget_id)
                if widget.display and not widget.disabled:
                    visible_ids.append(widget_id)
            except Exception:
                pass

        current_id = None
        for widget_id in visible_ids:
            try:
                if self.query_one(widget_id) is focused:
                    current_id = widget_id
                    break
            except Exception:
                pass

        if current_id is None:
            return

        try:
            idx = visible_ids.index(current_id)
        except ValueError:
            return

        if direction == "down":
            new_idx = (idx + 1) % len(visible_ids)
        else:
            new_idx = (idx - 1) % len(visible_ids)

        try:
            self.query_one(visible_ids[new_idx]).focus()
        except Exception:
            pass

    def _cycle_select(self, select: Select, direction: str) -> None:
        """Cycle through select options with left/right keys."""
        options = list(select._options)
        if not options:
            return

        current_value = select.value
        current_idx = -1
        for i, (_, value) in enumerate(options):
            if value == current_value:
                current_idx = i
                break

        if current_idx == -1:
            current_idx = 0

        if direction == "right":
            new_idx = (current_idx + 1) % len(options)
        else:
            new_idx = (current_idx - 1) % len(options)

        select.value = options[new_idx][1]

    @on(Select.Changed, "#mode")
    def handle_mode_change(self, event: Select.Changed) -> None:
        if event.value is not None:
            self.mode = str(event.value)
            self._update_mode_visibility()

    @on(Select.Changed, "#provider")
    def handle_provider_change(self, event: Select.Changed) -> None:
        if event.value is not None:
            self.provider = str(event.value)
            self._update_provider_defaults()

    @on(Select.Changed, "#api-style")
    def handle_api_style_change(self, event: Select.Changed) -> None:
        if event.value is not None:
            self.api_style = str(event.value)
            if self.provider == "openai":
                self._update_provider_defaults()

    @on(Button.Pressed, "#btn-clarify")
    def handle_clarify_button(self) -> None:
        self.action_run_clarification()

    @on(Button.Pressed, "#btn-research")
    def handle_research_button(self) -> None:
        self.action_run_research()

    @on(Button.Pressed, "#btn-status")
    def handle_status_button(self) -> None:
        self.action_check_status()

    @on(Button.Pressed, "#btn-save")
    def handle_save_button(self) -> None:
        self.action_save_output()

    def _build_config(self) -> ResearchConfig:
        """Build a ResearchConfig from current UI state."""
        return ResearchConfig(
            provider=self.query_one("#provider", Select).value or "openai",
            api_style=self.query_one("#api-style", Select).value or "responses",
            model=self.query_one("#model", Input).value,
            base_url=self.query_one("#base-url", Input).value or None,
            enable_clarification=True,
        )

    def _get_query(self) -> str:
        return self.query_one("#query-area", TextArea).text.strip()

    def _get_system_prompt(self) -> str:
        return (
            self.query_one("#system-prompt-area", TextArea).text.strip()
            or DEFAULT_SYSTEM_PROMPT
        )

    def _get_include_analysis(self) -> bool:
        return self.query_one("#include-analysis", Switch).value

    def _get_json_output(self) -> bool:
        return self.query_one("#json-output", Switch).value

    def action_run_clarification(self) -> None:
        """Run the clarification flow."""
        query = self._get_query()
        if not query:
            self._set_status("Error: No query provided")
            self.notify("Please enter a query first", severity="error")
            return

        if self.mode == "mcp":
            self._run_mcp_clarification(query)
        else:
            self._run_agent_clarification(query)

    @work(exclusive=True)
    async def _run_agent_clarification(self, query: str) -> None:
        """Run clarification via direct agent."""
        self._set_status("Running clarification...")
        self._set_output("Starting clarification process...\n")

        try:
            config = self._build_config()
            agent = DeepResearchAgent(config)

            result = agent.start_clarification(query)

            if not result.get("needs_clarification", False):
                reasoning = result.get("reasoning", "Query is sufficient")
                self._append_output(f"\nAssessment: {reasoning}\n")
                self._append_output("\nNo clarification needed. Ready for research.\n")
                self._set_status("Clarification complete - no questions needed")
                self.notify("No clarification needed", severity="information")
                return

            questions = result.get("questions", [])
            session_id = result.get("session_id")
            self.current_session_id = session_id

            reasoning = result.get("reasoning", "")
            self._append_output(f"\nReasoning: {reasoning}\n")
            self._append_output(f"\nSession ID: {session_id}\n")
            self._append_output("\nClarifying Questions:\n")
            for i, q in enumerate(questions, 1):
                self._append_output(f"  {i}. {q}\n")

            self._show_clarification_section(questions)
            self._set_status("Clarification questions ready - provide answers")
            self.notify(
                f"{len(questions)} clarification questions generated",
                severity="information",
            )

        except Exception as e:
            self._append_output(f"\nError: {e}\n")
            self._set_status(f"Clarification error: {e}")
            self.notify(f"Clarification failed: {e}", severity="error")

    @work(exclusive=True)
    async def _run_mcp_clarification(self, query: str) -> None:
        """Run clarification via MCP client."""
        self._set_status("Connecting to MCP server...")
        self._set_output("Starting MCP clarification...\n")

        server_url = self.query_one("#server-url", Input).value
        system_prompt = self._get_system_prompt()
        include_analysis = self._get_include_analysis()

        try:
            from mcp import ClientSession
            from mcp.client.streamable_http import streamablehttp_client

            async with streamablehttp_client(server_url) as (
                read_stream,
                write_stream,
                _,
            ):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()

                    result = await session.call_tool(
                        "deep_research",
                        {
                            "query": query,
                            "system_instructions": system_prompt,
                            "include_analysis": include_analysis,
                            "request_clarification": True,
                            "callback_url": "",
                        },
                    )

                    text = self._render_mcp_result(result)
                    self._append_output(f"\n{text}\n")

                    session_id, questions = self._parse_mcp_clarification(text)
                    if session_id and questions:
                        self.current_session_id = session_id
                        self._show_clarification_section(questions)
                        self._set_status("Clarification questions ready")
                        self.notify(
                            f"{len(questions)} questions received",
                            severity="information",
                        )
                    else:
                        self._set_status("Clarification complete")
                        self.notify("No clarification needed", severity="information")

        except Exception as e:
            self._append_output(f"\nMCP Error: {e}\n")
            self._set_status(f"MCP error: {e}")
            self.notify(f"MCP connection failed: {e}", severity="error")

    def action_run_research(self) -> None:
        """Run the deep research flow."""
        query = self._get_query()
        if not query:
            self._set_status("Error: No query provided")
            self.notify("Please enter a query first", severity="error")
            return

        if self.mode == "mcp":
            self._run_mcp_research(query)
        else:
            self._run_agent_research(query)

    @work(exclusive=True)
    async def _run_agent_research(self, query: str) -> None:
        """Run research via direct agent."""
        self._set_status("Running deep research...")
        self._set_output("Starting deep research...\n")

        try:
            config = self._build_config()
            agent = DeepResearchAgent(config)

            working_query = query

            if self.current_session_id and self.clarification_questions:
                panel = self.query_one(
                    "#clarification-answers", ClarificationAnswersPanel
                )
                answers = panel.get_answers()
                agent.add_clarification_answers(self.current_session_id, answers)
                enriched = agent.get_enriched_query(self.current_session_id)
                if enriched:
                    working_query = enriched
                    self._append_output(f"\nEnriched query: {enriched}\n")

            self._append_output(f"\nResearching: {working_query}\n")
            self._append_output("\nPlease wait, this may take several minutes...\n")

            system_prompt = self._get_system_prompt()
            include_analysis = self._get_include_analysis()

            result = await agent.research(
                query=working_query,
                system_prompt=system_prompt,
                include_code_interpreter=include_analysis,
            )

            if result.status == "completed":
                if self._get_json_output():
                    output = self._format_result_json(result)
                else:
                    output = self._format_report(result)
                self._set_output(output)
                self._set_status("Research completed")
                self.notify("Research completed successfully", severity="information")
                self._hide_clarification_section()
            else:
                msg = result.message or "Unknown error"
                self._append_output(f"\nResearch failed: {msg}\n")
                self._set_status(f"Research failed: {msg}")
                self.notify(f"Research failed: {msg}", severity="error")

        except ResearchError as e:
            self._append_output(f"\nResearch error: {e}\n")
            self._set_status(f"Research error: {e}")
            self.notify(f"Research error: {e}", severity="error")
        except Exception as e:
            self._append_output(f"\nUnexpected error: {e}\n")
            self._set_status(f"Error: {e}")
            self.notify(f"Error: {e}", severity="error")

    @work(exclusive=True)
    async def _run_mcp_research(self, query: str) -> None:
        """Run research via MCP client."""
        self._set_status("Connecting to MCP server...")
        self._set_output("Starting MCP research...\n")

        server_url = self.query_one("#server-url", Input).value
        system_prompt = self._get_system_prompt()
        include_analysis = self._get_include_analysis()

        try:
            from mcp import ClientSession
            from mcp.client.streamable_http import streamablehttp_client

            async with streamablehttp_client(server_url) as (
                read_stream,
                write_stream,
                _,
            ):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()

                    if self.current_session_id and self.clarification_questions:
                        panel = self.query_one(
                            "#clarification-answers", ClarificationAnswersPanel
                        )
                        answers = panel.get_answers()

                        self._append_output(
                            f"\nUsing session: {self.current_session_id}\n"
                        )
                        self._append_output("Sending answers and running research...\n")

                        result = await session.call_tool(
                            "research_with_context",
                            {
                                "session_id": self.current_session_id,
                                "answers": answers,
                                "system_instructions": system_prompt,
                                "include_analysis": include_analysis,
                                "callback_url": "",
                            },
                        )
                    else:
                        self._append_output(f"\nResearching: {query}\n")
                        self._append_output("\nPlease wait...\n")

                        result = await session.call_tool(
                            "deep_research",
                            {
                                "query": query,
                                "system_instructions": system_prompt,
                                "include_analysis": include_analysis,
                                "request_clarification": False,
                                "callback_url": "",
                            },
                        )

                    text = self._render_mcp_result(result)
                    self._set_output(text)

                    if result.isError:
                        self._set_status("Research failed")
                        self.notify("Research failed", severity="error")
                    else:
                        self._set_status("Research completed")
                        self.notify("Research completed", severity="information")
                        self._hide_clarification_section()

        except Exception as e:
            self._append_output(f"\nMCP Error: {e}\n")
            self._set_status(f"MCP error: {e}")
            self.notify(f"MCP error: {e}", severity="error")

    def action_check_status(self) -> None:
        """Check the status of a research task."""
        task_id = self.query_one("#task-id", Input).value.strip()
        if not task_id:
            self._set_status("Error: No task ID provided")
            self.notify("Please enter a task ID", severity="error")
            return

        if self.mode == "mcp":
            self._check_mcp_status(task_id)
        else:
            self._check_agent_status(task_id)

    @work(exclusive=True)
    async def _check_agent_status(self, task_id: str) -> None:
        """Check task status via direct agent."""
        self._set_status("Checking task status...")

        try:
            config = self._build_config()
            agent = DeepResearchAgent(config)
            status = await agent.get_task_status(task_id)

            lines = [
                f"Task ID: {status.task_id}",
                f"Status: {status.status}",
            ]
            if status.created_at is not None:
                lines.append(f"Created: {status.created_at}")
            if status.completed_at is not None:
                lines.append(f"Completed: {status.completed_at}")
            if status.message:
                lines.append(f"Message: {status.message}")
            if status.error:
                lines.append(f"Error: {status.error}")

            self._set_output("\n".join(lines))
            self._set_status(f"Status: {status.status}")

        except Exception as e:
            self._set_output(f"Status check error: {e}")
            self._set_status(f"Error: {e}")
            self.notify(f"Status check failed: {e}", severity="error")

    @work(exclusive=True)
    async def _check_mcp_status(self, task_id: str) -> None:
        """Check task status via MCP client."""
        self._set_status("Connecting to MCP server...")

        server_url = self.query_one("#server-url", Input).value

        try:
            from mcp import ClientSession
            from mcp.client.streamable_http import streamablehttp_client

            async with streamablehttp_client(server_url) as (
                read_stream,
                write_stream,
                _,
            ):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()

                    result = await session.call_tool(
                        "research_status",
                        {"task_id": task_id},
                    )

                    text = self._render_mcp_result(result)
                    self._set_output(text)

                    if result.isError:
                        self._set_status("Status check failed")
                    else:
                        self._set_status("Status retrieved")

        except Exception as e:
            self._set_output(f"MCP status error: {e}")
            self._set_status(f"MCP error: {e}")
            self.notify(f"MCP error: {e}", severity="error")

    def action_save_output(self) -> None:
        """Save the current output to file."""
        save_path = self.query_one("#save-path", Input).value.strip()
        if not save_path:
            self._set_status("Error: No save path provided")
            self.notify("Please enter a save path", severity="error")
            return

        if not self._output_text:
            self._set_status("Error: No output to save")
            self.notify("No output to save", severity="error")
            return

        try:
            path = Path(save_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(self._output_text, encoding="utf-8")
            self._set_status(f"Saved to {save_path}")
            self.notify(f"Output saved to {save_path}", severity="information")
        except Exception as e:
            self._set_status(f"Save error: {e}")
            self.notify(f"Save failed: {e}", severity="error")

    def _format_report(self, result: ResearchResult) -> str:
        """Format a ResearchResult as a human-readable report."""
        parts: list[str] = []
        parts.append("=" * 60)
        parts.append("RESEARCH REPORT")
        parts.append("=" * 60)

        if result.task_id:
            parts.append(f"Task ID: {result.task_id}")
        if result.total_steps:
            parts.append(f"Total steps: {result.total_steps}")
        if result.search_queries:
            parts.append(f"Search queries: {len(result.search_queries)}")
        if result.citations:
            parts.append(f"Citations: {len(result.citations)}")
        if isinstance(result.execution_time, (int, float)):
            parts.append(f"Execution time: {result.execution_time:.2f}s")

        parts.append("")
        parts.append(result.final_report)

        if result.citations:
            parts.append("")
            parts.append("=" * 60)
            parts.append("CITATIONS")
            parts.append("=" * 60)
            for citation in result.citations:
                parts.append(f"{citation.index}. [{citation.title}]({citation.url})")

        return "\n".join(parts)

    def _format_result_json(self, result: ResearchResult) -> str:
        """Format a ResearchResult as JSON."""
        data = asdict(result)
        return json.dumps(data, indent=2, ensure_ascii=False)

    def _render_mcp_result(self, result: Any) -> str:
        """Extract text from an MCP CallToolResult."""
        from mcp import types

        if result.structuredContent is not None:
            sc = result.structuredContent
            if isinstance(sc, dict) and "result" in sc:
                val = sc.get("result")
                return val if isinstance(val, str) else str(val)
            return str(sc)

        parts: list[str] = []
        for item in result.content or []:
            if isinstance(item, types.TextContent):
                parts.append(item.text)
            else:
                parts.append(str(item))
        return "\n".join(parts)

    def _parse_mcp_clarification(self, text: str) -> tuple[str | None, list[str]]:
        """Parse session ID and questions from MCP clarification output."""
        session_match = re.search(r"Session ID:\s*`([^`]+)`", text)
        session_id = session_match.group(1) if session_match else None
        questions = re.findall(r"^\d+\.\s+(.+)$", text, re.MULTILINE)
        return session_id, questions


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="deep-research-tui",
        description="Interactive full-screen terminal UI for Deep Research.",
    )
    parser.add_argument(
        "--config",
        default=None,
        metavar="PATH",
        help="Path to TOML config file (default: ~/.deep_research)",
    )
    parser.add_argument(
        "--mode",
        choices=["agent", "mcp"],
        default="agent",
        help="Operating mode (default: agent)",
    )
    parser.add_argument(
        "--server-url",
        default="http://127.0.0.1:8080/mcp",
        help="MCP server URL for mcp mode",
    )
    parser.add_argument(
        "--provider",
        choices=["openai", "gemini", "open-deep-research"],
        default="openai",
        help="Research provider (default: openai)",
    )
    parser.add_argument(
        "--api-style",
        choices=["responses", "chat_completions"],
        default="responses",
        help="OpenAI API style (default: responses)",
    )
    parser.add_argument(
        "--query",
        default="",
        help="Initial research query",
    )
    parser.add_argument(
        "--save-path",
        default="output.md",
        help="Default save path for output",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    defaults = get_provider_defaults(args.provider, args.api_style)

    startup_state = StartupState(
        config_path=args.config,
        mode=args.mode,
        server_url=args.server_url,
        query=args.query,
        save_path=args.save_path,
        system_prompt=DEFAULT_SYSTEM_PROMPT,
        include_analysis=True,
        json_output=False,
        config=defaults,
    )

    app = DeepResearchTUI(startup_state)
    app.run()


if __name__ == "__main__":
    main()
