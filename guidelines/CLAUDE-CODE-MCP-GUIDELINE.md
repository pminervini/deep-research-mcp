# Claude Code MCP usage guide

This guide explains how to integrate Model Context Protocol (MCP) services into Claude Code, covering configuration, runtime controls (including timeout tuning), observability, and usage tips for both human operators and AI agents running inside Claude Code sessions.

## Audience
- Human developers maintaining Claude Code environments or adding MCP servers to repositories.
- Automation authors and AI agents that need predictable MCP behaviour, detailed context, and clear failure modes.
- Security and operations roles responsible for reviewing MCP configurations before deployment.

## Terminology
- **MCP server**: An external process or HTTP/SSE endpoint that exposes tools, observations, or resources via the Model Context Protocol.
- **Transport**: How Claude Code connects to the server (`stdio`, `sse`, or `http`). Each transport has unique configuration knobs.
- **Tool**: An MCP-exposed action that Claude Code (or the AI agent within it) can invoke.
- **Resource**: Read-only data (files, records, URLs) that the server can stream back to Claude Code.
- **Prompt / Prompt template**: Pre-authored prompt fragments that the MCP server can return for re-use.
- **Scope**: Where an MCP configuration lives (`project`, `local`, or `user`). Scopes determine who receives the configuration and how it syncs across machines.

## Quick-start checklist
1. **Install Claude Code** (`npm install -g @anthropic-ai/claude-code`) and ensure Node.js 18+ is available.
2. **Confirm the MCP server runs locally or remotely** and supports the Model Context Protocol.
3. **Decide on configuration scope**:
   - `project`: committed `.mcp.json` file co-located with the repository.
   - `local`: machine-specific configuration stored by Claude Code (not checked in).
   - `user`: personal/global configuration shared across all projects on the same machine.
4. **Register the server** using `claude mcp add`, `claude mcp add-json`, or by referencing a config file with `--mcp-config`.
5. **Set timeouts** (`MCP_TIMEOUT`, `MCP_TOOL_TIMEOUT`) before launching `claude` if the defaults do not match your service SLAs.
6. **Validate** with `claude mcp list` and optionally `claude --mcp-debug` for verbose logging.
7. **Exercise tools and resources** inside a Claude session; confirm permissions prompts and returned data match expectations.

## Managing configurations

### Using the CLI scopes
- `claude mcp add`: Launches an interactive wizard that writes to your chosen scope.
- `claude mcp add-json <name> '<json>'`: Adds a server from a literal JSON object (handy for automation).
- `claude mcp add-from-claude-desktop`: Imports configurations from Claude Desktop if you maintain parity across environments.
- `claude mcp list`: Shows all configured servers, their scopes, health status, and whether they are enabled.
- Use additional subcommands listed in `claude mcp --help` to clean up or temporarily suspend servers that you no longer need.
- Pass multiple config sources on startup with `claude --mcp-config path/to/file1.json path/to/file2.json`. Later files override earlier entries with the same server name.

> **Tip:** When committing project-level configurations, prefer `project` scope so teammates and automation inherit identical MCP definitions simply by checking out the repository.

### File-based configuration
Claude Code expects JSON with an `mcpServers` object. Each entry key becomes the MCP server name that appears inside sessions.

```json
{
  "mcpServers": {
    "custom-stdio-server": {
      "transport": {
        "type": "stdio",
        "command": "node",
        "args": ["dist/server.js"],
        "env": {
          "LOG_LEVEL": "info"
        }
      },
      "instructions": "Provides repository-specific automation.",
      "permissions": [
        {
          "type": "filesystem",
          "path": "./",
          "access": "read"
        }
      ]
    }
  }
}
```

Key points:
- `instructions` appear in Claude Code’s UI and help both humans and AI agents reason about the server.
- `permissions` trigger consent prompts the first time a tool attempts an action (for example, file reads or writes). Keep them narrow.
- `env` values can reference environment variables; Claude Code expands them at runtime. Use this for secrets instead of hard-coding credentials.

### Transport-specific notes
- **stdio**: Launches a local process. Ensure the command is idempotent and exits on `SIGTERM`. Provide absolute paths for commands if the working directory is ambiguous.
- **sse**: Define `url`, optional `headers`, and (if needed) `heartbeatInterval`. Use headers for API keys or bearer tokens.
- **http**: Similar to `sse` but for request/response interactions; set `url`, `method`, and `headers`. Claude Code now supports streamable HTTP MCP servers, so keep responses chunk-friendly when large payloads are expected.
- All remote transports can specify `headersHelper` to compute dynamic headers (for OAuth exchanges, rotating API keys, etc.).

## Timeout and retry controls

Claude Code exposes two environment variables for coarse-grained timeouts. Set them before launching the CLI or in your process manager.

```bash
export MCP_TIMEOUT=45000        # milliseconds for server startup/handshake
export MCP_TOOL_TIMEOUT=120000  # milliseconds for individual tool calls
claude --mcp-config ./.mcp.json
```

