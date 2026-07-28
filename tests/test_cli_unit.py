# -*- coding: utf-8 -*-

"""Tests for the standalone CLI argument contract."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType

import pytest


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


@pytest.mark.parametrize(
    "arguments",
    [
        ["--enable-clarification", "config"],
        ["--triage-model", "gpt-5-mini", "config"],
        ["--clarifier-model", "gpt-5-mini", "config"],
        ["--clarification-base-url", "https://example.com/v1", "config"],
        ["--clarification-api-key", "test", "config"],
        ["--instruction-builder-model", "gpt-5-mini", "config"],
        ["research", "test query", "--clarify"],
    ],
)
def test_removed_clarification_flags_are_rejected(arguments: list[str]) -> None:
    parser = load_cli_module().build_parser()

    with pytest.raises(SystemExit) as error:
        parser.parse_args(arguments)

    assert error.value.code == 2
