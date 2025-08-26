# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Code Style Requirements

- **NO EMOJIS**: This codebase strictly prohibits the use of emojis in all Python (.py) and Markdown (.md) files. Do not add emojis to code, comments, docstrings, or documentation.

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

## Research Provider Options

This MCP server supports two research providers:

### 1. OpenAI (Default)
Uses OpenAI's Responses API with built-in web search and code interpreter tools.

### 2. Open Deep Research  
Uses the open-source alternative with smolagents framework, providing customizable search tools and local model support.

Choose your provider in the configuration file with the `provider` key in `[research]`, or set env `PROVIDER`.

## Clarification Feature

The MCP server includes an optional clarification system that can ask follow-up questions to improve research quality.

### Configuration

Add these settings to your `~/.deep_research` TOML file:

```toml
# Enable/disable clarification (default: false)
enable_clarification = true

# Models for clarification agents (default: gpt-5-mini for both)
triage_model = "gpt-5-mini"
clarifier_model = "gpt-5-mini"

# Instruction builder model (always enabled, default: gpt-5-mini)
instruction_builder_model = "gpt-5-mini"

# Custom API key for clarification models (optional)
clarification_api_key = "sk-your-clarification-api-key-here"

# Custom base URL for clarification models (optional)
clarification_base_url = "https://custom-api.example.com/v1"
```

### Usage

1. **Request clarification**: Call `deep_research()` with `request_clarification=True`
2. **Answer questions**: The tool returns clarifying questions and a session ID
3. **Enhanced research**: Use `research_with_context()` with the session ID and your answers

### Configuration Examples

#### OpenAI Configuration

```toml
[research]
provider = "openai"
model = "gpt-5-mini"                 # Pick a Responses API model
api_key = "sk-your-api-key-here"     # Or set env OPENAI_API_KEY
base_url = "https://api.openai.com/v1"
timeout = 1800
poll_interval = 30
max_retries = 3

[clarification]
enable_clarification = true
triage_model = "gpt-5-mini"
clarifier_model = "gpt-5-mini"
instruction_builder_model = "gpt-5-mini"
clarification_api_key = ""           # Optional, overrides api_key
clarification_base_url = ""          # Optional, overrides base_url
```

#### Open Deep Research Configuration

```toml
[research]
provider = "open-deep-research"
model = "openai/qwen/qwen3-coder-30b"  # Any LiteLLM-compatible model id
base_url = "http://localhost:1234/v1"  # OpenAI-compatible endpoint (local or remote)
api_key = ""                           # Optional if endpoint requires it
timeout = 1800

[logging]
level = "INFO"
```

Optional env variables for Open Deep Research tools:

- `SERPAPI_API_KEY` or `SERPER_API_KEY`: enable Google-style search
- `HF_TOKEN`: optional, logs into Hugging Face Hub for gated models

#### Installation for Open Deep Research

If using the Open Deep Research provider, all required dependencies are included in the main requirements file:

```bash
pip install -r requirements.txt
```

The ODR-specific dependencies are included via the `open-deep-research` extra in `requirements.txt` and will be installed automatically.
