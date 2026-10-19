# -*- coding: utf-8 -*-

"""Tests for the standalone CLI argument contract."""

from __future__ import annotations

import asyncio
import importlib.util
from importlib.metadata import entry_points
from pathlib import Path
import sys
from types import ModuleType

import pytest

from deep_research_mcp.cli import check_backend_flags, cmd_status, load_config


def load_cli_module() -> ModuleType:
    """Load the hyphenated CLI script as a Python module."""
    module_path = (
        Path(__file__).resolve().parent.parent / "cli" / "deep-research-cli.py"
    )
    module_name = "deep_research_cli_test_module"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_codex_provider_and_auth_commands_are_exposed() -> None:
    parser = load_cli_module().build_parser()

    provider_args = parser.parse_args(
        ["--provider", "openai-codex", "research", "test query"]
    )
    login_args = parser.parse_args(["auth", "login", "--import-codex", "--force"])
    status_args = parser.parse_args(["auth", "status"])
    logout_args = parser.parse_args(["auth", "logout"])

    assert provider_args.provider == "openai-codex"
    assert login_args.auth_action == "login"
    assert login_args.import_codex is True
    assert login_args.force is True
    assert status_args.auth_action == "status"
    assert logout_args.auth_action == "logout"


def test_unified_cli_is_exposed_as_an_installed_console_script() -> None:
    scripts = {
        entry.name: entry.value for entry in entry_points(group="console_scripts")
    }

    assert scripts["deep-research-cli"] == "deep_research_mcp.cli:main"
    assert scripts["deep-research-mcp"] == "deep_research_mcp.mcp_server:main"


def test_reasoning_effort_cli_overrides_toml(tmp_path: Path) -> None:
    config_path = tmp_path / ".deep_research"
    config_path.write_text(
        '[research]\nprovider = "openai-codex"\nreasoning_effort = "high"\n',
        encoding="utf-8",
    )
    cli = load_cli_module()
    args = cli.build_parser().parse_args(
        [
            "--config",
            str(config_path),
            "--reasoning-effort",
            "low",
            "research",
            "test query",
        ]
    )
    assert load_config(args).reasoning_effort == "low"


def test_tavily_cli_api_key_overrides_tavily_env(tmp_path: Path) -> None:
    config_path = tmp_path / ".deep_research"
    config_path.write_text('[research]\nprovider = "tavily"\n', encoding="utf-8")
    cli = load_cli_module()
    args = cli.build_parser().parse_args(
        [
            "--config",
            str(config_path),
            "--api-key",
            "cli-test-key",
            "research",
            "test query",
        ]
    )

    assert load_config(args).api_key == "cli-test-key"


def _write_backends_config(tmp_path: Path) -> Path:
    config_path = tmp_path / ".deep_research"
    config_path.write_text(
        "[research]\n"
        'provider = "dr-tulu"\n'
        'base_url = "http://127.0.0.1:18080"\n'
        "[backends.lab]\n"
        'provider = "tavily"\n'
        'api_key = "table-key"\n'
        'model = "pro"\n'
        "timeout = 600\n"
        "[backends.tulu-b]\n"
        'provider = "dr-tulu"\n'
        'base_url = "http://127.0.0.1:18081"\n',
        encoding="utf-8",
    )
    return config_path


def test_backend_flag_loads_named_backend(tmp_path: Path) -> None:
    config_path = _write_backends_config(tmp_path)
    cli = load_cli_module()
    args = cli.build_parser().parse_args(
        ["--config", str(config_path), "--backend", "lab", "research", "q"]
    )

    config = load_config(args)

    assert (config.provider, config.model, config.api_key) == (
        "tavily",
        "pro",
        "table-key",
    )


def test_backend_flag_rejects_provider_scoped_overrides(tmp_path: Path) -> None:
    config_path = _write_backends_config(tmp_path)
    cli = load_cli_module()
    parser = cli.build_parser()
    args = parser.parse_args(
        [
            "--config",
            str(config_path),
            "--backend",
            "lab",
            "--model",
            "mini",
            "research",
            "q",
        ]
    )

    with pytest.raises(SystemExit):
        check_backend_flags(parser, args)

    # Runtime flags are still allowed alongside --backend.
    args = parser.parse_args(
        [
            "--config",
            str(config_path),
            "--backend",
            "lab",
            "--timeout",
            "5",
            "research",
            "q",
        ]
    )
    check_backend_flags(parser, args)
    assert load_config(args).timeout == 5.0


def test_status_routes_prefixed_task_id_to_named_backend(
    tmp_path: Path, capsys
) -> None:
    """A '<backend>:<id>' task ID from MCP output selects that backend."""
    config_path = _write_backends_config(tmp_path)
    cli = load_cli_module()
    args = cli.build_parser().parse_args(
        ["--config", str(config_path), "status", "tulu-b:task-42"]
    )

    assert asyncio.run(cmd_status(args)) == 0

    output = capsys.readouterr().out
    assert "Task ID: task-42" in output
    assert "Status: unknown" in output


def test_status_strips_prefix_matching_backend_flag(tmp_path: Path, capsys) -> None:
    """--backend plus a matching prefix sends the raw ID to the provider."""
    config_path = _write_backends_config(tmp_path)
    cli = load_cli_module()
    args = cli.build_parser().parse_args(
        [
            "--config",
            str(config_path),
            "--backend",
            "tulu-b",
            "status",
            "tulu-b:task-42",
        ]
    )

    assert asyncio.run(cmd_status(args)) == 0
    assert "Task ID: task-42" in capsys.readouterr().out


def test_status_rejects_prefix_conflicting_with_backend_flag(tmp_path: Path) -> None:
    config_path = _write_backends_config(tmp_path)
    cli = load_cli_module()
    args = cli.build_parser().parse_args(
        ["--config", str(config_path), "--backend", "lab", "status", "tulu-b:task-42"]
    )

    assert asyncio.run(cmd_status(args)) == 1


def test_status_raw_id_uses_backend_flag(tmp_path: Path, capsys) -> None:
    config_path = _write_backends_config(tmp_path)
    cli = load_cli_module()
    args = cli.build_parser().parse_args(
        ["--config", str(config_path), "--backend", "tulu-b", "status", "task-42"]
    )

    assert asyncio.run(cmd_status(args)) == 0
    assert "Task ID: task-42" in capsys.readouterr().out
