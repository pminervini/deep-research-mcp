name: deep-research-mcp
description: Use this guide only for the `deep-research-mcp` repository/project when you need to run, integrate, or debug its CLI, Python API, or MCP server. It covers this repo's direct agent execution, provider/backend selection, OpenAI Responses with o4-mini-deep-research, Gemini Deep Research, DR-Tulu integration requirements, clarification workflows, status polling, and HTTP or stdio MCP usage. Do not use it for Deep Research systems in general, for unrelated MCP servers, or for the Textual TUI.
---

# Deep Research MCP

This document is specifically about the `deep-research-mcp` project/repository, not Deep Research systems in general.

Repository: `https://github.com/pminervini/deep-research-mcp`

This document is written in `SKILL.md` style, but kept in one file as requested. If you package it as a standard Codex skill later, place the same content in a directory-level `SKILL.md`.

## Use When

- You are working in or against the `deep-research-mcp` repository/project.
- You need to run `cli/deep-research-cli.py` in direct agent mode.
- You need to call `DeepResearchAgent` and `ResearchConfig` from Python.
- You need to expose the `deep-research-mcp` project as an MCP server with `deep-research-mcp`.
- You need to connect to the MCP server from another client over HTTP.
- You need to understand which backend is used for OpenAI, Gemini, DR-Tulu, or Open Deep Research.
- You need to troubleshoot provider mix-ups caused by values already stored in `~/.deep_research`.

## Do Not Use When

- You only need the Textual TUI in `cli/deep-research-tui.py`.
- You need a generic guide to Deep Research agents, generic research workflows, or MCP outside the `deep-research-mcp` codebase.
- You are looking for model-selection advice outside the providers this repository already implements.

## Mental Model

There are three layers:

1. `cli/deep-research-cli.py` is the user-facing CLI.
2. `src/deep_research_mcp/agent.py` orchestrates research, clarification, instruction building, callbacks, and status checks.
3. `src/deep_research_mcp/backends/*.py` performs provider-specific work.

The CLI can run in two modes:

- Agent mode: instantiate `DeepResearchAgent` directly.
- MCP client mode: connect to a running HTTP MCP server with `--server-url`.

The MCP server entrypoint is the console script:

```bash
uv run deep-research-mcp
```

It exposes three tools:

- `deep_research`
- `research_with_context`
- `research_status`

## Setup

The commands below assume you are running from the repository root.

### Recommended install

```bash
uv sync --upgrade --extra dev
```

### Compatible editable install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

### Optional Open Deep Research extras

```bash
uv sync --upgrade --extra dev --extra open-deep-research
```

### Environment variables by provider

OpenAI:

```bash
export OPENAI_API_KEY="YOUR_OPENAI_API_KEY"
```

Gemini:

```bash
export GEMINI_API_KEY="YOUR_GEMINI_API_KEY"
```

Clarification when the research provider is not OpenAI:

```bash
export CLARIFICATION_API_KEY="$OPENAI_API_KEY"
export CLARIFICATION_BASE_URL="https://api.openai.com/v1"
```

DR-Tulu:

- there is no single required key defined by `deep-research-mcp` itself
- you must have a running DR-Tulu service that exposes `POST {base_url}/chat`

## Provider Matrix

| Provider | Backend module | How research is executed | Status polling | Notes |
| --- | --- | --- | --- | --- |
| `openai` + `api_style=responses` | `openai_backend.py` | OpenAI Responses API in background mode with `web_search_preview`, optionally `code_interpreter` | Yes | Best match for `o4-mini-deep-research-*` |
| `openai` + `api_style=chat_completions` | `openai_backend.py` | One-shot Chat Completions call | No persistent status | Useful for OpenAI-compatible providers like Perplexity, Groq, Ollama, vLLM |
| `gemini` | `gemini_backend.py` | Gemini Interactions API with `background=True` | Yes | Uses `google-genai`; `include_analysis` is ignored by the backend |
| `dr-tulu` | `dr_tulu_backend.py` | `POST {base_url}/chat` | No | Requires a separately running DR-Tulu service |
| `open-deep-research` | `open_deep_research_backend.py` | Local Open Deep Research stack via `smolagents` | No | Needs extra optional dependencies |

