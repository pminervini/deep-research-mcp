# -*- coding: utf-8 -*-

"""
Configuration management for Deep Research MCP.
"""

import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


@dataclass
class ResearchConfig:
    """Configuration for Deep Research agent"""

    api_key: str
    model: str = "o3-deep-research"
    timeout: float = 1800.0  # 30 minutes
    poll_interval: float = 30.0
    max_retries: int = 3
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "ResearchConfig":
        """Create configuration from environment variables"""
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")

        return cls(
            api_key=api_key,
            model=os.environ.get("RESEARCH_MODEL", cls.model),
            timeout=float(os.environ.get("RESEARCH_TIMEOUT", cls.timeout)),
            poll_interval=float(os.environ.get("POLL_INTERVAL", cls.poll_interval)),
            max_retries=int(os.environ.get("MAX_RETRIES", cls.max_retries)),
            log_level=os.environ.get("LOG_LEVEL", cls.log_level),
        )

    def validate(self) -> bool:
        """Validate configuration settings"""
        if not self.api_key or not self.api_key.startswith("sk-"):
            raise ValueError("Invalid API key format")

        if self.timeout <= 0:
            raise ValueError("Timeout must be positive")

        if self.poll_interval <= 0:
            raise ValueError("Poll interval must be positive")

        if self.max_retries < 0:
            raise ValueError("Max retries must be non-negative")

        if self.model not in [
            "o3-deep-research",
            "o4-mini-deep-research",
        ]:
            raise ValueError(f"Unknown model: {self.model}")

        return True
