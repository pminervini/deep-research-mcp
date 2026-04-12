# -*- coding: utf-8 -*-

"""Tests for config loading and validation using real OpenAI API calls."""

import os
import pytest
from deep_research_mcp.config import ResearchConfig
from deep_research_mcp.errors import ConfigurationError


def test_config_creation_with_overrides():
    """Test config creation with custom values"""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY not set")

    config = ResearchConfig(
        api_key=api_key,
        model="gpt-5-mini",
        timeout=120.0,
        poll_interval=5.0,
        log_level="DEBUG",
    )

    assert config.api_key == api_key
    assert config.model == "gpt-5-mini"
    assert config.timeout == 120.0
    assert config.poll_interval == 5.0
    assert config.log_level == "DEBUG"


def test_validate_with_valid_model():
    """Test validation accepts a basic local config."""
    config = ResearchConfig(model="gpt-5-mini")
    assert config.validate() is True


@pytest.mark.parametrize(
    ("field_name", "field_value", "error_message"),
    [
        ("timeout", 0.0, "Timeout must be positive"),
        ("poll_interval", 0.0, "Poll interval must be positive"),
    ],
)
def test_validate_rejects_invalid_runtime_limits(
    field_name: str, field_value: float | int, error_message: str
):
    """Test validation rejects invalid timing and retry values."""
    config = ResearchConfig(model="gpt-5-mini")
    setattr(config, field_name, field_value)

    with pytest.raises(ConfigurationError, match=error_message):
        config.validate()


def test_validate_with_invalid_log_level():
    """Test validation rejects invalid log levels."""
    config = ResearchConfig(model="gpt-5-mini", log_level="not-a-level")

    with pytest.raises(ConfigurationError, match="Invalid log level"):
        config.validate()


def test_config_with_custom_endpoint():
    """Test config creation with custom OpenAI endpoint"""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY not set")

    custom_endpoint = "https://api.custom-provider.com/v1"
    config = ResearchConfig(
        api_key=api_key, base_url=custom_endpoint, model="gpt-5-mini"
    )

    assert config.api_key == api_key
    assert config.base_url == custom_endpoint
    assert config.model == "gpt-5-mini"
    assert config.validate() is True


def test_from_env_with_base_url():
    """Test loading base_url from environment variables"""
    old_model = os.environ.get("RESEARCH_MODEL")
    old_base_url = os.environ.get("RESEARCH_BASE_URL")

    os.environ["RESEARCH_MODEL"] = "gpt-5-mini"
    os.environ["RESEARCH_BASE_URL"] = "https://api.custom-provider.com/v1"

    try:
        config = ResearchConfig.from_env()
        assert config.base_url == "https://api.custom-provider.com/v1"
        assert config.model == "gpt-5-mini"
    finally:
        if old_model:
            os.environ["RESEARCH_MODEL"] = old_model
        else:
            del os.environ["RESEARCH_MODEL"]

        if old_base_url:
            os.environ["RESEARCH_BASE_URL"] = old_base_url
        else:
            if "RESEARCH_BASE_URL" in os.environ:
                del os.environ["RESEARCH_BASE_URL"]


def test_config_with_clarification_base_url():
    """Test config with separate clarification base URL"""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY not set")

    clarification_endpoint = "https://api.clarification.com/v1"
    config = ResearchConfig(
        api_key=api_key,
        model="gpt-5-mini",
        enable_clarification=True,
        clarification_base_url=clarification_endpoint,
    )

    assert config.api_key == api_key
    assert config.clarification_base_url == clarification_endpoint
    assert config.enable_clarification is True
    assert config.validate() is True