## Clarification Model Rule

Clarification is not implemented inside the Gemini or DR-Tulu backends. It is handled separately by `clarification.py` using OpenAI-compatible chat models:

- `triage_model`
- `clarifier_model`
- `instruction_builder_model`

If your research provider is not `openai`, set either:

- `CLARIFICATION_API_KEY` and `CLARIFICATION_BASE_URL`, or
- `OPENAI_API_KEY` and optionally `OPENAI_BASE_URL`

If clarification is disabled, `request_clarification=True` does not ask questions. It returns a "query is sufficient / clarification is disabled" response instead.

## Config Precedence And The Most Important Pitfall

`ResearchConfig.load()` merges:

1. Built-in defaults
2. `~/.deep_research`
3. Environment variables
4. CLI flags, which are injected as environment variables

This matters because the TOML file is flattened into keys like `RESEARCH_API_KEY` and `RESEARCH_BASE_URL`. If your saved config is pinned to Gemini and you run:

```bash
uv run python cli/deep-research-cli.py --provider openai research "..."
```

you may still send the request to Gemini or send the Gemini key to OpenAI unless you also override:

- `--api-key`
- `--base-url`
- sometimes `--model`

Safe pattern when switching providers from the command line:

```bash
uv run python cli/deep-research-cli.py \
  --provider openai \
  --api-style responses \
  --model o4-mini-deep-research-2025-06-26 \
  --api-key "$OPENAI_API_KEY" \
  --base-url https://api.openai.com/v1 \
  research "..."
```

## Recommended Minimal Config Files

### OpenAI Responses

```toml
[research]
provider = "openai"
api_style = "responses"
model = "o4-mini-deep-research-2025-06-26"
api_key = "YOUR_OPENAI_API_KEY"
base_url = "https://api.openai.com/v1"
timeout = 1800
poll_interval = 30
```

### Gemini Deep Research

```toml
[research]
provider = "gemini"
model = "deep-research-pro-preview-12-2025"
api_key = "YOUR_GEMINI_API_KEY"
base_url = "https://generativelanguage.googleapis.com"
timeout = 1800
poll_interval = 30
```

### DR-Tulu

```toml
[research]
provider = "dr-tulu"
model = "dr-tulu"
base_url = "http://localhost:8080"
api_key = ""
timeout = 1800
poll_interval = 30
```

`dr-tulu` is different from the others: the `deep-research-mcp` repository does not ship the DR-Tulu service itself. The backend only expects something else to be listening at `POST {base_url}/chat`.

## CLI: Direct Agent Mode

Direct agent mode is the default when you do not pass `--server-url`.

### Basic Shape

```bash
uv run python cli/deep-research-cli.py research "Your research query"
```

### Useful Flags

```bash
uv run python cli/deep-research-cli.py \
  --provider openai \
  --api-style responses \
  --model o4-mini-deep-research-2025-06-26 \
  --api-key "$OPENAI_API_KEY" \
  --base-url https://api.openai.com/v1 \
  --timeout 900 \
  --poll-interval 10 \
  research "Your research query" \
  --system-prompt "Custom instructions" \
  --output-file report.md
```

Key flags:

- `--provider`
- `--model`
- `--api-key`
- `--base-url`
- `--api-style`
- `--timeout`
- `--poll-interval`
- `--clarify`
- `--system-prompt` or `--system-prompt-file`
- `--no-analysis`
- `--output-file`
- `--json` in agent mode only

### Live OpenAI CLI Example

Command:

