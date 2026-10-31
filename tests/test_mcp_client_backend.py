# -*- coding: utf-8 -*-

"""
MCP-client-mode routing of task IDs to named backends.

These tests run the real MCP server over Streamable HTTP as a subprocess and
drive it with the real CLI and TUI client code paths.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import pytest

from deep_research_mcp.cli import cmd_status
from tests.test_cli_unit import load_cli_module
from tests.tui_test_utils import load_tui_module

TUI = load_tui_module()

# Default backend is Dr Tulu on a dead port; "lab" is openai-codex, whose
# status handler answers with a distinctive message without any network call.
SERVER_CONFIG = (
    "[research]\n"
    'provider = "dr-tulu"\n'
    'base_url = "http://127.0.0.1:18080"\n'
    "[backends.lab]\n"
    'provider = "openai-codex"\n'
)
CODEX_MESSAGE = "not available for the openai-codex provider"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(name="mcp_server_url")
def fixture_mcp_server_url(tmp_path: Path):
    """Start the MCP server over HTTP with a temp config and yield its URL."""
    (tmp_path / ".deep_research").write_text(SERVER_CONFIG, encoding="utf-8")
    env = dict(os.environ)
    env["HOME"] = str(tmp_path)
    env.pop("MCP_AUTH_ISSUER_URL", None)
    env.pop("MCP_AUTH_RESOURCE_URL", None)
    port = _free_port()
    process = subprocess.Popen(  # pylint: disable=consider-using-with
        [
            sys.executable,
            "-m",
            "deep_research_mcp.mcp_server",
            "--transport",
            "http",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.time() + 30
        while time.time() < deadline:
            if process.poll() is not None:
                raise RuntimeError("MCP server exited before accepting connections")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                    break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError("MCP server did not start listening in time")
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def test_cli_mcp_status_raw_id_uses_backend_flag(mcp_server_url, capsys):
    """--backend lab makes a raw ID reach the server's lab backend."""
    cli = load_cli_module()
    args = cli.build_parser().parse_args(
        ["--backend", "lab", "status", "task-42", "--server-url", mcp_server_url]
    )

    assert asyncio.run(cmd_status(args)) == 0

    output = capsys.readouterr().out
    payload = json.loads(output[output.index("{") :])
    assert payload["task_id"] == "lab:task-42"
    assert payload["status"] == "unknown"
    assert CODEX_MESSAGE in payload["message"]
    assert payload["result"] is None


def test_cli_mcp_status_without_backend_uses_server_default(mcp_server_url, capsys):
    cli = load_cli_module()
    args = cli.build_parser().parse_args(
        ["status", "task-42", "--server-url", mcp_server_url]
    )

    assert asyncio.run(cmd_status(args)) == 0

    output = capsys.readouterr().out
    payload = json.loads(output[output.index("{") :])
    assert payload["task_id"] == "default:task-42"
    assert payload["status"] == "unknown"
    assert CODEX_MESSAGE not in payload["message"]


def test_cli_mcp_status_rejects_conflicting_prefix(mcp_server_url):
    cli = load_cli_module()
    args = cli.build_parser().parse_args(
        ["--backend", "lab", "status", "other:task-42", "--server-url", mcp_server_url]
    )

    assert asyncio.run(cmd_status(args)) == 1


@pytest.mark.asyncio
async def test_tui_mcp_status_raw_id_uses_startup_backend(mcp_server_url):
    """The TUI started with --backend lab in MCP mode routes raw IDs to lab."""
    startup_state = TUI.StartupState(
        config_path=None,
        backend="lab",
        mode="mcp",
        server_url=mcp_server_url,
        task_id="task-42",
        config=TUI.get_provider_defaults("openai-codex"),
        provider="openai-codex",
    )
    app = TUI.DeepResearchTUI(startup_state)

    async with app.run_test(size=(140, 42)):
        # pylint: disable=protected-access
        app._check_mcp_status("task-42")
        await app.workers.wait_for_complete()
        output = app._output_text

    payload = json.loads(output)
    assert payload["task_id"] == "lab:task-42"
    assert payload["status"] == "unknown"
    assert CODEX_MESSAGE in payload["message"]
    assert payload["result"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "task_id, expect_codex",
    [
        ("default:task-42", False),
        ("lab:task-42", True),
    ],
)
async def test_tui_mcp_status_keeps_explicit_prefix(
    mcp_server_url, task_id, expect_codex
):
    """An explicit prefix wins over the TUI's startup backend in MCP mode."""
    startup_state = TUI.StartupState(
        config_path=None,
        backend="lab",
        mode="mcp",
        server_url=mcp_server_url,
        task_id=task_id,
        config=TUI.get_provider_defaults("openai-codex"),
        provider="openai-codex",
    )
    app = TUI.DeepResearchTUI(startup_state)

    async with app.run_test(size=(140, 42)):
        # pylint: disable=protected-access
        app._check_mcp_status(task_id)
        await app.workers.wait_for_complete()
        output = app._output_text

    payload = json.loads(output)
    assert payload["task_id"] == task_id
    assert payload["status"] == "unknown"
    assert (CODEX_MESSAGE in payload["message"]) is expect_codex
