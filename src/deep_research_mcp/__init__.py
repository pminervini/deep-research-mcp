# -*- coding: utf-8 -*-

"""
Deep Research MCP - OpenAI Deep Research Integration for Claude Code
"""

__version__ = "0.1.0"

from .agent import DeepResearchAgent
from .config import ResearchConfig
from .errors import ResearchError, RateLimitError, TaskTimeoutError

__all__ = [
    "DeepResearchAgent",
    "ResearchConfig",
    "ResearchError",
    "RateLimitError",
    "TaskTimeoutError",
]
