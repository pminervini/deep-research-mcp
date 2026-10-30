# -*- coding: utf-8 -*-

"""Structured backend discovery without provider requests or real credentials."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


def _list_backends(tmp_path: Path, config: str, oauth_present: bool = False) -> dict:
    """Run the real listing with isolated configuration and no provider environment."""
    (tmp_path / ".deep_research").write_text(config, encoding="utf-8")
    if oauth_present:
        # Discovery checks file presence, not credential contents or validity.
        (tmp_path / ".deep_research_auth.json").write_text("{}", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from deep_research_mcp.mcp_server import list_backends; "
            "print(list_backends().model_dump_json())",
        ],
        cwd=Path(__file__).resolve().parents[1],
        env={"HOME": str(tmp_path), "PATH": os.environ.get("PATH", "")},
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    return json.loads(result.stdout)


@pytest.mark.parametrize("provider", ["openai", "gemini", "tavily", "dr-tulu"])
@pytest.mark.parametrize("key_present", [False, True])
def test_list_backends_api_key_presence(
    tmp_path: Path, provider: str, key_present: bool
) -> None:
    key_setting = 'api_key = "listing-test-secret"\n' if key_present else ""
    result = _list_backends(
        tmp_path, f'[research]\nprovider = "{provider}"\n{key_setting}'
    )
    assert result["error"] is None
    assert len(result["backends"]) == 1
    backend = result["backends"][0]
    assert backend["name"] == "default"
    assert backend["provider"] == provider
    assert backend["api_key_present"] is key_present
    assert backend["oauth_present"] is None
    assert backend["run_options_present"] is None
    assert backend["shared_output_present"] is None
    assert backend["error"] is None
    assert "listing-test-secret" not in json.dumps(result)


def test_list_backends_named_settings_and_isolation(tmp_path: Path) -> None:
    result = _list_backends(
        tmp_path,
        '[research]\nprovider = "gemini"\napi_key = "default-secret"\n'
        '[backends.api]\nprovider = "openai"\napi_style = "chat_completions"\n'
        'model = "test-model"\nbase_url = "http://127.0.0.1:18081/v1"\n'
        'reasoning_effort = "high"\napi_key = "named-secret"\n'
        '[backends.other]\nprovider = "gemini"\n',
    )
    assert [item["name"] for item in result["backends"]] == [
        "default",
        "api",
        "other",
    ]
    backend = result["backends"][1]
    assert backend["provider"] == "openai"
    assert backend["model"] == "test-model"
    assert backend["base_url"] == "http://127.0.0.1:18081/v1"
    assert backend["api_style"] == "chat_completions"
    assert backend["reasoning_effort"] == "high"
    assert backend["api_key_present"] is True
    assert result["backends"][0]["api_style"] is None
    assert result["backends"][2]["api_key_present"] is False
    assert "default-secret" not in json.dumps(result)
    assert "named-secret" not in json.dumps(result)


@pytest.mark.parametrize("oauth_present", [False, True])
def test_list_backends_codex_oauth_presence(
    tmp_path: Path, oauth_present: bool
) -> None:
    result = _list_backends(
        tmp_path,
        '[research]\nprovider = "openai-codex"\n'
        'model = "gpt-6-sol"\nreasoning_effort = "high"\n'
        'api_key = "ignored-secret"\n',
        oauth_present=oauth_present,
    )
    backend = result["backends"][0]
    assert backend["model"] == "gpt-6-sol"
    assert backend["reasoning_effort"] == "high"
    assert backend["api_style"] is None
    assert backend["api_key_present"] is None
    assert backend["oauth_present"] is oauth_present
    assert "ignored-secret" not in json.dumps(result)


@pytest.mark.parametrize("options_present", [False, True])
@pytest.mark.parametrize("output_present", [False, True])
def test_list_backends_gnosis_file_presence(
    tmp_path: Path, options_present: bool, output_present: bool
) -> None:
    options = tmp_path / "options.json"
    output = tmp_path / "output"
    if options_present:
        options.write_text('{"private": "not-read-by-listing"}', encoding="utf-8")
    if output_present:
        output.mkdir()
    result = _list_backends(
        tmp_path,
        '[research]\nprovider = "gnosis"\n'
        f"gnosis_config_path = {json.dumps(str(options))}\n"
        f"gnosis_output_dir = {json.dumps(str(output))}\n",
    )
    backend = result["backends"][0]
    assert backend["run_options_present"] is options_present
    assert backend["shared_output_present"] is output_present
    assert backend["api_key_present"] is False
    assert backend["oauth_present"] is None
    assert "not-read-by-listing" not in json.dumps(result)
    assert str(options) not in json.dumps(result)
    assert str(output) not in json.dumps(result)


@pytest.mark.parametrize(
    "config",
    [
        "not valid TOML",
        '[backends.default]\nprovider = "gemini"\n',
        '[backends."invalid:name"]\nprovider = "gemini"\n',
        '[backends.missing]\nmodel = "test"\n',
    ],
)
def test_list_backends_configuration_errors_are_structured(
    tmp_path: Path, config: str
) -> None:
    result = _list_backends(tmp_path, config)
    assert result["backends"] == []
    assert isinstance(result["error"], str)
    assert result["error"]


@pytest.mark.parametrize("invalid_default", [False, True])
def test_list_backends_keeps_other_entries_after_backend_error(
    tmp_path: Path, invalid_default: bool
) -> None:
    provider = "unsupported" if invalid_default else "dr-tulu"
    other_provider = "dr-tulu" if invalid_default else "unsupported"
    result = _list_backends(
        tmp_path,
        f'[research]\nprovider = "{provider}"\n'
        f'[backends.other]\nprovider = "{other_provider}"\n',
    )
    assert result["error"] is None
    assert [item["name"] for item in result["backends"]] == ["default", "other"]
    invalid = result["backends"][0 if invalid_default else 1]
    valid = result["backends"][1 if invalid_default else 0]
    assert "unsupported" in invalid["error"]
    assert invalid["provider"] is None
    assert invalid["api_key_present"] is None
    assert valid["provider"] == "dr-tulu"
    assert valid["error"] is None
