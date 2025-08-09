# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

See [README.md](README.md) for a complete project description and features overview.

## Architecture

See [ARCH.md](ARCH.md) for detailed architecture documentation including component interactions and file-by-file descriptions.

## Development Commands

See [README.md](README.md) for installation instructions. Development commands:

```bash
# Install dependencies
pip install -r requirements.txt

# Editable development install
pip install -e .

# Run tests
pytest
pytest --cov=deep_research_mcp tests/
pytest tests/test_agent.py

# Code quality
black src/ tests/
pylint src/
mypy src/

# Run MCP server locally
python src/deep_research_mcp/mcp_server.py
```

## Environment Configuration

See [README.md](README.md) for complete configuration details.

## Claude Code Integration

See [README.md](README.md) for MCP server configuration instructions.

## Code Conventions

- Python 3.9+ required
- 4-space indentation, Black formatting
- Type hints required for public functions
- Snake_case for functions/variables, PascalCase for classes
- Use `structlog` for logging, avoid direct prints in library code
- Never commit API keys or secrets
- Never use emojis in code, comments, docstrings, or any part of the codebase

## Code Simplicity & Minimal Changes

- Keep code simple and clean: prefer straightforward solutions over complex ones
- Make minimal changes: only implement what was explicitly requested, nothing more
- Avoid adding extra functionality, features, or optimizations that weren't asked for
- Use existing patterns and structures in the codebase rather than introducing new approaches
- When fixing bugs, address only the specific issue without refactoring unrelated code