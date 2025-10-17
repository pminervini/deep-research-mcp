# MCP Python SDK Usage Guide

This guide teaches humans and coding agents how to build, run, and extend Model Context Protocol (MCP) solutions with the `mcp` Python package. It summarizes the repository layout, shows the preferred tooling, and provides end‑to‑end examples for authoring both MCP servers and clients.

## Repository Orientation
- Core implementation lives in `src/mcp` (`server`, `client`, `cli`, `shared`, `types.py`). Browse these modules when you need to understand runtime behaviour or extend the SDK.
- Ready-to-run samples are in `examples/`. The `examples/snippets` directory mirrors short tutorial code referenced throughout this document.
- Automated tests are under `tests/` and mirror the package layout; use them as blueprints when adding new behaviour.
- Documentation sources are in `docs/` (rendered with MkDocs). Utility scripts live in `scripts/`.

## Installation & Tooling
The SDK targets Python 3.10+. Use [uv](https://docs.astral.sh/uv/) for dependency management (the project’s tooling assumes it).

```bash
# bootstrap a uv project
uv init my-mcp-app
cd my-mcp-app

# install the SDK with CLI helpers
uv add "mcp[cli]"

# optional extras
uv add "mcp[rich]"           # colourized terminal output
uv add "mcp[ws]"             # websocket transport helpers
```

If you just need the CLI in an existing environment:

```bash
pip install "mcp[cli]"
```

Use `uv sync` to install dev dependencies (pytest, pyright, ruff) when contributing to this repository.

## Quickstart: Author a FastMCP Server
FastMCP is the high-level server framework that handles MCP transport, schema generation, and message routing. The snippet below creates a server exposing a resource, a tool, and a prompt.

```python
# server.py
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Demo Server", instructions="Expose basic utilities for demos.")

@mcp.resource("greeting://{name}")
def dynamic_greeting(name: str) -> str:
    """Return a personalised greeting resource."""
    return f"Hello, {name}!"

@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers with structured output."""
    return a + b

@mcp.prompt()
def greet_user(name: str, style: str = "friendly") -> str:
    """Return a reusable prompt template."""
    styles = {
        "friendly": "Write a warm greeting",
        "formal": "Compose a professional greeting",
        "casual": "Draft a relaxed greeting",
    }
    return f"{styles.get(style, styles['friendly'])} for someone named {name}."

if __name__ == "__main__":
    mcp.run()  # default stdio transport
```

### Run the Server
```bash
# iterate with the MCP Inspector (opens browser UI)
uv run mcp dev server.py

# install into Claude Desktop
uv run mcp install server.py --name "Demo Server"

# run directly (stdio transport)
uv run mcp run server.py
```

Add dependencies during dev runs with `--with package`, and mount local packages with `--with-editable path`.

## Resources, Tools, Prompts & Icons
### Resources
Resources expose read-only data via URI templates. Return lightweight, cacheable values.

```python
@mcp.resource("file://documents/{slug}")
def read_document(slug: str) -> str:
    """Serve document content to the LLM."""
    return fetch_from_disk(slug)
```

### Tools
Tools execute actions or heavy computation. Type hints control validation and structured output.

```python
from typing import TypedDict

class WeatherReport(TypedDict):
    temperature: float
    condition: str

@mcp.tool()
async def fetch_weather(city: str) -> WeatherReport:
    """Call an external API and return structured data."""
    payload = await call_weather_api(city)
    return WeatherReport(temperature=payload.temp_c, condition=payload.summary)
```

Opt out of schema generation with `@mcp.tool(structured_output=False)`.

### Prompts
Prompts encapsulate reusable message templates. Use them to standardize LLM conversations.

```python
@mcp.prompt()
def summarize(document: str, audience: str = "developer") -> list[dict[str, str]]:
    """Return system + user messages for the LLM."""
    return [
        {"role": "system", "content": "You summarize technical documents."},
        {"role": "user", "content": f"Summarize for a {audience}: {document}"},
    ]
```

### Icons & Branding
Expose icons or metadata for UI surfaces (Claude Desktop, MCP Inspector).

```python
from mcp.server.fastmcp import FastMCP, Icon

brand_icon = Icon(src="https://example.com/icon.png", mimeType="image/png", sizes="96x96")
mcp = FastMCP("Brand Server", icons=[brand_icon], website_url="https://example.com")
```

## Working with Context & Lifespan
FastMCP injects a typed `Context` when you request it via annotation. Use it for logging, progress, resource access, and retrieving lifespan state.

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession

@dataclass
class AppState:
    db: Database

@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[AppState]:
    db = await Database.connect()
    try:
        yield AppState(db=db)
    finally:
        await db.disconnect()

mcp = FastMCP("App", lifespan=lifespan)

@mcp.tool()
async def long_running(task: str, ctx: Context[ServerSession, AppState]) -> str:
    await ctx.info(f"Starting {task}")
    for step in range(5):
        await ctx.report_progress(progress=(step + 1) / 5, message=f"Step {step + 1}/5")
    result = ctx.request_context.lifespan_context.db.process(task)
    return result
```

Key context helpers:
- `await ctx.debug/info/warning/error(msg)` – stream logs to the client.
- `await ctx.report_progress(progress, total=1.0, message=...)` – surface progress bars.
- `await ctx.read_resource(uri)` – fetch another resource from inside a tool.
- `await ctx.elicit(message, schema)` – prompt users for structured follow-up data.

## Structured Output & Validation
Tools return structured JSON automatically when annotated types are serializable. Supported annotations include Pydantic models, dataclasses, TypedDicts, and primitive/collection types.

```python
from dataclasses import dataclass
from mcp.server.fastmcp import FastMCP

@dataclass
class Analysis:
    score: float
    rationale: str

mcp = FastMCP("Analysis")

@mcp.tool()
def grade(text: str) -> Analysis:
    """Return structured grading feedback."""
    return Analysis(score=0.87, rationale="Clear structure, minor grammar issues.")
```

If validation fails, FastMCP raises a structured error that surfaces in the client.

## Completions & Elicitation
Enhance UX by providing argument completions and follow-up questions.

```python
from mcp.types import CompletionResult, PromptParameter

@mcp.completion("repo://{owner}/{repo}")
async def complete_repo(name: str, ctx: Context) -> CompletionResult:
    suggestions = await ctx.fastmcp.store.suggest_repos(owner=name)
    return CompletionResult(values=suggestions)
```

Use `ctx.elicit` to request additional user input mid-tool:

```python
from pydantic import BaseModel, Field

class BookingPrefs(BaseModel):
    checkAlternative: bool = Field(description="Search another date?")
    alternativeDate: str = Field(description="YYYY-MM-DD date to try next.")

@mcp.tool()
async def book(date: str, ctx: Context) -> str:
    if date == "2024-12-25":
        prefs = await ctx.elicit(
            message="Requested date is booked. Provide preferences.",
            schema=BookingPrefs,
        )
        if prefs.checkAlternative:
            return f"Searching for {prefs.alternativeDate}"
    return "Table confirmed."
```

## Logging & Notifications
Use the context logger to emit diagnostic messages and change notifications. Clients can subscribe to these for UI feedback.

```python
@mcp.tool()
async def process(payload: str, ctx: Context) -> str:
    await ctx.debug(f"Received payload: {payload}")
    await ctx.warning("Running experimental processor.")
    await ctx.session.send_resource_list_changed()
    return payload.upper()
```

## Running Servers in Different Transports
### Development Mode (Inspector)
```bash
uv run mcp dev server.py
uv run mcp dev server.py --with pandas --with-editable .
```

### Claude Desktop Installation
```bash
uv run mcp install server.py
uv run mcp install server.py --name "Analytics Server"
uv run mcp install server.py -v API_KEY=abc -f .env
```

### Direct Execution
```bash
uv run direct-execution-server    # example: examples/snippets/servers/direct_execution.py
python servers/direct_execution.py
```

### Streamable HTTP Transport
Use Streamable HTTP for multi-client deployments or web integrations.

```python
# examples/snippets/servers/streamable_config.py
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("StatefulServer")                 # stateful sessions
# mcp = FastMCP("StatelessServer", stateless_http=True, json_response=True)

if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)
```

Mount inside a Starlette app:

```python
from starlette.applications import Starlette
from starlette.routing import Mount
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("App")

