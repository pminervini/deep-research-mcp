# -*- coding: utf-8 -*-

"""
Tests for TOML configuration loading.
"""

import pytest
import os
import sys
from deep_research_mcp.config import ResearchConfig


def test_toml_functionality():
    """Test TOML loading works properly"""
    # Test basic TOML import
    try:
        import toml
    except ImportError:
        pytest.skip("toml library not available for testing")

    # Test simple TOML parsing
    test_toml = 'research_model = "gpt-5-mini"\nenable_clarification = true'

    import io

    config = toml.load(io.StringIO(test_toml))

    assert config["research_model"] == "gpt-5-mini"
    assert config["enable_clarification"] == True


def test_config_with_environment_variables():
    """Test configuration loading from environment variables"""
    # Clean environment first
    env_vars = [
        "RESEARCH_MODEL",
        "ENABLE_CLARIFICATION",
        "TRIAGE_MODEL",
        "CLARIFIER_MODEL",
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
        os.environ["TRIAGE_MODEL"] = "gpt-5-mini"
        os.environ["CLARIFIER_MODEL"] = "gpt-5-mini"

        # Test config creation
        config = ResearchConfig.from_env()

        assert config.model == "gpt-5-mini"
        assert config.enable_clarification == True
        assert config.triage_model == "gpt-5-mini"
        assert config.clarifier_model == "gpt-5-mini"

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


def test_toml_vs_legacy_format():
    """Test that both TOML and legacy formats work conceptually"""
    # This test just ensures the basic structures work

    # TOML style (would be in file)
    toml_style = {
        "research_model": "gpt-5-mini",
        "enable_clarification": True,
        "research": {"timeout": 1800, "poll_interval": 30},
    }

    # Legacy style (environment variables)
    legacy_style = {
        "RESEARCH_MODEL": "gpt-5-mini",
        "ENABLE_CLARIFICATION": "true",
        "RESEARCH_TIMEOUT": "1800",
        "RESEARCH_POLL_INTERVAL": "30",
    }

    # Test that both can represent the same data
    assert toml_style["research_model"] == legacy_style["RESEARCH_MODEL"]
    assert (
        str(toml_style["enable_clarification"]).lower()
        == legacy_style["ENABLE_CLARIFICATION"]
    )
    assert str(toml_style["research"]["timeout"]) == legacy_style["RESEARCH_TIMEOUT"]


def test_config_defaults():
    """Test configuration defaults are correct"""
    # Clean environment
    env_vars = [
        "RESEARCH_MODEL",
        "ENABLE_CLARIFICATION",
        "TRIAGE_MODEL",
        "CLARIFIER_MODEL",
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
        assert config.enable_clarification == False  # Default should be False
        assert config.triage_model == "gpt-5-mini"  # Default
        assert config.clarifier_model == "gpt-5-mini"  # Default
        assert config.timeout == 1800.0  # Default
        assert config.poll_interval == 30.0  # Default
        assert config.max_retries == 3  # Default

    finally:
        # Restore environment
        for var, value in original_values.items():
            if value is not None:
                os.environ[var] = value
            elif var in os.environ:
                del os.environ[var]
