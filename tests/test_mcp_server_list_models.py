# -*- coding: utf-8 -*-

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
import pytest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_PATH = ROOT / "src"


class _StubFastMCP:
    def __init__(self, name: str):
        self.name = name

    def tool(self):  # acts as a decorator factory
        def _decorator(fn):
            return fn

        return _decorator

    def run(self):  # no-op for tests
        return None


def load_mcp_with_stub() -> types.ModuleType:
    # Ensure package path is importable
    if str(SRC_PATH) not in sys.path:
        sys.path.insert(0, str(SRC_PATH))

    # Inject stub before module import
    sys.modules.setdefault("fastmcp", types.ModuleType("fastmcp"))
    sys.modules["fastmcp"].FastMCP = _StubFastMCP  # type: ignore[attr-defined]

    # Stub agent to avoid importing openai via deep_research_mcp.agent
    pkg_name = "deep_research_mcp"
    agent_mod_name = f"{pkg_name}.agent"
    if agent_mod_name not in sys.modules:
        stub_agent = types.ModuleType(agent_mod_name)

        class _StubAgent:
            pass

        stub_agent.DeepResearchAgent = _StubAgent
        sys.modules[agent_mod_name] = stub_agent

    # Import module via package path to satisfy relative imports
    return importlib.import_module("deep_research_mcp.mcp_server")


@pytest.mark.asyncio
async def test_list_models_output_contains_known_models():
    mcp_mod = load_mcp_with_stub()
    result = await mcp_mod.list_models()
    assert "Available Deep Research Models" in result
    assert "o3-deep-research-2025-06-26" in result
    assert "o4-mini-deep-research-2025-06-26" in result