app = Starlette(
    routes=[Mount("/mcp", mcp.streamable_http_app())],
    lifespan=mcp.session_manager.lifespan(),
)
```

Expose `Mcp-Session-Id` via CORS when serving browsers:

```python
from starlette.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://myclient.example"],
    allow_methods=["GET", "POST", "DELETE"],
    expose_headers=["Mcp-Session-Id"],
)
```

### SSE Transport
FastMCP still supports SSE for backward compatibility (`mcp.run(transport="sse")`). Prefer Streamable HTTP for new work.

## Building MCP Clients
### stdio Client
```python
import asyncio
import os

from pydantic import AnyUrl
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
from mcp.shared.context import RequestContext

server_params = StdioServerParameters(
    command="uv",
    args=["run", "server", "fastmcp_quickstart", "stdio"],
    env={"UV_INDEX": os.environ.get("UV_INDEX", "")},
)

async def on_sampling(
    context: RequestContext[ClientSession, None], params: types.CreateMessageRequestParams
) -> types.CreateMessageResult:
    return types.CreateMessageResult(
        role="assistant",
        content=types.TextContent(type="text", text="Sampled response"),
        model="gpt-4o-mini",
        stopReason="endTurn",
    )

async def main() -> None:
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write, sampling_callback=on_sampling) as session:
            await session.initialize()
            await session.list_resources()
            await session.list_tools()
            prompt = await session.get_prompt("greet_user", {"name": "Alice"})
            result = await session.call_tool("add", {"a": 5, "b": 7})
            structured = result.structuredContent
            resource = await session.read_resource(AnyUrl("greeting://World"))
            print(prompt.messages, structured, resource.contents)

