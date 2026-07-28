# -*- coding: utf-8 -*-

"""Tests for the standalone CLI argument contract."""

from __future__ import annotations

import importlib.util
from importlib.metadata import entry_points
from pathlib import Path
import sys
from types import ModuleType


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