```bash
OPENAI_API_KEY="$OPENAI_API_KEY" \
uv run python cli/deep-research-cli.py \
  --provider openai \
  --api-style responses \
  --model o4-mini-deep-research-2025-06-26 \
  --api-key "$OPENAI_API_KEY" \
  --base-url https://api.openai.com/v1 \
  --timeout 900 \
  --poll-interval 10 \
  research "What are flow matching models in generative AI, and how do they differ from diffusion models?" \
  --system-prompt "Answer in exactly 3 bullets and one final takeaway sentence. Keep the whole answer under 180 words. Prefer recent, high-signal sources." \
  --output-file openai-report.md
```

Observed output excerpt:

```text
============================================================
RESEARCH REPORT
============================================================
Task ID: <openai_task_id>
Total steps: 72
Search queries: 35
Citations: 8
Execution time: 216.15s

- **Flow-matching models** train continuous normalizing flows by learning a time-dependent vector field that pushes a simple prior (e.g. Gaussian noise) into the data distribution along a chosen probability path ...
- **Diffusion models** instead progressively add noise to data (via an SDE) and learn a score-based denoiser to reverse that process ...
- **Sampling differences:** Flow-matching generates samples by solving a learned ODE in (often) one shot ...

**Takeaway:** Flow-matching models use smooth ODE flows (vector fields) to map noise->data, subsuming diffusion's process as a special case; they typically allow a more direct, faster sampling path.
```

What this tells you:

- OpenAI Responses mode is genuinely multi-step in `deep-research-mcp`.
- `total_steps` and `search_queries` are meaningful for this backend.
- Direct agent mode blocks until the task completes.

### Live Gemini CLI Example

Command:

```bash
GEMINI_API_KEY="$GEMINI_API_KEY" \
uv run python cli/deep-research-cli.py \
  --provider gemini \
  --model deep-research-pro-preview-12-2025 \
  --timeout 900 \
  --poll-interval 10 \
  research "What are flow matching models in generative AI, and how do they differ from diffusion models?" \
  --system-prompt "Answer in exactly 3 bullets and one final takeaway sentence. Keep the whole answer under 180 words. Prefer recent, high-signal sources." \
  --output-file gemini-report.md
```

Observed output excerpt:

```text
============================================================
RESEARCH REPORT
============================================================
Task ID: <gemini_task_id>
Total steps: 1
Execution time: 99.00s

# Flow Matching vs. Diffusion Models

* **Core Concept:** Flow matching is a generative modeling framework that learns a deterministic, continuous velocity field ...
* **Key Differences:** While diffusion models rely on a fixed, stochastic process ...
* **Efficiency:** Because these generation trajectories are straighter and deterministic ...

Ultimately, while the two paradigms share deep mathematical connections, flow matching streamlines the generative process ...
```

Important Gemini-specific behavior:

- The normalized citation list may be empty even when the report text includes a `Sources:` section.
- Grounding URLs may appear as Google redirect URLs rather than the final origin URL.
- `include_analysis` does not map to a Gemini code-execution tool toggle in this backend.

### Live DR-Tulu CLI Example

Command:

```bash
uv run python cli/deep-research-cli.py \
  --provider dr-tulu \
  --model dr-tulu \
  --base-url http://localhost:8080 \
  --timeout 1800 \
  research "What is flow matching in generative AI?" \
  --system-prompt "Answer in exactly 2 bullets and one takeaway sentence. Keep the whole answer under 120 words." \
  --no-analysis \
  --output-file dr-tulu-report.md
```

Observed output excerpt:

```text
============================================================
RESEARCH REPORT
============================================================
Task ID: <dr_tulu_task_id>
Total steps: 3
Citations: 25
Execution time: 177.66s

- Flow matching trains a continuous normalizing flow by regressing a conditional drift (vector field) that deterministically maps noise to data in one straight-line ODE ...
- In practice, sampling solves the learned ODE forward ... and recent variants remove ODE solvers at generation time ...

Takeaway: Flow matching defines generative models as learned deterministic transport maps from noise to data via a conditional vector field ...
```

What this tells you:

- The current `dr-tulu` backend works against a live `POST /chat` service.
- `total_steps` comes from `metadata.total_tool_calls`.
- Citation extraction works by normalizing `metadata.searched_links`.
- DR-Tulu latency can still be substantial even for short prompts.