def test_from_env_with_clarification_base_url():
    """Test loading clarification_base_url from environment variables"""
    old_model = os.environ.get("RESEARCH_MODEL")
    old_clarification_base_url = os.environ.get("CLARIFICATION_BASE_URL")

    os.environ["RESEARCH_MODEL"] = "gpt-5-mini"
    os.environ["CLARIFICATION_BASE_URL"] = "https://api.clarification.com/v1"

    try:
        config = ResearchConfig.from_env()
        assert config.clarification_base_url == "https://api.clarification.com/v1"
        assert config.model == "gpt-5-mini"
    finally:
        if old_model:
            os.environ["RESEARCH_MODEL"] = old_model
        else:
            del os.environ["RESEARCH_MODEL"]

        if old_clarification_base_url:
            os.environ["CLARIFICATION_BASE_URL"] = old_clarification_base_url
        else:
            if "CLARIFICATION_BASE_URL" in os.environ:
                del os.environ["CLARIFICATION_BASE_URL"]


def test_config_with_clarification_api_key():
    """Test config with separate clarification API key"""
    clarification_api_key = "sk-clarification-test-key"
    config = ResearchConfig(
        api_key="sk-main-test-key",
        model="gpt-5-mini",
        enable_clarification=True,
        clarification_api_key=clarification_api_key,
    )

    assert config.api_key == "sk-main-test-key"
    assert config.clarification_api_key == clarification_api_key
    assert config.enable_clarification is True
    assert config.validate() is True


def test_from_env_with_clarification_api_key():
    """Test loading clarification_api_key from environment variables"""
    old_model = os.environ.get("RESEARCH_MODEL")
    old_clarification_api_key = os.environ.get("CLARIFICATION_API_KEY")

    os.environ["RESEARCH_MODEL"] = "gpt-5-mini"
    os.environ["CLARIFICATION_API_KEY"] = "sk-clarification-env-key"

    try:
        config = ResearchConfig.from_env()
        assert config.clarification_api_key == "sk-clarification-env-key"
        assert config.model == "gpt-5-mini"
    finally:
        if old_model:
            os.environ["RESEARCH_MODEL"] = old_model
        else:
            del os.environ["RESEARCH_MODEL"]

        if old_clarification_api_key:
            os.environ["CLARIFICATION_API_KEY"] = old_clarification_api_key
        else:
            if "CLARIFICATION_API_KEY" in os.environ:
                del os.environ["CLARIFICATION_API_KEY"]


def test_config_with_instruction_builder_model():
    """Test config with instruction builder model"""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY not set")

    config = ResearchConfig(
        api_key=api_key, model="gpt-5-mini", instruction_builder_model="gpt-5-mini"
    )

    assert config.api_key == api_key
    assert config.instruction_builder_model == "gpt-5-mini"
    assert config.validate() is True


def test_from_env_with_instruction_builder_model():
    """Test loading instruction_builder_model from environment variables"""
    old_model = os.environ.get("RESEARCH_MODEL")
    old_instruction_builder_model = os.environ.get(
        "CLARIFICATION_INSTRUCTION_BUILDER_MODEL"
    )

    os.environ["RESEARCH_MODEL"] = "gpt-5-mini"
    os.environ["CLARIFICATION_INSTRUCTION_BUILDER_MODEL"] = "gpt-5-mini"

    try:
        config = ResearchConfig.from_env()
        assert config.instruction_builder_model == "gpt-5-mini"
        assert config.model == "gpt-5-mini"
    finally:
        if old_model:
            os.environ["RESEARCH_MODEL"] = old_model
        else:
            del os.environ["RESEARCH_MODEL"]

        if old_instruction_builder_model:
            os.environ["CLARIFICATION_INSTRUCTION_BUILDER_MODEL"] = (
                old_instruction_builder_model
            )
        else:
            if "CLARIFICATION_INSTRUCTION_BUILDER_MODEL" in os.environ:
                del os.environ["CLARIFICATION_INSTRUCTION_BUILDER_MODEL"]


def test_instruction_builder_model_defaults():
    """Test that instruction_builder_model has correct default"""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY not set")

    config = ResearchConfig(api_key=api_key, model="gpt-5-mini")

    assert config.instruction_builder_model == "gpt-5-mini"
    assert config.validate() is True


