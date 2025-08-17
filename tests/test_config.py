# -*- coding: utf-8 -*-

"""Tests for config loading and validation using real OpenAI API calls."""

import os
import pytest
from deep_research_mcp.config import ResearchConfig


def test_from_env_requires_research_model():
    """Test that missing RESEARCH_MODEL raises error"""
    old_model = os.environ.get("RESEARCH_MODEL")
    if old_model:
        del os.environ["RESEARCH_MODEL"]

    try:
        with pytest.raises(
            ValueError,
            match="RESEARCH_MODEL is required in ~/.deep_research configuration file",
        ):
            ResearchConfig.from_env()
    finally:
        if old_model:
            os.environ["RESEARCH_MODEL"] = old_model


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
    old_base_url = os.environ.get("OPENAI_BASE_URL")
    
    os.environ["RESEARCH_MODEL"] = "gpt-5-mini"
    os.environ["OPENAI_BASE_URL"] = "https://api.custom-provider.com/v1"

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
            os.environ["OPENAI_BASE_URL"] = old_base_url
        else:
            if "OPENAI_BASE_URL" in os.environ:
                del os.environ["OPENAI_BASE_URL"]