### Live `status` CLI Example

Command:

```bash
OPENAI_API_KEY="$OPENAI_API_KEY" \
uv run python cli/deep-research-cli.py \
  --provider openai \
  --api-key "$OPENAI_API_KEY" \
  --base-url https://api.openai.com/v1 \
  status YOUR_OPENAI_TASK_ID
```

Observed output:

```text
Task ID: YOUR_OPENAI_TASK_ID
Status: completed
Created: <provider_created_timestamp>
Completed: <provider_completed_timestamp>
```

Note that timestamp formatting is provider-specific:

- OpenAI Responses returned Unix timestamps here.
- Gemini `research_status` returned formatted datetimes in this environment.

## Python API: `ResearchConfig` + `DeepResearchAgent`

The direct Python API is the cleanest way to embed the framework in another program.

### Generic Pattern

```python
import asyncio
from deep_research_mcp import DeepResearchAgent, ResearchConfig

async def main() -> None:
    config = ResearchConfig(
        provider="openai",
        api_style="responses",
        model="o4-mini-deep-research-2025-06-26",
        api_key="YOUR_OPENAI_API_KEY",
        base_url="https://api.openai.com/v1",
        timeout=900,
        poll_interval=10,
    )

    agent = DeepResearchAgent(config)
    result = await agent.research(
        query="What are the current tradeoffs between flow matching and diffusion?",
        system_prompt="Answer in 3 bullets.",
        include_code_interpreter=False,
    )

    print(result.status)
    print(result.task_id)
    print(result.final_report)

asyncio.run(main())
```

### Live Gemini Python Example

Code:

```python
import asyncio
import json
from deep_research_mcp import DeepResearchAgent, ResearchConfig

async def main() -> None:
    config = ResearchConfig(
        provider="gemini",
        model="deep-research-pro-preview-12-2025",
        base_url="https://generativelanguage.googleapis.com",
        timeout=900,
        poll_interval=10,
    )

    agent = DeepResearchAgent(config)
    result = await agent.research(
        query="Why can flow matching models sample faster than diffusion models?",
        system_prompt="Answer in exactly 2 bullets and one takeaway sentence. Keep the whole answer under 140 words. Prefer papers or technical sources.",
        include_code_interpreter=False,
    )

    payload = {
        "status": result.status,
        "task_id": result.task_id,
        "execution_time": result.execution_time,
        "total_steps": result.total_steps,
        "report": result.final_report,
        "citations": [
            {"index": c.index, "title": c.title, "url": c.url}
            for c in result.citations[:5]
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))

asyncio.run(main())
```

Observed output excerpt:

```json
{
  "status": "completed",
  "task_id": "<gemini_task_id>",
  "execution_time": 99.92130708694458,
  "total_steps": 1,
  "report": "# Acceleration in Generative Models\nResearch suggests that flow matching fundamentally accelerates generative sampling by replacing the complex stochasticity of diffusion with a highly efficient, straight-line mathematical path ...",
  "citations": []
}
```

What to expect from the Python result model:

- `result.status` is normalized across backends.
- `result.task_id` is always the backend task or synthetic task ID.
- `result.final_report` is the main payload.
- `result.citations` is normalized when the backend can extract them. Do not assume every provider fills it equally.

## MCP Server

### Start In Stdio Mode

```bash
uv run deep-research-mcp
```

Use this when another client will spawn the server as a subprocess.

### Start In HTTP Mode

```bash
uv run deep-research-mcp --transport http --host 127.0.0.1 --port 8080
```

The Streamable HTTP endpoint is:

```text
http://127.0.0.1:8080/mcp
```

### Provider-Pinned HTTP Server Example

This pattern avoids accidental reuse of a different provider's saved credentials:

