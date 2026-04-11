# Repository Guidelines

## Project Structure & Module Organization
- `src/deep_research_mcp/`: core package.
  - `agent.py`: provider-aware research agent (OpenAI, open-deep-research).
  - `mcp_server.py`: MCP server tools (`deep_research`, `research_with_context`, `research_status`).
  - `config.py`, `errors.py`, `clarification.py`, `prompts/` (YAML prompt templates).
- `cli/`: unified CLI tool (`deep-research-cli.py`) for agent mode, MCP client mode, and config viewing.
- `tests/`: `pytest` suite (`test_*.py`) with markers configured in `pytest.ini`.
- `pyproject.toml`, `requirements.txt` (unpinned compatibility install), `README.md`, `ARCH.md`, `LICENSE`.

## Build, Test, and Development Commands
- Setup env: `uv sync --upgrade --extra dev` (or compatibility: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && pip install -e .`).
- Run MCP server: `uv run deep-research-mcp`.
- Try CLI: `uv run python cli/deep-research-cli.py research "What’s new in quantum computing?" --model gpt-5-mini`.
- Tests: `uv run pytest -v` or `uv run pytest --cov=deep_research_mcp tests/`.
- Lint/format/type-check: `uv run black .`, `uv run pylint src/deep_research_mcp tests`, `uv run mypy src/deep_research_mcp`.
- Before committing or opening a PR, run `uv run black --fast --check .` to match the CI formatting check.

## Coding Style & Naming Conventions
- Python 3.11+, 4-space indentation, use type hints in new/changed code.
- Format with `black` defaults; keep imports and docstrings idiomatic.
- Prefer f-strings over `%s`-style string interpolation, including in logging calls.
- Naming: snake_case for modules/functions, PascalCase for classes, UPPER_CASE for constants.
- Keep public tool signatures stable; document changes in `README.md`/`ARCH.md`.

## Testing Guidelines
- Framework: `pytest`; markers available: `unit`, `integration`, `slow`, `api` (see `pytest.ini`).
- Test files: `tests/test_*.py`; keep focused and deterministic. Place shared fixtures in `conftest.py` if introduced.
- Tests that hit OpenAI APIs require `OPENAI_API_KEY`; such tests are skip-aware—prefer marking and clear env checks.
- ABSOLUTELY DO NOT use monkey patching or mock classes in `tests/`.
- If tests in `tests/` target obsolete behavior from an older code version, update the tests to match the intended current behavior instead of patching the code to preserve outdated behavior.

## Commit & Pull Request Guidelines
- Conventional Commits: `feat:`, `fix:`, `docs:`, `refactor:`, `chore:` (see git history).
- PRs should include: clear description, linked issues, tests for behavior changes, and doc updates (`README.md`, `ARCH.md`, examples in `cli/`) when applicable.
- Add example commands/logs for new tools or flows; call out config/env impacts.

## Security & Configuration Tips
- Do not commit secrets. Configure via `~/.deep_research` (TOML) or env vars (`OPENAI_API_KEY`, `OPENAI_BASE_URL`, `PROVIDER`, `RESEARCH_MODEL`, clarification settings).
- Gate network-dependent tests behind markers; avoid requiring keys in CI by default.

## Updating the TUI Demo GIF
The README includes an animated GIF demonstrating the TUI (`docs/images/tui-demo.gif`). To update it after TUI changes:

1. Install VHS (terminal recording tool): `brew install vhs`
2. Edit the tape file at `docs/tui-demo.tape` to adjust the demo sequence
3. Run VHS to regenerate the GIF: `vhs docs/tui-demo.tape`
4. The output is written to `docs/images/tui-demo.gif`

The tape file uses VHS scripting syntax:
- `Set Width/Height`: terminal dimensions (currently 1400x900)
- `Type "..."`: simulates typing
- `Enter`, `Up`, `Down`, `Left`, `Right`: key presses
- `Sleep Xs`: pause for X seconds/milliseconds

Example workflow in the current tape:
1. Start TUI with `uv run python cli/deep-research-tui.py`
2. Navigate to Provider selector and switch to Gemini
3. Navigate to Query area and enter a research question
4. Press `r` to start research
5. Press `q` to quit

After regenerating, commit both the tape file and the new GIF.
