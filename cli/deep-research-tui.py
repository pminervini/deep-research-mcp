#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Full-screen Textual TUI for Deep Research.
"""

# pylint: disable=too-many-lines,wrong-import-position

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.widgets import (
    Button,
    Collapsible,
    Footer,
    Header,
    Input,
    Label,
    Select,
    Static,
    Switch,
    TextArea,
)

# Add src to path to import the deep_research_mcp package
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

import structlog

from deep_research_mcp import (
    DeepResearchAgent,
    ResearchConfig,
    ResearchError,
    ResearchResult,
)
from deep_research_mcp.results import ResearchTaskStatus

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

DEFAULT_SAVE_PATH = "reports/deep-research-output.md"
DEFAULT_MCP_SERVER_URL = "http://127.0.0.1:8080/mcp"
NO_ANSWER_PLACEHOLDER = "[No answer provided]"

MODE_OPTIONS: list[tuple[str, str]] = [
    ("Direct Agent", "agent"),
    ("MCP Client", "mcp"),
]

PROVIDER_OPTIONS: list[tuple[str, str]] = [
    ("OpenAI", "openai"),
    ("Gemini", "gemini"),
    ("Open Deep Research", "open-deep-research"),
]

API_STYLE_OPTIONS: list[tuple[str, str]] = [
    ("Responses API", "responses"),
    ("Chat Completions", "chat_completions"),
]

LOG_LEVEL_OPTIONS: list[tuple[str, str]] = [
    ("DEBUG", "DEBUG"),
    ("INFO", "INFO"),
    ("WARNING", "WARNING"),
    ("ERROR", "ERROR"),
    ("CRITICAL", "CRITICAL"),
]


@dataclass(slots=True)
class StartupState:
    """Initial values used to seed the TUI."""

    config_path: str | None
    mode: str
    server_url: str
    query: str
    task_id: str
    save_path: str
    system_prompt: str
    include_analysis: bool
    json_output: bool
    config: ResearchConfig


class ClarificationAnswersPanel(Container):
    """Renders answer inputs for the current clarification session."""

    questions: reactive[tuple[str, ...]] = reactive(tuple(), recompose=True)
    answer_defaults: reactive[tuple[str, ...]] = reactive(tuple(), recompose=True)

    def set_questions(
        self, questions: list[str], answers: list[str] | None = None
    ) -> None:
        self.questions = tuple(questions)
        self.answer_defaults = tuple(answers or [])

    def compose(self) -> ComposeResult:
        yield Static("Clarification Answers", classes="panel-title")
        if not self.questions:
            yield Static(
                "Run clarification to generate focused follow-up questions.",
                classes="helper-copy",
            )
            return

        for index, question in enumerate(self.questions, start=1):
            default_answer = (
                self.answer_defaults[index - 1]
                if index - 1 < len(self.answer_defaults)
                else ""
            )
            with Container(classes="answer-card"):
                yield Static(f"{index}. {question}", classes="question-copy")
                yield Input(
                    value=default_answer,
                    placeholder="Type an answer or leave blank",
                    id=f"answer-{index - 1}",
                    classes="answer-input",
                )


# ---------------------------------------------------------------------------
# Shared CLI-style helpers
# ---------------------------------------------------------------------------


def build_cli_env(args: argparse.Namespace) -> dict[str, str]:
    """Build an env dict with CLI flag overrides injected."""

    mapping: dict[str, str] = {
        "provider": "RESEARCH_PROVIDER",
        "model": "RESEARCH_MODEL",
        "api_key": "RESEARCH_API_KEY",
        "base_url": "RESEARCH_BASE_URL",
        "api_style": "RESEARCH_API_STYLE",
        "timeout": "RESEARCH_TIMEOUT",
        "poll_interval": "RESEARCH_POLL_INTERVAL",
        "log_level": "LOGGING_LEVEL",
        "triage_model": "CLARIFICATION_TRIAGE_MODEL",
        "clarifier_model": "CLARIFICATION_CLARIFIER_MODEL",
        "clarification_base_url": "CLARIFICATION_BASE_URL",
        "clarification_api_key": "CLARIFICATION_API_KEY",
        "instruction_builder_model": "CLARIFICATION_INSTRUCTION_BUILDER_MODEL",
    }

    env = dict(os.environ)
    for attr_name, env_key in mapping.items():
        value = getattr(args, attr_name, None)
        if value is not None:
            env[env_key] = str(value)

    if getattr(args, "enable_clarification", False):
        env["ENABLE_CLARIFICATION"] = "true"
    if getattr(args, "enable_reasoning_summaries", False):
        env["ENABLE_REASONING_SUMMARIES"] = "true"

    return env


def load_config(args: argparse.Namespace) -> ResearchConfig:
    """Load config from file + env, then layer CLI overrides on top."""

    cli_env = build_cli_env(args)
    config_path = getattr(args, "config", None)
    return ResearchConfig.load(config_path=config_path, env=cli_env)


def resolve_system_prompt(args: argparse.Namespace) -> str:
    """Resolve the startup system prompt."""

    if getattr(args, "system_prompt_file", None):
        path = Path(args.system_prompt_file)
        return path.read_text(encoding="utf-8").strip()
    if getattr(args, "system_prompt", None):
        return args.system_prompt
    return DEFAULT_SYSTEM_PROMPT


def get_provider_defaults(provider: str, api_style: str) -> ResearchConfig:
    """Return provider-aware defaults for the selected provider."""

    env = {
        "RESEARCH_PROVIDER": provider,
        "RESEARCH_API_STYLE": api_style,
    }
    return ResearchConfig.from_env(env=env)


def normalize_answers(questions: list[str], answers: list[str]) -> list[str]:
    """Pad missing answers with the standard placeholder."""

    normalized: list[str] = []
    for index, _question in enumerate(questions):
        answer = answers[index] if index < len(answers) else ""
        stripped = answer.strip()
        normalized.append(stripped if stripped else NO_ANSWER_PLACEHOLDER)
    return normalized


def parse_task_id_from_output(text: str) -> str | None:
    """Extract a task identifier from report or status output."""

    patterns = [
        r"\*\*Task ID\*\*:\s*`?([A-Za-z0-9_.:-]+)`?",
        r"Task ID:\s*`?([A-Za-z0-9_.:-]+)`?",
        r"Task\s+([A-Za-z0-9_.:-]+)\s+status:",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def render_agent_clarification_output(query: str, result: dict[str, Any]) -> str:
    """Render direct-agent clarification results as readable text."""

    if not result.get("needs_clarification", False):
        assessment = result.get("query_assessment", "Query is sufficient for research")
        reasoning = result.get("reasoning", "Proceed with research directly")
        return (
            "# Query Analysis\n\n"
            f"**Original Query:** {query}\n\n"
            f"**Assessment:** {assessment}\n\n"
            f"**Recommendation:** {reasoning}\n"
        )

    questions = result.get("questions", [])
    questions_formatted = "\n".join(
        f"{index}. {question}" for index, question in enumerate(questions, start=1)
    )
    created_at = result.get("created_at")
    created_line = f"\n**Created At:** {created_at}\n" if created_at else "\n"
    return (
        "# Clarifying Questions Needed\n\n"
        f"**Original Query:** {query}\n\n"
        f"**Why clarification is helpful:** {result.get('reasoning', 'Additional context will improve research quality')}\n\n"
        f"**Session ID:** `{result.get('session_id', '')}`\n"
        f"{created_line}\n"
        "**Please answer these questions to improve the research:**\n\n"
        f"{questions_formatted}\n"
    )


def write_output_file(path: str, content: str) -> str:
    """Persist output text to disk and return the saved path."""

    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return str(target)


def format_report(result: ResearchResult) -> str:
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


def format_result_json(result: ResearchResult) -> str:
    """Format a ResearchResult as JSON."""

    data = asdict(result)
    return json.dumps(data, indent=2, ensure_ascii=False)


def format_task_status(status: ResearchTaskStatus) -> str:
    """Format a task status response."""

    parts = [f"Task ID: {status.task_id}", f"Status: {status.status}"]
    if status.created_at is not None:
        parts.append(f"Created: {status.created_at}")
    if status.completed_at is not None:
        parts.append(f"Completed: {status.completed_at}")
    if status.message:
        parts.append(f"Message: {status.message}")
    if status.error:
        parts.append(f"Error: {status.error}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# MCP helpers
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _mcp_connect(url: str) -> AsyncIterator:
    """Connect to an MCP server over Streamable HTTP."""

    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async with streamablehttp_client(url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            yield session


async def _mcp_progress_callback(
    progress: float, total: float | None, message: str | None
) -> None:
    del progress, total, message


def _render_mcp_result(result: Any) -> str:
    """Extract text from an MCP CallToolResult."""

    from mcp import types

    if result.structuredContent is not None:
        structured_content = result.structuredContent
        if isinstance(structured_content, dict) and "result" in structured_content:
            value = structured_content.get("result")
            return value if isinstance(value, str) else str(value)
        return str(structured_content)

    parts: list[str] = []
    for item in result.content or []:
        if isinstance(item, types.TextContent):
            parts.append(item.text)
        else:
            parts.append(str(item))
    return "\n".join(parts)


async def mcp_research(
    url: str,
    query: str,
    system_instructions: str,
    include_analysis: bool,
    request_clarification: bool,
) -> tuple[int, str]:
    """Call the deep_research MCP tool."""

    async with _mcp_connect(url) as session:
        result = await session.call_tool(
            "deep_research",
            {
                "query": query,
                "system_instructions": system_instructions,
                "include_analysis": include_analysis,
                "request_clarification": request_clarification,
                "callback_url": "",
            },
            progress_callback=_mcp_progress_callback,
        )
        return (2 if result.isError else 0, _render_mcp_result(result))


async def mcp_research_with_context(
    url: str,
    session_id: str,
    answers: list[str],
    system_instructions: str,
    include_analysis: bool,
) -> tuple[int, str]:
    """Call the research_with_context MCP tool."""

    async with _mcp_connect(url) as session:
        result = await session.call_tool(
            "research_with_context",
            {
                "session_id": session_id,
                "answers": answers,
                "system_instructions": system_instructions,
                "include_analysis": include_analysis,
                "callback_url": "",
            },
            progress_callback=_mcp_progress_callback,
        )
        return (2 if result.isError else 0, _render_mcp_result(result))


async def mcp_status(url: str, task_id: str) -> tuple[int, str]:
    """Call the research_status MCP tool."""

    async with _mcp_connect(url) as session:
        result = await session.call_tool(
            "research_status",
            {"task_id": task_id},
            progress_callback=_mcp_progress_callback,
        )
        return (2 if result.isError else 0, _render_mcp_result(result))


def parse_mcp_clarification(text: str) -> tuple[str | None, list[str]]:
    """Parse session ID and numbered clarification questions."""

    session_match = re.search(r"Session ID:\s*`([^`]+)`", text)
    session_id = session_match.group(1) if session_match else None
    questions = re.findall(r"^\d+\.\s+(.+)$", text, re.MULTILINE)
    return session_id, questions


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


class DeepResearchTUI(App[None]):
    """Interactive terminal UI for deep research workflows."""

    TITLE = "Deep Research TUI"
    SUB_TITLE = "Neon operations deck for clarification and autonomous research"

    CSS = """
    Screen {
        background: #05070d;
        color: #dffcff;
    }

    Header {
        background: #090f1b;
        color: #00f5ff;
        border-bottom: solid #17324b;
    }

    Footer {
        background: #090f1b;
        color: #89ff00;
        border-top: solid #17324b;
    }

    #layout {
        layout: horizontal;
        height: 1fr;
    }

    #control-dock {
        width: 44;
        min-width: 38;
        max-width: 52;
        padding: 1;
        border-right: solid #17324b;
        background: #070b12;
    }

    #output-dock {
        padding: 1 2;
        background: #04070d;
    }

    .panel {
        border: round #153a58;
        background: #08111d;
        padding: 0 1 1 1;
        margin-bottom: 1;
    }

    .panel-title {
        color: #ff4fa3;
        text-style: bold;
        padding: 0 0 1 0;
    }

    .helper-copy {
        color: #89ff00;
        text-style: italic;
    }

    .question-copy {
        color: #dffcff;
        padding-bottom: 1;
    }

    .field-label {
        color: #89ff00;
        padding-top: 1;
    }

    Input,
    Select,
    TextArea {
        background: #050b14;
        color: #dffcff;
        border: tall #17324b;
    }

    Input:focus,
    Select:focus,
    TextArea:focus {
        border: tall #00f5ff;
    }

    Switch {
        padding: 0 0 1 0;
    }

    Switch:focus {
        background: #0b1624;
        tint: #00f5ff 25%;
    }

    Button {
        width: 1fr;
        margin-top: 1;
        border: tall #17324b;
        background: #0d1523;
        color: #dffcff;
    }

    Button.primary {
        background: #ff2d95;
        color: #05070d;
        text-style: bold;
    }

    Button.secondary {
        background: #00d4ff;
        color: #05070d;
        text-style: bold;
    }

    Button:hover {
        tint: #00f5ff 15%;
    }

    #brand {
        color: #00f5ff;
        text-style: bold;
        padding-bottom: 1;
    }

    #app-status {
        color: #89ff00;
        padding-bottom: 1;
    }

    #output-title {
        color: #ff4fa3;
        text-style: bold;
        padding-bottom: 1;
    }

    #output-meta {
        color: #89ff00;
        padding-bottom: 1;
    }

    #output-text {
        height: 1fr;
        border: round #00f5ff;
        background: #03060c;
        color: #dffcff;
    }

    #query,
    #system-prompt,
    #output-text {
        min-height: 8;
    }

    #system-prompt {
        min-height: 10;
    }

    .answer-card {
        border: tall #122a40;
        background: #07101b;
        padding: 1;
        margin-top: 1;
    }

    .answer-input {
        margin-top: 1;
    }

    Collapsible {
        margin-bottom: 1;
    }
    """

    BINDINGS = [
        ("c", "run_clarification", "Clarify"),
        ("r", "run_research", "Research"),
        ("t", "check_status", "Status"),
        ("s", "save_output", "Save"),
        ("q", "quit", "Quit"),
    ]

    busy = reactive(False)
    current_status = reactive("Idle // ready for new instructions")

    def __init__(self, startup: StartupState):
        super().__init__()
        self.startup = startup
        self.latest_output = ""
        self.latest_output_title = "Signal Buffer"
        self.latest_task_id = startup.task_id.strip()
        self.pending_clarification_session_id: str | None = None
        self.pending_clarification_query: str | None = None
        self.pending_clarification_questions: list[str] = []
        self._agent: DeepResearchAgent | None = None
        self._agent_signature: str | None = None
        self._hydrating = True

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True, icon="<>")
        with Horizontal(id="layout"):
            with VerticalScroll(id="control-dock"):
                yield Static("DEEP RESEARCH // NIGHT DECK", id="brand")
                yield Static(self.current_status, id="app-status")

                with Container(classes="panel"):
                    yield Static("Session", classes="panel-title")
                    yield Label("Mode", classes="field-label")
                    yield Select(MODE_OPTIONS, id="mode", allow_blank=False)

                    yield Label("Save Path", classes="field-label")
                    yield Input(
                        value=self.startup.save_path,
                        placeholder=DEFAULT_SAVE_PATH,
                        id="save-path",
                    )

                    yield Label("Task ID", classes="field-label")
                    yield Input(
                        value=self.startup.task_id,
                        placeholder="Paste a task id or let the TUI detect one",
                        id="task-id",
                    )

                with Container(classes="panel", id="agent-settings"):
                    yield Static("Agent Runtime", classes="panel-title")
                    yield Label("Provider", classes="field-label")
                    yield Select(PROVIDER_OPTIONS, id="provider", allow_blank=False)

                    yield Label("OpenAI API Style", classes="field-label")
                    yield Select(
                        API_STYLE_OPTIONS,
                        id="api-style",
                        allow_blank=False,
                    )

                    yield Label("Model", classes="field-label")
                    yield Input(
                        value=self.startup.config.model or "",
                        placeholder="Provider default model",
                        id="model",
                    )

                    yield Label("Provider Base URL", classes="field-label")
                    yield Input(
                        value=self.startup.config.base_url or "",
                        placeholder="Provider endpoint",
                        id="base-url",
                    )

                    yield Label("Provider API Key", classes="field-label")
                    yield Input(
                        value=self.startup.config.api_key or "",
                        placeholder="Loaded from config or env",
                        password=True,
                        id="api-key",
                    )

                with Container(classes="panel", id="mcp-settings"):
                    yield Static("MCP Connection", classes="panel-title")
                    yield Label("MCP Server URL", classes="field-label")
                    yield Input(
                        value=self.startup.server_url,
                        placeholder=DEFAULT_MCP_SERVER_URL,
                        id="server-url",
                    )
                    yield Static(
                        "Connect to a running streamable HTTP MCP server.",
                        classes="helper-copy",
                    )

                with Container(classes="panel"):
                    yield Static("Research Query", classes="panel-title")
                    yield Label("Query", classes="field-label")
                    yield TextArea(
                        self.startup.query,
                        id="query",
                        soft_wrap=True,
                        placeholder="What do you want to investigate?",
                    )

                    yield Label("System Prompt", classes="field-label")
                    yield TextArea(
                        self.startup.system_prompt,
                        id="system-prompt",
                        soft_wrap=True,
                        placeholder="Optional system guidance",
                    )

                with Container(classes="panel"):
                    yield Static("Execution Flags", classes="panel-title")
                    yield Label("Include Analysis Tools", classes="field-label")
                    yield Switch(self.startup.include_analysis, id="include-analysis")

                    yield Label("Enable Clarification Pipeline", classes="field-label")
                    yield Switch(
                        self.startup.config.enable_clarification,
                        id="enable-clarification",
                    )

                    yield Label("JSON Output", classes="field-label")
                    yield Switch(self.startup.json_output, id="json-output")

                with Collapsible(
                    title="Advanced Controls",
                    collapsed=True,
                    classes="panel",
                    id="advanced-controls",
                ):
                    yield Label("Timeout (seconds)", classes="field-label")
                    yield Input(
                        value=str(self.startup.config.timeout),
                        placeholder="1800",
                        id="timeout",
                    )

                    yield Label("Poll Interval (seconds)", classes="field-label")
                    yield Input(
                        value=str(self.startup.config.poll_interval),
                        placeholder="30",
                        id="poll-interval",
                    )

                    yield Label("Log Level", classes="field-label")
                    yield Select(
                        LOG_LEVEL_OPTIONS,
                        id="log-level",
                        allow_blank=False,
                    )

                    yield Label("Triage Model", classes="field-label")
                    yield Input(
                        value=self.startup.config.triage_model,
                        placeholder="gpt-5-mini",
                        id="triage-model",
                    )

                    yield Label("Clarifier Model", classes="field-label")
                    yield Input(
                        value=self.startup.config.clarifier_model,
                        placeholder="gpt-5-mini",
                        id="clarifier-model",
                    )

                    yield Label("Instruction Builder Model", classes="field-label")
                    yield Input(
                        value=self.startup.config.instruction_builder_model,
                        placeholder="gpt-5-mini",
                        id="instruction-builder-model",
                    )

                    yield Label("Clarification Base URL", classes="field-label")
                    yield Input(
                        value=self.startup.config.clarification_base_url or "",
                        placeholder="Optional clarification endpoint",
                        id="clarification-base-url",
                    )

                    yield Label("Clarification API Key", classes="field-label")
                    yield Input(
                        value=self.startup.config.clarification_api_key or "",
                        placeholder="Optional clarification key",
                        password=True,
                        id="clarification-api-key",
                    )

                with Container(classes="panel"):
                    yield ClarificationAnswersPanel(id="clarification-answers")

                with Container(classes="panel"):
                    yield Static("Actions", classes="panel-title")
                    with Horizontal():
                        yield Button(
                            "Clarify",
                            id="run-clarification",
                            classes="secondary",
                        )
                        yield Button("Research", id="run-research", classes="primary")
                    with Horizontal():
                        yield Button("Status", id="run-status")
                        yield Button("Save Output", id="save-output")

            with Vertical(id="output-dock"):
                yield Static(self.latest_output_title, id="output-title")
                yield Static("", id="output-meta")
                yield TextArea(
                    "",
                    id="output-text",
                    read_only=True,
                    soft_wrap=True,
                    show_line_numbers=False,
                    placeholder="Clarification notes, reports, and task status will appear here.",
                )

        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#mode", Select).value = self.startup.mode
        self.query_one("#provider", Select).value = self.startup.config.provider
        self.query_one("#api-style", Select).value = self.startup.config.api_style
        self.query_one("#log-level", Select).value = (
            self.startup.config.log_level.upper()
        )
        self._refresh_provider_defaults_ui()
        self._refresh_mode_visibility()
        self._refresh_output_meta()
        self._refresh_action_state()
        self.query_one("#query", TextArea).focus()
        self._hydrating = False

    def watch_busy(self, busy: bool) -> None:
        self.current_status = (
            "Link hot // remote research in progress"
            if busy
            else "Idle // ready for new instructions"
        )
        self.query_one("#app-status", Static).update(self.current_status)
        self._refresh_action_state()

    def _refresh_action_state(self) -> None:
        disabled = self.busy
        for widget_id in (
            "run-clarification",
            "run-research",
            "run-status",
            "save-output",
        ):
            self.query_one(f"#{widget_id}", Button).disabled = disabled

    def _refresh_output_meta(self) -> None:
        mode = self._selected_mode()
        task_id = self.latest_task_id or "none"
        session = self.pending_clarification_session_id or "none"
        if mode == "agent":
            source = self.query_one("#provider", Select).value
        else:
            source = (
                self.query_one("#server-url", Input).value.strip() or "unconfigured"
            )
        metadata = f"mode={mode}  source={source}  task={task_id}  session={session}"
        self.query_one("#output-meta", Static).update(metadata)

    def _set_output(self, title: str, text: str) -> None:
        self.latest_output_title = title
        self.latest_output = text
        self.query_one("#output-title", Static).update(title)
        self.query_one("#output-text", TextArea).load_text(text)
        detected_task_id = parse_task_id_from_output(text)
        if detected_task_id:
            self.latest_task_id = detected_task_id
            self.query_one("#task-id", Input).value = detected_task_id
        self._refresh_output_meta()

    def _clear_clarification_state(self, keep_output: bool = True) -> None:
        del keep_output
        self.pending_clarification_session_id = None
        self.pending_clarification_query = None
        self.pending_clarification_questions = []
        self.query_one(
            "#clarification-answers", ClarificationAnswersPanel
        ).set_questions([])
        self._refresh_output_meta()

    def _set_clarification_state(
        self, query: str, session_id: str | None, questions: list[str]
    ) -> None:
        self.pending_clarification_session_id = session_id
        self.pending_clarification_query = query
        self.pending_clarification_questions = list(questions)
        self.query_one(
            "#clarification-answers", ClarificationAnswersPanel
        ).set_questions(questions)
        self._refresh_output_meta()

    def _selected_mode(self) -> str:
        return str(self.query_one("#mode", Select).value)

    def _refresh_mode_visibility(self) -> None:
        mode = self._selected_mode()
        self.query_one("#agent-settings", Container).display = mode == "agent"
        self.query_one("#mcp-settings", Container).display = mode == "mcp"
        json_switch = self.query_one("#json-output", Switch)
        json_switch.disabled = mode == "mcp"
        self._refresh_output_meta()

    def _refresh_provider_defaults_ui(self) -> None:
        provider = str(self.query_one("#provider", Select).value)
        api_style_widget = self.query_one("#api-style", Select)
        current_api_style = str(api_style_widget.value)
        is_openai = provider == "openai"

        api_style_widget.disabled = not is_openai
        if not is_openai:
            api_style_widget.value = "responses"
            current_api_style = "responses"

        defaults = get_provider_defaults(provider, current_api_style)
        self.query_one("#model", Input).value = defaults.model
        self.query_one("#base-url", Input).value = defaults.base_url or ""

    def _collect_answers(self) -> list[str]:
        answer_inputs = self.query_one(
            "#clarification-answers", ClarificationAnswersPanel
        ).query(Input)
        return normalize_answers(
            self.pending_clarification_questions,
            [answer_input.value for answer_input in answer_inputs],
        )

    def _runtime_env(self) -> dict[str, str]:
        provider = str(self.query_one("#provider", Select).value)
        api_style = str(self.query_one("#api-style", Select).value)

        env = dict(os.environ)
        env["RESEARCH_PROVIDER"] = provider
        env["RESEARCH_MODEL"] = self.query_one("#model", Input).value
        env["RESEARCH_API_KEY"] = self.query_one("#api-key", Input).value
        env["RESEARCH_BASE_URL"] = self.query_one("#base-url", Input).value
        env["RESEARCH_API_STYLE"] = api_style
        env["RESEARCH_TIMEOUT"] = self.query_one("#timeout", Input).value
        env["RESEARCH_POLL_INTERVAL"] = self.query_one("#poll-interval", Input).value
        env["LOGGING_LEVEL"] = str(self.query_one("#log-level", Select).value)
        env["CLARIFICATION_TRIAGE_MODEL"] = self.query_one("#triage-model", Input).value
        env["CLARIFICATION_CLARIFIER_MODEL"] = self.query_one(
            "#clarifier-model", Input
        ).value
        env["CLARIFICATION_INSTRUCTION_BUILDER_MODEL"] = self.query_one(
            "#instruction-builder-model", Input
        ).value
        env["CLARIFICATION_BASE_URL"] = self.query_one(
            "#clarification-base-url", Input
        ).value
        env["CLARIFICATION_API_KEY"] = self.query_one(
            "#clarification-api-key", Input
        ).value
        env["ENABLE_CLARIFICATION"] = str(
            self.query_one("#enable-clarification", Switch).value
        ).lower()
        env["ENABLE_REASONING_SUMMARIES"] = "false"
        return env

    def _build_runtime_config(
        self, *, force_enable_clarification: bool = False
    ) -> ResearchConfig:
        config = ResearchConfig.load(
            config_path=self.startup.config_path,
            env=self._runtime_env(),
        )
        if force_enable_clarification:
            config.enable_clarification = True
        config.validate()
        return config

    def _config_signature(self, config: ResearchConfig) -> str:
        return json.dumps(asdict(config), sort_keys=True)

    def _ensure_agent(self, config: ResearchConfig) -> DeepResearchAgent:
        signature = self._config_signature(config)
        if self._agent is None or self._agent_signature != signature:
            if (
                self._agent_signature is not None
                and self.pending_clarification_session_id
            ):
                self._clear_clarification_state()
                self.notify(
                    "Configuration changed; pending clarification session was cleared.",
                    severity="warning",
                )
            self._agent = DeepResearchAgent(config)
            self._agent_signature = signature
        return self._agent

    def _query_text(self) -> str:
        return self.query_one("#query", TextArea).text.strip()

    def _system_prompt_text(self) -> str:
        system_prompt = self.query_one("#system-prompt", TextArea).text.strip()
        return system_prompt or DEFAULT_SYSTEM_PROMPT

    def _include_analysis(self) -> bool:
        return self.query_one("#include-analysis", Switch).value

    def _server_url(self) -> str:
        return self.query_one("#server-url", Input).value.strip()

    def _task_id(self) -> str:
        task_id = self.query_one("#task-id", Input).value.strip()
        return task_id or self.latest_task_id

    def action_run_clarification(self) -> None:
        if self.busy:
            self.notify("An operation is already running.", severity="warning")
            return
        self._run_clarification_worker()

    def action_run_research(self) -> None:
        if self.busy:
            self.notify("An operation is already running.", severity="warning")
            return
        self._run_research_worker()

    def action_check_status(self) -> None:
        if self.busy:
            self.notify("An operation is already running.", severity="warning")
            return
        self._run_status_worker()

    def action_save_output(self) -> None:
        if not self.latest_output.strip():
            self.notify("There is no output to save yet.", severity="warning")
            return

        save_path = (
            self.query_one("#save-path", Input).value.strip() or DEFAULT_SAVE_PATH
        )
        saved_path = write_output_file(save_path, self.latest_output)
        self.notify(f"Saved output to {saved_path}", severity="information")

    @on(Button.Pressed, "#run-clarification")
    def on_run_clarification_pressed(self, _event: Button.Pressed) -> None:
        self.action_run_clarification()

    @on(Button.Pressed, "#run-research")
    def on_run_research_pressed(self, _event: Button.Pressed) -> None:
        self.action_run_research()

    @on(Button.Pressed, "#run-status")
    def on_run_status_pressed(self, _event: Button.Pressed) -> None:
        self.action_check_status()

    @on(Button.Pressed, "#save-output")
    def on_save_output_pressed(self, _event: Button.Pressed) -> None:
        self.action_save_output()

    @on(Select.Changed, "#mode")
    def on_mode_changed(self, _event: Select.Changed) -> None:
        if self._hydrating:
            return
        self._refresh_mode_visibility()
        self._clear_clarification_state()

    @on(Select.Changed, "#provider")
    def on_provider_changed(self, _event: Select.Changed) -> None:
        if self._hydrating:
            return
        self._refresh_provider_defaults_ui()

    @on(Select.Changed, "#api-style")
    def on_api_style_changed(self, _event: Select.Changed) -> None:
        if self._hydrating:
            return
        self._refresh_provider_defaults_ui()

    @on(Input.Changed, "#server-url")
    def on_server_url_changed(self, _event: Input.Changed) -> None:
        self._refresh_output_meta()

    @work(group="operations", exclusive=True, exit_on_error=False)
    async def _run_clarification_worker(self) -> None:
        query = self._query_text()
        if not query:
            self.notify("Enter a research query first.", severity="warning")
            return

        self.busy = True
        try:
            self._set_output(
                "Clarification // running", "Negotiating a clarification session..."
            )
            mode = self._selected_mode()
            if mode == "agent":
                config = self._build_runtime_config(force_enable_clarification=True)
                agent = self._ensure_agent(config)
                result = await agent.start_clarification_async(query)
                rendered = render_agent_clarification_output(query, result)
                self._set_output("Clarification // agent", rendered)
                if result.get("needs_clarification", False):
                    self._set_clarification_state(
                        query,
                        result.get("session_id"),
                        list(result.get("questions", [])),
                    )
                    self.notify(
                        "Clarification questions loaded into the control panel.",
                        severity="information",
                    )
                else:
                    self._clear_clarification_state()
                    self.notify(
                        "No clarification needed. The query is ready for research.",
                        severity="information",
                    )
                return

            server_url = self._server_url()
            if not server_url:
                self.notify("Set an MCP server URL first.", severity="warning")
                return

            rc, text = await mcp_research(
                url=server_url,
                query=query,
                system_instructions=self._system_prompt_text(),
                include_analysis=self._include_analysis(),
                request_clarification=True,
            )
            self._set_output("Clarification // mcp", text)

            session_id, questions = parse_mcp_clarification(text)
            if session_id and questions:
                self._set_clarification_state(query, session_id, questions)
                self.notify(
                    "Clarification questions received from the MCP server.",
                    severity="information",
                )
            else:
                self._clear_clarification_state()
                severity = "error" if rc else "information"
                message = (
                    "Clarification request failed."
                    if rc
                    else "The MCP server reported that no clarification is needed."
                )
                self.notify(message, severity=severity)
        except ResearchError as error:
            self._set_output("Clarification // error", f"Research error: {error}")
            self.notify(str(error), severity="error")
        except Exception as error:  # pylint: disable=broad-exception-caught
            self._set_output("Clarification // error", f"Unexpected error: {error}")
            self.notify(str(error), severity="error")
        finally:
            self.busy = False

    @work(group="operations", exclusive=True, exit_on_error=False)
    async def _run_research_worker(self) -> None:
        query = self._query_text()
        if not query:
            self.notify("Enter a research query first.", severity="warning")
            return

        self.busy = True
        try:
            self._set_output("Research // running", "Booting the research worker...")
            mode = self._selected_mode()
            include_analysis = self._include_analysis()
            system_prompt = self._system_prompt_text()

            if (
                self.pending_clarification_session_id
                and self.pending_clarification_query
                and self.pending_clarification_query != query
            ):
                self._clear_clarification_state()
                self.notify(
                    "The query changed, so the previous clarification session was discarded.",
                    severity="warning",
                )

            if mode == "agent":
                use_pending_clarification = (
                    self.pending_clarification_session_id is not None
                )
                config = self._build_runtime_config(
                    force_enable_clarification=use_pending_clarification
                )
                agent = self._ensure_agent(config)
                working_query = query

                if use_pending_clarification and self.pending_clarification_questions:
                    answers = self._collect_answers()
                    session_status = agent.add_clarification_answers(
                        self.pending_clarification_session_id or "",
                        answers,
                    )
                    if session_status.get("error"):
                        self._clear_clarification_state()
                        self.notify(
                            "The clarification session expired. Run clarification again.",
                            severity="warning",
                        )
                    else:
                        enriched_query = await agent.get_enriched_query_async(
                            self.pending_clarification_session_id or ""
                        )
                        if enriched_query:
                            working_query = enriched_query

                result = await agent.research(
                    query=working_query,
                    system_prompt=system_prompt,
                    include_code_interpreter=include_analysis,
                )

                if result.status == "completed":
                    text = (
                        format_result_json(result)
                        if self.query_one("#json-output", Switch).value
                        else format_report(result)
                    )
                    self._set_output("Research // completed", text)
                    if result.task_id:
                        self.latest_task_id = result.task_id
                        self.query_one("#task-id", Input).value = result.task_id
                    self.notify(
                        "Deep research completed successfully.", severity="information"
                    )
                    return

                message = result.message or "Unknown provider failure"
                if result.error_code:
                    message = f"{message} (code: {result.error_code})"
                self._set_output("Research // failed", message)
                self.notify(message, severity="error")
                return

            server_url = self._server_url()
            if not server_url:
                self.notify("Set an MCP server URL first.", severity="warning")
                return

            if (
                self.pending_clarification_session_id
                and self.pending_clarification_questions
            ):
                answers = self._collect_answers()
                rc, text = await mcp_research_with_context(
                    url=server_url,
                    session_id=self.pending_clarification_session_id,
                    answers=answers,
                    system_instructions=system_prompt,
                    include_analysis=include_analysis,
                )
            else:
                rc, text = await mcp_research(
                    url=server_url,
                    query=query,
                    system_instructions=system_prompt,
                    include_analysis=include_analysis,
                    request_clarification=False,
                )

            self._set_output("Research // mcp", text)
            if rc:
                self.notify("The MCP research request failed.", severity="error")
            else:
                self.notify(
                    "Deep research completed successfully.", severity="information"
                )
        except ResearchError as error:
            self._set_output("Research // error", f"Research error: {error}")
            self.notify(str(error), severity="error")
        except Exception as error:  # pylint: disable=broad-exception-caught
            self._set_output("Research // error", f"Unexpected error: {error}")
            self.notify(str(error), severity="error")
        finally:
            self.busy = False

    @work(group="operations", exclusive=True, exit_on_error=False)
    async def _run_status_worker(self) -> None:
        task_id = self._task_id()
        if not task_id:
            self.notify("Enter or detect a task id first.", severity="warning")
            return

        self.busy = True
        try:
            self._set_output(
                "Status // running", f"Checking task status for {task_id}..."
            )
            mode = self._selected_mode()
            if mode == "agent":
                config = self._build_runtime_config()
                agent = self._ensure_agent(config)
                status = await agent.get_task_status(task_id)
                self._set_output("Status // agent", format_task_status(status))
                self.notify("Task status updated.", severity="information")
                return

            server_url = self._server_url()
            if not server_url:
                self.notify("Set an MCP server URL first.", severity="warning")
                return

            rc, text = await mcp_status(server_url, task_id)
            self._set_output("Status // mcp", text)
            severity = "error" if rc else "information"
            self.notify("Task status updated.", severity=severity)
        except ResearchError as error:
            self._set_output("Status // error", f"Research error: {error}")
            self.notify(str(error), severity="error")
        except Exception as error:  # pylint: disable=broad-exception-caught
            self._set_output("Status // error", f"Unexpected error: {error}")
            self.notify(str(error), severity="error")
        finally:
            self.busy = False


# ---------------------------------------------------------------------------
# Argument parsing and entry point
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the startup argument parser."""

    parser = argparse.ArgumentParser(
        prog="deep-research-tui",
        description="Interactive full-screen TUI for deep research workflows.",
    )

    parser.add_argument(
        "--config",
        default=None,
        metavar="PATH",
        help="Path to TOML config file (default: ~/.deep_research)",
    )
    parser.add_argument(
        "--mode",
        default=None,
        choices=["agent", "mcp"],
        help="Startup mode (defaults to agent unless --server-url is provided)",
    )
    parser.add_argument(
        "--server-url",
        default="",
        help="MCP server URL for client mode",
    )
    parser.add_argument(
        "--query",
        default="",
        help="Initial research query to prefill",
    )
    parser.add_argument(
        "--task-id",
        default="",
        help="Initial task id to prefill",
    )
    parser.add_argument(
        "--output-file",
        default=DEFAULT_SAVE_PATH,
        metavar="PATH",
        help="Default output save path",
    )
    parser.add_argument(
        "--no-analysis",
        action="store_true",
        help="Disable code interpreter / analysis tools",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Enable JSON output in agent mode",
    )
    prompt_group = parser.add_mutually_exclusive_group()
    prompt_group.add_argument(
        "--system-prompt",
        default=None,
        help="Inline system prompt text",
    )
    prompt_group.add_argument(
        "--system-prompt-file",
        default=None,
        metavar="PATH",
        help="Read the system prompt from a file",
    )

    parser.add_argument(
        "--provider",
        default=None,
        choices=["openai", "gemini", "open-deep-research"],
        help="Research provider",
    )
    parser.add_argument("--model", default=None, help="Model or agent ID")
    parser.add_argument("--api-key", default=None, help="Provider API key")
    parser.add_argument("--base-url", default=None, help="Provider API base URL")
    parser.add_argument(
        "--api-style",
        default=None,
        choices=["responses", "chat_completions"],
        help="OpenAI API style",
    )
    parser.add_argument(
        "--timeout",
        default=None,
        type=float,
        help="Max research timeout in seconds",
    )
    parser.add_argument(
        "--poll-interval",
        default=None,
        type=float,
        help="Task poll interval in seconds",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level",
    )
    parser.add_argument(
        "--enable-clarification",
        action="store_true",
        default=False,
        help="Enable the clarification pipeline on startup",
    )
    parser.add_argument(
        "--enable-reasoning-summaries",
        action="store_true",
        default=False,
        help="Enable reasoning summaries",
    )
    parser.add_argument("--triage-model", default=None, help="Model for query triage")
    parser.add_argument(
        "--clarifier-model", default=None, help="Model for query enrichment"
    )
    parser.add_argument(
        "--clarification-base-url",
        default=None,
        help="Base URL for clarification models",
    )
    parser.add_argument(
        "--clarification-api-key",
        default=None,
        help="API key for clarification models",
    )
    parser.add_argument(
        "--instruction-builder-model",
        default=None,
        help="Model for instruction building",
    )

    return parser


def build_startup_state(args: argparse.Namespace) -> StartupState:
    """Build the initial app state from CLI args and config."""

    config = load_config(args)
    config.validate()
    mode = args.mode or ("mcp" if args.server_url else "agent")
    return StartupState(
        config_path=args.config,
        mode=mode,
        server_url=args.server_url or DEFAULT_MCP_SERVER_URL,
        query=args.query,
        task_id=args.task_id,
        save_path=args.output_file or DEFAULT_SAVE_PATH,
        system_prompt=resolve_system_prompt(args),
        include_analysis=not args.no_analysis,
        json_output=args.json_output,
        config=config,
    )


def main() -> None:
    """Launch the TUI."""

    parser = build_parser()
    args = parser.parse_args()
    startup = build_startup_state(args)

    level_name = (getattr(args, "log_level", None) or startup.config.log_level).upper()
    log_level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(level=log_level, format="%(message)s")
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
    )

    app = DeepResearchTUI(startup)
    app.run()


if __name__ == "__main__":
    main()