```bash
RESEARCH_PROVIDER=gemini \
RESEARCH_API_KEY="$GEMINI_API_KEY" \
RESEARCH_BASE_URL=https://generativelanguage.googleapis.com \
RESEARCH_MODEL=deep-research-pro-preview-12-2025 \
RESEARCH_POLL_INTERVAL=10 \
uv run deep-research-mcp --transport http --host 127.0.0.1 --port 8081
```

If you want clarification on that server too:

```bash
RESEARCH_PROVIDER=gemini \
RESEARCH_API_KEY="$GEMINI_API_KEY" \
RESEARCH_BASE_URL=https://generativelanguage.googleapis.com \
RESEARCH_MODEL=deep-research-pro-preview-12-2025 \
RESEARCH_POLL_INTERVAL=10 \
ENABLE_CLARIFICATION=true \
CLARIFICATION_API_KEY="$OPENAI_API_KEY" \
CLARIFICATION_BASE_URL=https://api.openai.com/v1 \
uv run deep-research-mcp --transport http --host 127.0.0.1 --port 8082
```

## MCP Tools

### `deep_research`

Use for normal research. Key inputs:

- `query`
- `system_instructions`
- `include_analysis`
- `request_clarification`
- `callback_url`

### `research_with_context`

Use only after `deep_research(..., request_clarification=True)` returns a session ID and questions.

### `research_status`

Use to poll a known task ID.

## CLI As MCP Client

When you pass `--server-url`, the CLI becomes an MCP client instead of creating `DeepResearchAgent` itself.

### Live CLI-over-MCP Example

Command:

```bash
uv run python cli/deep-research-cli.py \
  research "Why can flow matching models use fewer inference steps than diffusion models?" \
  --server-url http://127.0.0.1:8081/mcp \
  --system-prompt "Answer in exactly 2 bullets and one takeaway sentence. Keep the whole answer under 140 words. Prefer technical sources." \
  --no-analysis \
  --output-file mcp-report.md
```

Observed client-side progress output:

```text
[progress] 0.0 Research started...
[progress] 1.0 Research in progress (1 minute)
[progress] 100.0% Research completed successfully
```

Observed report excerpt:

```text
# Research Report: Why can flow matching models use fewer inference steps than diffusion models?

# Inference Efficiency of Flow Matching

* **Optimal Transport Trajectories:** Unlike diffusion models that reverse stochastic, highly curved random walks, flow matching models learn a continuous, deterministic vector field ...
* **Reduced Discretization Error:** Because these straight flow trajectories possess near-minimal curvature ...

**Takeaway:** Flow matching models require significantly fewer inference steps because they replace tortuous stochastic diffusion processes with highly rectified, deterministic ODEs ...

## Research Metadata
- **Total research steps**: 1
- **Search queries executed**: 0
- **Citations found**: 0
- **Task ID**: <mcp_task_id>
- **Execution time**: 88.10 seconds
```

## Python Speaking MCP Directly

### Live `research_status` Example

Code:

```python
import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

TASK_ID = "YOUR_TASK_ID"

async def main() -> None:
    async with streamablehttp_client("http://127.0.0.1:8081/mcp") as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool("research_status", {"task_id": TASK_ID})
            print(result.structuredContent)

asyncio.run(main())
```

Observed output:

```text
{'result': 'Task YOUR_TASK_ID status: completed\nCreated at: <created_at>\nCompleted at: <completed_at>'}
```

## Full MCP Clarification Flow

This only works if the server was started with `ENABLE_CLARIFICATION=true`.

### Step 1: Ask For Clarification

Code:

```python
import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def main() -> None:
    async with streamablehttp_client("http://127.0.0.1:8082/mcp") as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(
                "deep_research",
                {
                    "query": "quantum computing",
                    "request_clarification": True,
                    "include_analysis": False,
                    "system_instructions": "",
                    "callback_url": "",
                },
            )
            print(result.structuredContent)

asyncio.run(main())
```

Observed output excerpt:

