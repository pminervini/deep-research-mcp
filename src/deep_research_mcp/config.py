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
        provider = os.environ.get("PROVIDER", cls.provider)
        
        # Set different defaults based on provider
        default_model = default_base_url = None
        if provider in {"open-deep-research"}:
            # For open-deep-research, model is the LLM model to use
            default_model = "openai/qwen/qwen3-coder-30b"
            default_base_url = "http://localhost:1234/v1"
        elif provider in {"openai"}:
            # For OpenAI, model is the Deep Research model
            default_model = "gpt-5-mini"
            default_base_url = "https://api.openai.com/v1"
        else:
            raise ConfigurationError(f"Provider '{provider}' is not supported")
        
        research_model = os.environ.get("RESEARCH_MODEL", default_model)


        api_key = os.environ.get("OPENAI_API_KEY")
        base_url = os.environ.get("OPENAI_BASE_URL", default_base_url)

        if api_key is None:
             api_key = os.environ.get("API_KEY")

        if base_url is None:
            base_url = os.environ.get("BASE_URL")

        return cls(
            api_key=api_key,
            base_url=base_url,
            provider=os.environ.get("PROVIDER", cls.provider),
            model=research_model,
            timeout=float(os.environ.get("RESEARCH_TIMEOUT", cls.timeout)),
            poll_interval=float(os.environ.get("POLL_INTERVAL", cls.poll_interval)),
            max_retries=int(os.environ.get("MAX_RETRIES", cls.max_retries)),
            log_level=os.environ.get("LOG_LEVEL", cls.log_level),
            enable_clarification=os.environ.get("ENABLE_CLARIFICATION", "false").lower()
            in ("true", "1", "yes"),
            triage_model=os.environ.get("TRIAGE_MODEL", cls.triage_model),
            clarifier_model=os.environ.get("CLARIFIER_MODEL", cls.clarifier_model),
            clarification_base_url=os.environ.get("CLARIFICATION_BASE_URL"),
            clarification_api_key=os.environ.get("CLARIFICATION_API_KEY"),
            instruction_builder_model=os.environ.get(
                "INSTRUCTION_BUILDER_MODEL", cls.instruction_builder_model
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
