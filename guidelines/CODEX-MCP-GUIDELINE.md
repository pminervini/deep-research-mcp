# Codex MCP Integration Guideline

> Audience: AI agents running inside Codex (including automated workflows) and human operators building or consuming MCP services with Codex. This document explains how Codex discovers, connects to, and uses Model Context Protocol (MCP) servers, with special focus on timeout controls and operational best practices.

## Quick Reference

| Setting / Concept | Default / Requirement | Where to set or observe | Why it matters |
| --- | --- | --- | --- |
| `mcp_servers.<id>.startup_timeout_sec` | 10s | `~/.codex/config.toml` | Maximum time Codex waits for a server to launch and complete the initial `initialize` + `tools/list` handshake. Supports fractional seconds; implicitly applied to streamable HTTP connect + initial queries. |
| `mcp_servers.<id>.tool_timeout_sec` | 60s | `~/.codex/config.toml` | Timeout for `call_tool`, `resources/list`, `resources/read`, and `resources/templates/list`. Set higher for long-running tools. |
| `mcp_servers.<id>.enabled` | `true` | `~/.codex/config.toml` | Toggle a server without deleting its configuration. Disabled servers are ignored at startup. |
| Server name | `^[a-zA-Z0-9_-]+$` | `mcp_servers.<id>` key | Names must match the pattern; invalid names are skipped with a startup error. |
| Transport | `command` (STDIO) or `url` (streamable HTTP) | `mcp_servers.<id>` | Determines whether Codex launches a local process or connects to an HTTP endpoint. |
| Experimental Rust MCP client | `false` | Top-level `experimental_use_rmcp_client = true` | Switches STDIO clients to the new RMCP implementation, enables OAuth login flows for streamable HTTP, and shares OAuth tokens with `codex mcp login`. |
| CLI management | N/A | `codex mcp ...` | Add, inspect, log in, and remove MCP server definitions without editing `config.toml` manually. |
| Qualified tool names | `mcp__<server>__<tool>` | Appears in TUI / tool specs | Codex rewrites MCP tool names to comply with the OpenAI tool naming rules and avoid collisions. |
| Default STDIO env | `HOME`, `LOGNAME`, `PATH`, `SHELL`, `USER`, `LANG`, `LC_ALL`, `TERM`, `TMPDIR`, `TZ`, … | Automatic | These variables are always forwarded to STDIO servers. Add more via `env_vars` or `env`. |
| Logs | `~/.codex/log/codex-tui.log` (TUI) or stderr (`codex exec`) | Use `tail -F` or `RUST_LOG` | Inspect handshake failures, timeout warnings, and tool call output. |

---

## 1. Understanding MCP in Codex

### 1.1 Model Context Protocol recap

