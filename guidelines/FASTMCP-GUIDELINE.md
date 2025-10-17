# FastMCP Usage Guideline

> An in-depth field guide to building, running, and consuming FastMCP 2.x servers. It targets both human developers and autonomous coding agents that need deterministic patterns, strong typing, and clear integration touchpoints.

## Table of Contents

1. [Orientation](#orientation)
2. [Installation & Environment Setup](#installation--environment-setup)
3. [Project Layout & Configuration Files](#project-layout--configuration-files)
4. [Building Servers with `FastMCP`](#building-servers-with-fastmcp)
5. [Tools: From Functions to MCP Actions](#tools-from-functions-to-mcp-actions)
6. [Resources & Resource Templates](#resources--resource-templates)
7. [Prompts](#prompts)
8. [Working with `Context`](#working-with-context)
9. [Middleware, Lifespans, and Composition](#middleware-lifespans-and-composition)
10. [Authentication & Security](#authentication--security)
11. [Running Servers & Transport Options](#running-servers--transport-options)
12. [Consuming Servers with `fastmcp.Client`](#consuming-servers-with-fastmcpclient)
13. [Testing Patterns](#testing-patterns)
14. [Deployment Workflows](#deployment-workflows)
15. [Agent-Focused Usage Notes](#agent-focused-usage-notes)
16. [Troubleshooting & Best Practices](#troubleshooting--best-practices)
17. [Quick Reference Cheat Sheet](#quick-reference-cheat-sheet)

---

## Orientation

- **What FastMCP provides**: A batteries-included Python framework for Model Context Protocol (MCP) servers and a typed async client. It wraps low-level protocol details with decorators, managers, CLI utilities, and testing helpers.
- **Primary abstractions**: `FastMCP` servers expose *tools*, *resources* (including templates), and *prompts*. Clients discover and invoke them through the MCP schema.
- **Why teams choose it**: Strong typing, async support, structured outputs, automatic JSON schema inference, built-in auth providers, HTTP/SSE transports, middleware, OpenAPI generation, and a CLI that manages packaging/deployment.
- **Who should read this guide**: Service authors, QA engineers, deployment teams, and coding agents automating integration or testing flows.

---

## Installation & Environment Setup

FastMCP targets Python 3.10+. The project uses [uv](https://docs.astral.sh/uv/) for dependency management, but standard `pip` workflows also work.

### Quick installation

```bash
# Using uv (recommended for reproducible builds)
uv pip install fastmcp

# Using pip
python -m pip install --upgrade fastmcp
```

### Verifying the install

```bash
python -c "import fastmcp; print(fastmcp.__version__)"

# CLI check
fastmcp --version
```

### Development extras

- Install optional packages (`uv pip install "fastmcp[dev]"`) when you need linting, docs, or testing extras.
- Enable structured logging by setting `FASTMCP_LOG_ENABLED=1`.
- Control default transport metadata via environment variables such as:
  - `FASTMCP_RESOURCE_PREFIX_FORMAT` (`protocol` or `path`)
  - `FASTMCP_INCLUDE_FASTMCP_META` (`true`/`false`)

Agents should record these configuration knobs when presenting instructions to users.

---

## Project Layout & Configuration Files

A conventional repository layout mirrors the upstream project:

```
.
├── src/
│   └── my_app/
│       ├── server.py          # FastMCP server definition
│       ├── resources.py       # Resource functions/templates
│       ├── prompts.py         # Prompt definitions
│       └── middleware.py      # Optional middleware
├── examples/                  # Standalone runnable servers
├── tests/                     # pytest suite (asyncio_mode="auto")
├── docs/                      # User documentation (Mintlify)
├── FASTMCP-GUIDELINE.md       # This file
└── fastmcp.json               # Optional declarative configuration
```

### `fastmcp.json`

- A declarative file describing transports, environment variables, dependencies, and server entrypoints.
- Automatically discovered by `fastmcp run`, `fastmcp dev`, and `fastmcp install`.

Example:

```json
{
  "server": "src/my_app/server.py:mcp",
  "transport": "http",
  "host": "0.0.0.0",
  "port": 8080,
  "environment": {
    "OPENAI_API_KEY": "env:OPENAI_API_KEY"
  },
  "dependencies": {
    "python": "3.11",
    "packages": [
      "fastmcp",
      "httpx>=0.28"
    ]
  }
}
```

---

## Building Servers with `FastMCP`

Create one `FastMCP` object per server. Decorate functions to expose tools, resources, and prompts. Optionally configure auth, middleware, tool transformations, or lifespan hooks.

```python
from fastmcp import Context, FastMCP
from fastmcp.tools.tool import ToolResult

mcp = FastMCP(
    name="Inventory Assistant",
    instructions=(
        "Use the resources to inspect SKUs before calling tools. "
        "Prefer structured outputs for downstream automations."
    ),
    include_tags={"public"},          # Only expose components tagged "public"
    strict_input_validation=False,    # Default (Pydantic coercion)
    mask_error_details=True           # Hide internal stack traces from clients
)

@mcp.tool(tags={"public", "inventory"})
async def restock_sku(sku: str, quantity: int, ctx: Context) -> ToolResult:
    """Submit a restock request and return a summary."""
    await ctx.info(f"Restocking {sku} with {quantity} units")
    await ctx.report_progress(progress=5, total=100, message="Preparing payload")
    ticket_id = await create_ticket_async(sku, quantity)
    return ToolResult(
        content=[{"type": "text", "text": f"Ticket {ticket_id} lodged."}],
        structured_content={
            "ticket_id": ticket_id,
            "sku": sku,
            "quantity": quantity
        }
    )

@mcp.resource("inventory://catalog")
async def catalog() -> list[dict[str, str]]:
    """Expose the current SKU catalog for the LLM."""
    return await load_catalog()

@mcp.resource("inventory://sku/{sku}")
async def sku_detail(sku: str, ctx: Context) -> dict:
    """Templated resource that pulls per-SKU data."""
    await ctx.debug(f"Fetching details for {sku}")
    return await fetch_sku_record(sku)

@mcp.prompt("restock_summary", tags={"public"})
def restock_summary_prompt(sku: str, quantity: int) -> str:
    """Reusable prompt for summarising restock actions."""
    return (
        f"Summarise the restock for SKU {sku} with target quantity {quantity}. "
        "Work from the latest inventory readings."
    )

if __name__ == "__main__":
    mcp.run()  # Defaults to stdio transport, suitable for local LLM clients
```

Key constructor arguments:

| Parameter | Purpose |
| --------- | ------- |
| `name` / `instructions` | Human-readable metadata visible to clients. |
| `auth` | Attach an `AuthProvider` for HTTP/SSE transports. |
| `middleware` | Ordered list of async callables that wrap each request. |
| `lifespan` | Async context manager to run startup/shutdown logic (seed caches, open DB connections). |
| `tools`, `tool_transformations` | Register tools programmatically or attach response transformers (see [`ToolTransformConfig`](https://gofastmcp.com/servers/tools#tool-transforms)). |
| `include_tags` / `exclude_tags` | Filter components at registration time. |
| `strict_input_validation` | Toggle Pydantic coercion vs. strict JSON-schema validation. |
| `mask_error_details` | Replace unhandled exception messages with generic text. |
| `include_fastmcp_meta` | Disable FastMCP’s `_fastmcp` namespace if your client dislikes custom metadata. |

---

## Tools: From Functions to MCP Actions

### Basic decorator usage

```python
@mcp.tool
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b
```

- The function name becomes the tool name.
- The docstring becomes the description.
- Type hints define the JSON schema for arguments.
- Return annotations define the output schema when possible.

### Customising metadata

```python
from fastmcp.tools.tool import ToolAnnotations

@mcp.tool(
    name="find_products",
    description="Search the catalog with optional category filtering.",
    tags={"catalogue", "search"},
    annotations=ToolAnnotations(destructiveHint=False, readOnlyHint=True),
    meta={"owner": "catalog-team", "version": "2025.06"}
)
def search_products(query: str, category: str | None = None) -> list[dict]:
    """Internal docstring; clients see the decorator description instead."""
    return perform_search(query, category)
```

### Async and blocking work

- Use `async def` for I/O bound work. FastMCP runs on AnyIO, so you can call other async libraries naturally.
- Wrap blocking functions with `anyio.to_thread.run_sync()` or a dedicated background executor.

```python
import anyio

@mcp.tool
async def encode_large_file(path: str) -> str:
    """Offload CPU-heavy work to a worker thread."""
    return await anyio.to_thread.run_sync(expensive_encoder, path)
```

### Excluding inputs from the schema

Use `exclude_args` to prevent helper parameters from being exposed:

```python
@mcp.tool(exclude_args=["ctx"])
async def privileged_action(user_id: str, ctx: Context) -> str:
    ...
```

### Structured outputs

1. **Annotated return types** (preferred): return dataclasses, Pydantic models, or builtin types. FastMCP serialises them, generates JSON schema, and hydrates them on the client.
2. **`ToolResult`**: full control over content blocks *and* structured payloads.

```python
from dataclasses import dataclass

@dataclass
class WeatherReading:
    city: str
    temperature_c: float
    observed_at: str

@mcp.tool
def get_weather(city: str) -> WeatherReading:
    data = query_weather(city)
    return WeatherReading(
        city=city,
        temperature_c=data.temperature,
        observed_at=data.timestamp_iso,
    )
```

On the client, `CallToolResult.data` becomes a `WeatherReading` instance.

### Error handling

- Raise standard exceptions (`ValueError`, `RuntimeError`) for unexpected states.
- Raise `fastmcp.exceptions.ToolError` to send a controlled message even when `mask_error_details=True`.

```python
from fastmcp.exceptions import ToolError

@mcp.tool
def divide(a: float, b: float) -> float:
    if b == 0:
        raise ToolError("Division by zero is not allowed.")
    return a / b
```

### Enabling/disabling tools

```python
@mcp.tool(enabled=False)
def maintenance_mode() -> str:
    return "Temporarily offline."

# Toggle at runtime
maintenance_mode.enable()
maintenance_mode.disable()
```

### Tag-driven filtering

Apply `include_tags`/`exclude_tags` during server construction to expose only the relevant tools for a given environment or client.

---

## Resources & Resource Templates

Resources expose read-only data. Templates allow parameterised URIs.

```python
@mcp.resource("config://v1")
def app_config() -> dict:
    """Static configuration snapshot."""
    return {"theme": "dark", "features": ["tools", "resources"]}

@mcp.resource(
    uri="logs://{date}/summary",
    description="Log summary for a given ISO date.",
    mime_type="application/json",
    tags={"public", "observability"},
)
async def daily_logs(date: str, ctx: Context) -> dict:
    await ctx.debug(f"Generating log summary for {date}")
    return await summarise_logs(date)
```

Return types map to MCP content:

| Return value | Resulting MCP content |
| ------------ | --------------------- |
| `str` | `TextResourceContents` (`text/plain`) |
| `dict` / `list` / Pydantic model | JSON serialised (`application/json`) |
| `bytes` | `BlobResourceContents` (specify `mime_type`) |
| `None` | Empty content list |

### Programmatic control

```python
resource = app_config  # Decorator returns a Resource object
resource.disable()
resource.enable()
```

### Context integration

Resources (and templates) accept `Context` parameters; see [Working with `Context`](#working-with-context).

---

## Prompts

Prompts package reusable message templates that clients can request via `prompts/get`.

```python
@mcp.prompt(tags={"analysis"})
def sentiment_prompt(text: str) -> str:
    """Explain the sentiment of the provided text."""
    return (
        "You are a sentiment analyst. Provide a JSON response with fields "
        f"`sentiment` and `rationale` for the text: {text!r}."
    )
```

Prompts support async functions and `Context` injection, just like tools/resources.

Clients use `await client.get_prompt("sentiment_prompt", {"text": "hello"})` to retrieve the rendered string and metadata.

---

## Working with `Context`

Any tool, resource, or prompt can accept a parameter annotated with `fastmcp.Context`. This unlocks MCP-specific capabilities.

```python
from fastmcp import Context

@mcp.tool
async def process_order(order_id: str, ctx: Context) -> dict:
    await ctx.info(f"Processing order {order_id}")
    await ctx.report_progress(10, 100, "Fetching order details")

    # Read another resource
    [details] = await ctx.read_resource("orders://catalog")

    # Persist data within the request scope
    ctx.set_state("order_id", order_id)

    # Request additional user input (elicit)
    response = await ctx.elicit(
        "Do you want to expedite shipping?",
        response_type=["standard", "express"],
    )
    if response.action == "accept":
        await ctx.info(f"User selected: {response.data}")

    # Ask the client LLM for help
    completion = await ctx.sample(
        messages=[
            "Summarise the following order issues:",
            f"Order data: {details.content[0].text}",
        ],
        system_prompt="Respond with a short bullet list.",
        max_tokens=200,
    )

    return {
        "order_id": order_id,
        "resolution": completion.text if hasattr(completion, "text") else None,
    }
```

Available capabilities include:

- **Logging**: `await ctx.debug(...)`, `info`, `warning`, `error`. Messages flow to the client’s log handler.
- **Progress reporting**: `await ctx.report_progress(progress=25, total=100, message="...")`.
- **Resource access**: `await ctx.read_resource("uri")`, `await ctx.list_resources()`.
- **Sampling**: `await ctx.sample(...)` to request an LLM completion from the client, with optional server-side fallback handlers.
- **User elicitation**: `await ctx.elicit(prompt, response_type=...)` to request structured user input mid-tool-call.
- **State management**: `ctx.set_state("key", value)` and `ctx.get_state("key", default=None)` share data with middleware during the same request.
- **Request metadata**: `ctx.request_id`, `ctx.client_id`, `ctx.session_id`, and `ctx.fastmcp` give access to runtime information.
- **Notifications**: `await ctx.notify(level="info", message="...")` sends asynchronous notifications outside of standard responses.

For code that cannot directly accept a `Context` parameter, import `fastmcp.server.dependencies.get_context()` to retrieve the active context during a request.

---

## Middleware, Lifespans, and Composition

### Lifespan management

Use the `lifespan` argument to run setup/teardown around the server lifecycle.

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(server: FastMCP):
    connection = await open_database()
    server.state["db"] = connection
    try:
        yield {"db": connection}  # Exposed via ctx.fastmcp.lifespan_result
    finally:
        await connection.close()

mcp = FastMCP(name="DB Server", lifespan=lifespan)
```

### Middleware

Middleware wraps every MCP request (tool call, resource read, prompt get, list operations). Use it for cross-cutting concerns such as authz, rate limiting, or tracing.

```python
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.exceptions import ToolError

async def audit_middleware(
    ctx: MiddlewareContext,
    call_next,
) -> object:
    if ctx.kind == "call_tool":
        await ctx.context.info(f"Calling tool {ctx.target}")
    result = await call_next(ctx)
    if ctx.kind == "call_tool" and isinstance(result, Exception):
        raise ToolError("Tool denied by middleware.") from result
    return result

mcp = FastMCP(middleware=[Middleware(audit_middleware)])
```

`MiddlewareContext` exposes:
- `kind` (`"call_tool"`, `"read_resource"`, `"list_tools"`, etc.)
- `target` (tool name, resource URI)
- `params` (arguments payload)
- `context` (`Context` instance)

### Server composition (`mount`)

Combine multiple FastMCP servers under one namespace:

```python
from fastmcp import FastMCP

weather = FastMCP("Weather")
news = FastMCP("News")

app = FastMCP("Portal")
app.mount(server=weather, prefix="weather")
app.mount(server=news, prefix="news")
```

- Mounted tools are accessible under `weather_<tool_name>`.
- Mounted resources adopt URI prefixes `weather://...`.
- Errors during mounting can be surfaced by setting `FASTMCP_MOUNTED_COMPONENTS_RAISE_ON_LOAD_ERROR=1`.

### Proxies and OpenAPI

- Use `FastMCPProxy` to front remote MCP servers while applying middleware locally (see `docs/servers/proxy.mdx`).
- Generate HTTP APIs with `FastMCPOpenAPI` (found in `fastmcp.experimental.server.openapi`). This builds FastAPI apps from your MCP components.

---

## Authentication & Security

HTTP/SSE transports can require auth via `auth=`. FastMCP ships with providers under `fastmcp.server.auth.providers`.

### Token-based auth

```python
from fastmcp.server.auth.providers.in_memory import InMemoryOAuthProvider

oauth = InMemoryOAuthProvider()
mcp = FastMCP(name="Secured", auth=oauth)
```

- `InMemoryOAuthProvider`: Local OAuth 2.1 provider for testing.
- `JWTVerifier` (`fastmcp.server.auth.providers.jwt`): Validate JWTs/JWKS for bearer-token flows.
- Enterprise providers: `google`, `github`, `azure`, `auth0`, `workos`, `descope`, `scalekit`, `supabase`.

Each provider exposes configuration such as allowed audiences, required scopes, redirect validation, and revocation endpoints.

### Custom verification

Implement `AuthProvider` (see `fastmcp.server.auth.auth`) to integrate proprietary auth.

### Transport-level security

- For SSE/HTTP, terminate TLS upstream (FastMCP does not manage certificates directly).
- Set `mask_error_details=True` to avoid leaking stack traces over the wire.
- Use middleware for request-level authorisation.

---

## Running Servers & Transport Options

### From Python

```python
mcp.run()                                   # stdio (default)
mcp.run(transport="http", host="0.0.0.0", port=8000, root_path="/mcp")
mcp.run(transport="sse", port=7000, message_path="/sse/")
mcp.run(transport="streamable-http", port=9000)
```

- `run()` is synchronous and wraps `run_async()` via `anyio.run`.
- HTTP-based transports expose Starlette apps; you can add routes with `mcp.add_http_route(Route(...))`.
- `stateless_http=True` (transport kwarg) forces a new request context per HTTP request (useful behind load balancers).

### via CLI (`fastmcp run`)

```bash
fastmcp run server.py                     # Infer server variable (mcp/server/app)
fastmcp run server.py:my_server           # Explicit object
fastmcp run server.py:create_server       # Factory function (sync or async)
fastmcp run https://api.example.com/mcp   # Proxy a remote MCP server
fastmcp run fastmcp.json                  # Declarative config
```

Important flags:

| Flag | Purpose |
| ---- | ------- |
| `--transport {stdio,http,sse}` | Override the transport. |
| `--port`, `--host`, `--path` | HTTP binding. |
| `--python 3.11` | Run inside `uv run` with a specific interpreter. |
| `--with fastmcp --with httpx` | Install extra packages in the ephemeral environment. |
| `--with-requirements requirements.txt` | Bulk install dependencies. |
| `--project ./env` | Use a prepared uv project directory. |
| `--skip-env` | Skip dependency resolution (already inside managed env). |
| `--no-banner` | Hide the startup ASCII art. |

Related commands:

- `fastmcp dev server.py` → Runs the server with the MCP Inspector UI (debug).
- `fastmcp install server.py` → Installs into supported MCP clients (Claude Desktop, Gemini CLI, etc.).
- `fastmcp inspect server.py` → Outputs a JSON manifest of tools/resources/prompts.
- `fastmcp project prepare fastmcp.json --output ./env` → Materialise a reusable uv environment.

---

## Consuming Servers with `fastmcp.Client`

`fastmcp.Client` is an async context manager that infers transports and offers typed responses.

```python
import asyncio
from fastmcp import Client, FastMCP

server = FastMCP("Example")

# Define a simple tool for demonstration
@server.tool
def greet(name: str) -> str:
    return f"Hello, {name}!"

async def main():
    async with Client(server) as client:        # In-memory transport
        tools = await client.list_tools()
        result = await client.call_tool("greet", {"name": "world"})
        print(result.data)                      # -> "Hello, world!"

asyncio.run(main())
```

### Transport inference

| Client argument | Transport |
| --------------- | --------- |
| `FastMCP` instance | In-memory (perfect for tests) |
| `"path/to/server.py"` | Local stdio (Python) |
| `"path/to/server.js"` | Local stdio (Node) |
| `"https://example.com/mcp"` | HTTP/SSE (auto based on server capabilities) |
| `{"mcpServers": {...}}` | Multi-server client (namespaced tool/resource calls) |

### Connection lifecycle

```python
client = Client("server.py")
async with client:
    assert client.is_connected()
```

When the `async with` block exits, connections close cleanly.

### Discovering components

```python
async with client:
    tools = await client.list_tools()
    resources = await client.list_resources()
    templates = await client.list_resource_templates()
    prompts = await client.list_prompts()
```

Tool metadata includes FastMCP’s `_fastmcp.tags` namespace when enabled.

### Calling tools

```python
async with client:
    result = await client.call_tool(
        "inventory_restock_sku",
        {"sku": "A-123", "quantity": 5},
        timeout=5.0,
        progress_handler=lambda update: print(update.progress),
    )

    if result.is_error:
        print(result.error)
    else:
        print("Structured:", result.data)             # Hydrated Python object
        print("Text:", result.content[0].text)        # Standard MCP content
```

- `result.data`: Fully typed object (FastMCP extension).
- `result.structured_content`: Raw JSON (MCP standard).
- `result.content`: List of `ContentBlock` objects (text, image, audio, etc.).

### Reading resources & prompts

```python
async with client:
    config_contents = await client.read_resource("config://v1")
    print(config_contents[0].text)

    prompt = await client.get_prompt("restock_summary", {"sku": "A-123", "quantity": 5})
    print(prompt.prompt)
```

### Logging, progress, and sampling callbacks

```python
async def log_handler(log):
    print(f"[{log.level}] {log.message}")

async def progress_handler(update):
    print(f"{update.progress}/{update.total}: {update.message}")

async def sampling_handler(messages, params, ctx):
    # Use your own LLM to satisfy sampling requests
    return "Fallback completion from custom handler"

client = Client(
    server,
    log_handler=log_handler,
    progress_handler=progress_handler,
    sampling_handler=sampling_handler,
    sampling_handler_behavior="fallback",   # or "always"
)
```

### Multi-server clients

When initialised with an MCP configuration, tool names are automatically namespaced (`{server_key}_{tool_name}`) and resource URIs prefixed (`{server_key}://...`).

### Authentication helpers

Use `BearerTokenAuth` or OAuth flows on the client side to attach headers/tokens automatically. See `docs/clients/auth/*.mdx` for patterns.

---

## Testing Patterns

Leverage the in-memory transport for deterministic, fast tests.

```python
import pytest
from fastmcp import Client, FastMCP

@pytest.mark.anyio
async def test_add_tool_behaviour():
    mcp = FastMCP("Test")

    @mcp.tool
    def add(a: int, b: int) -> int:
        return a + b

    async with Client(mcp) as client:
        result = await client.call_tool("add", {"a": 2, "b": 3})
        assert result.data == 5
```

Additional recommendations:

- Set `asyncio_mode="auto"` globally (as in this repository’s `pytest.ini`).
- Use fixtures to share servers across tests.
- For structured outputs, use `pytest_inline_snapshot` to capture JSON or dataclasses.
- Simulate sampling responses by providing `sampling_handler` to the client.
- Validate logging via the client’s `log_handler`.

---

## Deployment Workflows

### Local development

1. Install dependencies: `uv sync`.
2. Run formatters and static checks: `uv run pre-commit run --all-files`.
3. Execute tests: `uv run pytest`.
4. Start the server: `fastmcp dev server.py` (with inspector) or `fastmcp run server.py`.

### Packaging servers

- Use `fastmcp run fastmcp.json --with fastmcp --with httpx` to bundle dependencies.
- `fastmcp project prepare fastmcp.json --output ./env` creates a reusable environment for repeated launches.
- `fastmcp install server.py --with fastmcp --with requests` installs the server into supported MCP clients (Claude Desktop, Gemini CLI, etc.).

### FastMCP Cloud

- Deploy via the FastMCP Cloud UI by specifying:
  - Entrypoint (`server.py:mcp`)
  - Runtime dependencies
  - Environment variables (secrets, API keys)
  - Transport configuration (HTTP or SSE)

### Observability in production

- Configure server logging (`FASTMCP_LOG_LEVEL=INFO`).
- Add middleware for tracing identifiers (request IDs, user IDs).
- Use `ctx.notify` to surface human-readable messages in control planes.

---

## Agent-Focused Usage Notes

Coding agents integrating with FastMCP should:

1. **Use the LLM-friendly docs**: fetch `https://gofastmcp.com/llms.txt` or `llms-full.txt` for up-to-date endpoints and schema references.
2. **Inspect servers safely**: run `fastmcp inspect <entrypoint>` to retrieve JSON definitions without starting transports.
3. **Respect tool metadata**: check `_fastmcp.tags` and `annotations` to decide whether a tool is safe/destructive/idempotent.
4. **Handle structured outputs**: prefer `CallToolResult.data` for typed results; fall back to `structured_content` or `content` if empty.
5. **Prepare for elicitation**: server tools may call `ctx.elicit`, which requires agents to surface follow-up questions to users.
6. **Sampling coordination**: if acting as a proxy, provide a `sampling_handler` so `ctx.sample` calls succeed even when the client LLM lacks native support.
7. **Retry with context**: when encountering `ToolError`, display the human-readable message; when facing generic errors and `mask_error_details` is on, prompt the user for corrective input.
8. **Prefer in-memory transports** during automated testing to avoid process management overhead.

---

## Troubleshooting & Best Practices

- **Tool not listed**: ensure the decorator ran (module imported) and the tool isn’t disabled or filtered out by tags.
- **“Unknown resource”**: confirm URI patterns and that templates are registered; use `await mcp.get_resources()` during debugging.
- **Blocking event loop**: wrap CPU-heavy code with `anyio.to_thread.run_sync`.
- **Structured output missing**: verify the return type can be serialised (e.g., dataclass, dict, Pydantic model). For total control, return `ToolResult`.
- **Masking errors for production**: set `mask_error_details=True` and raise `ToolError` with user-safe messages for expected failures.
- **Client timeouts**: provide per-call `timeout=` values or adjust the client-level default (`Client(..., timeout=10.0)`).
- **Sampling failures**: ensure the downstream client advertises sampling capability; otherwise set `sampling_handler_behavior="fallback"` and supply a handler.
- **Auth configuration drift**: centralise OAuth/JWT settings in `fastmcp.json` and load secrets via environment variables.

Best practices:

- Keep functions well-typed; FastMCP leans heavily on annotations.
- Document components with clear docstrings/descriptions—LLMs read them.
- Use tags to segment functionality (e.g., `"public"`, `"beta"`, `"admin"`).
- Write tests against the in-memory client before exposing servers publicly.
- Align CLI workflows (`fastmcp run/dev/install`) with CI pipelines for reproducibility.

---

## Quick Reference Cheat Sheet

| Task | How |
| ---- | --- |
| Create server | `mcp = FastMCP("Name", instructions="...")` |
| Register tool | `@mcp.tool\ndef fn(...): ...` |
| Register resource | `@mcp.resource("uri")\ndef fn(...): ...` |
| Register prompt | `@mcp.prompt("id")\ndef fn(...): ...` |
| Access context | `async def fn(..., ctx: Context): ...` |
| Structured output | Return dataclass / Pydantic / `ToolResult` |
| Run server | `mcp.run(transport="http", port=8000)` |
| CLI run | `fastmcp run server.py` |
| Inspect server | `fastmcp inspect server.py` |
| Connect client | `async with Client(mcp_or_path_or_url) as client:` |
| Call tool | `await client.call_tool("name", {"arg": value})` |
| Read resource | `await client.read_resource("uri")` |
| Get prompt | `await client.get_prompt("id", {"var": "value"})` |
| Report progress | `await ctx.report_progress(50, 100, "Halfway")` |
| Request sampling | `await ctx.sample("Prompt text")` |
| Elicit input | `await ctx.elicit("Question?", response_type=list_options)` |
| Middleware | Pass `middleware=[Middleware(fn)]` to `FastMCP` |
| Mount servers | `parent.mount(server=child, prefix="child")` |
| Auth (OAuth) | `FastMCP(auth=InMemoryOAuthProvider(...))` |

Keep this guideline close while building or automating against FastMCP servers. It mirrors the repository’s code and documentation structure and should help both humans and agents onboard quickly.