```text
{'result': "# Clarifying Questions Needed

**Original Query:** quantum computing

**Why clarification is helpful:** The query 'quantum computing' is extremely broad and underspecified ...

**Session ID:** `YOUR_SESSION_ID`

**Please answer these questions to improve the research:**

1. What is your goal? ...
2. Who is the audience and technical level? ...
3. Which subtopics interest you? ...
...
8. Any source preferences or restrictions? ..."}
```

### Step 2: Continue With `research_with_context`

Code:

```python
import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

SESSION_ID = "YOUR_SESSION_ID"
ANSWERS = [
    "Compare technologies and identify recent research directions.",
    "Graduate-level reader.",
    "Hardware, error correction, and performance benchmarks.",
    "Focus on 2024-2026 developments and near-term outlook.",
    "Global, with emphasis on IBM, Google, and Quantinuum.",
    "Short summary with citations.",
    "Compare performance, error rates, and scalability.",
    "Prefer peer-reviewed papers and official company or lab announcements.",
]

async def main() -> None:
    async with streamablehttp_client("http://127.0.0.1:8082/mcp") as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(
                "research_with_context",
                {
                    "session_id": SESSION_ID,
                    "answers": ANSWERS,
                    "system_instructions": "Answer in exactly 3 bullets and one takeaway sentence. Keep the whole answer under 180 words. Prefer technical and official sources.",
                    "include_analysis": False,
                    "callback_url": "",
                },
            )
            print(result.structuredContent["result"])

asyncio.run(main())
```

Observed output excerpt:

```text
# Enhanced Research Report

**Original Query Enhanced With User Context**

**Enriched Query:** Provide a concise, graduate-level summary with citations ... compares current quantum computing hardware platforms and error-correction approaches worldwide, focusing on developments from 2024-2026 ...

# 2024-2026 Quantum Hardware Review

Fault-tolerance is physically validated. Logical qubits are operational. Scaling hurdles are significant ...

* **Architectural Breakthroughs:** Google achieved below-threshold surface codes ...
* **Error Correction Advancements:** Landmark QEC demonstrations include Quantinuum's 23-second logical qubit ...
* **Scaling Challenges:** Utility-scale operations remain constrained by severe engineering bottlenecks ...

**Takeaway:** The 2024-2026 period successfully validated fault-tolerant quantum principles, but commercializing these architectures demands overcoming immense classical control and interconnect scaling barriers.
```

Important behavior:

- `research_with_context` stores answers against the server-side clarification session.
- If you restart the server, in-memory clarification sessions are lost.
- In `deep-research-mcp`, clarification can be followed by instruction building, which means the final backend query may be more detailed than the simple Q/A pairs alone suggest.

## Backend-Specific Notes

### OpenAI Responses Backend

- Implemented in `src/deep_research_mcp/backends/openai_backend.py`
- Uses `client.responses.create(..., background=True)`
- Polls with `client.responses.retrieve(task_id)`
- Adds `web_search_preview`
- Adds `code_interpreter` only when `include_code_interpreter=True`
- `enable_reasoning_summaries=True` adds `reasoning={"summary": "auto"}`

Use this when you want:

- background execution
- search-query accounting
- best support for `research_status`
- the `deep-research-mcp` repo's intended "deep research" path

### OpenAI Chat Completions Backend

Still `provider="openai"`, but set:

```bash
--api-style chat_completions
```

Differences:

- no background task
- no `research_status` tracking
- no `code_interpreter`
- good for compatible third-party endpoints

### Gemini Backend

- Implemented in `src/deep_research_mcp/backends/gemini_backend.py`
- Uses `google.genai.Client(...).interactions`
- Creates background interactions with `store=True`
- Polls until the interaction is `completed`
- Ignores `include_code_interpreter`

Observed real-world consequences from live runs:

- often `total_steps` is small
- the report may embed a `Sources:` section directly
- the normalized citation list may still be empty
- URLs may be grounding redirects

### DR-Tulu Backend

- Implemented in `src/deep_research_mcp/backends/dr_tulu_backend.py`
- Sends one request to:

```text
POST {base_url}/chat
```

