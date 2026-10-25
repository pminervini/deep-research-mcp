# -*- coding: utf-8 -*-

"""
Configuration management for Deep Research MCP.
"""

from __future__ import annotations

import logging
import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from deep_research_mcp.errors import ConfigurationError

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path.home() / ".deep_research"
OPENAI_CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"

# Per-provider (default model, default base URL, extra API-key settings,
# extra base-URL settings). The openai default model also depends on api_style.
_PROVIDER_DEFAULTS: dict[str, tuple[str, str, tuple[str, ...], tuple[str, ...]]] = {
    "openai": (
        "gpt-6-sol",
        "https://api.openai.com/v1",
        ("OPENAI_API_KEY",),
        ("OPENAI_BASE_URL",),
    ),
    "gemini": (
        "deep-research-preview-04-2026",
        "https://generativelanguage.googleapis.com",
        ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        ("GEMINI_BASE_URL",),
    ),
    "tavily": (
        "mini",
        "https://api.tavily.com",
        ("TAVILY_API_KEY",),
        ("TAVILY_BASE_URL",),
    ),
    "dr-tulu": (
        "dr-tulu",
        "http://localhost:8080/",
        ("DR_TULU_API_KEY",),
        ("DR_TULU_BASE_URL",),
    ),
    "gnosis": (
        "gnosis",
        "http://127.0.0.1:8089",
        ("GNOSIS_API_KEY",),
        ("GNOSIS_BASE_URL",),
    ),
    "openai-codex": (
        "auto",
        OPENAI_CODEX_BASE_URL,
        (),
        (),
    ),
}

# Name of the backend described by the [research] table (and RESEARCH_* env vars).
DEFAULT_BACKEND_NAME = "default"

# Settings that describe the default backend's provider and must not leak into a
# named [backends.<name>] configuration.
_PROVIDER_SCOPED_SETTINGS = (
    "RESEARCH_PROVIDER",
    "PROVIDER",
    "RESEARCH_API_KEY",
    "RESEARCH_BASE_URL",
    "RESEARCH_MODEL",
    "RESEARCH_API_STYLE",
    "RESEARCH_REASONING_EFFORT",
    "RESEARCH_GNOSIS_CONFIG_PATH",
    "RESEARCH_GNOSIS_OUTPUT_DIR",
)


def load_config_file(config_path: Path | str | None = None) -> dict[str, Any]:
    """Load configuration data from a TOML file without mutating process state."""
    resolved_path = (
        Path(config_path) if config_path is not None else DEFAULT_CONFIG_PATH
    )

    if not resolved_path.exists():
        logger.debug("Configuration file not found: %s", resolved_path)
        return {}

    logger.info("Loading configuration from %s", resolved_path)
    with resolved_path.open("rb") as config_file:
        return tomllib.load(config_file)


def load_backend_names(config_path: Path | str | None = None) -> list[str]:
    """Return the names declared under [backends] in the config file, validated."""
    backends = load_config_file(config_path).get("backends", {})
    if not isinstance(backends, Mapping):
        raise ConfigurationError("[backends] must be a table of named backends")

    for name, table in backends.items():
        if name == DEFAULT_BACKEND_NAME:
            raise ConfigurationError(
                f"Backend name '{DEFAULT_BACKEND_NAME}' is reserved for [research]"
            )
        if ":" in name:
            raise ConfigurationError(f"Backend name '{name}' must not contain ':'")
        if not isinstance(table, Mapping) or "provider" not in table:
            raise ConfigurationError(f"Backend '{name}' must set a provider")

    return list(backends)


def split_backend_task_id(
    task_id: str, config_path: Path | str | None = None
) -> tuple[str, str]:
    """Split '<backend>:<id>' into its parts.

    Returns ``("", task_id)`` when the ID carries no recognized backend prefix,
    so callers can fall back to whichever backend they currently use.
    """
    prefix, separator, raw_task_id = task_id.partition(":")
    if separator and (
        prefix == DEFAULT_BACKEND_NAME or prefix in load_backend_names(config_path)
    ):
        return prefix, raw_task_id
    return "", task_id


