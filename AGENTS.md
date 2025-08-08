# Repository Guidelines

## Project Structure & Modules
- `src/deep_research_mcp/`: Python package.
  - `agent.py`: Orchestrates Deep Research flows.
  - `config.py`: Pydantic settings and `.env` loading.
  - `mcp_server.py`: MCP entrypoint used by Claude Code.
  - `rate_limiter.py`: Retry/backoff and throttling.
  - `errors.py`: Exception types.
- Tests (expected): `tests/` alongside `src/` using `pytest`.

## Build, Test, and Development
- Install: `pip install -r requirements.txt` (use Python 3.9+).
- Editable install (optional): `pip install -e .`
- Run MCP server locally: `python src/deep_research_mcp/mcp_server.py`
- Run tests: `pytest` or `pytest --cov=deep_research_mcp tests/`
- Format: `black src/ tests/`
- Lint: `pylint src/`
- Type check: `mypy src/`

## Coding Style & Naming
- Python style: 4-space indent, Black formatting, import sorting consistent with Black.
- Type hints: required for public functions and class methods.
- Naming: `snake_case` for functions/vars, `PascalCase` for classes, `UPPER_SNAKE` for constants, module names in `snake_case`.
- Docstrings: short, imperative summaries; include error cases and return types where non-obvious.
- Logging: prefer `structlog`; avoid printing directly in library code.
- Never use emojis in code, comments, docstrings, or any part of the codebase.

## Testing Guidelines
- Frameworks: `pytest`, `pytest-asyncio` for async behavior.
- Location: place files under `tests/` matching `test_*.py`; mirror package structure where helpful.
- Async tests: mark with `@pytest.mark.asyncio`.
- Coverage: target ≥80% for changed code; include edge cases (timeouts, rate limits, API errors).

## Commit & Pull Requests
- Commits: use Conventional Commits where possible (e.g., `feat: add task polling`, `fix(rate): backoff jitter bug`). Keep diffs focused.
- PRs must include:
  - Clear description, context, and rationale; link issues.
  - How to test (commands/inputs) and expected outcomes.
  - Screenshots or logs when behavior is user-visible (e.g., MCP server output).
  - Checklist: tests pass, formatted, lint/type checks clean.

## Security & Configuration
- Secrets: never commit API keys. Use `.env` and `ResearchConfig.from_env()`.
- Example Claude Code config: point to `src/deep_research_mcp/mcp_server.py` in `~/.config/claude-code/mcp.json` and pass `OPENAI_API_KEY` via env.
- Cost/rate limits: prefer the mini model for iteration; respect `MAX_RETRIES` and backoff.

## Architecture Notes
- Core flow: `DeepResearchAgent` (domain) + `mcp_server.py` (transport) + `config.py` (settings) + `rate_limiter.py` (resilience).
- Keep business logic in `agent.py`; avoid coupling transport logic into domain code.