if __name__ == "__main__":
    asyncio.run(main())
```

### Streamable HTTP Client
```python
import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def main() -> None:
    async with streamablehttp_client("http://localhost:8000/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            response = await session.call_tool("echo", {"message": "hello"})
            print(response.structuredContent)

if __name__ == "__main__":
    asyncio.run(main())
```

### Display Utilities
```python
from mcp.shared.metadata_utils import get_display_name

tools = await session.list_tools()
for tool in tools.tools:
    print(get_display_name(tool), tool.description)
```

### OAuth-Protected Servers
Implement `TokenVerifier` to validate bearer tokens when exposing protected resources.

```python
from pydantic import AnyHttpUrl
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP

class SimpleVerifier(TokenVerifier):
    async def verify_token(self, token: str) -> AccessToken | None:
        if token == "demo-token":
            return AccessToken(subject="demo", scopes=["user"])
        return None

mcp = FastMCP(
    "Secure Server",
    token_verifier=SimpleVerifier(),
    auth=AuthSettings(
        issuer_url=AnyHttpUrl("https://auth.example.com"),
        resource_server_url=AnyHttpUrl("http://localhost:3001"),
        required_scopes=["user"],
    ),
)
```

Clients discover the authorization server automatically and attach tokens; see `examples/snippets/clients/oauth_client.py`.

## CLI Reference
- `uv run mcp dev server.py`: launch the MCP Inspector for rapid iteration.
- `uv run mcp install server.py`: install a server descriptor (e.g., into Claude Desktop).
- `uv run mcp run path/to/server.py`: run a server with stdio transport.
- `uv run mcp run path/to/server.py --transport streamable-http --port 8000`: run with HTTP transport.
- `uv run mcp list`: list installed servers.
- `uv run mcp uninstall <name>`: remove a server registration.

## Testing, Linting & Type Checking
Keep behaviour reliable by running the project’s dev tooling (matches CI defaults).

```bash
uv run pytest                        # run tests (auto-parallel via pytest-xdist)
PYTEST_DISABLE_PLUGIN_AUTOLOAD="" uv run pytest   # replicate CI
uv run pyright                       # strict static typing
uv run ruff check .                  # lint
uv run ruff format .                 # format
pre-commit run --all-files           # run configured hooks
```

When writing asynchronous tests, use AnyIO fixtures (`pytest.mark.anyio`). The repository enforces strict `xfail_strict`; temporary `xfail`s must include rationale.

## Debugging & Troubleshooting
- Enable verbose logs by passing `debug=True` to `FastMCP(...)` or setting `MCP_LOG_LEVEL=DEBUG`.
- Use context logging (`ctx.debug`, `ctx.info`, etc.) for per-request telemetry.
- For transport issues, confirm the server is reachable and that transports match (stdio vs streamable HTTP). Streamable HTTP endpoints default to `/mcp`; adjust with `mcp.settings.streamable_http_path`.
- When running in browsers, configure CORS to expose `Mcp-Session-Id`, otherwise sessions cannot resume.
- Authentication failures usually indicate invalid tokens or missing scopes; inspect server logs for `TokenVerifier` messages.

## Additional Resources
- Protocol specification: <https://modelcontextprotocol.io>
- SDK documentation: <https://modelcontextprotocol.github.io/python-sdk/>
- Example gallery: `examples/servers/*`, `examples/snippets/*`, `examples/clients/*`

Armed with these patterns—FastMCP helpers, context utilities, typed tool outputs, and the CLI—you can rapidly author MCP servers, build compatible clients, and deploy them into LLM-friendly environments.
