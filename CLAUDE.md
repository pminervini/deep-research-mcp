# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Deep Research MCP is a Python-based agent that integrates OpenAI's Deep Research API with Claude Code through the Model Context Protocol (MCP). It enables autonomous research tasks with web search, code execution, and citation management capabilities.

## Architecture

- **Core Agent**: `src/deep_research_mcp/agent.py` - Main `DeepResearchAgent` class that orchestrates Deep Research API interactions, handles async task polling, and manages research workflows
- **MCP Server**: `src/deep_research_mcp/mcp_server.py` - FastMCP-based server that exposes research capabilities to Claude Code via MCP protocol
- **Configuration**: `src/deep_research_mcp/config.py` - Environment-based settings using Pydantic dataclasses, handles API keys and research parameters
- **Rate Limiting**: `src/deep_research_mcp/rate_limiter.py` - Retry logic with exponential backoff for API resilience
- **Error Handling**: `src/deep_research_mcp/errors.py` - Custom exception types for research failures, timeouts, and rate limits

The agent supports two Deep Research models: `o3-deep-research-2025-06-26` (full model) and `o4-mini-deep-research-2025-06-26` (faster, lower-cost alternative).

## Development Commands

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

## Testing Strategy

Uses `pytest` with `pytest-asyncio` for async tests. Test files mirror package structure in `tests/` directory. Mark async tests with `@pytest.mark.asyncio`. Focus on testing error conditions like API failures, timeouts, and rate limiting scenarios.

## Environment Configuration

Required environment variables:
- `OPENAI_API_KEY`: OpenAI API key (must start with "sk-")
- `RESEARCH_MODEL`: Model to use (defaults to "o3-deep-research-2025-06-26")
- `RESEARCH_TIMEOUT`: Task timeout in seconds (default: 1800)
- `POLL_INTERVAL`: Polling interval in seconds (default: 30)

## Claude Code Integration

Configure in `~/.config/claude-code/mcp.json`:
```json
{
  "mcpServers": {
    "deep-research": {
      "command": "python",
      "args": ["/path/to/deep-research-mcp/src/deep_research_mcp/mcp_server.py"],
      "env": {
        "OPENAI_API_KEY": "${OPENAI_API_KEY}",
        "RESEARCH_MODEL": "o3-deep-research-2025-06-26"
      }
    }
  }
}
```

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