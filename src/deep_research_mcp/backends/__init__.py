# -*- coding: utf-8 -*-

"""
Provider-specific research backend package.
"""

import logging

from deep_research_mcp.config import ResearchConfig
from deep_research_mcp.errors import ConfigurationError

from .base import ResearchBackend
from .dr_tulu_backend import DrTuluResearchBackend
from .gemini_backend import GeminiResearchBackend
from .open_deep_research_backend import OpenDeepResearchBackend
from .openai_backend import OpenAIResearchBackend

_BACKENDS: dict[str, type[ResearchBackend]] = {
    "openai": OpenAIResearchBackend,
    "dr-tulu": DrTuluResearchBackend,
    "gemini": GeminiResearchBackend,
    "open-deep-research": OpenDeepResearchBackend,
}


def build_research_backend(
    config: ResearchConfig, logger: logging.Logger
) -> ResearchBackend:
    """Construct the provider-specific backend for the current configuration."""
    backend_cls = _BACKENDS.get(config.provider)
    if backend_cls is None:
        raise ConfigurationError(f"Provider '{config.provider}' is not supported")
    return backend_cls(config, logger)


__all__ = [
    "ResearchBackend",
    "OpenAIResearchBackend",
    "DrTuluResearchBackend",
    "GeminiResearchBackend",
    "OpenDeepResearchBackend",
    "build_research_backend",
]
