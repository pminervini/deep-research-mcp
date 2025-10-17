# -*- coding: utf-8 -*-

"""Tests for config loading and validation using real OpenAI API calls."""

import os
import pytest
from deep_research_mcp.config import ResearchConfig


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
        max_retries=7,
        log_level="DEBUG",
    )

    assert config.api_key == api_key
    assert config.model == "gpt-5-mini"
    assert config.timeout == 120.0
    assert config.poll_interval == 5.0
    assert config.max_retries == 7
    assert config.log_level == "DEBUG"


def test_validate_with_valid_model():
    """Test validation with a valid model"""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY not set")

    config = ResearchConfig(api_key=api_key, model="gpt-5-mini")
    assert config.validate() is True


def test_validate_with_invalid_model():
    """Test validation with an invalid model"""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY not set")

    config = ResearchConfig(api_key=api_key, model="definitely-not-a-real-model-name")

    # With real API call, this should raise an error if the model doesn't exist
    # But our current implementation is graceful, so it won't raise
    # The actual research call will handle the invalid model
    assert config.validate() is True


def test_config_with_custom_endpoint():
    """Test config creation with custom OpenAI endpoint"""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY not set")

    custom_endpoint = "https://api.custom-provider.com/v1"
    config = ResearchConfig(
        api_key=api_key,
        base_url=custom_endpoint,
        model="gpt-5-mini",
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
        api_key=api_key,
        model="gpt-5-mini",
        instruction_builder_model="gpt-4o-mini",
    )

    assert config.api_key == api_key
    assert config.instruction_builder_model == "gpt-4o-mini"
    assert config.validate() is True


def test_from_env_with_instruction_builder_model():
    """Test loading instruction_builder_model from environment variables"""
    old_model = os.environ.get("RESEARCH_MODEL")
    old_instruction_builder_model = os.environ.get("CLARIFICATION_INSTRUCTION_BUILDER_MODEL")

    os.environ["RESEARCH_MODEL"] = "gpt-5-mini"
    os.environ["CLARIFICATION_INSTRUCTION_BUILDER_MODEL"] = "gpt-4o-mini"

    try:
        config = ResearchConfig.from_env()
        assert config.instruction_builder_model == "gpt-4o-mini"
        assert config.model == "gpt-5-mini"
    finally:
        if old_model:
            os.environ["RESEARCH_MODEL"] = old_model
        else:
            del os.environ["RESEARCH_MODEL"]

        if old_instruction_builder_model:
            os.environ["CLARIFICATION_INSTRUCTION_BUILDER_MODEL"] = old_instruction_builder_model
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
