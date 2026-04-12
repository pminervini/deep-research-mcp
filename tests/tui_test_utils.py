# -*- coding: utf-8 -*-

"""Shared helpers for testing the deep research TUI module."""

from __future__ import annotations

from functools import lru_cache
import importlib.util
from pathlib import Path
import sys
from types import ModuleType


@lru_cache(maxsize=1)
def load_tui_module() -> ModuleType:
    """Import the TUI module once and reuse it across test files."""
    module_path = (
        Path(__file__).resolve().parent.parent / "cli" / "deep-research-tui.py"
    )
    module_name = "deep_research_tui_test_module"

    if module_name in sys.modules:
        return sys.modules[module_name]

    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module