- `MCP_TIMEOUT` bounds how long Claude Code waits for the MCP server to start and complete the initial handshake. Tune this for stdio transports that perform heavy bootstrapping.
- `MCP_TOOL_TIMEOUT` limits tool invocations. Long-running calculations should either stream incremental results or be split into smaller actions; otherwise, Claude Code cancels the call and surfaces an error.
- Both values default to Claude Code’s internal settings (subject to change in releases). Always define explicit values if you require deterministic SLAs.
- Servers should handle cancellation requests gracefully. Claude Code sends cancellation signals when timeouts expire or users cancel tool calls.

For iterative debugging, run the CLI with `--mcp-debug` to emit detailed connection logs and tool payloads:

```bash
claude --mcp-debug
```

Combine this flag with the timeout environment variables to reproduce edge cases reliably.

## Activating MCP servers during sessions
- Claude Code automatically loads enabled servers at startup. Use `/mcp` inside a session to inspect available servers, tools, and current status.
- Mention a server with `@server-name` to toggle it on or off for the current conversation thread.
- Tools appear in the tool palette once enabled. Humans can trigger them explicitly; the AI agent can decide to call them based on the conversation context.
- Resource references returned by a server can be mentioned with `@resource-id` to inject them into the chat.

## Workflow tips for humans
- Keep an eye on the permission prompts that surface the first time a tool requests access; respond thoughtfully to maintain least-privilege access.
- When a tool call fails, check `claude mcp list` for the health indicator. Restart the server process if the status is `error` or `disconnected`.
- Capture verification steps in your project README so teammates can follow the authentication flow (for example, exporting `GITHUB_TOKEN` before hitting GitHub APIs).
- Restart your Claude Code session after editing project-level `.mcp.json` so the new configuration is loaded.

## Workflow tips for AI agents
- Read `instructions` provided in the MCP configuration; they summarize safe usage. Incorporate them into tool selection heuristics.
- Before calling a tool that interacts with external systems, confirm required parameters are available. If not, ask the user for clarification or gather missing context via other tools.
- Respect tool return types. Many MCP servers supply structured JSON; propagate these structures instead of reformatting unless the user requests otherwise.
- Monitor timeout handling: if a tool call was cancelled, consider whether a follow-up call with tighter scope or different parameters could succeed within `MCP_TOOL_TIMEOUT`.
- Surface resource links (`resource://` URIs) back to the user rather than inlining large blobs. Claude Code now supports `resource_link` tool results; use them to keep the conversation tidy.

## Security and secrets management
- Never hard-code tokens in configuration files. Use environment variable substitutions (`${TOKEN_NAME}`) and set the values before launching Claude Code.
- Rely on `headersHelper` or OAuth discovery if the server supports automatic token refresh. Claude Code refreshes tokens proactively when configured.
- Limit permissions to the minimal filesystem paths or network domains required.
- Review `SECURITY.md` when connecting to services that manage authentication, webhooks, or third-party data.

## Testing and observability
- Smoke-test new servers by running `claude` locally, enabling the server, and executing representative tool calls end-to-end.
- If your automation depends on MCP interactions, add a CI step that launches Claude Code in headless mode with `--mcp-config` and verifies connectivity.
- For stdio transports, log to `stderr` so Claude Code captures output in debug mode.
- Take advantage of auto-reconnection for SSE transports; still, ensure the remote endpoint supports resumed sessions or idempotent calls.

## Troubleshooting checklist
- **Server never appears**: Confirm the config file is referenced (`--mcp-config`) or the correct scope is enabled. Validate JSON syntax.
- **Handshake timeout**: Increase `MCP_TIMEOUT` and review server startup logs with `--mcp-debug`.
- **Tool call cancelled**: Inspect `MCP_TOOL_TIMEOUT`, retry with reduced scope, or stream incremental results.
- **Duplicate tools**: Remove extra declarations if the server is registered in multiple scopes under the same name.
- **Permission prompt not shown**: Ensure the server declares `permissions` and that Claude Code has not already cached an earlier approval.
- **OAuth failures**: Launch with `--mcp-debug` to capture token exchange details; double-check redirect URIs and dynamic headers configuration.

## Checklist before sharing with teammates
- [ ] `.mcp.json` (project scope) validated with `jq` and committed.
- [ ] Secrets documented as environment variables (not committed).
- [ ] Timeout values confirmed for each server.
- [ ] Instructions and capability notes included so AI agents understand intended usage.
- [ ] Manual verification steps appended to the project README or runbook.

## Further references
- Run `claude mcp --help` for the latest CLI options and subcommands.
- Review the Model Context Protocol specification for transport schemas and tool/response payload formats.
- Follow the Claude Code changelog (`CHANGELOG.md`) to track new MCP features such as dynamic headers, OAuth improvements, and resource link support.