def prefix_task_id_with_backend(task_id: str, backend: str | None) -> str:
    """Make sure a task ID sent to an MCP server names the selected backend.

    This is pure string logic: the server's backend names need not exist in
    the local config. An un-prefixed ID gets ``<backend>:`` added; an ID that
    already carries the same prefix is returned unchanged; a different prefix
    is a conflict.
    """
    if not backend:
        return task_id
    prefix, separator, _ = task_id.partition(":")
    if not separator:
        return f"{backend}:{task_id}"
    if prefix != backend:
        raise ConfigurationError(
            f"Task ID names backend '{prefix}' but --backend is '{backend}'"
        )
    return task_id


def flatten_config_data(
    config_data: Mapping[str, Any], prefix: str = ""
) -> dict[str, str]:
    """Flatten nested TOML tables into env-style keys."""
    flattened: dict[str, str] = {}

    for key, value in config_data.items():
        env_key = f"{prefix}{key}".upper()
        if isinstance(value, Mapping):
            flattened.update(flatten_config_data(value, prefix=f"{prefix}{key}_"))
            continue
        if value is None:
            continue
        flattened[env_key] = str(value)

    return flattened


def build_settings_map(
    config_data: Mapping[str, Any] | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Merge file-backed config with environment values, giving precedence to env."""
    settings: dict[str, str] = {}

    if config_data:
        settings.update(flatten_config_data(config_data))

    if env is None:
        env = os.environ

    settings.update({key: value for key, value in env.items() if value is not None})
    return settings


@dataclass
class ResearchConfig:
    """Configuration for Deep Research agent"""

    api_key: str | None = None
    base_url: str | None = None
    provider: str = "openai"
    model: str = "gpt-6-sol"
    api_style: str = "responses"
    timeout: float = 1800.0
    poll_interval: float = 30.0
    cancel_on_timeout: bool = False
    log_level: str = "INFO"
    enable_reasoning_summaries: bool = False
    reasoning_effort: str | None = None
    gnosis_config_path: str | None = None
    gnosis_output_dir: str | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> ResearchConfig:
        """Create configuration from environment values only."""
        return cls._from_settings_map(build_settings_map(env=env))

    @classmethod
    def load(
        cls,
        config_path: Path | str | None = None,
        env: Mapping[str, str] | None = None,
        *,
        backend: str | None = None,
    ) -> ResearchConfig:
        """Create configuration by explicitly loading TOML config plus environment overrides.

        ``backend`` selects a named ``[backends.<name>]`` table. Provider-scoped
        settings from ``[research]`` and ``RESEARCH_*`` env vars do not apply to
        a named backend; runtime settings (timeouts, logging) are inherited.
        """
        config_data = dict(load_config_file(config_path))
        backends = config_data.pop("backends", {})
        settings = build_settings_map(config_data=config_data, env=env)

        if backend and backend != DEFAULT_BACKEND_NAME:
            table = backends.get(backend) if isinstance(backends, Mapping) else None
            if not isinstance(table, Mapping) or "provider" not in table:
                raise ConfigurationError(
                    f"Backend '{backend}' is not defined in the [backends] table"
                )
            for key in _PROVIDER_SCOPED_SETTINGS:
                settings.pop(key, None)
            # Values set in the table win over the provider's own env aliases.
            _, _, api_key_keys, base_url_keys = _PROVIDER_DEFAULTS.get(
                str(table["provider"]), ("", "", (), ())
            )
            if "api_key" in table:
                for key in api_key_keys:
                    settings.pop(key, None)
            if "base_url" in table:
                for key in base_url_keys:
                    settings.pop(key, None)
            settings.update(flatten_config_data({"research": table}))

        return cls._from_settings_map(settings)

    @classmethod
    def _from_settings_map(cls, settings: Mapping[str, str]) -> ResearchConfig:
        """Create configuration from a merged settings map."""

        def get_setting_first(*keys: str, default: str | None = None) -> str | None:
            for key in keys:
                value = settings.get(key)
                if value is not None:
                    return value
            return default

        def get_bool_setting(*keys: str, default: bool = False) -> bool:
            truthy = {"true", "1", "yes", "y", "on"}
            falsy = {"false", "0", "no", "n", "off", ""}

            for key in keys:
                value = settings.get(key)
                if value is None:
                    continue
                normalized = value.strip().lower()
                if normalized in truthy:
                    return True
                if normalized in falsy:
                    return False

            return default

        provider = get_setting_first(
            "RESEARCH_PROVIDER", "PROVIDER", default=cls.provider
        )
        api_style = (
            get_setting_first("RESEARCH_API_STYLE", default=cls.api_style)
            or cls.api_style
        )

        if api_style not in {"responses", "chat_completions"}:
            if provider == "openai":
                raise ConfigurationError(
                    f"Invalid api_style '{api_style}'. Must be 'responses' or 'chat_completions'"
                )
            api_style = cls.api_style

        if provider not in _PROVIDER_DEFAULTS:
            raise ConfigurationError(f"Provider '{provider}' is not supported")

        default_model, default_base_url, api_key_keys, base_url_keys = (
            _PROVIDER_DEFAULTS[provider]
        )
        if provider == "openai" and api_style == "chat_completions":
            default_model = "gpt-6-luna"
        api_key: str | None
        base_url: str | None
        if provider == "openai-codex":
            api_key = None
            base_url = default_base_url
        else:
            if provider == "tavily":
                api_key = get_setting_first(*api_key_keys, "RESEARCH_API_KEY")
            else:
                api_key = get_setting_first("RESEARCH_API_KEY", *api_key_keys)
            base_url = get_setting_first(
                "RESEARCH_BASE_URL", *base_url_keys, default=default_base_url
            )

        return cls(
            api_key=api_key,
            base_url=base_url,
            provider=provider,
            api_style=api_style,
            model=get_setting_first("RESEARCH_MODEL", default=default_model)
            or default_model,
            timeout=float(
                get_setting_first("RESEARCH_TIMEOUT", default=str(cls.timeout))
                or cls.timeout
            ),
            poll_interval=float(
                get_setting_first(
                    "RESEARCH_POLL_INTERVAL", default=str(cls.poll_interval)
                )
                or cls.poll_interval
            ),
            cancel_on_timeout=get_bool_setting(
                "RESEARCH_CANCEL_ON_TIMEOUT", "CANCEL_ON_TIMEOUT", default=False
            ),
            log_level=get_setting_first("LOGGING_LEVEL", default=cls.log_level)
            or cls.log_level,
            enable_reasoning_summaries=get_bool_setting(
                "ENABLE_REASONING_SUMMARIES", default=False
            ),
            reasoning_effort=get_setting_first("RESEARCH_REASONING_EFFORT") or None,
            gnosis_config_path=get_setting_first(
                "RESEARCH_GNOSIS_CONFIG_PATH", "GNOSIS_CONFIG_PATH"
            )
            or None,
            gnosis_output_dir=get_setting_first(
                "RESEARCH_GNOSIS_OUTPUT_DIR", "GNOSIS_OUTPUT_DIR"
            )
            or None,
        )

    def validate(self) -> bool:
        """Validate configuration settings"""
        if self.timeout <= 0:
            raise ConfigurationError("Timeout must be positive")

        if self.poll_interval <= 0:
            raise ConfigurationError("Poll interval must be positive")

        if self.reasoning_effort is not None:
            if self.reasoning_effort not in {
                "none",
                "low",
                "medium",
                "high",
                "xhigh",
                "max",
            }:
                raise ConfigurationError(
                    f"Invalid reasoning effort '{self.reasoning_effort}'"
                )
            if self.provider not in {"openai", "openai-codex"}:
                raise ConfigurationError("Reasoning effort requires an OpenAI provider")

        if self.provider == "openai-codex" and self.base_url:
            if self.base_url.rstrip("/") != OPENAI_CODEX_BASE_URL:
                raise ConfigurationError(
                    "The openai-codex provider only supports "
                    f"{OPENAI_CODEX_BASE_URL}"
                )

        normalized_log_level = self.log_level.upper()
        if not isinstance(logging.getLevelName(normalized_log_level), int):
            raise ConfigurationError(f"Invalid log level '{self.log_level}'")

        return True
