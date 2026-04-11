# Deep Research MCP

[![CI](https://img.shields.io/github/actions/workflow/status/pminervini/deep-research-mcp/ci.yml?branch=main&label=CI)](https://github.com/pminervini/deep-research-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-compatible-4a5568)](https://modelcontextprotocol.io/)
[![Claude Code](https://img.shields.io/badge/Claude_Code-ready-cc785c)](https://github.com/pminervini/deep-research-mcp#claude-code-integration)
[![OpenAI](https://img.shields.io/badge/OpenAI-compatible-10a37f)](https://platform.openai.com/)
[![Gemini](https://img.shields.io/badge/Gemini-supported-4285F4)](https://ai.google.dev/)

A Python-based agent that integrates research providers with Claude Code through the Model Context Protocol (MCP). It supports OpenAI (Responses API with web search and code interpreter, or Chat Completions API for broad provider compatibility), Gemini Deep Research via the Interactions API, and the open-source Open Deep Research stack (based on smolagents).

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) installed
- One of:
  - OpenAI API access (Responses API models, e.g., `o4-mini-deep-research-2025-06-26`)
  - Gemini API access with the Interactions API / Deep Research agent enabled
  - Open Deep Research dependencies (installed via `uv sync --extra open-deep-research`)
- Claude Code, or any other assistant supporting MCP integration

## Installation

Recommended setup (resolves the latest compatible versions):

```bash
# Install runtime dependencies + project in editable mode
uv sync --upgrade

# Development tooling (pytest, black, pylint, mypy, pre-commit)
uv sync --upgrade --extra dev

# Enable the pre-commit hook so black runs automatically before each commit
uv run pre-commit install

# Optional docs tooling
uv sync --upgrade --extra docs

# Optional Open Deep Research provider dependencies
uv sync --upgrade --extra open-deep-research
```

Compatibility setup (pip-based):

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

`requirements.txt` is intentionally unpinned (uses `>=`) and can be edited directly.
`uv.lock` is not tracked in this repository.

## Code Layout

- `src/deep_research_mcp/agent.py`: orchestration layer; owns clarification, instruction building, callbacks, and delegates provider work to backends
- `src/deep_research_mcp/backends/`: provider-specific implementations for OpenAI, Gemini, and Open Deep Research
- `src/deep_research_mcp/mcp_server.py`: FastMCP server and tool entrypoints
- `src/deep_research_mcp/clarification.py`: clarification agents, sessions, and enrichment flow
- `src/deep_research_mcp/prompts/`: YAML prompt templates used by clarification and instruction building
- `cli/deep-research-cli.py`: unified CLI for agent mode, MCP client mode, and configuration viewing
- `cli/deep-research-tui.py`: interactive full-screen terminal UI for clarification, research, status checks, and saving output to disk
- `tests/`: `pytest` suite covering configuration, MCP integration, prompts, results, and clarification flows

## Configuration

### Configuration File

Create a `~/.deep_research` file in your home directory using TOML format.

Library note: `ResearchConfig.load()` explicitly reads this file and applies environment variable overrides. `ResearchConfig.from_env()` reads environment variables only.

Common settings:

```toml
[research]                                  # Core Deep Research functionality
provider = "openai"                         # Available options: "openai", "dr-tulu", "gemini", "open-deep-research" -- defaults to "openai"
api_style = "responses"                     # Only applies to provider="openai"; use "chat_completions" for Perplexity, Groq, Ollama, etc.
model = "o4-mini-deep-research-2025-06-26"  # OpenAI: model identifier; Dr Tulu: logical provider id; Gemini: agent id; ODR: LiteLLM model identifier
api_key = "your-api-key"                    # API key, optional
base_url = "https://api.openai.com/v1"      # OpenAI: OpenAI-compatible endpoint; Dr Tulu: service base URL; Gemini: https://generativelanguage.googleapis.com; ODR: LiteLLM-compatible endpoint

# Task behavior
timeout = 1800
poll_interval = 30

# Largely based on https://cookbook.openai.com/examples/deep_research_api/introduction_to_deep_research_api_agents
[clarification]                                       # Optional query clarification component
enable = true
triage_model = "gpt-5-mini"
clarifier_model = "gpt-5-mini"
instruction_builder_model = "gpt-5-mini"
api_key = "sk-your-api-key"             # Optional, overrides api_key
base_url = "https://api.openai.com/v1"  # Optional, overrides base_url

[logging]
level = "INFO"
```

OpenAI provider example:

```toml
[research]
provider = "openai"
model = "o4-mini-deep-research-2025-06-26"  # OpenAI model
api_key = "sk-..."                          # Defaults to OPENAI_API_KEY
base_url = "https://api.openai.com/v1"      # OpenAI-compatible endpoint
timeout = 1800
poll_interval = 30
```

Gemini Deep Research provider example:

```toml
[research]
provider = "gemini"
model = "deep-research-pro-preview-12-2025"     # Gemini Deep Research agent id
api_key = "AIza..."                             # Defaults to GEMINI_API_KEY or GOOGLE_API_KEY
base_url = "https://generativelanguage.googleapis.com"
timeout = 1800
poll_interval = 30
```

Dr Tulu provider example:

```toml
[research]
provider = "dr-tulu"
model = "dr-tulu"                   # Logical provider model id; currently informational
base_url = "http://10.8.0.42/"      # Dr Tulu service base URL; the backend calls /chat
api_key = ""                        # Optional; defaults to RESEARCH_API_KEY / DR_TULU_API_KEY if set
timeout = 1800
poll_interval = 30
```

Perplexity (via [Sonar Deep Research](https://docs.perplexity.ai/getting-started/models/models/sonar-deep-research) and Perplexity's [OpenAI-compatible endpoint](https://docs.perplexity.ai/guides/chat-completions-guide)) provider example:

```toml
[research]
provider = "openai"
api_style = "chat_completions"              # Required for Perplexity (no Responses API)
model = "sonar-deep-research"               # Perplexity's Sonar Deep Research
api_key = "ppl-..."                         # Defaults to OPENAI_API_KEY
base_url = "https://api.perplexity.ai"      # Perplexity's OpenAI-compatible endpoint
timeout = 1800
```

Open Deep Research provider example:

```toml
[research]
provider = "open-deep-research"
model = "openai/qwen/qwen3-coder-30b"  # LiteLLM-compatible model id
base_url = "http://localhost:1234/v1"  # LiteLLM-compatible endpoint (local or remote)
api_key = ""                           # Optional if endpoint requires it
timeout = 1800
```

Ollama (local) provider example:

```toml
[research]
provider = "openai"
api_style = "chat_completions"
model = "llama3.1"                     # Any model available in your Ollama instance
base_url = "http://localhost:11434/v1" # Ollama's OpenAI-compatible endpoint
api_key = ""                           # Not required for local Ollama
timeout = 600
```

llama-server (local llama.cpp server) provider example:

```toml
[research]
provider = "openai"
api_style = "chat_completions"
model = "qwen2.5-0.5b"                 # Must match the --alias passed to llama-server
base_url = "http://127.0.0.1:8081/v1"  # llama-server OpenAI-compatible endpoint
api_key = "test"                       # Must match the --api-key passed to llama-server
timeout = 600
```

Generic OpenAI-compatible Chat Completions provider (Groq, Together AI, vLLM, etc.):

```toml
[research]
provider = "openai"
api_style = "chat_completions"
model = "your-model-name"
api_key = "your-api-key"
base_url = "https://api.your-provider.com/v1"
timeout = 600
```

Optional env variables for Open Deep Research tools:

- `SERPAPI_API_KEY` or `SERPER_API_KEY`: enable Google-style search
- `HF_TOKEN`: optional, logs into Hugging Face Hub for gated models

### Claude Code Integration

1. **Configure MCP Server**

Choose one of the transports below.

**Option A: stdio (recommended when Claude Code should spawn the server itself)**

If your provider credentials are already stored in `~/.deep_research`, the
minimal setup is:

```bash
claude mcp add deep-research -- uv run --directory /path/to/deep-research-mcp deep-research-mcp
```

If you want Claude Code to pass `OPENAI_API_KEY` through to the spawned MCP
process explicitly, use:

```bash
claude mcp add -e OPENAI_API_KEY="$OPENAI_API_KEY" \
  deep-research -- \
  uv run --directory /path/to/deep-research-mcp deep-research-mcp
```

**Option B: HTTP (recommended when you want to run the server separately)**

Start the server in one terminal:

```bash
OPENAI_API_KEY="$OPENAI_API_KEY" \
uv run --directory /path/to/deep-research-mcp \
  deep-research-mcp --transport http --host 127.0.0.1 --port 8080
```

Then add the HTTP MCP server in Claude Code:

```bash
claude mcp add --transport http deep-research-http http://127.0.0.1:8080/mcp
```

Replace `/path/to/deep-research-mcp/` with the actual path to your cloned repository.
The verified Streamable HTTP endpoint is `http://127.0.0.1:8080/mcp`.

For multi-hour research, raise Claude Code's tool timeout before launching the CLI and rely on incremental status polls:

```bash
export MCP_TOOL_TIMEOUT=14400000  # 4 hours
claude --mcp-config ./.mcp.json
```

Kick off work with `deep_research` or `research_with_context`, note the returned job ID, and call `research_status` to stream progress without letting any single tool call stagnate.

2. **Use in Claude Code**:
   - The research tools will appear in Claude Code's tool palette
   - Simply ask Claude to "research [your topic]" and it will use the Deep Research agent
   - For clarified research, ask Claude to "research [topic] with clarification" to get follow-up questions

### OpenAI Codex Integration

1. **Configure MCP Server**

Choose one of the transports below.

**Option A: stdio (recommended when Codex should spawn the server itself)**

Add the MCP server configuration to your `~/.codex/config.toml` file:

```toml
[mcp_servers.deep-research]
command = "uv"
args = ["run", "--directory", "/path/to/deep-research-mcp", "deep-research-mcp"]
# If your provider credentials live in shell env vars rather than ~/.deep_research,
# pass them through to the MCP subprocess explicitly:
env_vars = ["OPENAI_API_KEY"]
startup_timeout_ms = 30000  # 30 seconds for server startup
request_timeout_ms = 7200000  # 2 hours for long-running research tasks
# Alternatively, set tool_timeout_sec when using newer Codex clients
# tool_timeout_sec = 14400.0     # 4 hours for deep research runs
```

Replace `/path/to/deep-research-mcp/` with the actual path to your cloned repository.

If your credentials are already configured in `~/.deep_research`, `env_vars` is
optional. It is required when you expect the spawned MCP server to inherit
`OPENAI_API_KEY` from the parent shell.

**Option B: HTTP (recommended when you want to run the server separately)**

Start the server in one terminal:

```bash
OPENAI_API_KEY="$OPENAI_API_KEY" \
uv run --directory /path/to/deep-research-mcp \
  deep-research-mcp --transport http --host 127.0.0.1 --port 8080
```

Then add this to `~/.codex/config.toml`:

```toml
[mcp_servers.deep-research-http]
url = "http://127.0.0.1:8080/mcp"
tool_timeout_sec = 14400.0
```

The verified Streamable HTTP endpoint is `http://127.0.0.1:8080/mcp`.

**Important timeout configuration:**
- `startup_timeout_ms`: Time allowed for the MCP server to start (default: 30000ms / 30 seconds)
- `request_timeout_ms`: Maximum time for research queries to complete (recommended: 7200000ms / 2 hours for comprehensive research)
- `tool_timeout_sec`: Preferred for newer Codex clients; set this to a large value (e.g., `14400.0` for 4 hours) when you expect long-running research.
- Kick off research once to capture the job ID, then poll `research_status` so each tool call remains short and avoids hitting client timeouts.

Without proper timeout configuration, long-running research queries may fail with "request timed out" errors.

2. **Use in OpenAI Codex**:
   - The research tools will be available automatically when you start Codex
   - Ask Codex to "research [your topic]" and it will use the Deep Research MCP server
   - For clarified research, ask for "research [topic] with clarification"

### Gemini CLI Integration

1. **Configure MCP Server**

Add the MCP server using Gemini CLI's built-in command:

```bash
gemini mcp add deep-research -- uv run --directory /path/to/deep-research-mcp deep-research-mcp
```

Or manually add to your `~/.gemini/settings.json` file:

```json
{
  "mcpServers": {
    "deep-research": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/deep-research-mcp", "deep-research-mcp"],
      "env": {
        "RESEARCH_PROVIDER": "gemini",
        "GEMINI_API_KEY": "$GEMINI_API_KEY"
      }
    }
  }
}
```

Replace `/path/to/deep-research-mcp/` with the actual path to your cloned repository.

2. **Use in Gemini CLI**:
   - Start Gemini CLI with `gemini`
   - The research tools will be available automatically
   - Ask Gemini to "research [your topic]" and it will use the Deep Research MCP server
   - Use `/mcp` command to view server status and available tools

HTTP transport: If your Gemini environment supports MCP-over-HTTP, you may run
the server with `--transport http` and configure Gemini with the server URL.

## Usage

### As a Standalone Python Module

```python
import asyncio
from deep_research_mcp.agent import DeepResearchAgent
from deep_research_mcp.config import ResearchConfig

async def main():
    # Initialize configuration
    config = ResearchConfig.load()
    
    # Create agent
    agent = DeepResearchAgent(config)
    
    # Perform research
    result = await agent.research(
        query="What are the latest advances in quantum computing?",
        system_prompt="Focus on practical applications and recent breakthroughs"
    )
    
    # Print results
    print(f"Report: {result.final_report}")
    print(f"Citations: {result.citations}")
    print(f"Research steps: {result.reasoning_steps}")
    print(f"Execution time: {result.execution_time:.2f}s")

# Run the research
asyncio.run(main())
```

### As an MCP Server

Two transports are supported: stdio (default) and HTTP streaming.

```bash
# 1) stdio (default) — for editors/CLIs that spawn a local process
uv run deep-research-mcp

# 2) HTTP streaming — start a local HTTP MCP server
uv run deep-research-mcp --transport http --host 127.0.0.1 --port 8080
```

Notes:
- HTTP mode uses streaming responses provided by FastMCP. The tools in this
  server return their full results when a research task completes; streaming is
  still beneficial for compatible clients and for future incremental outputs.
- The verified Streamable HTTP endpoint is `/mcp`, so the default local URL is
  `http://127.0.0.1:8080/mcp`.
- If you start the server outside the client and rely on environment variables
  for credentials, export them before launching the server process. If you use
  `stdio` and let the client spawn the server, make sure the client passes the
  required env vars through.

### Command-Line Interface

The unified CLI at `cli/deep-research-cli.py` provides direct access to all
research functionality from the terminal. It supports two modes of operation:
**agent mode** (default) which runs `DeepResearchAgent` directly, and **MCP
client mode** which connects to a running MCP server over HTTP.

Configuration is loaded from `~/.deep_research` by default. Every
`ResearchConfig` parameter can be overridden via CLI flags, which take
precedence over both the TOML file and environment variables.

### Terminal UI

The repository also ships with a full-screen terminal UI at
`cli/deep-research-tui.py`. It presents the same core functionality as the
CLI in a dark, keyboard-driven interface for running clarification, deep
research, task status checks, and saving output to disk.

![Deep Research TUI Demo](docs/images/tui-demo.gif)

The TUI features a split-panel layout:
- **Left panel**: Configuration controls for mode selection (Agent/MCP), provider settings, model configuration, query input, and system prompt
- **Right panel**: Output display showing research results, clarification questions, or status information

The animation above demonstrates the TUI workflow: selecting the Chat Completions API style, entering a research query about nuclear fusion, running the research, viewing results in the output panel, and saving the output to file.

#### Quick Start

```bash
# Start in direct agent mode
uv run python cli/deep-research-tui.py

# Start in MCP client mode
uv run python cli/deep-research-tui.py --mode mcp \
  --server-url http://127.0.0.1:8080/mcp

# Start with Gemini selected
uv run python cli/deep-research-tui.py --provider gemini
```

#### TUI Workflow

- Use the left control panel to edit provider settings, query text, system prompt, and save path.
- The TUI starts focused on the `Mode` selector rather than inside the query editor.
- Use `Tab` / `Shift+Tab` to move through all controls.
- Use `Up` / `Down` to move between non-editor controls, including single-line inputs.
- Use `Left` / `Right` to toggle booleans and cycle through choice fields when a `Switch` or `Select` has focus.
- Press `Enter` to activate buttons, toggle switches, cycle selects, or move forward from a single-line input.
- `TextArea` widgets such as `Query` and `System Prompt` keep normal cursor-key editing behavior.
- Use `c` to run clarification, `r` to run deep research, `t` to check task status, `s` to save the current output, and `q` to quit.
- The right panel shows the latest clarification output, research report, or status response.

#### Provider Defaults

In `agent` mode, the TUI applies provider-aware defaults:

- `openai` + `responses`: model `o4-mini-deep-research-2025-06-26`, base URL `https://api.openai.com/v1`
- `openai` + `chat_completions`: model `gpt-5-mini`, base URL `https://api.openai.com/v1`
- `dr-tulu`: model `dr-tulu`, base URL `http://10.8.0.42/`
- `gemini`: model `deep-research-pro-preview-12-2025`, base URL `https://generativelanguage.googleapis.com`
- `open-deep-research`: model `openai/qwen/qwen3-coder-30b`, base URL `http://localhost:1234/v1`

Switching provider or OpenAI API style automatically refreshes the model and
base URL defaults. You can still override those fields manually afterward.

#### Clarification, Research, and Saving Output

- In `agent` mode, `Run Clarification` calls the clarification flow directly through `DeepResearchAgent`.
- In `mcp` mode, `Run Clarification` calls the MCP `deep_research` tool with `request_clarification=true`.
- If clarification questions are returned, the TUI adds answer fields dynamically and uses those answers on the next research run.
- `Run Deep Research` executes either the direct agent flow or the MCP client flow, depending on the selected mode.
- `Save Output` writes the current contents of the output panel to the configured path, creating parent directories if needed.

#### Notes

- In `mcp` mode, set `MCP Server URL` to a running Streamable HTTP endpoint such as `http://127.0.0.1:8080/mcp`.
- The TUI reuses the same config-loading behavior as `cli/deep-research-cli.py`, so `~/.deep_research` and any startup overrides still apply.
- Direct-agent JSON rendering is available through the `JSON Output` toggle; MCP mode saves the textual tool response exactly as returned by the server.
- The current layout is designed for terminals at least 100 columns wide and 28 rows tall.

#### Quick Start

```bash
# Basic research query
uv run python cli/deep-research-cli.py research "What are the latest advances in quantum computing?"

# View resolved configuration
uv run python cli/deep-research-cli.py config --pretty

# Show all available options
uv run python cli/deep-research-cli.py --help
```

#### Commands

**`research QUERY`** -- perform deep research on a query.

```bash
# Simple research (agent mode)
uv run python cli/deep-research-cli.py research "Economic impact of AI adoption"

# Override provider and model for a single run
uv run python cli/deep-research-cli.py --provider gemini research "Climate change policies"

# Use a custom system prompt from a file
uv run python cli/deep-research-cli.py research "Healthcare trends" --system-prompt-file prompts/health.txt

# Or pass the system prompt inline
uv run python cli/deep-research-cli.py research "Healthcare trends" --system-prompt "Focus on peer-reviewed sources only"

# Output as JSON (includes metadata, citations, execution time)
uv run python cli/deep-research-cli.py research "AI safety" --json

# Save the report to a file
uv run python cli/deep-research-cli.py research "Renewable energy" --output-file report.md

# Disable code interpreter / data analysis tools
uv run python cli/deep-research-cli.py research "Simple topic" --no-analysis

# Notify a webhook when research completes
uv run python cli/deep-research-cli.py research "Long query" --callback-url https://example.com/webhook
```

#### Tested local OpenAI-compatible backends

The unified CLI works with local servers that expose an OpenAI-compatible
Chat Completions API. The commands below were tested against local Ollama and
local `llama-server` (from `llama.cpp`).

##### Ollama

Basic `research` flow:

```bash
uv run python cli/deep-research-cli.py \
  --provider openai \
  --api-style chat_completions \
  --base-url http://localhost:11434/v1 \
  --api-key test \
  --model qwen3.5:0.8b \
  --timeout 180 \
  research "Reply with exactly: ok"
```

Observed output:

```text
HTTP Request: POST http://localhost:11434/v1/chat/completions "HTTP/1.1 200 OK"
============================================================
RESEARCH REPORT
============================================================
Task ID: chatcmpl-215
Total steps: 1
Execution time: 14.33s

ok
```

Interactive clarification with Ollama needs the clarification models pinned to
the same local endpoint. In testing, `qwen3.5:4b` worked for clarification,
while `qwen3.5:0.8b` was too small to reliably satisfy the structured triage
step.

```bash
uv run python cli/deep-research-cli.py \
  --provider openai \
  --api-style chat_completions \
  --base-url http://localhost:11434/v1 \
  --api-key test \
  --model qwen3.5:0.8b \
  --clarification-base-url http://localhost:11434/v1 \
  --clarification-api-key test \
  --triage-model qwen3.5:4b \
  --clarifier-model qwen3.5:4b \
  --instruction-builder-model qwen3.5:4b \
  --timeout 180 \
  research "best laptop" --clarify
```

Observed interaction:

```text
Starting clarification process...

Please answer the following clarifying questions:

1. What is your budget range?
Your answer (or press Enter to skip): Under $1500

2. What will you primarily use the laptop for (gaming, work, students, creative tasks)?
Your answer (or press Enter to skip): Programming and general work

3. Do you have a preferred operating system (macOS, Windows,)?
Your answer (or press Enter to skip): macOS preferred, Windows acceptable

...

Enriched query: What are the best laptops under $1500 for professional programming work, preferably macOS with 16GB RAM, 512GB SSD, 13-15 inch display, and good battery life?
```

##### llama-server

Start a local OpenAI-compatible server and let it download a small GGUF model
from Hugging Face automatically:

```bash
llama-server \
  --host 127.0.0.1 \
  --port 8081 \
  --api-key test \
  --ctx-size 4096 \
  --alias qwen2.5-0.5b \
  -hf Qwen/Qwen2.5-0.5B-Instruct-GGUF:Q4_K_M
```

Then point the CLI at the server:

```bash
uv run python cli/deep-research-cli.py \
  --provider openai \
  --api-style chat_completions \
  --base-url http://127.0.0.1:8081/v1 \
  --api-key test \
  --model qwen2.5-0.5b \
  --timeout 120 \
  research "Reply with exactly: ok"
```

Observed output:

```text
HTTP Request: POST http://127.0.0.1:8081/v1/chat/completions "HTTP/1.1 200 OK"
============================================================
RESEARCH REPORT
============================================================
Task ID: chatcmpl-uzqSNDzRgYchZRxn1Kq2MNYyc2w6hpc6
Total steps: 1
Execution time: 0.15s

Ok
```

`--clarify` is model-sensitive on `llama-server`. Small tested models
(`qwen2.5-0.5b` and `qwen2.5-3b`) completed the basic `research` command but
did not reliably ask follow-up questions. Example output with
`qwen2.5-3b`:

```text
Starting clarification process...
Triage assessment: The query is focused on finding the best laptop, which is a common and specific research topic.
Assessment: The query 'best laptop' is clear and specific enough for direct research.
Proceeding with original query
```

**`research QUERY --clarify`** -- interactive clarification before research.

The `--clarify` flag runs an interactive clarification flow: the agent
analyzes your query, asks follow-up questions to improve specificity, and
then performs research using an enriched query. This works in both agent mode
and MCP client mode.

In agent mode, `--clarify` automatically enables the clarification pipeline
regardless of the `enable_clarification` setting in your config file.

```bash
# Interactive clarification (agent mode)
uv run python cli/deep-research-cli.py research "Quantum computing applications" --clarify

# Interactive clarification (MCP client mode)
uv run python cli/deep-research-cli.py research "Quantum computing" --clarify \
  --server-url http://localhost:8080/mcp
```

Example session:

```
Starting clarification process...

Please answer the following clarifying questions:

1. Are you interested in near-term applications or long-term theoretical possibilities?
Your answer (or press Enter to skip): Near-term commercial applications

2. Which industries are you most interested in?
Your answer (or press Enter to skip): Finance and pharmaceuticals

3. Should the report focus on specific hardware platforms?
Your answer (or press Enter to skip):

Enriched query: Quantum computing applications in finance and pharmaceuticals...
Starting research with query: '...'
```

**`research QUERY --server-url URL`** -- use MCP client mode.

Instead of running the agent directly, connect to a running Deep Research MCP
server over Streamable HTTP.

```bash
# First, start the MCP server in another terminal:
uv run deep-research-mcp --transport http --host 127.0.0.1 --port 8080

# Then run queries against it:
uv run python cli/deep-research-cli.py research "AI trends" \
  --server-url http://127.0.0.1:8080/mcp
```

**`status TASK_ID`** -- check the status of a running research task.

```bash
# Agent mode
uv run python cli/deep-research-cli.py status abc123-def456-ghi789

# MCP client mode
uv run python cli/deep-research-cli.py status abc123-def456-ghi789 \
  --server-url http://127.0.0.1:8080/mcp
```

**`config`** -- display the resolved configuration.

Shows the final configuration after merging the TOML file, environment
variables, and any CLI overrides.

```bash
# JSON output (default), with secrets masked
uv run python cli/deep-research-cli.py config

# Human-readable output
uv run python cli/deep-research-cli.py config --pretty

# Show full API keys
uv run python cli/deep-research-cli.py config --pretty --show-secrets

# See the effect of CLI overrides
uv run python cli/deep-research-cli.py --provider gemini --timeout 600 config --pretty

# Skip config validation
uv run python cli/deep-research-cli.py config --no-validate
```

#### Configuration Overrides

All global flags are placed **before** the subcommand and override the
corresponding `ResearchConfig` field:

| Flag | Description |
|------|-------------|
| `--config PATH` | Path to TOML config file (default: `~/.deep_research`) |
| `--provider {openai,dr-tulu,gemini,open-deep-research}` | Research provider |
| `--model MODEL` | Model or agent ID |
| `--api-key KEY` | Provider API key |
| `--base-url URL` | Provider API base URL |
| `--api-style {responses,chat_completions}` | OpenAI API style |
| `--timeout SECONDS` | Max research timeout |
| `--poll-interval SECONDS` | Task poll interval |
| `--log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}` | Logging level |
| `--enable-clarification` | Enable the clarification pipeline |
| `--enable-reasoning-summaries` | Enable reasoning summaries |
| `--triage-model MODEL` | Model for query triage |
| `--clarifier-model MODEL` | Model for query enrichment |
| `--clarification-base-url URL` | Base URL for clarification models |
| `--clarification-api-key KEY` | API key for clarification models |
| `--instruction-builder-model MODEL` | Model for instruction building |

Configuration precedence (highest to lowest): CLI flags > environment
variables > TOML config file (`~/.deep_research`) > built-in defaults.

#### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Research or configuration error |
| 2 | MCP tool error |
| 3 | Unexpected error |

### Example Queries

```python
# Basic research query
result = await agent.research("Explain the transformer architecture in AI")

# Research with code analysis
result = await agent.research(
    query="Analyze global temperature trends over the last 50 years",
    include_code_interpreter=True
)

# Custom system instructions
result = await agent.research(
    query="Review the safety considerations for AGI development",
    system_prompt="""
    Provide a balanced analysis including:
    - Technical challenges
    - Current safety research
    - Regulatory approaches
    - Industry perspectives
    Include specific examples and data where available.
    """
)

# With clarification (requires ENABLE_CLARIFICATION=true)
clarification_result = agent.start_clarification("quantum computing applications")
if clarification_result.get("needs_clarification"):
    # Answer questions programmatically or present to user
    answers = ["Hardware applications", "Last 5 years", "Commercial products"]
    agent.add_clarification_answers(clarification_result["session_id"], answers)
    enriched_query = agent.get_enriched_query(clarification_result["session_id"])
    result = await agent.research(enriched_query)
```

## Clarification Features

The agent includes an optional clarification system to improve research quality through follow-up questions.

### Configuration

Enable clarification in your `~/.deep_research` file:
```toml
[clarification]
enable_clarification = true
triage_model = "gpt-5-mini"                                    # Optional, defaults to gpt-5-mini
clarifier_model = "gpt-5-mini"                                 # Optional, defaults to gpt-5-mini
instruction_builder_model = "gpt-5-mini"                       # Optional, defaults to gpt-5-mini
clarification_api_key = "sk-your-clarification-api-key-here"   # Optional custom API key for clarification models
clarification_base_url = "https://custom-api.example.com/v1"   # Optional custom endpoint for clarification models
```

Clarification and instruction-building remain OpenAI-compatible chat flows. If your main research provider is `dr-tulu`, `gemini`, or `open-deep-research`, set `clarification_api_key` / `clarification_base_url` explicitly, or provide `OPENAI_API_KEY` / `OPENAI_BASE_URL` in the environment for those helper models.

### Usage Flow

1. **Start Clarification**:
   ```python
   result = agent.start_clarification("your research query")
   ```

2. **Check if Questions are Needed**:
   ```python
   if result.get("needs_clarification"):
       questions = result["questions"]
       session_id = result["session_id"]
   ```

3. **Provide Answers**:
   ```python
   answers = ["answer1", "answer2", "answer3"]
   agent.add_clarification_answers(session_id, answers)
   ```

4. **Get Enriched Query**:
   ```python
   enriched_query = agent.get_enriched_query(session_id)
   final_result = await agent.research(enriched_query)
   ```

### Integration with AI Assistants

When using with AI Assistants via MCP tools:

1. **Request Clarification**: Use `deep_research()` with `request_clarification=True`
2. **Answer Questions**: The AI Assistant will present questions to you
3. **Deep Research**: The AI Asssitant will automatically use `research_with_context()` with your answers

## API Reference

### DeepResearchAgent

The main class for performing research operations.

#### Methods

- `research(query, system_prompt=None, include_code_interpreter=True, callback_url=None)`
  - Performs deep research on a query
  - `callback_url`: optional webhook notified when research completes
  - Returns: Dictionary with final report, citations, and metadata

- `get_task_status(task_id)`
  - Check the status of a research task
  - Returns: Task status information

- `start_clarification(query)`
  - Analyze query and generate clarifying questions if needed
  - Returns: Dictionary with questions and session ID

- `add_clarification_answers(session_id, answers)`
  - Add answers to clarification questions
  - Returns: Session status information

- `get_enriched_query(session_id)`
  - Generate enriched query from clarification session
  - Returns: Enhanced query string

### ResearchConfig

Configuration class for the research agent.

#### Parameters

- `provider`: Research provider (`openai`, `dr-tulu`, `gemini`, or `open-deep-research`; default: `openai`)
- `api_style`: API style for the `openai` provider (`responses` or `chat_completions`; default: `responses`). Ignored for `dr-tulu`, `gemini`, and `open-deep-research`.
- `model`: Model identifier
  - OpenAI: Responses model (e.g., `gpt-5-mini`)
  - Dr Tulu: logical provider id (default: `dr-tulu`)
  - Gemini: Deep Research agent id (for example `deep-research-pro-preview-12-2025`)
  - Open Deep Research: LiteLLM model id (e.g., `openai/qwen/qwen3-coder-30b`)
- `api_key`: API key for the configured endpoint (optional). Defaults to env `OPENAI_API_KEY` for `openai`, `DR_TULU_API_KEY` for `dr-tulu`, `GEMINI_API_KEY` / `GOOGLE_API_KEY` for `gemini`.
- `base_url`: Provider API base URL (optional). Defaults to `https://api.openai.com/v1` for `openai`, `http://10.8.0.42/` for `dr-tulu`, `https://generativelanguage.googleapis.com` for `gemini`, and `http://localhost:1234/v1` for `open-deep-research`.
- `timeout`: Maximum time for research in seconds (default: 1800)
- `poll_interval`: Polling interval in seconds (default: 30)
- `enable_clarification`: Enable clarifying questions (default: False)
- `triage_model`: Model for query analysis (default: `gpt-5-mini`)
- `clarifier_model`: Model for query enrichment (default: `gpt-5-mini`)
- `clarification_api_key`: Custom API key for clarification models (optional; defaults to the main OpenAI credentials when `provider=openai`, otherwise falls back to env `OPENAI_API_KEY` if present)
- `clarification_base_url`: Custom OpenAI-compatible endpoint for clarification models (optional; defaults to the main OpenAI endpoint when `provider=openai`, otherwise falls back to env `OPENAI_BASE_URL` if present)

## Development

### Running Tests

```bash
# Install dev dependencies
uv sync --extra dev

# Run all tests
uv run pytest -v

# Run with coverage
uv run pytest --cov=deep_research_mcp tests/

# Run specific test file
uv run pytest tests/test_agents.py
```

### Lint, Format, Type Check

```bash
uv run black .
uv run pylint src/deep_research_mcp tests
uv run mypy src/deep_research_mcp
```
