# -*- coding: utf-8 -*-

"""
Tests for prompt loading and auto-discovery.
"""

import os
from pathlib import Path

from deep_research_mcp.prompts import PromptManager


def test_prompt_manager_discovers_bundled_prompts_directory():
    """PromptManager should find bundled prompts relative to prompts.py."""
    repo_root = Path(__file__).resolve().parents[1]
    original_home = os.environ.get("HOME")
    original_prompts_dir = os.environ.get("DEEP_RESEARCH_PROMPTS_DIR")

    os.environ["HOME"] = str(repo_root / ".tmp-test-home")
    os.environ.pop("DEEP_RESEARCH_PROMPTS_DIR", None)

    try:
        manager = PromptManager()
        assert (
            manager.prompts_dir
            == (repo_root / "src/deep_research_mcp/prompts").resolve()
        )
        prompt = manager.get_instruction_builder_prompt("quantum computing")
        assert "quantum computing" in prompt
    finally:
        if original_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = original_home

        if original_prompts_dir is None:
            os.environ.pop("DEEP_RESEARCH_PROMPTS_DIR", None)
        else:
            os.environ["DEEP_RESEARCH_PROMPTS_DIR"] = original_prompts_dir


def test_prompt_manager_loads_from_package_resources_when_filesystem_missing():
    """Package-resource fallback should still work when no filesystem directory is used."""
    manager = PromptManager()
    manager.prompts_cache.clear()
    manager.prompts_dir = None

    prompt = manager.get_triage_prompt("artificial intelligence")
    assert "artificial intelligence" in prompt
