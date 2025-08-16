# -*- coding: utf-8 -*-

"""
Custom exceptions for Deep Research MCP.
"""


class ResearchError(Exception):
    """Base exception for research operations"""

    pass



class TaskTimeoutError(ResearchError):
    """Task exceeded maximum execution time"""

    pass


class ConfigurationError(ResearchError):
    """Configuration error"""

    pass
