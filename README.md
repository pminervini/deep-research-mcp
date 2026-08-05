# Deep Research MCP

[![CI](https://img.shields.io/github/actions/workflow/status/pminervini/deep-research-mcp/ci.yml?branch=main&label=CI)](https://github.com/pminervini/deep-research-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-compatible-4a5568)](https://modelcontextprotocol.io/)
[![Claude Code](https://img.shields.io/badge/Claude_Code-ready-cc785c)](https://github.com/pminervini/deep-research-mcp#claude-code-integration)
[![OpenAI](https://img.shields.io/badge/OpenAI-compatible-10a37f)](https://platform.openai.com/)
[![Gemini](https://img.shields.io/badge/Gemini-supported-4285F4)](https://ai.google.dev/)

A Python-based agent that integrates research providers with Claude Code through the Model Context Protocol (MCP). It supports OpenAI (Responses API with web search and code interpreter, Chat Completions API for broad provider compatibility, or experimental ChatGPT subscription access through Codex OAuth), Gemini Deep Research via the Interactions API, Allen AI's DR-Tulu research agent, and the open-source Open Deep Research stack (based on smolagents).

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) installed
- One of:
  - OpenAI API access (Responses API model `gpt-5.6-sol`)
  - ChatGPT subscription with Codex access (experimental `openai-codex` provider)
  - Gemini API access with the Interactions API / Deep Research agent enabled
  - DR-Tulu service running locally or remotely (see [DR-Tulu setup](#dr-tulu-provider-example))
  - Open Deep Research dependencies (installed via `uv sync --extra open-deep-research`)
- Claude Code, or any other assistant supporting MCP integration

## Installation

### Run Without Cloning

With `uv` and Git installed, run the packaged commands directly from GitHub.
`uvx` builds an isolated environment and reuses it from the local uv cache:

```bash
uvx --from "git+https://github.com/pminervini/deep-research-mcp.git@main" \
  deep-research-cli --help

uvx --from "git+https://github.com/pminervini/deep-research-mcp.git@main" \
  deep-research-mcp --help
```

For reproducible installation, replace `main` with a release tag or commit SHA.
The `openai-codex` device login is also available without a checkout:

```bash
uvx --from "git+https://github.com/pminervini/deep-research-mcp.git@main" \
  deep-research-cli auth login
```

### Source Checkout

Recommended development setup (resolves the latest compatible versions):

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

## Code Layout

- `src/deep_research_mcp/agent.py`: orchestration layer; owns callbacks and delegates provider work to backends
- `src/deep_research_mcp/backends/`: provider-specific implementations for OpenAI, OpenAI Codex subscription, Gemini, DR-Tulu, and Open Deep Research
- `src/deep_research_mcp/cli.py`: installed `deep-research-cli` implementation
- `src/deep_research_mcp/mcp_server.py`: FastMCP server and tool entrypoints
- `cli/deep-research-cli.py`: compatibility wrapper for source-checkout usage
- `cli/deep-research-tui.py`: interactive full-screen terminal UI for research, status checks, and saving output to disk
- `tests/`: `pytest` suite covering configuration, MCP integration, results, and UI flows

## Configuration

### Configuration File

Create a `~/.deep_research` file in your home directory using TOML format.

Library note: `ResearchConfig.load()` explicitly reads this file and applies environment variable overrides. `ResearchConfig.from_env()` reads environment variables only.

Common settings:

```toml
[research]                                  # Core Deep Research functionality
provider = "openai"                         # Available options: "openai", "openai-codex", "dr-tulu", "gemini", "open-deep-research" -- defaults to "openai"
api_style = "responses"                     # Only applies to provider="openai"; use "chat_completions" for Perplexity, Groq, Ollama, etc.
model = "gpt-5.6-sol"                       # OpenAI: model identifier; Codex: "auto" or account model slug; Dr Tulu: logical provider id; Gemini: agent id; ODR: LiteLLM model identifier
api_key = "your-api-key"                    # API key, optional
base_url = "https://api.openai.com/v1"      # OpenAI: OpenAI-compatible endpoint; Codex uses a fixed endpoint; Dr Tulu: service base URL; Gemini: https://generativelanguage.googleapis.com; ODR: LiteLLM-compatible endpoint

# Task behavior
timeout = 1800
poll_interval = 30
cancel_on_timeout = false  # When true, cancel the provider task if it exceeds timeout. Default false: the task keeps running and the result can be recovered with research_status

[logging]
level = "INFO"
```

Note on precedence: `[research] api_key` and `base_url` map to the `RESEARCH_API_KEY` and `RESEARCH_BASE_URL` settings, which apply to every provider except `openai-codex`. The Codex subscription provider ignores API keys and endpoint overrides so its bearer token cannot be redirected. If you switch another provider via an environment override (e.g. `RESEARCH_PROVIDER=openai`) while the file is configured for a different provider, also override `RESEARCH_API_KEY` and `RESEARCH_BASE_URL`.

OpenAI provider example:

```toml
[research]
provider = "openai"
model = "gpt-5.6-sol"                       # OpenAI model
api_key = "YOUR_OPENAI_API_KEY"             # Defaults to OPENAI_API_KEY
base_url = "https://api.openai.com/v1"      # OpenAI-compatible endpoint
timeout = 1800
poll_interval = 30
```

OpenAI Codex subscription provider example:

```toml
[research]
provider = "openai-codex"
model = "auto"                              # First picker-visible account model
timeout = 1800
```

Authenticate before starting the CLI or MCP server:

```bash
# Recommended: independent device-code session
uv run deep-research-cli auth login

# Optional short-lived import; never copies the Codex refresh token
uv run deep-research-cli auth login --import-codex

uv run deep-research-cli auth status
```

Credentials are stored independently in `~/.deep_research_auth.json` with
owner-only permissions. `auth logout` removes only this file. Model names are
loaded from the signed-in account's `/models` catalogue; an explicit model must
be present in that catalogue.

This provider uses the undocumented
`https://chatgpt.com/backend-api/codex` consumer endpoint. It is not an official
OpenAI API integration and can change or reject third-party clients without
notice. It identifies itself as `deep_research_mcp` and does not impersonate the
Codex CLI. Review the current [OpenAI Terms of
Use](https://openai.com/policies/terms-of-use/) before enabling it.

Limitations:

- Native web search is enabled, but Code Interpreter is unavailable.
- Calls are synchronous SSE streams; `research_status`, completed-report
  recovery, background polling, and `cancel_on_timeout` are unavailable.
- Imported Codex credentials cannot refresh. Run `auth login` when the imported
  access token expires.

Gemini Deep Research provider example:

```toml
[research]
provider = "gemini"
model = "deep-research-preview-04-2026"     # Gemini Deep Research agent id
api_key = "YOUR_GEMINI_API_KEY"                # Defaults to GEMINI_API_KEY or GOOGLE_API_KEY
base_url = "https://generativelanguage.googleapis.com"
timeout = 1800
poll_interval = 30
```

Available Gemini Deep Research agent IDs:

| Agent ID | Intended use |
| --- | --- |
| `deep-research-preview-04-2026` | Faster, more efficient research; this is the project default |
| `deep-research-max-preview-04-2026` | Maximum comprehensiveness for context gathering and synthesis |
| `deep-research-pro-preview-12-2025` | Older Gemini 3.1 Pro-based preview for accuracy-focused, long-running research |

Google's current [Gemini Deep Research documentation](https://ai.google.dev/gemini-api/docs/deep-research)
lists the April 2026 standard and Max agents as the supported versions. The
December 2025 Pro agent remains present in the Gemini API model catalogue and
has a separate [model page](https://ai.google.dev/gemini-api/docs/models/deep-research-pro-preview-12-2025),
but it is no longer listed among the current supported versions. Set any agent
ID above as `research.model`; all are preview identifiers and may change.

Dr Tulu provider example:

```toml
[research]
provider = "dr-tulu"
model = "dr-tulu"                   # Logical provider model id; currently informational
base_url = "http://localhost:8080/"   # Dr Tulu service base URL; the backend calls /chat
api_key = ""                        # Optional; defaults to RESEARCH_API_KEY / DR_TULU_API_KEY if set
timeout = 1800
poll_interval = 30
```

Running Dr Tulu locally:

1. Clone and configure [`dr-tulu`](https://github.com/allenai/dr-tulu) separately.
2. In `dr-tulu/agent/.env`, set at least:
   - `SERPER_API_KEY`
   - `JINA_API_KEY`
   - `S2_API_KEY` (optional but recommended)
3. Start the DR-Tulu model server:

```bash
cd /path/to/dr-tulu/agent
conda run -n vllm bash -lc '
  CUDA_VISIBLE_DEVICES=0 \
  vllm serve rl-research/DR-Tulu-8B \
    --port 30001 \
    --dtype auto \
    --max-model-len 16384 \
    --gpu-memory-utilization 0.60 \
    --enforce-eager
'
```

4. Start the Dr Tulu MCP backend:

```bash
cd /path/to/dr-tulu/agent
conda run -n vllm python -m dr_agent.mcp_backend.main --port 8000
```

5. Start the Dr Tulu app service:

```bash
cd /path/to/dr-tulu/agent
conda run -n vllm python workflows/auto_search_sft.py serve \
  --port 8080 \
  --config workflows/auto_search_sft.yaml \
  --config-overrides "search_agent_max_tokens=12000,browse_agent_max_tokens=12000"
```

6. Point `deep-research-mcp` at that service:

```toml
[research]
provider = "dr-tulu"
base_url = "http://localhost:8080/"
timeout = 1800
```

The `dr-tulu` backend calls `POST {base_url}/chat`, so if you front Dr Tulu behind a different host, port, or reverse proxy, update `base_url` accordingly.

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

### Install The Included Skill In Claude Code Or Codex

This repository also ships a repo-specific skill guide at
[`skills/deep-research-mcp/SKILL.md`](skills/deep-research-mcp/SKILL.md).

Installing that file as a local skill gives Claude Code or Codex a focused
playbook for this repository's CLI, Python API, providers, and MCP server.
It does **not** install Python dependencies, start the MCP server, or replace
the provider configuration in `~/.deep_research`. Treat it as complementary to
the MCP setup below, not a substitute for it.

#### Claude Code skill install

Claude Code's skills docs use these locations:

- personal skill: `~/.claude/skills/<skill-name>/SKILL.md`
- project skill: `.claude/skills/<skill-name>/SKILL.md`

Personal install:

```bash
mkdir -p ~/.claude/skills/deep-research-mcp
cp /path/to/deep-research-mcp/skills/deep-research-mcp/SKILL.md \
  ~/.claude/skills/deep-research-mcp/SKILL.md
```

If you prefer to keep the installed skill linked to this checkout:

```bash
mkdir -p ~/.claude/skills/deep-research-mcp
ln -sf /path/to/deep-research-mcp/skills/deep-research-mcp/SKILL.md \
  ~/.claude/skills/deep-research-mcp/SKILL.md
```

Project-local install from the repository root:

```bash
mkdir -p .claude/skills/deep-research-mcp
cp skills/deep-research-mcp/SKILL.md .claude/skills/deep-research-mcp/SKILL.md
```

After that, restart Claude Code or open a new session if the skill does not
appear immediately. The skill can be invoked directly as
`/deep-research-mcp`, and Claude can also load it automatically when the task
matches the skill description. For a reusable shared extension, package the
same skill into a Claude Code plugin instead of copying it by hand.

Official docs:

- Claude Code skills: <https://docs.claude.com/en/docs/claude-code/skills>
- Claude Code plugins: <https://docs.claude.com/en/docs/claude-code/plugins>

#### Codex skill install

Current Codex docs describe skills as skill folders containing `SKILL.md`,
stored globally in `$HOME/.agents/skills` or repo-locally in `.agents/skills`.

Personal install:

```bash
mkdir -p ~/.agents/skills/deep-research-mcp
cp /path/to/deep-research-mcp/skills/deep-research-mcp/SKILL.md \
  ~/.agents/skills/deep-research-mcp/SKILL.md
```

Or keep the installed skill linked to this checkout:

```bash
mkdir -p ~/.agents/skills/deep-research-mcp
ln -sf /path/to/deep-research-mcp/skills/deep-research-mcp/SKILL.md \
  ~/.agents/skills/deep-research-mcp/SKILL.md
```

Project-local install from the repository root:

```bash
mkdir -p .agents/skills/deep-research-mcp
cp skills/deep-research-mcp/SKILL.md .agents/skills/deep-research-mcp/SKILL.md
```

If your Codex setup still follows older CLI conventions that use
`~/.codex/skills` or `.codex/skills`, mirror the same directory structure
there instead.

Codex can invoke the skill implicitly when the task matches its description, or
explicitly by mentioning `$deep-research-mcp` in the prompt. If the skill does
not show up immediately, restart Codex.

Official docs:

- Codex skills: <https://developers.openai.com/codex/skills>
- Codex customization and skill locations: <https://developers.openai.com/codex/concepts/customization#skills>

### Claude Code Integration

1. **Configure MCP Server**

Choose one of the transports below.

**Option A: stdio (recommended when Claude Code should spawn the server itself)**

Clone-free user installation:

```bash
claude mcp add --scope user --transport stdio deep-research -- \
  uvx --from "git+https://github.com/pminervini/deep-research-mcp.git@main" \
  deep-research-mcp
```

For a source checkout with provider credentials already stored in
`~/.deep_research`, use:

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

Kick off work with `deep_research`, note the returned job ID, and call `research_status` to stream progress without letting any single tool call stagnate.

Output size: Claude Code limits MCP tool output (about 25,000 tokens by default, configurable via `MAX_MCP_OUTPUT_TOKENS`). The research tools declare the `anthropic/maxResultSizeChars` annotation so recent Claude Code versions accept large reports without extra configuration; on older versions, raise the limit before launching the CLI:

```bash
export MAX_MCP_OUTPUT_TOKENS=50000
claude
```

Timeout recovery: if a research task exceeds the configured `timeout`, the server leaves the provider task running by default and returns its task ID; call `research_status` with that ID to retrieve the full report once it completes. Pass `--cancel-on-timeout` to `deep-research-mcp` (or set `cancel_on_timeout = true` in `~/.deep_research`) to restore the old cancel behavior.

2. **Use in Claude Code**:
   - The research tools will appear in Claude Code's tool palette
   - Simply ask Claude to "research [your topic]" and it will use the Deep Research agent

### OpenAI Codex Integration

1. **Configure MCP Server**

Choose one of the transports below.

**Option A: stdio (recommended when Codex should spawn the server itself)**

Clone-free installation:

```bash
codex mcp add deep-research -- \
  uvx --from "git+https://github.com/pminervini/deep-research-mcp.git@main" \
  deep-research-mcp
```

For a source checkout, add the MCP server configuration to
`~/.codex/config.toml`:

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

#### OAuth authentication for HTTP

HTTP OAuth is opt-in. Set both variables below before starting the server:

```bash
export MCP_AUTH_ISSUER_URL="https://firm-mermaid-02-staging.authkit.app"
export MCP_AUTH_RESOURCE_URL="http://127.0.0.1:8080/mcp"

uv run deep-research-mcp --transport http --host 127.0.0.1 --port 8080
```

`MCP_AUTH_RESOURCE_URL` must exactly match the Resource Indicator configured in
WorkOS, including the `/mcp` path. When enabled, the server verifies each
AuthKit access token's signature, issuer, expiration, and audience and publishes
RFC 9728 protected-resource metadata for MCP clients. No WorkOS API key or
client secret is required by the server. Local `stdio` usage is unchanged.

In WorkOS, enable Client ID Metadata Documents (CIMD), keep Dynamic Client
Registration (DCR) enabled for older clients, and add the resource URL under
Connect → Configuration. See the [WorkOS MCP authentication
guide](https://workos.com/docs/authkit/mcp).

### Command-Line Interface

The installed `deep-research-cli` command provides direct access to all
research functionality from the terminal. Its implementation lives in
`src/deep_research_mcp/cli.py`, while `cli/deep-research-cli.py` remains a
source-checkout compatibility wrapper. It supports two modes of operation:
**agent mode** (default) which runs `DeepResearchAgent` directly, and **MCP
client mode** which connects to a running MCP server over HTTP.

Configuration is loaded from `~/.deep_research` by default. Every
`ResearchConfig` parameter can be overridden via CLI flags, which take
precedence over both the TOML file and environment variables.

### Terminal UI

The repository also ships with a full-screen terminal UI at
`cli/deep-research-tui.py`. It presents the same core functionality as the
CLI in a dark, keyboard-driven interface for running deep research, task status
checks, and saving output to disk.

![Deep Research TUI Demo](docs/images/tui-demo.gif)

The TUI features a split-panel layout:
- **Left panel**: Configuration controls for mode selection (Agent/MCP), provider settings, model configuration, query input, and system prompt
- **Right panel**: Output display showing research results or status information

The animation above demonstrates the TUI workflow: loading a research query,
running it through a local Dr Tulu-compatible demo endpoint, viewing the result
in the output panel, and saving the output to a file.

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
- Use `r` to run deep research, `t` to check task status, `s` to save the current output, and `q` to quit.
- The right panel shows the latest research report or status response.

#### Provider Defaults

In `agent` mode, the TUI applies provider-aware defaults:

- `openai` + `responses`: model `gpt-5.6-sol`, base URL `https://api.openai.com/v1`
- `openai` + `chat_completions`: model `gpt-5-mini`, base URL `https://api.openai.com/v1`
- `openai-codex`: model `auto`, fixed base URL `https://chatgpt.com/backend-api/codex`
- `dr-tulu`: model `dr-tulu`, base URL `http://localhost:8080/`
- `gemini`: model `deep-research-preview-04-2026`, base URL `https://generativelanguage.googleapis.com`
- `open-deep-research`: model `openai/qwen/qwen3-coder-30b`, base URL `http://localhost:1234/v1`

Switching provider or OpenAI API style automatically refreshes the model and
base URL defaults. You can still override those fields manually afterward.

#### Research and Saving Output

- `Run Deep Research` executes either the direct agent flow or the MCP client flow, depending on the selected mode.
- `Save Output` writes the current contents of the output panel to the configured path, creating parent directories if needed.

#### Notes

- In `mcp` mode, set `MCP Server URL` to a running Streamable HTTP endpoint such as `http://127.0.0.1:8080/mcp`.
- The TUI reuses the same config-loading behavior as `deep-research-cli`, so `~/.deep_research` and any startup overrides still apply.
- Direct-agent JSON rendering is available through the `JSON Output` toggle; MCP mode saves the textual tool response exactly as returned by the server.
- The current layout is designed for terminals at least 100 columns wide and 28 rows tall.

#### Quick Start

**Gemini Deep Research:**

```bash
uv run deep-research-cli \
  --provider gemini \
  --model deep-research-preview-04-2026 \
  --base-url https://generativelanguage.googleapis.com \
  research "What is the capital of France?"
```

Expected output (snippet):

```text
============================================================
RESEARCH REPORT
============================================================
Task ID: v1_Chd5YUxjYVpXRUotYWxrZFVQOF9lcTRRVRIX...
Total steps: 1
Execution time: 245.94s

# Comprehensive Analysis of the French Capital: Demographic,
# Economic, and Historical Dimensions of Paris

**Key Points**
*   **The capital of France is Paris**, acting as the undisputed
    political, economic, and cultural epicenter of the nation.
*   Data indicates that the Paris metropolitan area commands a
    Gross Domestic Product (GDP) exceeding $1.03 trillion ...
```

**OpenAI GPT-5.6 Sol research:**

```bash
uv run deep-research-cli \
  --provider openai \
  --model gpt-5.6-sol \
  --base-url https://api.openai.com/v1 \
  research "What is the capital of France?"
```

Expected output:

```text
============================================================
RESEARCH REPORT
============================================================
Task ID: resp_0e55abdae3d3ce390069dca3c7d78c819f91...
Total steps: 22
Search queries: 10
Citations: 1
Execution time: 34.34s

The capital of France is **Paris**
(www.britannica.com/place/Paris)

============================================================
CITATIONS
============================================================
1. Paris | Definition, Map, Population, Facts, & History
   https://www.britannica.com/place/Paris
```

**OpenAI Codex subscription research:**

```bash
uv run deep-research-cli auth login
uv run deep-research-cli \
  --provider openai-codex \
  research "What is the capital of France?"
```

**DR-Tulu** (requires a running [dr-tulu](https://github.com/allenai/dr-tulu) service; see [Dr Tulu provider example](#dr-tulu-provider-example)):

```bash
uv run deep-research-cli \
  --provider dr-tulu \
  --base-url http://localhost:8080/ \
  research "What is the capital of France?"
```

Expected output:

```text
============================================================
RESEARCH REPORT
============================================================
Task ID: 7f3a1b2c-...
Total steps: 4
Citations: 2
Execution time: 18.72s

The capital of France is Paris. Paris has served as the
French capital since the late 10th century ...

============================================================
CITATIONS
============================================================
1. Source 1
   https://en.wikipedia.org/wiki/Paris
2. Source 2
   https://www.britannica.com/place/Paris
```

View resolved configuration or all available options:

```bash
uv run deep-research-cli config --pretty
uv run deep-research-cli --help
```

#### Commands

**`research QUERY`** -- perform deep research on a query.

```bash
# Simple research (agent mode)
uv run deep-research-cli research "Economic impact of AI adoption"

# Override provider and model for a single run
uv run deep-research-cli --provider gemini research "Climate change policies"

# Use a custom system prompt from a file
uv run deep-research-cli research "Healthcare trends" --system-prompt-file prompts/health.txt

# Or pass the system prompt inline
uv run deep-research-cli research "Healthcare trends" --system-prompt "Focus on peer-reviewed sources only"

# Output as JSON (includes metadata, citations, execution time)
uv run deep-research-cli research "AI safety" --json

# Save the report to a file
uv run deep-research-cli research "Renewable energy" --output-file report.md

# Disable code interpreter / data analysis tools
uv run deep-research-cli research "Simple topic" --no-analysis

# Notify a webhook when research completes
uv run deep-research-cli research "Long query" --callback-url https://example.com/webhook
```

#### Tested local OpenAI-compatible backends

The unified CLI works with local servers that expose an OpenAI-compatible
Chat Completions API. The commands below were tested against local Ollama and
local `llama-server` (from `llama.cpp`).

##### Ollama

Basic `research` flow:

```bash
uv run deep-research-cli \
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
uv run deep-research-cli \
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

**`research QUERY --server-url URL`** -- use MCP client mode.

Instead of running the agent directly, connect to a running Deep Research MCP
server over Streamable HTTP.

```bash
# First, start the MCP server in another terminal:
uv run deep-research-mcp --transport http --host 127.0.0.1 --port 8080

# Then run queries against it:
uv run deep-research-cli research "AI trends" \
  --server-url http://127.0.0.1:8080/mcp
```

**`status TASK_ID`** -- check the status of a running research task.

```bash
# Agent mode
uv run deep-research-cli status abc123-def456-ghi789

# MCP client mode
uv run deep-research-cli status abc123-def456-ghi789 \
  --server-url http://127.0.0.1:8080/mcp
```

**`config`** -- display the resolved configuration.

Shows the final configuration after merging the TOML file, environment
variables, and any CLI overrides.

```bash
# JSON output (default), with secrets masked
uv run deep-research-cli config

# Human-readable output
uv run deep-research-cli config --pretty

# Show full API keys
uv run deep-research-cli config --pretty --show-secrets

# See the effect of CLI overrides
uv run deep-research-cli --provider gemini --timeout 600 config --pretty

# Skip config validation
uv run deep-research-cli config --no-validate
```

**`auth {login,status,logout}`** -- manage the independent OpenAI Codex
subscription session.

```bash
uv run deep-research-cli auth login
uv run deep-research-cli auth status
uv run deep-research-cli auth logout
```

#### Configuration Overrides

All global flags are placed **before** the subcommand and override the
corresponding `ResearchConfig` field:

| Flag | Description |
|------|-------------|
| `--config PATH` | Path to TOML config file (default: `~/.deep_research`) |
| `--provider {openai,openai-codex,dr-tulu,gemini,open-deep-research}` | Research provider |
| `--model MODEL` | Model or agent ID |
| `--api-key KEY` | Provider API key |
| `--base-url URL` | Provider API base URL |
| `--api-style {responses,chat_completions}` | OpenAI API style |
| `--timeout SECONDS` | Max research timeout |
| `--poll-interval SECONDS` | Task poll interval |
| `--log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}` | Logging level |
| `--enable-reasoning-summaries` | Enable reasoning summaries |

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
```

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

### ResearchConfig

Configuration class for the research agent.

#### Parameters

- `provider`: Research provider (`openai`, `openai-codex`, `dr-tulu`, `gemini`, or `open-deep-research`; default: `openai`)
- `api_style`: API style for the `openai` provider (`responses` or `chat_completions`; default: `responses`). Ignored for `openai-codex`, `dr-tulu`, `gemini`, and `open-deep-research`.
- `model`: Model identifier
  - OpenAI: Responses model (e.g., `gpt-5-mini`)
  - OpenAI Codex subscription: `auto` (default) or an account catalogue slug
  - Dr Tulu: logical provider id (default: `dr-tulu`)
  - Gemini: Deep Research agent id (for example `deep-research-preview-04-2026`)
  - Open Deep Research: LiteLLM model id (e.g., `openai/qwen/qwen3-coder-30b`)
- `api_key`: API key for the configured endpoint (optional). Defaults to env `OPENAI_API_KEY` for `openai`, `DR_TULU_API_KEY` for `dr-tulu`, `GEMINI_API_KEY` / `GOOGLE_API_KEY` for `gemini`. Ignored for `openai-codex`.
- `base_url`: Provider API base URL (optional). Defaults to `https://api.openai.com/v1` for `openai`, the fixed `https://chatgpt.com/backend-api/codex` endpoint for `openai-codex`, `http://localhost:8080/` for `dr-tulu`, `https://generativelanguage.googleapis.com` for `gemini`, and `http://localhost:1234/v1` for `open-deep-research`.
- `timeout`: Maximum time for research in seconds (default: 1800)
- `poll_interval`: Polling interval in seconds (default: 30)

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

When `~/.deep_research_auth.json` contains a current or refreshable
`openai-codex` session, a normal `uv run pytest tests/` run automatically
executes the live Codex end-to-end test and consumes subscription allowance.
Without that session, the test is skipped. Use `-m "not api"` to exclude all
live provider tests explicitly.

### Lint, Format, Type Check

```bash
uv run black .
uv run pylint src/deep_research_mcp tests
uv run mypy src/deep_research_mcp
```
