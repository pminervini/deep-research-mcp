# Repository Guidelines

## Project Structure & Module Organization
- `src/deep_research_mcp/`: core package.
  - `agent.py`: provider-aware research agent (OpenAI, open-deep-research).
  - `mcp_server.py`: MCP server tools (`deep_research`, `research_with_context`, `research_status`).
  - `config.py`, `errors.py`, `clarification.py`, `prompts/` (YAML prompt templates).
- `cli/`: runnable examples and utilities (e.g., `agent-cli.py`).
- `tests/`: `pytest` suite (`test_*.py`) with markers configured in `pytest.ini`.
- `pyproject.toml`, `requirements.txt` (unpinned compatibility install), `README.md`, `ARCH.md`, `LICENSE`.

## Build, Test, and Development Commands
- Setup env: `uv sync --upgrade --extra dev` (or compatibility: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && pip install -e .`).
- Run MCP server: `uv run deep-research-mcp`.
- Try CLI: `uv run python cli/agent-cli.py research "What’s new in quantum computing?" --model gpt-5-mini`.
- Tests: `uv run pytest -v` or `uv run pytest --cov=deep_research_mcp tests/`.
- Lint/format/type-check: `uv run black .`, `uv run pylint src/deep_research_mcp tests`, `uv run mypy src/deep_research_mcp`.

## Coding Style & Naming Conventions
- Python 3.10+, 4-space indentation, use type hints in new/changed code.
- Format with `black` defaults; keep imports and docstrings idiomatic.
- Keep every import, method/function call, and `assert` statement on a single line.
- Naming: snake_case for modules/functions, PascalCase for classes, UPPER_CASE for constants.
- Keep public tool signatures stable; document changes in `README.md`/`ARCH.md`.

## Testing Guidelines
- Framework: `pytest`; markers available: `unit`, `integration`, `slow`, `api` (see `pytest.ini`).
- Test files: `tests/test_*.py`; keep focused and deterministic. Place shared fixtures in `conftest.py` if introduced.
- Tests that hit OpenAI APIs require `OPENAI_API_KEY`; such tests are skip-aware—prefer marking and clear env checks.
- ABSOLUTELY DO NOT use monkey patching or mock classes in `tests/`.

## Commit & Pull Request Guidelines
- Conventional Commits: `feat:`, `fix:`, `docs:`, `refactor:`, `chore:` (see git history).
- PRs should include: clear description, linked issues, tests for behavior changes, and doc updates (`README.md`, `ARCH.md`, examples in `cli/`) when applicable.
- Add example commands/logs for new tools or flows; call out config/env impacts.

## Security & Configuration Tips
- Do not commit secrets. Configure via `~/.deep_research` (TOML) or env vars (`OPENAI_API_KEY`, `OPENAI_BASE_URL`, `PROVIDER`, `RESEARCH_MODEL`, clarification settings).
- Gate network-dependent tests behind markers; avoid requiring keys in CI by default.
