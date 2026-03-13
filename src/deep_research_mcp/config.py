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
        config_data = tomllib.load(config_file)

    if not isinstance(config_data, dict):
        raise ConfigurationError(
            f"Configuration file {resolved_path} did not contain a TOML table"
        )

    return config_data


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
    model: str = "o4-mini-deep-research-2025-06-26"
    api_style: str = "responses"
    timeout: float = 1800.0
    poll_interval: float = 30.0
    max_retries: int = 3
    log_level: str = "INFO"
    enable_clarification: bool = False
    triage_model: str = "gpt-5-mini"
    clarifier_model: str = "gpt-5-mini"
    clarification_base_url: str | None = None
    clarification_api_key: str | None = None
    instruction_builder_model: str = "gpt-5-mini"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> ResearchConfig:
        """Create configuration from environment values only."""
        return cls._from_settings_map(build_settings_map(env=env))

    @classmethod
    def load(
        cls,
        config_path: Path | str | None = None,
        env: Mapping[str, str] | None = None,
    ) -> ResearchConfig:
        """Create configuration by explicitly loading TOML config plus environment overrides."""
        return cls._from_settings_map(
            build_settings_map(config_data=load_config_file(config_path), env=env)
        )

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

        if provider in {"openai"} and api_style not in {
            "responses",
            "chat_completions",
        }:
            raise ConfigurationError(
                f"Invalid api_style '{api_style}'. Must be 'responses' or 'chat_completions'"
            )

        if provider not in {"openai"} and api_style not in {
            "responses",
            "chat_completions",
        }:
            api_style = cls.api_style

        if provider in {"open-deep-research"}:
            default_model = "openai/qwen/qwen3-coder-30b"
            default_base_url = "http://localhost:1234/v1"
            api_key = get_setting_first("RESEARCH_API_KEY", "OPENAI_API_KEY")
            base_url = get_setting_first(
                "RESEARCH_BASE_URL", "OPENAI_BASE_URL", default=default_base_url
            )
        elif provider in {"openai"}:
            default_model = (
                "gpt-5-mini"
                if api_style == "chat_completions"
                else "o4-mini-deep-research-2025-06-26"
            )
            default_base_url = "https://api.openai.com/v1"
            api_key = get_setting_first("RESEARCH_API_KEY", "OPENAI_API_KEY")
            base_url = get_setting_first(
                "RESEARCH_BASE_URL", "OPENAI_BASE_URL", default=default_base_url
            )
        elif provider in {"gemini"}:
            default_model = "deep-research-pro-preview-12-2025"
            default_base_url = "https://generativelanguage.googleapis.com"
            api_key = get_setting_first(
                "RESEARCH_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"
            )
            base_url = get_setting_first(
                "RESEARCH_BASE_URL", "GEMINI_BASE_URL", default=default_base_url
            )
        else:
            raise ConfigurationError(f"Provider '{provider}' is not supported")

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
            max_retries=int(
                get_setting_first("RESEARCH_MAX_RETRIES", default=str(cls.max_retries))
                or cls.max_retries
            ),
            log_level=get_setting_first("LOGGING_LEVEL", default=cls.log_level)
            or cls.log_level,
            enable_clarification=get_bool_setting(
                "ENABLE_CLARIFICATION", "CLARIFICATION_ENABLE", default=False
            ),
            triage_model=get_setting_first(
                "CLARIFICATION_TRIAGE_MODEL", "TRIAGE_MODEL", default=cls.triage_model
            )
            or cls.triage_model,
            clarifier_model=get_setting_first(
                "CLARIFICATION_CLARIFIER_MODEL",
                "CLARIFIER_MODEL",
                default=cls.clarifier_model,
            )
            or cls.clarifier_model,
            instruction_builder_model=get_setting_first(
                "CLARIFICATION_INSTRUCTION_BUILDER_MODEL",
                "INSTRUCTION_BUILDER_MODEL",
                default=cls.instruction_builder_model,
            )
            or cls.instruction_builder_model,
            clarification_base_url=get_setting_first("CLARIFICATION_BASE_URL"),
            clarification_api_key=get_setting_first("CLARIFICATION_API_KEY"),
        )

    def validate(self) -> bool:
        """Validate configuration settings"""
        if self.timeout <= 0:
            raise ConfigurationError("Timeout must be positive")

        if self.poll_interval <= 0:
            raise ConfigurationError("Poll interval must be positive")

        if self.max_retries < 0:
            raise ConfigurationError("Max retries must be non-negative")

        normalized_log_level = self.log_level.upper()
        if not isinstance(logging.getLevelName(normalized_log_level), int):
            raise ConfigurationError(f"Invalid log level '{self.log_level}'")

        return True
