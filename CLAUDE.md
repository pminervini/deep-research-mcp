# Claude Code Guide

This short guide is for Claude Code (claude.ai/code) when working with this repository.

Code Style
- NO EMOJIS in any Python or Markdown files.
- Prefer f-strings over `%s`-style string interpolation, including in logging calls.

Authoritative Docs
- Overview, setup, configuration, and usage: see README.md.
- Architecture and component details: see ARCH.md.

MCP Integration
- For adding the MCP server, transports (stdio/HTTP), and up-to-date CLI commands, follow the “Claude Code Integration” and “As an MCP Server” sections in README.md.

Configuration
- The canonical ~/.deep_research TOML examples and key mappings are maintained in README.md. Refer there to avoid drift.

Exposed Tools
- deep_research: autonomous research with web search and analysis (supports clarification)
- research_with_context: research using enriched queries from clarification
- research_status: check status of running research tasks

Development
- Testing, linting, formatting, and type-checking commands are documented in README.md. Use those as the single source of truth.
- Before committing or opening a PR, run `uv run black --fast --check .` to match the CI formatting check.
- ABSOLUTELY DO NOT use monkey patching or mock classes in `tests/`.
- If tests in `tests/` reflect obsolete behavior from an older code version, update the tests to match the intended current behavior instead of patching the code to preserve outdated behavior.

TUI Demo GIF
- The TUI demo animation is at `docs/images/tui-demo.gif`, generated from `docs/tui-demo.tape`.
- To update after TUI changes: install VHS (`brew install vhs`), edit the tape file, run `vhs docs/tui-demo.tape`.
- The tape file controls terminal size, typing, key presses, and timing. See AGENTS.md for full details.
