# -*- coding: utf-8 -*-

"""
Tests for TOML configuration loading.
"""

import os

from deep_research_mcp.config import ResearchConfig, load_config_file


def test_load_config_file_is_side_effect_free(tmp_path):
    """Test TOML loading returns data without mutating environment variables."""
    config_path = tmp_path / ".deep_research"
    config_path.write_text(
        '[research]\nmodel = "file-model"\nprovider = "gemini"\n', encoding="utf-8"
    )

    original_model = os.environ.get("RESEARCH_MODEL")
    os.environ.pop("RESEARCH_MODEL", None)

    try:
        config_data = load_config_file(config_path)
        assert config_data["research"]["model"] == "file-model"
        assert "RESEARCH_MODEL" not in os.environ
    finally:
        if original_model is None:
            os.environ.pop("RESEARCH_MODEL", None)
        else:
            os.environ["RESEARCH_MODEL"] = original_model


def test_load_merges_toml_with_environment_overrides(tmp_path):
    """Test explicit config loading merges TOML values with environment overrides."""
    config_path = tmp_path / ".deep_research"
    config_path.write_text(
        '[research]\nprovider = "gemini"\nmodel = "file-model"\ntimeout = 45\n',
        encoding="utf-8",
    )

    config = ResearchConfig.load(
        config_path=config_path,
        env={
            "RESEARCH_MODEL": "env-model",
            "RESEARCH_TIMEOUT": "90",
        },
    )

    assert config.provider == "gemini"
    assert config.model == "env-model"
    assert config.timeout == 90.0


def test_cancel_on_timeout_parsing():
    """cancel_on_timeout defaults to False and parses env/TOML booleans."""
    original_val = os.environ.get("RESEARCH_CANCEL_ON_TIMEOUT")
    original_model = os.environ.get("RESEARCH_MODEL")

    try:
        os.environ["RESEARCH_MODEL"] = "gpt-5-mini"
        os.environ.pop("RESEARCH_CANCEL_ON_TIMEOUT", None)

        config = ResearchConfig.from_env()
        assert config.cancel_on_timeout is False

        os.environ["RESEARCH_CANCEL_ON_TIMEOUT"] = "true"
        config = ResearchConfig.from_env()
        assert config.cancel_on_timeout is True

        os.environ["RESEARCH_CANCEL_ON_TIMEOUT"] = "false"
        config = ResearchConfig.from_env()
        assert config.cancel_on_timeout is False

    finally:
        if original_val is not None:
            os.environ["RESEARCH_CANCEL_ON_TIMEOUT"] = original_val
        else:
            os.environ.pop("RESEARCH_CANCEL_ON_TIMEOUT", None)

        if original_model is not None:
            os.environ["RESEARCH_MODEL"] = original_model
        else:
            os.environ.pop("RESEARCH_MODEL", None)
