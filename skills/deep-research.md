---
name: deep-research
description: >-
  Use when the user asks to research a topic, investigate a question,
  find information, produce a research report, or needs comprehensive
  analysis with citations from web sources.
---

# Deep Research

Calls the deep-research MCP server for autonomous web research with multiple provider backends. Returns structured markdown reports with citations.

## Quick Start

Call `deep_research` with the user's query:

```
deep_research(query="Latest breakthroughs in quantum computing")
```

The tool handles decomposition, web search, analysis, and report generation. Results include inline citations and metadata.

## Workflow Patterns

### Direct Research (default)

1. Call `deep_research(query="...")`.
2. Inform the user that research is in progress -- it may take 1-30 minutes depending on the provider and query complexity.
3. When complete, present the report. Preserve citations. Summarize key findings if the user asks.

### Clarification-Enhanced Research

Use when the query is ambiguous or the user explicitly asks to refine the question first. Requires `enable_clarification = true` in config.

1. Call `deep_research(query="...", request_clarification=True)`.
2. Parse the returned clarifying questions and `session_id`.
3. Present the questions to the user and collect their answers.
4. Call `research_with_context(session_id="...", answers=["answer1", "answer2", ...])`.
5. Present the enriched report.

### Long-Running Research

1. If research is taking a long time, extract the `task_id` from a previous result or progress message.
2. Call `research_status(task_id="...")` to check progress.
3. Note: only OpenAI (Responses API) and Gemini backends support task status tracking. Dr Tulu and Open Deep Research always return "unknown".

## System Instructions

Use the `system_instructions` parameter to shape the research approach when the user specifies a focus:

- "Focus on peer-reviewed sources only"
- "Include financial data and charts"
- "Compare to industry benchmarks"
- "Prioritize developments from 2024-2025"

Translate the user's angle into `system_instructions` rather than embedding it in the query itself. When left empty, a default prompt is used that focuses on data-rich insights, statistics, peer-reviewed sources, inline citations, and analytical reasoning.

---

## Provider Comparison

| Provider | Default Model | Code Execution | Task Status | Async Polling | Notes |
|----------|--------------|----------------|-------------|---------------|-------|
| `openai` (responses) | `o4-mini-deep-research-2025-06-26` | Yes | Yes | Yes | Default provider. Full-featured with web search + code interpreter |
| `openai` (chat_completions) | `gpt-5-mini` | No | No | No | Synchronous. Compatible with Perplexity, Groq, Ollama, and other OpenAI-compatible APIs |
| `gemini` | `deep-research-pro-preview-12-2025` | No | Yes | Yes | Uses Gemini Interactions API |
| `dr-tulu` | `dr-tulu` | No | No | No | Simple /chat endpoint. Fastest but least feature-rich |
| `open-deep-research` | `openai/qwen/qwen3-coder-30b` | No | No | No | Uses smolagents framework. Requires HF_TOKEN. Most comprehensive but slowest |

**Key differences:**
- `include_analysis` only has effect with the OpenAI Responses API backend. Other backends ignore it.
- Chat Completions mode does not support task status or code execution -- use it for OpenAI-compatible third-party APIs.
- Open Deep Research requires a HuggingFace token (`HF_TOKEN` env var) and optionally `SERPAPI_API_KEY` or `SERPER_API_KEY` for Google search.

---

## MCP Tool Reference

When registered as an MCP server, tools may be prefixed with a namespace (e.g., `mcp__deep-research__deep_research` in Claude Code). The parameter names and return formats are the same regardless of prefix.

### deep_research

Performs autonomous deep research with web search and analysis.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `query` | string | Yes | -- | The research question or topic |
| `system_instructions` | string | No | `""` | Custom instructions to shape research approach |
| `include_analysis` | boolean | No | `true` | Enable code execution for data analysis and charts (OpenAI Responses API only) |
| `request_clarification` | boolean | No | `false` | Return clarifying questions instead of starting research |
| `callback_url` | string | No | `""` | Webhook URL notified on completion |

**Return format** (normal research):

```markdown
# Research Report: {query}

{report content with inline citations}

## Research Metadata
- **Total research steps**: N
- **Search queries executed**: N
- **Citations found**: N
- **Task ID**: UUID
- **Execution time**: X.XX seconds

## Citations
1. [Title](URL)
2. [Title](URL)
```

**Return format** (clarification needed):

