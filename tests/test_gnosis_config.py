# -*- coding: utf-8 -*-

"""Gnosis provider configuration and CLI/TUI routing contracts."""

from pathlib import Path
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import pytest
from textual.widgets import Input, Select

from deep_research_mcp.cli import build_parser, check_backend_flags, load_config
from deep_research_mcp.config import ResearchConfig
from tests.tui_test_utils import load_tui_module


def test_gnosis_defaults() -> None:
    config = ResearchConfig.from_env({"RESEARCH_PROVIDER": "gnosis"})
    assert config.provider == "gnosis"
    assert config.model == "gnosis"
    assert config.base_url == "http://127.0.0.1:8089"
    assert config.api_key is None
    assert config.gnosis_config_path is None
    assert config.gnosis_output_dir is None
    assert config.validate()


def test_gnosis_env_aliases() -> None:
    config = ResearchConfig.from_env(
        {
            "RESEARCH_PROVIDER": "gnosis",
            "GNOSIS_BASE_URL": "http://gnosis:8089",
            "GNOSIS_API_KEY": "service-key",
            "GNOSIS_CONFIG_PATH": "/private/options.json",
            "GNOSIS_OUTPUT_DIR": "/shared/output",
        }
    )
    assert config.base_url == "http://gnosis:8089"
    assert config.api_key == "service-key"
    assert config.gnosis_config_path == "/private/options.json"
    assert config.gnosis_output_dir == "/shared/output"


def test_named_gnosis_config_isolated_and_table_wins(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        '[research]\nprovider = "openai"\ngnosis_config_path = "/default.json"\n'
        'gnosis_output_dir = "/default-output"\n'
        '[backends.local]\nprovider = "gnosis"\n'
        'gnosis_config_path = "/named.json"\n'
        'gnosis_output_dir = "/named-output"\n'
        '[backends.other]\nprovider = "gnosis"\n',
        encoding="utf-8",
    )
    env = {
        "RESEARCH_GNOSIS_CONFIG_PATH": "/generic-env.json",
        "GNOSIS_CONFIG_PATH": "/provider-env.json",
        "RESEARCH_GNOSIS_OUTPUT_DIR": "/generic-output",
        "GNOSIS_OUTPUT_DIR": "/provider-output",
    }
    config = ResearchConfig.load(path, env=env, backend="local")
    assert config.gnosis_config_path == "/named.json"
    assert config.gnosis_output_dir == "/named-output"
    assert config.model == "gnosis"
    assert ResearchConfig.load(path, env=env, backend="other").gnosis_config_path == (
        "/provider-env.json"
    )
    assert ResearchConfig.load(path, env={}, backend="other").gnosis_config_path is None
    assert ResearchConfig.load(path, env={}, backend="other").gnosis_output_dir is None


def test_gnosis_cli_options_override_toml(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        '[research]\nprovider = "gnosis"\ngnosis_config_path = "/file.json"\n',
        encoding="utf-8",
    )
    args = build_parser().parse_args(
        [
            "--config",
            str(path),
            "--provider",
            "gnosis",
            "--gnosis-config-path",
            "/cli.json",
            "research",
            "test",
        ]
    )
    assert load_config(args).gnosis_config_path == "/cli.json"


def test_named_backend_rejects_gnosis_cli_override() -> None:
    parser = build_parser()
    args = parser.parse_args(
        ["--backend", "local", "--gnosis-config-path", "/other.json", "status", "id"]
    )
    with pytest.raises(SystemExit):
        check_backend_flags(parser, args)


@pytest.mark.asyncio
async def test_gnosis_tui_preserves_named_request_options(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        '[backends.local]\nprovider = "gnosis"\n'
        'gnosis_config_path = "/private/options.json"\n',
        encoding="utf-8",
    )
    tui = load_tui_module()
    defaults = tui.get_provider_defaults("gnosis")
    assert defaults.model == "gnosis"
    assert defaults.base_url == "http://127.0.0.1:8089"
    assert tui.build_parser().parse_args(["--provider", "gnosis"]).provider == "gnosis"
    app = tui.DeepResearchTUI(
        tui.StartupState(
            config_path=str(path), backend="local", provider="gnosis", config=defaults
        )
    )
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        assert app.query_one("#provider", Select).value == "gnosis"
        assert app.query_one("#base-url", Input).value == "http://127.0.0.1:8089"
        config = app._build_config()  # pylint: disable=protected-access
        assert config.provider == "gnosis"
        assert config.gnosis_config_path == "/private/options.json"


@pytest.mark.asyncio
async def test_gnosis_named_backend_is_discoverable_over_stdio(tmp_path: Path) -> None:
    """Discover a named Gnosis backend without submitting research or loading secrets."""
    (tmp_path / ".deep_research").write_text(
        '[research]\nprovider = "gnosis"\n'
        '[backends.gnosis]\nprovider = "gnosis"\n'
        f'gnosis_output_dir = "{tmp_path}"\n',
        encoding="utf-8",
    )
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "deep_research_mcp.mcp_server"],
        cwd=Path(__file__).resolve().parents[1],
        env={"HOME": str(tmp_path), "PATH": os.environ.get("PATH", "")},
    )
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            result = await session.call_tool("list_backends", {})
            assert not result.isError
            text = "\n".join(
                item.text for item in result.content if item.type == "text"
            )
            assert "- gnosis: provider=gnosis, model=gnosis" in text
            assert "run_options: missing, shared_output: present" in text