# --- api_style tests ---


def test_api_style_defaults_to_responses():
    """Test that api_style defaults to 'responses'"""
    config = ResearchConfig(api_key="sk-test", model="gpt-5-mini")
    assert config.api_style == "responses"


def test_api_style_from_env():
    """Test loading api_style from RESEARCH_API_STYLE env var"""
    old_api_style = os.environ.get("RESEARCH_API_STYLE")
    old_model = os.environ.get("RESEARCH_MODEL")

    os.environ["RESEARCH_API_STYLE"] = "chat_completions"
    os.environ["RESEARCH_MODEL"] = "gpt-5-mini"

    try:
        config = ResearchConfig.from_env()
        assert config.api_style == "chat_completions"
    finally:
        if old_api_style:
            os.environ["RESEARCH_API_STYLE"] = old_api_style
        else:
            os.environ.pop("RESEARCH_API_STYLE", None)

        if old_model:
            os.environ["RESEARCH_MODEL"] = old_model
        else:
            os.environ.pop("RESEARCH_MODEL", None)


def test_api_style_invalid_value_rejected():
    """Test that invalid api_style values are rejected"""
    old_api_style = os.environ.get("RESEARCH_API_STYLE")

    os.environ["RESEARCH_API_STYLE"] = "invalid_value"

    try:
        with pytest.raises(ConfigurationError, match="Invalid api_style"):
            ResearchConfig.from_env()
    finally:
        if old_api_style:
            os.environ["RESEARCH_API_STYLE"] = old_api_style
        else:
            os.environ.pop("RESEARCH_API_STYLE", None)


def test_api_style_chat_completions_skips_api_key_validation():
    """Test that API key validation is skipped for chat_completions mode"""
    config = ResearchConfig(
        api_key="ppl-perplexity-key", model="gpt-5-mini", api_style="chat_completions"
    )
    # Should not raise despite non-sk- prefix
    assert config.validate() is True


def test_api_style_chat_completions_default_model():
    """Test that chat_completions mode defaults to gpt-5-mini for openai provider"""
    old_api_style = os.environ.get("RESEARCH_API_STYLE")
    old_model = os.environ.get("RESEARCH_MODEL")

    os.environ["RESEARCH_API_STYLE"] = "chat_completions"
    os.environ.pop("RESEARCH_MODEL", None)

    try:
        config = ResearchConfig.from_env()
        assert config.api_style == "chat_completions"
        assert config.model == "gpt-5-mini"
    finally:
        if old_api_style:
            os.environ["RESEARCH_API_STYLE"] = old_api_style
        else:
            os.environ.pop("RESEARCH_API_STYLE", None)

        if old_model:
            os.environ["RESEARCH_MODEL"] = old_model
        else:
            os.environ.pop("RESEARCH_MODEL", None)


def test_gemini_provider_defaults():
    """Test Gemini provider default model and endpoint resolution."""
    old_provider = os.environ.get("RESEARCH_PROVIDER")
    old_model = os.environ.get("RESEARCH_MODEL")
    old_base_url = os.environ.get("RESEARCH_BASE_URL")

    os.environ["RESEARCH_PROVIDER"] = "gemini"
    os.environ.pop("RESEARCH_MODEL", None)
    os.environ.pop("RESEARCH_BASE_URL", None)

    try:
        config = ResearchConfig.from_env()
        assert config.provider == "gemini"
        assert config.model == "deep-research-pro-preview-12-2025"
        assert config.base_url == "https://generativelanguage.googleapis.com"
    finally:
        if old_provider:
            os.environ["RESEARCH_PROVIDER"] = old_provider
        else:
            os.environ.pop("RESEARCH_PROVIDER", None)

        if old_model:
            os.environ["RESEARCH_MODEL"] = old_model
        else:
            os.environ.pop("RESEARCH_MODEL", None)

        if old_base_url:
            os.environ["RESEARCH_BASE_URL"] = old_base_url
        else:
            os.environ.pop("RESEARCH_BASE_URL", None)