```markdown
# Clarifying Questions Needed

**Original Query:** {query}
**Why clarification is helpful:** {reasoning}
**Session ID:** `{session_id}`

**Please answer these questions to improve the research:**
1. Question 1
2. Question 2
```

**Return format** (query already sufficient):

```markdown
# Query Analysis

**Original Query:** {query}
**Assessment:** {assessment}
**Recommendation:** Proceed with research directly
```

### research_with_context

Performs research using an enriched query built from clarification answers.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `session_id` | string | Yes | -- | Session ID from a prior `deep_research` clarification request |
| `answers` | list[string] | Yes | -- | Answers to clarifying questions, in presentation order |
| `system_instructions` | string | No | `""` | Custom research approach instructions |
| `include_analysis` | boolean | No | `true` | Enable code execution for analysis |
| `callback_url` | string | No | `""` | Webhook URL notified on completion |

**Return format:**

```markdown
# Enhanced Research Report

**Original Query Enhanced With User Context**
**Enriched Query:** {enriched_query}
**User Clarifications Provided:** N answers

---

{report content}

## Research Metadata
- **Total research steps**: N
- **Search queries executed**: N
- **Citations found**: N
- **Task ID**: UUID
- **Clarification Session**: {session_id}
- **Execution time**: X.XX seconds

## Citations
1. [Title](URL)
```

### research_status

Check progress of a running research task.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `task_id` | string | Yes | -- | Task ID (UUID) from a research result |

**Return format** (plain text):

```
Task {task_id} status: running|completed|failed
Created at: {timestamp}
Completed at: {timestamp}
Message: {message}
```

---

## Clarification Workflow

The clarification system uses a two-step flow to refine ambiguous queries before research begins. It requires `enable_clarification = true` in config (or `ENABLE_CLARIFICATION=true` env var). The clarification pipeline uses separate OpenAI-compatible models for triage and enrichment (configurable via `triage_model`, `clarifier_model`, `instruction_builder_model`).

**Use clarification when:**
- The query is broad or ambiguous (e.g., "best programming language")
- The user explicitly asks to refine or narrow down the question
- Multiple valid research angles exist and the user's intent is unclear

**Do NOT use clarification when:**
- The query is specific and well-defined
- The user wants quick results
- The user says "just research it" or similar

### Step 1: Request Clarification

```
deep_research(query="best database for my project", request_clarification=True)
```

If clarification is needed, the response contains a "Clarifying Questions Needed" section with a `**Session ID:** \`{uuid}\`` line and numbered questions. If clarification is NOT needed, the response contains a "Query Analysis" section -- proceed with a normal `deep_research` call instead.

### Step 2: Provide Answers

```
research_with_context(
    session_id="the-session-id-from-step-1",
    answers=["Answer to question 1", "Answer to question 2", "Answer to question 3"]
)
```

The `answers` list must be in the same order as the questions were presented.

### Automatic Query Enhancement

When `enable_clarification` is enabled, even direct research calls (without `request_clarification=True`) will automatically enhance the query through an instruction builder before sending it to the research backend. This is transparent to the caller.

### Example

1. User: "Research the best database for my project"
2. Call: `deep_research(query="best database for my project", request_clarification=True)`
3. Response includes questions like:
   - "What type of data will you store (relational, document, time-series)?"
   - "What scale are you targeting (thousands vs millions of records)?"
   - "Do you need ACID compliance?"
4. Present questions to the user and collect answers.
5. Call: `research_with_context(session_id="abc-123", answers=["Relational data with some JSON", "Millions of records", "Yes, ACID is required"])`
6. Present the enhanced research report.

---

## Callback Webhooks

When `callback_url` is provided and research completes successfully, the server sends an HTTP POST with:

```json
{
  "status": "completed",
  "task_id": "uuid-string",
  "timestamp": 1234567890.123,
  "result_preview": "first 500 characters of the report..."
}
```

Callback failures are logged but do not affect research results.

---

## Python API

The package exports these public classes for programmatic use:

```python
from deep_research_mcp import (
    DeepResearchAgent,
    ResearchConfig,
    ResearchResult,
    ResearchCitation,
    ResearchTaskStatus,
    ResearchError,
    TaskTimeoutError,
    PromptManager,
)
```

### ResearchConfig

Load configuration from `~/.deep_research` (TOML) and/or environment variables:

