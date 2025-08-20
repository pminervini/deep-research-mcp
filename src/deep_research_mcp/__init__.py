# -*- coding: utf-8 -*-

"""
Deep Research MCP - OpenAI Deep Research Integration for Claude Code
"""

__version__ = "0.1.0"

from deep_research_mcp.agent import DeepResearchAgent
from deep_research_mcp.config import ResearchConfig
from deep_research_mcp.errors import ResearchError, TaskTimeoutError
from deep_research_mcp.prompts import PromptManager

__all__ = [
    "DeepResearchAgent",
    "ResearchConfig",
    "ResearchError",
    "TaskTimeoutError",
    "PromptManager",
]