Codex implements the [Model Context Protocol specification (2025-06-18)](https://modelcontextprotocol.io/specification/2025-06-18/). An MCP **client** (Codex in its default mode) connects to one or more MCP **servers** to discover tools, list and read resources, and invoke external capabilities. The handshake consists of:

1. `initialize` — Codex announces `client_info` (`codex-mcp-client`) and its supported capabilities.
2. `tools/list` — Codex fetches the tool manifest and caches it.
3. `resources/list` and `resources/templates/list` — optional follow-up calls on demand.

Servers must reply within the configured timeouts and implement the MCP schema for requests and responses.

### 1.2 Codex roles

Codex can play both roles:

- **MCP client (common case).** The CLI/TUI launches or connects to user-configured MCP servers before a session begins. Discovered tools become available to both the human operator and the AI model.
- **MCP server (optional).** Running `codex mcp-server` exposes Codex as a server with the `codex` and `codex-reply` tools so external MCP-aware agents can drive Codex itself. See [§6](#6-running-codex-as-an-mcp-server).

### 1.3 Supported transports

Codex understands both transports defined by the spec:

- **STDIO** — Codex spawns a local process (`command` + `args`) and speaks MCP on the process’s stdin/stdout. Use this for local binaries, Node scripts, Python entrypoints, etc.
- **Streamable HTTP** — Codex connects to a long-lived HTTP endpoint that supports Server-Sent Events (SSE) for streaming. OAuth login is supported when `experimental_use_rmcp_client = true`.

### 1.4 Tool naming scheme

After discovery, Codex exposes each MCP tool under a fully qualified name of the form

```
mcp__<server-name>__<original-tool-name>
```

This guarantees uniqueness and satisfies the OpenAI tool whitelist (`^[a-zA-Z0-9_-]+$`). When calling tools manually (for example via `codex exec --json` tooling or the TUI’s “Invoke tool” prompt), use the qualified name exactly as displayed.

---

## 2. Configuring Codex to connect to MCP servers

### 2.1 Where configuration lives

Global MCP configuration resides in `~/.codex/config.toml`. Codex merges:

1. Values from `config.toml` (including optional `profiles.<name>.mcp_servers` blocks).
2. CLI overrides (`--config mcp_servers.docs.tool_timeout_sec=180.0` etc.).
3. Transient overrides chosen inside the TUI.

The `codex mcp` CLI writes to the global file for you; manual edits are also supported.

### 2.2 Server naming requirements

The key under `[mcp_servers]` is the canonical server name. It must match `^[a-zA-Z0-9_-]+$`. Invalid names are skipped at startup and reported in the log / CLI output.

### 2.3 STDIO server configuration

```toml
[mcp_servers.docs]
command = "npx"
args = ["-y", "@modelcontextprotocol/inspector", "docs-mcp"]
cwd = "/Users/you/dev/docs-mcp"
startup_timeout_sec = 20.0      # give the server extra time to boot
tool_timeout_sec = 180.0        # allow long document fetches
env_vars = ["GITHUB_TOKEN"]     # forward selected vars from your shell
enabled = true

[mcp_servers.docs.env]
API_KEY = "sk-example-123"
```

Key points:

- `command` must be the executable (`bash`/`python` wrappers are allowed).
- `args` is optional; omit when the command line is self-contained.
- `cwd` sets the working directory before launching the process.
- `env_vars` is a vector of variable names to **forward** from Codex’s environment.
- `env` (inline or as a sub-table) sets **fixed** values.
- Codex automatically sets `CODEX_SANDBOX_NETWORK_DISABLED=1` whenever the current sandbox forbids networking; honor this flag in your server to avoid failing on unsupported features.

### 2.4 Streamable HTTP server configuration

```toml
[mcp_servers.linear]
url = "https://mcp.linear.app/mcp"
bearer_token_env_var = "LINEAR_MCP_TOKEN"
startup_timeout_sec = 15.0
tool_timeout_sec = 90.0

[mcp_servers.linear.http_headers]
"X-Codex-Client" = "codex-cli"

[mcp_servers.linear.env_http_headers]
"X-Org-Id" = "LINEAR_ORG_ID"
```

- `bearer_token_env_var` reads the secret from your environment at runtime (empty or missing variables produce an error).
- `http_headers` adds static headers.
- `env_http_headers` sources header values from environment variables (skips empty values).
- Use HTTPS for remote servers; localhost URLs (e.g., `http://127.0.0.1:5005/mcp`) are valid.

### 2.5 Optional toggles shared by both transports

```toml
[mcp_servers.analytics]
command = "analytics-mcp"
enabled = false              # keep the entry but skip connecting
startup_timeout_sec = 5.0    # faster failover for flaky services
tool_timeout_sec = 30.0      # short-lived queries only
```

Setting `enabled = false` preserves the configuration while removing it from active sessions. Timeouts accept fractional seconds; Codex converts them to `Duration`.

### 2.6 Timeout tuning in depth

- **Startup timeout** (`startup_timeout_sec`, default **10s**):
  - Applied to the entire initialization sequence: launching the process (STDIO), establishing the HTTP connection, responding to `initialize`, and completing the **first** `tools/list`.
  - Also reused when Codex needs to refresh tool metadata during the session.
  - Old configurations may use `startup_timeout_ms`; Codex still accepts it but emits seconds internally.
  - For slow language runtimes (large Node projects, cold Python environments) consider 20–30 seconds.
  - For tiny local helpers, lowering to 3–5 seconds helps fail fast when binaries are missing.

- **Per-tool timeout** (`tool_timeout_sec`, default **60s**):
  - Applies to `call_tool`, `resources/list`, `resources/read`, and `resources/templates/list`.
  - Set to a large value (e.g., several minutes) for long-running operations such as browser automation or bulk exports.
  - Codex treats a timeout as a tool failure; the assistant sees the error message and can retry or present it to the user.
  - `None` (omit the field) means “use the default”; there is no infinite timeout. If you truly need unbounded time, choose a very high number and make the server stream progress updates so users see activity.

- **How AI agents should react**:
  - When an operation times out, Codex surfaces the failure in the turn transcript. The assistant should either adjust arguments, request a higher timeout, or propose an out-of-band solution.
  - Avoid starting multiple long calls in parallel unless you understand the server’s concurrency limits; Codex issues calls sequentially per server but different servers run concurrently.

### 2.7 Switching to the experimental Rust MCP client

Add this at the top level of `config.toml`:

```toml
experimental_use_rmcp_client = true
```

Effects:

- STDIO servers use the new `codex_rmcp_client`, which shares more code with the upstream Rust SDK.
- Streamable HTTP servers use the same client, enabling OAuth device-code flows via `codex mcp login`.
- OAuth tokens are stored under `~/.codex/mcp/<server>/` and reused across sessions.
- This path is the future default; report bugs via the Codex issue tracker.

### 2.8 Managing servers with the CLI

```bash
# Inspect current entries
codex mcp list
codex mcp list --json

# Show a single server in detail
codex mcp get docs
codex mcp get docs --json

# Add or update an entry (stdio example)
codex mcp add docs -- env API_KEY=... -- node docs-mcp-server.js

# Remove an entry
codex mcp remove docs

# OAuth flows (requires experimental_use_rmcp_client = true)
codex mcp login linear
codex mcp logout linear
```

`codex mcp add` rewrites the `mcp_servers.<name>` section in `config.toml`. To modify timeouts or toggles later, either re-run `add` with the desired flags or edit the file manually.

### 2.9 Per-run overrides

You can override MCP settings for a single run:

```bash
codex exec \
  --config 'mcp_servers.docs.tool_timeout_sec=300.0' \
  --config 'mcp_servers.docs.enabled=true' \
  "Summarize the latest docs via the MCP server."
```

Overrides obey TOML syntax. Arrays and objects can be injected with inline syntax (`--config 'mcp_servers.docs.env={API_KEY="sk-..."}'`). These overrides are ephemeral and do not touch `config.toml`.

---

## 3. Runtime behavior inside Codex

### 3.1 Startup flow

When a session starts (TUI launch, `codex exec`, or the IDE extension), Codex:

1. Loads the effective configuration (including profiles and overrides).
2. Launches or connects to each enabled MCP server concurrently.
3. Captures any startup errors (missing binaries, invalid config) and surfaces them in the log and session transcript.
4. Qualifies tools and caches them in the `McpConnectionManager`.

Servers that fail to start do not block others; Codex continues with the remaining set.

### 3.2 Tool discovery and updates

- The initial `tools/list` response is cached for the session. When Codex needs fresh metadata (for example, after a reconnect), it repeats the call using the same startup timeout.
- If a server returns duplicate tool names, Codex warns and keeps the first entry.
- Qualified names appear in the TUI’s tool list and in the OpenAI tool schema the model receives each turn.

### 3.3 Resources

Codex exposes three resource operations:

- `resources/list` — Enumerate resource URIs and titles. Supports pagination via `next_cursor`.
- `resources/templates/list` — Fetch available resource templates (useful for prompts asking for structured input).
- `resources/read` — Retrieve the content of a specific resource.

Codex automatically paginates when aggregating resources across all servers, but when the assistant (or a script) queries a single server it must handle `next_cursor` itself.

### 3.4 Tool invocation

- When the model (or a human via the TUI) invokes an MCP tool, Codex records an `mcp_tool_call` event. In `codex exec --json` mode you will see paired `mcp_tool_call.begin` / `.end` entries.
- Tool arguments must satisfy the JSON Schema provided in `tools/list`. Codex validates obvious errors (missing required fields, wrong types) before sending the request.
- Tool results may contain multiple `output` items; Codex renders them sequentially, including images or rich text if the server supports them.
- Failures (timeout, schema mismatch, server-side error) propagate back to the agent, which can recover or escalate.

### 3.5 Concurrency and throttling

- Each MCP server gets its own client instance plus timeout settings.
- Requests to different servers run in parallel; requests to the same server are serialized unless the server explicitly supports multiplexing via streaming responses.
- Use server-specific rate limits or `tool_timeout_sec` adjustments to avoid overwhelming downstream APIs.

---

## 4. Using MCP services from the Codex CLI and TUI (humans)

1. **Verify configuration.** Run `codex mcp list` to ensure each server resolves correctly and shows the intended timeouts.
2. **Launch the TUI (`codex`).** Newly discovered tools appear under the “Available tools” section. Hover to see the original MCP name and description.
3. **Invoke tools manually.** Press `:` to open the command palette, choose “Call tool…”, and enter the qualified name (`mcp__docs__search`). Provide arguments as JSON when prompted.
4. **Monitor output.** Tool calls stream results directly into the conversation history; long-running calls show live updates until completion or timeout.
5. **Non-interactive runs.** With `codex exec --json`, you can capture `mcp_tool_call` events alongside command executions. Combine with `--output-schema` if you want structured summaries of tool outputs.
6. **Inspect logs.** Use `tail -F ~/.codex/log/codex-tui.log` (or set `RUST_LOG=codex_core=debug`) to diagnose handshake failures, timeout triggers, and resource pagination.

---

## 5. Using MCP services as an AI agent inside Codex

Codex exposes helper functions to agents so they can reason about MCP resources safely:

- `list_mcp_resources` — Enumerate resources on a server. Accepts `server` and optional `cursor`; returns the raw MCP `resources` array plus `next_cursor`. Loop until `next_cursor` is `null`.
- `list_mcp_resource_templates` — Similar to `list_mcp_resources`, but for templates.
- `read_mcp_resource` — Fetches the content of a resource by URI (requires `server` and `uri`).

Best practices for agents:

1. Call `list_mcp_resources` before invoking a tool if your task depends on existing context (for example, to discover documentation pages or database names).
2. Honor `next_cursor` to avoid missing entries. Plan for multiple calls when the server paginates.
3. After fetching a resource, cache key excerpts in your reasoning before issuing follow-up commands; this mitigates repeated network calls when token limits are tight.
4. When using an MCP tool, always reference the qualified name from the tool schema and validate arguments against the provided JSON Schema to reduce trial-and-error.
5. Respect timeouts: if a call fails with a timeout, either shrink the query, ask the human for approval to raise `tool_timeout_sec`, or choose a different approach.
6. The environment sets `CODEX_SANDBOX_NETWORK_DISABLED=1` when outbound network access is blocked. Servers that rely on networking should handle this gracefully and return an informative error so the agent can pivot.

---

## 6. Running Codex as an MCP server

Codex can itself be an MCP server so that other agents can embed Codex workflows.

1. Ensure the Codex CLI is up to date and launch via:

   ```bash
   codex mcp-server
   ```

2. Available tools:
   - `codex`: starts a new Codex session. Key parameters mirror the CLI flags: `prompt` (required), `approval-policy`, `sandbox`, `cwd`, `config` overrides, `profile`, `include-plan-tool`, etc.
   - `codex-reply`: continues an existing session by `conversationId`.

3. When testing with the [MCP Inspector](https://modelcontextprotocol.io/legacy/tools/inspector), increase its request and total timeouts to **600000 ms** (10 minutes) to accommodate Codex’s multi-turn workflows.

4. Tool outputs stream as the Codex session progresses. Use the inspector or your client’s transcript viewer to follow along.

5. The same configuration file (`config.toml`) controls sandboxing, approvals, models, and MCP client connections for sessions launched through the MCP server.

---

## 7. Troubleshooting and best practices

- **Server fails to appear.** Check `codex mcp list --json` for `startup_timeout_sec`/`tool_timeout_sec` values and verify `enabled = true`. Inspect `~/.codex/log/*.log` for errors such as missing binaries or invalid JSON.
- **Timeout during initialization.** Raise `startup_timeout_sec` or profile the server’s startup path. For STDIO servers, pre-warm dependencies (e.g., `npm install`) outside Codex to avoid cold-start overhead.
- **Tool call timeouts.** Increase `tool_timeout_sec` or refactor the server to stream intermediate results so users know it is still running.
- **Authentication errors.** Ensure the environment variables referenced by `env_vars`, `env`, or `bearer_token_env_var` exist and contain non-empty Unicode values. For OAuth-backed HTTP servers, rerun `codex mcp login <server>`.
- **Resource pagination loops.** Servers must advance `next_cursor`; Codex defends against duplicate cursors by failing the request. Fix the server if you see `resources/list returned duplicate cursor`.
- **Name collisions.** If two servers expose tools with the same original name, Codex still guarantees unique qualified names. However, pick descriptive tool names in your server to keep them readable (`search_docs` instead of `search`).
- **Developing a new server.** Validate against the MCP schema (Codex bundles it under `codex-rs/mcp-types/schema/`). Start a `cargo test -p codex-mcp-server` run locally to mirror Codex’s expectations.

---

## 8. Sandbox and security considerations

- Codex may run inside a sandbox (`read-only`, `workspace-write`, or `danger-full-access`). When networking is disabled, the environment variable `CODEX_SANDBOX_NETWORK_DISABLED=1` is injected for child processes, including MCP STDIO servers.
- When Codex executes inside macOS Seatbelt, child processes inherit `CODEX_SANDBOX=seatbelt`. Servers should heed these signals to disable incompatible features instead of failing unpredictably.
- Avoid hardcoding secrets in `config.toml`. Prefer environment variables (`env_vars`, `bearer_token_env_var`, `env_http_headers`) or OAuth flows.

---

## 9. MCP-specific configuration reference

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `mcp_servers.<id>.command` | string | — | Executable for STDIO servers. Mutually exclusive with `url`. |
| `mcp_servers.<id>.args` | array<string> | `[]` | Command-line arguments for STDIO servers. |
| `mcp_servers.<id>.cwd` | string | Current working directory | Working directory for the spawned process. |
| `mcp_servers.<id>.env` | map<string, string> | `{}` | Additional fixed environment variables for STDIO servers. |
| `mcp_servers.<id>.env_vars` | array<string> | `[]` | Environment variable names to forward from Codex. |
| `mcp_servers.<id>.url` | string | — | Endpoint for streamable HTTP servers. Mutually exclusive with `command`. |
| `mcp_servers.<id>.bearer_token_env_var` | string | — | Environment variable containing the bearer token for HTTP servers. |
| `mcp_servers.<id>.http_headers` | map<string, string> | `{}` | Static HTTP headers to include with every request. |
| `mcp_servers.<id>.env_http_headers` | map<string, string> | `{}` | HTTP headers whose values are read from environment variables. |
| `mcp_servers.<id>.startup_timeout_sec` | float (seconds) | 10.0 | Startup timeout; accepts fractional seconds. |
| `mcp_servers.<id>.tool_timeout_sec` | float (seconds) | 60.0 | Tool/resource timeout; accepts fractional seconds. |
| `mcp_servers.<id>.enabled` | boolean | `true` | Skip initialization when `false`. |
| `experimental_use_rmcp_client` | boolean | `false` | Enable the Rust MCP client and OAuth support. |
| `codex mcp login <id>` | command | — | Performs OAuth device-code login when supported. |
| `codex mcp logout <id>` | command | — | Clears stored OAuth tokens. |

---

## 10. Additional resources

- **Codex configuration guide:** `docs/config.md#mcp-integration`
- **Advanced MCP usage:** `docs/advanced.md#model-context-protocol-mcp` and `docs/advanced.md#mcp-server`
- **Non-interactive workflows:** `docs/exec.md`
- **MCP schema definitions bundled with Codex:** `codex-rs/mcp-types/schema/`
- **Inspector & tooling:** <https://modelcontextprotocol.io>
- **Codex issue tracker:** Report MCP bugs or feature requests on the Codex GitHub repository.

With these settings and practices, both humans and AI agents can compose reliable, timeout-aware workflows on top of Codex’s MCP integration.

