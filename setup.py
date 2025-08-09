#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Setup script for deep-research-mcp package.
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="deep-research-mcp",
    version="0.1.0",
    author="Deep Research MCP Team",
    description="A Python-based agent that integrates OpenAI's Deep Research API with Claude Code through MCP",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/pminervini/deep-research-mcp",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.9",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "deep-research-mcp=deep_research_mcp.mcp_server:main",
        ],
    },
    include_package_data=True,
)