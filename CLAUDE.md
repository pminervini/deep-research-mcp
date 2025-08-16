# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Documentation

For complete project overview, installation instructions, and usage examples, see [README.md](README.md).

For detailed architecture and component descriptions, see [ARCH.md](ARCH.md).

## Development Commands

### Testing
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=deep_research_mcp tests/

# Run specific test file
pytest tests/test_agent.py
```

### Code Quality
```bash
# Format code
black src/ tests/

# Lint code
pylint src/deep_research_mcp/

# Type checking
mypy src/deep_research_mcp/
```

### Running the MCP Server
```bash
# Start the MCP server directly
python src/deep_research_mcp/mcp_server.py

# Or use the installed console script
deep-research-mcp
```

## MCP Integration for Claude Code

To add this MCP server to Claude Code:
```bash
claude mcp add deep-research python /path/to/deep-research-mcp/src/deep_research_mcp/mcp_server.py
```

The server exposes three main tools:
- `deep_research()` - Perform autonomous research with web search and analysis (supports clarification)
- `research_with_context()` - Perform research using enriched queries from clarification
- `research_status()` - Check status of running research tasks

## Clarification Feature

The MCP server includes an optional clarification system that can ask follow-up questions to improve research quality.

### Configuration

Add these settings to your `~/.deep_research` TOML file:

```toml
# Enable/disable clarification (default: false)
enable_clarification = true

# Models for clarification agents (default: gpt-4o-mini for both)
triage_model = "gpt-4o-mini"
clarifier_model = "gpt-4o-mini"
```

### Usage

1. **Request clarification**: Call `deep_research()` with `request_clarification=True`
2. **Answer questions**: The tool returns clarifying questions and a session ID
3. **Enhanced research**: Use `research_with_context()` with the session ID and your answers

### Example Configuration File

Complete `~/.deep_research` TOML example:

```toml
# Required
research_model = "o4-mini-deep-research-2025-06-26"

# Optional (will use environment variable if not set)
openai_api_key = "sk-your-api-key-here"

# Standard settings
research_timeout = 1800
poll_interval = 30
max_retries = 3
log_level = "INFO"

# Clarification settings
enable_clarification = true
triage_model = "gpt-4o-mini"
clarifier_model = "gpt-4o-mini"
```