def test_dr_tulu_provider_defaults():
    """Test Dr Tulu provider default model and endpoint resolution."""
    old_provider = os.environ.get("RESEARCH_PROVIDER")
    old_model = os.environ.get("RESEARCH_MODEL")
    old_base_url = os.environ.get("RESEARCH_BASE_URL")

    os.environ["RESEARCH_PROVIDER"] = "dr-tulu"
    os.environ.pop("RESEARCH_MODEL", None)
    os.environ.pop("RESEARCH_BASE_URL", None)

    try:
        config = ResearchConfig.from_env()
        assert config.provider == "dr-tulu"
        assert config.model == "dr-tulu"
        assert config.base_url == "http://localhost:8080/"
    finally:
        if old_provider:
            os.environ["RESEARCH_PROVIDER"] = old_provider
        else:
            os.environ.pop("RESEARCH_PROVIDER", None)

        if old_model:
            os.environ["RESEARCH_MODEL"] = old_model
        else:
            os.environ.pop("RESEARCH_MODEL", None)

        if old_base_url:
            os.environ["RESEARCH_BASE_URL"] = old_base_url
        else:
            os.environ.pop("RESEARCH_BASE_URL", None)


def test_gemini_api_key_aliases():
    """Test Gemini provider API key aliases."""
    old_provider = os.environ.get("RESEARCH_PROVIDER")
    old_research_api_key = os.environ.get("RESEARCH_API_KEY")
    old_gemini_api_key = os.environ.get("GEMINI_API_KEY")
    old_google_api_key = os.environ.get("GOOGLE_API_KEY")

    os.environ["RESEARCH_PROVIDER"] = "gemini"
    os.environ.pop("RESEARCH_API_KEY", None)
    os.environ["GEMINI_API_KEY"] = "gemini-key"
    os.environ.pop("GOOGLE_API_KEY", None)

    try:
        config = ResearchConfig.from_env()
        assert config.api_key == "gemini-key"
    finally:
        if old_provider:
            os.environ["RESEARCH_PROVIDER"] = old_provider
        else:
            os.environ.pop("RESEARCH_PROVIDER", None)

        if old_research_api_key:
            os.environ["RESEARCH_API_KEY"] = old_research_api_key
        else:
            os.environ.pop("RESEARCH_API_KEY", None)

        if old_gemini_api_key:
            os.environ["GEMINI_API_KEY"] = old_gemini_api_key
        else:
            os.environ.pop("GEMINI_API_KEY", None)

        if old_google_api_key:
            os.environ["GOOGLE_API_KEY"] = old_google_api_key
        else:
            os.environ.pop("GOOGLE_API_KEY", None)


def test_provider_alias_env_var():
    """Test backward-compatible PROVIDER env var support."""
    old_provider = os.environ.get("PROVIDER")
    old_research_provider = os.environ.get("RESEARCH_PROVIDER")
    old_model = os.environ.get("RESEARCH_MODEL")

    os.environ["PROVIDER"] = "gemini"
    os.environ.pop("RESEARCH_PROVIDER", None)
    os.environ.pop("RESEARCH_MODEL", None)

    try:
        config = ResearchConfig.from_env()
        assert config.provider == "gemini"
        assert config.model == "deep-research-pro-preview-12-2025"
    finally:
        if old_provider:
            os.environ["PROVIDER"] = old_provider
        else:
            os.environ.pop("PROVIDER", None)

        if old_research_provider:
            os.environ["RESEARCH_PROVIDER"] = old_research_provider
        else:
            os.environ.pop("RESEARCH_PROVIDER", None)

        if old_model:
            os.environ["RESEARCH_MODEL"] = old_model
        else:
            os.environ.pop("RESEARCH_MODEL", None)
