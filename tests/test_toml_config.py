# -*- coding: utf-8 -*-

"""
Tests for TOML configuration loading.
"""

import os

import pytest

from deep_research_mcp.config import (
    ResearchConfig,
    load_backend_names,
    load_config_file,
    split_backend_task_id,
)
from deep_research_mcp.errors import ConfigurationError


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


def test_reasoning_effort_toml_env_precedence(tmp_path):
    config_path = tmp_path / ".deep_research"
    config_path.write_text(
        '[research]\nprovider = "openai"\nreasoning_effort = "high"\n',
        encoding="utf-8",
    )
    assert ResearchConfig.load(config_path, env={}).reasoning_effort == "high"
    assert (
        ResearchConfig.load(
            config_path, env={"RESEARCH_REASONING_EFFORT": "low"}
        ).reasoning_effort
        == "low"
    )


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


def _write_backends_config(tmp_path, body: str):
    config_path = tmp_path / ".deep_research"
    config_path.write_text(body, encoding="utf-8")
    return config_path


def test_named_backend_ignores_default_provider_settings(tmp_path):
    """A named backend never inherits provider-scoped values from [research]."""
    config_path = _write_backends_config(
        tmp_path,
        "[research]\n"
        'provider = "openai"\n'
        'api_key = "openai-key"\n'
        'base_url = "https://custom/v1"\n'
        'model = "gpt-x"\n'
        'reasoning_effort = "high"\n'
        "[backends.g]\n"
        'provider = "gemini"\n',
    )

    config = ResearchConfig.load(
        config_path, env={"GEMINI_API_KEY": "gem-key"}, backend="g"
    )

    assert config.provider == "gemini"
    assert config.api_key == "gem-key"
    assert config.base_url == "https://generativelanguage.googleapis.com"
    assert config.model == "deep-research-preview-04-2026"
    assert config.reasoning_effort is None
    assert config.validate() is True


def test_named_backend_inherits_runtime_settings(tmp_path):
    """Runtime values come from [research] unless the backend table overrides them."""
    config_path = _write_backends_config(
        tmp_path,
        "[research]\n"
        'provider = "openai"\n'
        "timeout = 42\n"
        "[backends.inherit]\n"
        'provider = "dr-tulu"\n'
        "[backends.override]\n"
        'provider = "dr-tulu"\n'
        "timeout = 7\n",
    )

    assert ResearchConfig.load(config_path, env={}, backend="inherit").timeout == 42.0
    assert ResearchConfig.load(config_path, env={}, backend="override").timeout == 7.0


def test_named_backend_ignores_generic_env_overrides(tmp_path):
    """RESEARCH_* env vars describe the default backend, not named ones."""
    config_path = _write_backends_config(
        tmp_path, '[backends.g]\nprovider = "gemini"\n'
    )

    config = ResearchConfig.load(
        config_path,
        env={"RESEARCH_MODEL": "env-model", "RESEARCH_API_KEY": "env-key"},
        backend="g",
    )

    assert config.model == "deep-research-preview-04-2026"
    assert config.api_key is None


def test_named_backend_table_beats_provider_env_alias(tmp_path):
    """An api_key set in the table wins over TAVILY_API_KEY; omitted falls back."""
    config_path = _write_backends_config(
        tmp_path,
        "[backends.with-key]\n"
        'provider = "tavily"\n'
        'api_key = "table-key"\n'
        "[backends.without-key]\n"
        'provider = "tavily"\n',
    )
    env = {"TAVILY_API_KEY": "env-key"}

    assert ResearchConfig.load(config_path, env=env, backend="with-key").api_key == (
        "table-key"
    )
    assert ResearchConfig.load(config_path, env=env, backend="without-key").api_key == (
        "env-key"
    )


def test_named_backends_same_provider_different_specs(tmp_path):
    """Two backends may share a provider and differ in endpoint and model."""
    config_path = _write_backends_config(
        tmp_path,
        "[backends.a]\n"
        'provider = "dr-tulu"\n'
        'base_url = "http://a:8080/"\n'
        "[backends.b]\n"
        'provider = "dr-tulu"\n'
        'base_url = "http://b:8080/"\n'
        'model = "tulu-b"\n',
    )

    config_a = ResearchConfig.load(config_path, env={}, backend="a")
    config_b = ResearchConfig.load(config_path, env={}, backend="b")

    assert (config_a.base_url, config_a.model) == ("http://a:8080/", "dr-tulu")
    assert (config_b.base_url, config_b.model) == ("http://b:8080/", "tulu-b")


def test_default_backend_name_matches_plain_load(tmp_path):
    """backend="default" is the same as not naming a backend."""
    config_path = _write_backends_config(
        tmp_path,
        "[research]\n"
        'provider = "gemini"\n'
        'model = "file-model"\n'
        "[backends.g]\n"
        'provider = "gemini"\n',
    )

    assert ResearchConfig.load(config_path, env={}, backend="default") == (
        ResearchConfig.load(config_path, env={})
    )


@pytest.mark.parametrize(
    "body, backend, match",
    [
        ("[research]\n", "nope", "not defined"),
        ('[backends.bad]\nmodel = "x"\n', "bad", "not defined"),
        ('[backends.bad]\nprovider = "nope"\n', "bad", "not supported"),
    ],
)
def test_named_backend_errors(tmp_path, body, backend, match):
    config_path = _write_backends_config(tmp_path, body)

    with pytest.raises(ConfigurationError, match=match):
        ResearchConfig.load(config_path, env={}, backend=backend)


def test_load_backend_names(tmp_path):
    """Names come back in file order; a missing table yields an empty list."""
    config_path = _write_backends_config(
        tmp_path,
        "[backends.second-first]\n"
        'provider = "gemini"\n'
        "[backends.alpha]\n"
        'provider = "tavily"\n',
    )

    assert load_backend_names(config_path) == ["second-first", "alpha"]
    assert not load_backend_names(_write_backends_config(tmp_path, "[research]\n"))


@pytest.mark.parametrize(
    "body, match",
    [
        ('[backends.default]\nprovider = "gemini"\n', "reserved"),
        ('[backends."a:b"]\nprovider = "gemini"\n', "must not contain"),
        ('[backends.bad]\nmodel = "x"\n', "must set a provider"),
    ],
)
def test_load_backend_names_rejects_invalid_entries(tmp_path, body, match):
    config_path = _write_backends_config(tmp_path, body)

    with pytest.raises(ConfigurationError, match=match):
        load_backend_names(config_path)


@pytest.mark.parametrize(
    "task_id, expected",
    [
        ("abc", ("default", "abc")),
        ("default:abc", ("default", "abc")),
        ("g:abc", ("g", "abc")),
        ("g:a:b", ("g", "a:b")),
        ("unknown:abc", ("default", "unknown:abc")),
    ],
)
def test_split_backend_task_id(tmp_path, task_id, expected):
    config_path = _write_backends_config(
        tmp_path, '[backends.g]\nprovider = "gemini"\n'
    )

    assert split_backend_task_id(task_id, config_path) == expected
