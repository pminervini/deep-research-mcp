# -*- coding: utf-8 -*-

"""
Custom exceptions for deep-research-mcp.
"""


class ResearchError(Exception):
    """Base exception for research operations"""


class TaskTimeoutError(ResearchError):
    """Task exceeded maximum execution time"""


class ConfigurationError(ResearchError):
    """Configuration error"""
