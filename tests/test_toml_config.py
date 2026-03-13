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
        '[research]\nprovider = "gemini"\nmodel = "file-model"\ntimeout = 45\n[clarification]\nenable = true\ntriage_model = "file-triage"\n',
        encoding="utf-8",
    )

    config = ResearchConfig.load(
        config_path=config_path,
        env={
            "RESEARCH_MODEL": "env-model",
            "RESEARCH_TIMEOUT": "90",
            "CLARIFICATION_CLARIFIER_MODEL": "env-clarifier",
        },
    )

    assert config.provider == "gemini"
    assert config.model == "env-model"
    assert config.timeout == 90.0
    assert config.enable_clarification == True
    assert config.triage_model == "file-triage"
    assert config.clarifier_model == "env-clarifier"


def test_from_env_only_uses_explicit_environment_values():
    """Test env-only loading does not require or implicitly read TOML configuration."""
    config = ResearchConfig.from_env(
        env={"RESEARCH_MODEL": "env-only-model", "ENABLE_CLARIFICATION": "true"}
    )

    assert config.provider == "openai"
    assert config.model == "env-only-model"
    assert config.enable_clarification == True


def test_config_with_environment_variables():
    """Test configuration loading from environment variables"""
    # Clean environment first
    env_vars = [
        "RESEARCH_MODEL",
        "ENABLE_CLARIFICATION",
        "CLARIFICATION_TRIAGE_MODEL",
        "CLARIFICATION_CLARIFIER_MODEL",
        "CLARIFICATION_INSTRUCTION_BUILDER_MODEL",
    ]
    original_values = {}
    for var in env_vars:
        original_values[var] = os.environ.get(var)
        if var in os.environ:
            del os.environ[var]

    try:
        # Set test environment variables
        os.environ["RESEARCH_MODEL"] = "gpt-5-mini"
        os.environ["ENABLE_CLARIFICATION"] = "true"
        os.environ["CLARIFICATION_TRIAGE_MODEL"] = "gpt-5-mini"
        os.environ["CLARIFICATION_CLARIFIER_MODEL"] = "gpt-5-mini"
        os.environ["CLARIFICATION_INSTRUCTION_BUILDER_MODEL"] = "gpt-5-mini"

        # Test config creation
        config = ResearchConfig.from_env()

        assert config.model == "gpt-5-mini"
        assert config.enable_clarification == True
        assert config.triage_model == "gpt-5-mini"
        assert config.clarifier_model == "gpt-5-mini"
        assert config.instruction_builder_model == "gpt-5-mini"

    finally:
        # Restore original environment
        for var, value in original_values.items():
            if value is not None:
                os.environ[var] = value
            elif var in os.environ:
                del os.environ[var]


def test_toml_boolean_parsing():
    """Test that TOML boolean values are parsed correctly"""
    # Clean environment
    if "ENABLE_CLARIFICATION" in os.environ:
        original_val = os.environ["ENABLE_CLARIFICATION"]
    else:
        original_val = None

    if "RESEARCH_MODEL" in os.environ:
        original_model = os.environ["RESEARCH_MODEL"]
    else:
        original_model = None

    try:
        os.environ["RESEARCH_MODEL"] = "gpt-5-mini"

        # Test various boolean representations
        for bool_val in ["true", "True", "TRUE", "1", "yes", "Yes"]:
            os.environ["ENABLE_CLARIFICATION"] = bool_val
            config = ResearchConfig.from_env()
            assert config.enable_clarification == True, f"Failed for value: {bool_val}"

        for bool_val in ["false", "False", "FALSE", "0", "no", "No", ""]:
            os.environ["ENABLE_CLARIFICATION"] = bool_val
            config = ResearchConfig.from_env()
            assert config.enable_clarification == False, f"Failed for value: {bool_val}"

    finally:
        # Restore environment
        if original_val is not None:
            os.environ["ENABLE_CLARIFICATION"] = original_val
        elif "ENABLE_CLARIFICATION" in os.environ:
            del os.environ["ENABLE_CLARIFICATION"]

        if original_model is not None:
            os.environ["RESEARCH_MODEL"] = original_model
        elif "RESEARCH_MODEL" in os.environ:
            del os.environ["RESEARCH_MODEL"]


def test_config_defaults():
    """Test configuration defaults are correct"""
    # Clean environment
    env_vars = [
        "RESEARCH_MODEL",
        "ENABLE_CLARIFICATION",
        "TRIAGE_MODEL",
        "CLARIFIER_MODEL",
        "INSTRUCTION_BUILDER_MODEL",
        "RESEARCH_TIMEOUT",
        "POLL_INTERVAL",
        "MAX_RETRIES",
    ]
    original_values = {}
    for var in env_vars:
        original_values[var] = os.environ.get(var)
        if var in os.environ:
            del os.environ[var]

    try:
        # Set only required value
        os.environ["RESEARCH_MODEL"] = "gpt-5-mini"

        config = ResearchConfig.from_env()

        # Test defaults
        assert config.provider == "openai"
        assert config.enable_clarification == False  # Default should be False
        assert config.triage_model == "gpt-5-mini"  # Default
        assert config.clarifier_model == "gpt-5-mini"  # Default
        assert config.instruction_builder_model == "gpt-5-mini"  # Default
        assert config.timeout == 1800.0  # Default
        assert config.poll_interval == 30.0  # Default
        assert config.log_level == "INFO"

    finally:
        # Restore environment
        for var, value in original_values.items():
            if value is not None:
                os.environ[var] = value
            elif var in os.environ:
                del os.environ[var]