```python
config = ResearchConfig.load()            # file + env
config = ResearchConfig.from_env()        # env only
config = ResearchConfig.load(config_path="/path/to/config.toml")
config.validate()
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `provider` | str | `"openai"` | Backend: `openai`, `gemini`, `dr-tulu`, `open-deep-research` |
| `model` | str | per-provider | Model identifier (see Provider Comparison) |
| `api_key` | str or None | None | Provider API key |
| `base_url` | str or None | per-provider | Provider API base URL |
| `api_style` | str | `"responses"` | OpenAI only: `responses` or `chat_completions` |
| `timeout` | float | `1800.0` | Max research timeout in seconds |
| `poll_interval` | float | `30.0` | Seconds between task status checks |
| `log_level` | str | `"INFO"` | Logging level |
| `enable_clarification` | bool | `False` | Enable the clarification/instruction-builder pipeline |
| `enable_reasoning_summaries` | bool | `False` | Extract reasoning summaries (OpenAI only) |
| `triage_model` | str | `"gpt-5-mini"` | Model for clarification triage |
| `clarifier_model` | str | `"gpt-5-mini"` | Model for query enrichment |
| `instruction_builder_model` | str | `"gpt-5-mini"` | Model for research instruction enhancement |
| `clarification_base_url` | str or None | None | Separate base URL for clarification models |
| `clarification_api_key` | str or None | None | Separate API key for clarification models |

**Environment variables** (override config file):

| Variable | Maps to |
|----------|---------|
| `RESEARCH_PROVIDER` | `provider` |
| `RESEARCH_MODEL` | `model` |
| `RESEARCH_API_KEY` | `api_key` |
| `RESEARCH_BASE_URL` | `base_url` |
| `RESEARCH_API_STYLE` | `api_style` |
| `RESEARCH_TIMEOUT` | `timeout` |
| `RESEARCH_POLL_INTERVAL` | `poll_interval` |
| `LOGGING_LEVEL` | `log_level` |
| `ENABLE_CLARIFICATION` | `enable_clarification` |
| `ENABLE_REASONING_SUMMARIES` | `enable_reasoning_summaries` |
| `CLARIFICATION_TRIAGE_MODEL` | `triage_model` |
| `CLARIFICATION_CLARIFIER_MODEL` | `clarifier_model` |
| `CLARIFICATION_INSTRUCTION_BUILDER_MODEL` | `instruction_builder_model` |
| `CLARIFICATION_BASE_URL` | `clarification_base_url` |
| `CLARIFICATION_API_KEY` | `clarification_api_key` |

Provider-specific key fallbacks: `OPENAI_API_KEY`, `GEMINI_API_KEY` / `GOOGLE_API_KEY`, `DR_TULU_API_KEY`.

### DeepResearchAgent

```python
agent = DeepResearchAgent(config)

# Main research
result = await agent.research(
    query="...",
    system_prompt="optional instructions",
    include_code_interpreter=True,
    callback_url="https://example.com/webhook",
)

# Task status
status = await agent.get_task_status(task_id)

# Clarification flow
clarification = await agent.start_clarification_async(user_query)
agent.add_clarification_answers(session_id, answers)
enriched_query = await agent.get_enriched_query_async(session_id)

# Query enhancement (used automatically when enable_clarification=True)
enhanced = await agent.build_research_instruction_async(query)
```

### ResearchResult

| Field | Type | Description |
|-------|------|-------------|
| `status` | str | `"completed"`, `"failed"`, or `"error"` |
| `task_id` | str or None | Provider task identifier |
| `final_report` | str | Markdown report content |
| `citations` | list[ResearchCitation] | Each has `index`, `title`, `url` |
| `reasoning_steps` | int | Count of reasoning steps (OpenAI only) |
| `search_queries` | list[str] | Search queries executed |
| `total_steps` | int | Total execution steps |
| `message` | str or None | Error message if failed |
| `error_code` | str or None | Provider error code if available |
| `execution_time` | float or None | Seconds elapsed |
| `is_completed` | bool (property) | True when `status == "completed"` |

### ResearchTaskStatus

| Field | Type | Description |
|-------|------|-------------|
| `task_id` | str | Task identifier |
| `status` | str | `"running"`, `"completed"`, `"failed"`, `"unknown"`, or `"error"` |
| `created_at` | Any | Creation timestamp (provider-specific format) |
| `completed_at` | Any | Completion timestamp |
| `message` | str or None | Status message |
| `error` | str or None | Error details |

### Error Types

| Exception | Description |
|-----------|-------------|
| `ResearchError` | Base exception for all research operations |
| `TaskTimeoutError` | Task exceeded `timeout` seconds (subclass of ResearchError) |
| `ConfigurationError` | Invalid configuration (import from `deep_research_mcp.errors`) |

---

## MCP Server

The server supports two transport modes:

```bash
# stdio (default) -- for editors/CLIs that spawn a local process
uv run deep-research-mcp

