# -*- coding: utf-8 -*-

"""Minimal offline tests for config loading and validation.
Avoid importing the package root to prevent optional deps from loading.
"""

from __future__ import annotations

import os
import pathlib
import importlib.util
import types
import pytest


ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "src" / "deep_research_mcp" / "config.py"


def load_config_module() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(
        "deep_research_mcp_config", str(CONFIG_PATH)
    )
    assert spec and spec.loader, "Failed to create spec for config.py"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


def test_from_env_requires_api_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    cfg_mod = load_config_module()
    with pytest.raises(ValueError):
        cfg_mod.ResearchConfig.from_env()


def test_from_env_loads_overrides(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setenv("RESEARCH_MODEL", "o4-mini-deep-research-2025-06-26")
    monkeypatch.setenv("RESEARCH_TIMEOUT", "120")
    monkeypatch.setenv("POLL_INTERVAL", "5")
    monkeypatch.setenv("MAX_RETRIES", "7")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    cfg_mod = load_config_module()
    cfg = cfg_mod.ResearchConfig.from_env()

    assert cfg.api_key == "sk-test-key"
    assert cfg.model == "o4-mini-deep-research-2025-06-26"
    assert cfg.timeout == 120.0
    assert cfg.poll_interval == 5.0
    assert cfg.max_retries == 7
    assert cfg.log_level == "DEBUG"


def test_validate_passes_with_valid_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-valid")
    cfg_mod = load_config_module()
    cfg = cfg_mod.ResearchConfig.from_env()
    assert cfg.validate() is True


def test_validate_rejects_invalid_model(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-valid")
    monkeypatch.setenv("RESEARCH_MODEL", "not-a-real-model")
    cfg_mod = load_config_module()
    cfg = cfg_mod.ResearchConfig.from_env()
    with pytest.raises(ValueError):
        cfg.validate()
