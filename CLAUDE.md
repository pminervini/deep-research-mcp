# Claude Code Guide

This short guide is for Claude Code (claude.ai/code) when working with this repository.

Code Style
- NO EMOJIS in any Python or Markdown files.

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
