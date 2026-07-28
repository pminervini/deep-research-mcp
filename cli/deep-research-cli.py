#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Compatibility wrapper for the installed deep-research-cli command."""

from deep_research_mcp.cli import build_parser, main

__all__ = ["build_parser", "main"]


if __name__ == "__main__":
    main()
