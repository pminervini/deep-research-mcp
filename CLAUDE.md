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

The server exposes two main tools:
- `deep_research()` - Perform autonomous research with web search and analysis
- `research_status()` - Check status of running research tasks