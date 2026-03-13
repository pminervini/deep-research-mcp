# -*- coding: utf-8 -*-

"""
Provider-specific research backend package.
"""

import logging

from deep_research_mcp.config import ResearchConfig
from deep_research_mcp.errors import ConfigurationError

from .base import ResearchBackend
from .gemini_backend import GeminiResearchBackend
from .open_deep_research_backend import OpenDeepResearchBackend
from .openai_backend import OpenAIResearchBackend


def build_research_backend(
    config: ResearchConfig, logger: logging.Logger
) -> ResearchBackend:
    """Construct the provider-specific backend for the current configuration."""
    if config.provider in {"openai"}:
        return OpenAIResearchBackend(config, logger)
    if config.provider in {"gemini"}:
        return GeminiResearchBackend(config, logger)
    if config.provider in {"open-deep-research"}:
        return OpenDeepResearchBackend(config, logger)
    raise ConfigurationError(f"Provider '{config.provider}' is not supported")


__all__ = [
    "ResearchBackend",
    "OpenAIResearchBackend",
    "GeminiResearchBackend",
    "OpenDeepResearchBackend",
    "build_research_backend",
]
