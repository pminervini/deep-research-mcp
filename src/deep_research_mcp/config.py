# -*- coding: utf-8 -*-

"""
Configuration management for Deep Research MCP.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from deep_research_mcp.errors import ConfigurationError

import toml

import logging

logger = logging.getLogger(__name__)


def load_config_file():
    """Load configuration from ~/.deep_research TOML file"""
    logger.info("Loading configuration from ~/.deep_research file")
    config_file = Path.home() / ".deep_research"
    if config_file.exists():
        with open(config_file, "r") as f:
            config = toml.load(f)

        # Flatten nested config and set environment variables
        def set_env_vars(data, prefix=""):
            for key, value in data.items():
                env_key = f"{prefix}{key}".upper()
                if isinstance(value, dict):
                    set_env_vars(value, f"{prefix}{key}_")
                else:
                    if env_key in os.environ:
                        logger.warning(f"Environment variable {env_key} already exists, skipping")
                    else:
                        os.environ[env_key] = str(value)

        set_env_vars(config)

    return


# Load configuration from ~/.deep_research file
load_config_file()


@dataclass
class ResearchConfig:
    """Configuration for Deep Research agent"""

    api_key: Optional[str] = None
    base_url: Optional[str] = None
    provider: str = "openai"
    model: str = "o4-mini-deep-research-2025-06-26"
    timeout: float = 1800.0  # 30 minutes
    poll_interval: float = 30.0
    max_retries: int = 3
    log_level: str = "INFO"

    # Clarification settings
    enable_clarification: bool = False
    triage_model: str = "gpt-5-mini"
    clarifier_model: str = "gpt-5-mini"
    clarification_base_url: Optional[str] = None
    clarification_api_key: Optional[str] = None

    # Instruction builder settings
    instruction_builder_model: str = "gpt-5-mini"

    @classmethod
    def from_env(cls) -> "ResearchConfig":
        """Create configuration from environment variables"""
        logger.info("Creating configuration from environment variables")
        provider = os.environ.get("RESEARCH_PROVIDER", cls.provider)

        # Helpers for resolving environment variables with backward-compatible aliases
        def get_env_first(*keys: str, default: Optional[str] = None) -> Optional[str]:
            for key in keys:
                val = os.environ.get(key)
                if val is not None:
                    return val
            return default

        def get_bool_env(*keys: str, default: bool = False) -> bool:
            truthy = {"true", "1", "yes", "y", "on"}
            falsy = {"false", "0", "no", "n", "off"}
            for key in keys:
                val = os.environ.get(key)
                if val is not None:
                    v = val.strip().lower()
                    if v in truthy:
                        return True
                    if v in falsy:
                        return False
            return default

        # Print all environment variables for debugging
        logger.debug("All environment variables:")
        for key, value in sorted(os.environ.items()):
            logger.debug(f"  {key}={value}")

        # Set different defaults based on provider
        default_model = default_base_url = None
        if provider in {"open-deep-research"}:
            # For open-deep-research, model is the LLM model to use
            default_model = "openai/qwen/qwen3-coder-30b"
            default_base_url = "http://localhost:1234/v1"
        elif provider in {"openai"}:
            # For OpenAI, model is the Deep Research model
            default_model = "o4-mini-deep-research-2025-06-26"
            default_base_url = "https://api.openai.com/v1"
        else:
            raise ConfigurationError(f"Provider '{provider}' is not supported")
        
        research_model = os.environ.get("RESEARCH_MODEL", default_model)

        api_key = get_env_first("RESEARCH_API_KEY", "OPENAI_API_KEY")
        base_url = get_env_first("RESEARCH_BASE_URL", "OPENAI_BASE_URL", default=default_base_url)

        return cls(
            api_key=api_key,
            base_url=base_url,
            provider=os.environ.get("RESEARCH_PROVIDER", cls.provider),
            model=research_model,
            timeout=float(os.environ.get("RESEARCH_TIMEOUT", cls.timeout)),
            poll_interval=float(os.environ.get("RESEARCH_POLL_INTERVAL", cls.poll_interval)),
            max_retries=int(os.environ.get("RESEARCH_MAX_RETRIES", cls.max_retries)),
            log_level=os.environ.get("LOGGING_LEVEL", cls.log_level),
            enable_clarification=get_bool_env(
                # Preferred env var (used in README examples)
                "ENABLE_CLARIFICATION",
                # Existing env var created by TOML flattener for [clarification].enable_clarification
                "CLARIFICATION_ENABLE",
                default=False,
            ),
            triage_model=os.environ.get("CLARIFICATION_TRIAGE_MODEL", cls.triage_model),
            clarifier_model=os.environ.get("CLARIFICATION_CLARIFIER_MODEL", cls.clarifier_model),
            instruction_builder_model=get_env_first(
                # Preferred when set under [clarification] in TOML
                "CLARIFICATION_INSTRUCTION_BUILDER_MODEL",
                # Backward-compatible top-level env var
                "INSTRUCTION_BUILDER_MODEL",
                default=cls.instruction_builder_model,
            ),
            clarification_base_url=get_env_first(
                # Standard from [clarification].base_url
                "CLARIFICATION_BASE_URL",
                # Also accept [clarification].clarification_base_url (would flatten twice)
                "CLARIFICATION_CLARIFICATION_BASE_URL",
            ),
            clarification_api_key=get_env_first(
                # Standard from [clarification].api_key
                "CLARIFICATION_API_KEY",
                # Also accept [clarification].clarification_api_key (would flatten twice)
                "CLARIFICATION_CLARIFICATION_API_KEY",
            ),
        )

    def validate(self) -> bool:
        """Validate configuration settings"""
        if self.provider in {"openai"}:
            if self.api_key and not self.api_key.startswith("sk-"):
                raise ConfigurationError("Invalid API key format")

        if self.timeout <= 0:
            raise ConfigurationError("Timeout must be positive")

        if self.poll_interval <= 0:
            raise ConfigurationError("Poll interval must be positive")

        if self.max_retries < 0:
            raise ConfigurationError("Max retries must be non-negative")

        return True