- Expects JSON response fields:
  - `response`
  - `metadata.searched_links`
  - `metadata.total_tool_calls`
- `research_status()` always returns `unknown`

Correct direct CLI shape:

```bash
uv run python cli/deep-research-cli.py \
  --provider dr-tulu \
  --model dr-tulu \
  --base-url http://localhost:8080 \
  research "Your query here"
```

Correct Python shape:

```python
from deep_research_mcp import DeepResearchAgent, ResearchConfig

config = ResearchConfig(
    provider="dr-tulu",
    model="dr-tulu",
    base_url="http://localhost:8080",
)
agent = DeepResearchAgent(config)
```

Important limitation:

- The `deep-research-mcp` repository does not bootstrap DR-Tulu for you.
- You need a separately running DR-Tulu service that exposes `/chat`.
- Without that service, DR-Tulu examples fail immediately with a connection error.
- The current backend expects `base_url` without the `/chat` suffix, because it appends `/chat` internally.
- A live run was verified against a separately running DR-Tulu deployment whose base URL pointed at the service root; the current backend uses `/chat`.

## Troubleshooting

### Symptom: OpenAI call hits Gemini or sends the wrong key

Cause:

- your `~/.deep_research` file already has `research.api_key` or `research.base_url` for another provider

Fix:

- override `--api-key`
- override `--base-url`
- optionally override `--model`
- or use a provider-specific config file with `--config`

### Symptom: `request_clarification=True` says clarification is disabled

Cause:

- `ENABLE_CLARIFICATION` or `CLARIFICATION_ENABLE` was false when the agent/server was created

Fix:

```bash
ENABLE_CLARIFICATION=true \
CLARIFICATION_API_KEY="$OPENAI_API_KEY" \
CLARIFICATION_BASE_URL=https://api.openai.com/v1 \
uv run deep-research-mcp --transport http --host 127.0.0.1 --port 8082
```

### Symptom: `research_status` is not useful

Cause:

- you are using `chat_completions`, `dr-tulu`, or `open-deep-research`

Fix:

- use `openai` + `responses` or `gemini` if you need task polling

### Symptom: Gemini report has sources in text but `citations` is empty

Cause:

- the Gemini backend only populates normalized citations when it can map annotations/output objects cleanly

Fix:

- treat `final_report` as the canonical user-facing output
- treat `result.citations` as best-effort normalization

## Short Recipes

### Fastest safe OpenAI command

```bash
OPENAI_API_KEY="$OPENAI_API_KEY" \
uv run python cli/deep-research-cli.py \
  --provider openai \
  --api-style responses \
  --model o4-mini-deep-research-2025-06-26 \
  --api-key "$OPENAI_API_KEY" \
  --base-url https://api.openai.com/v1 \
  research "Your query"
```

### Fastest safe Gemini command

```bash
GEMINI_API_KEY="$GEMINI_API_KEY" \
uv run python cli/deep-research-cli.py \
  --provider gemini \
  --model deep-research-pro-preview-12-2025 \
  --api-key "$GEMINI_API_KEY" \
  --base-url https://generativelanguage.googleapis.com \
  research "Your query"
```

### Start an HTTP MCP server and use the CLI as the client

Terminal 1:

```bash
RESEARCH_PROVIDER=gemini \
RESEARCH_API_KEY="$GEMINI_API_KEY" \
RESEARCH_BASE_URL=https://generativelanguage.googleapis.com \
uv run deep-research-mcp --transport http --host 127.0.0.1 --port 8081
```

Terminal 2:

```bash
uv run python cli/deep-research-cli.py \
  research "Your query" \
  --server-url http://127.0.0.1:8081/mcp
```

## Final Guidance

If you only remember three things, remember these:

1. Use full provider overrides when your saved TOML file is already specialized.
2. Use `openai` + `responses` or `gemini` when you need status polling.
3. Treat DR-Tulu as an external dependency: the `deep-research-mcp` repo's DR-Tulu backend is a client, not the service itself.
