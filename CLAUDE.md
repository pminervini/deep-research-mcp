# Claude Code Guide

This short guide is for Claude Code (claude.ai/code) when working with this repository.

## Behavioral Guidelines

These guidelines reduce common LLM coding mistakes. They bias toward caution over speed; for trivial tasks, use judgment.

### Think Before Coding
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them -- don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### Simplicity First
- No features beyond what was asked.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.
- Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### Surgical Changes
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it -- don't delete it.
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.
- The test: every changed line should trace directly to the user's request.

### Goal-Driven Execution
- Transform tasks into verifiable goals:
  - "Add validation" -> "Write tests for invalid inputs, then make them pass"
  - "Fix the bug" -> "Write a test that reproduces it, then make it pass"
  - "Refactor X" -> "Ensure tests pass before and after"
- For multi-step tasks, state a brief plan with verification checks.
- Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

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