# HTTP streaming -- for network MCP clients
uv run deep-research-mcp --transport http --host 127.0.0.1 --port 8080
```

| Flag | Default | Description |
|------|---------|-------------|
| `--transport` | `stdio` | `stdio` or `http` |
| `--host` | `127.0.0.1` | Bind address for HTTP mode |
| `--port` | `8080` | Bind port for HTTP mode |

---

## CLI Reference

The CLI at `cli/deep-research-cli.py` provides an alternative interface. Run from the project root directory. Supports two modes: **agent mode** (default, runs research directly) and **MCP client mode** (connects to a running MCP server via `--server-url`).

### Global Configuration Overrides

These flags apply to all subcommands and override values from `~/.deep_research` and environment variables:

| Flag | Type | Description |
|------|------|-------------|
| `--config PATH` | string | Path to TOML config file (default: `~/.deep_research`) |
| `--provider` | choice | `openai`, `gemini`, `dr-tulu`, `open-deep-research` |
| `--model` | string | Model or agent ID |
| `--api-key` | string | Provider API key |
| `--base-url` | string | Provider API base URL |
| `--api-style` | choice | OpenAI API style: `responses` or `chat_completions` |
| `--timeout` | float | Max research timeout in seconds |
| `--poll-interval` | float | Task poll interval in seconds |
| `--log-level` | choice | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `--enable-clarification` | flag | Enable the clarification pipeline |
| `--enable-reasoning-summaries` | flag | Enable reasoning summaries (OpenAI only) |
| `--triage-model` | string | Model for clarification triage |
| `--clarifier-model` | string | Model for query enrichment |
| `--clarification-base-url` | string | Base URL for clarification models |
| `--clarification-api-key` | string | API key for clarification models |
| `--instruction-builder-model` | string | Model for instruction building |

### research

```bash
uv run python cli/deep-research-cli.py research "What are the latest treatments for diabetes?"
```

| Flag | Description |
|------|-------------|
| `--clarify` | Enable interactive clarification before research |
| `--system-prompt TEXT` | Inline system prompt (mutually exclusive with `--system-prompt-file`) |
| `--system-prompt-file PATH` | Read system prompt from a file (mutually exclusive with `--system-prompt`) |
| `--no-analysis` | Disable code interpreter / analysis tools |
| `--callback-url URL` | Webhook URL to notify on completion |
| `--server-url URL` | MCP server URL for client mode (e.g., `http://localhost:8080/mcp`) |
| `--output-file PATH` | Write report to file instead of stdout |
| `--json` | Output full result as JSON (agent mode only) |

### status

```bash
uv run python cli/deep-research-cli.py status <task-id>
```

| Flag | Description |
|------|-------------|
| `--server-url URL` | MCP server URL for client mode |

### config

```bash
uv run python cli/deep-research-cli.py config [--pretty] [--show-secrets] [--no-validate]
```

| Flag | Description |
|------|-------------|
| `--pretty` | Human-readable key-value output (default: JSON) |
| `--show-secrets` | Show full API keys (default: masked with last 4 chars visible) |
| `--no-validate` | Skip configuration validation |

### CLI Examples

```bash
# Basic research
uv run python cli/deep-research-cli.py research "Quantum computing trends"

# Research with a specific provider and model
uv run python cli/deep-research-cli.py --provider gemini research "Healthcare costs in the US"

# Research with interactive clarification
uv run python cli/deep-research-cli.py research "Best database" --clarify

# Research with custom system prompt and save to file
uv run python cli/deep-research-cli.py research "AI trends" \
  --system-prompt-file prompts/custom.txt \
  --output-file report.md

# Research via MCP server (client mode)
uv run python cli/deep-research-cli.py research "Climate change" \
  --server-url http://localhost:8080/mcp

# JSON output in agent mode
uv run python cli/deep-research-cli.py research "Quick query" --json

# View config with secrets visible
uv run python cli/deep-research-cli.py config --pretty --show-secrets

# Override provider and timeout for a single run
uv run python cli/deep-research-cli.py --provider openai --api-style chat_completions \
  --timeout 600 research "Quick query"
```
