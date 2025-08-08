# -*- coding: utf-8 -*-

from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import types
import pytest


ROOT = pathlib.Path(__file__).resolve().parents[1]
RL_PATH = ROOT / "src" / "deep_research_mcp" / "rate_limiter.py"


def load_rl_module() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(
        "deep_research_mcp_rate_limiter", str(RL_PATH)
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


def test_acquire_basic():
    rl_mod = load_rl_module()
    limiter = rl_mod.RateLimiter(tokens_per_minute=10)
    # Initially full bucket
    assert asyncio.run(limiter.acquire(5)) is True
    # Not enough remaining for 6
    assert asyncio.run(limiter.acquire(6)) is False


@pytest.mark.asyncio
async def test_wait_and_acquire_refill_fast():
    rl_mod = load_rl_module()
    limiter = rl_mod.RateLimiter(tokens_per_minute=6000)  # ~100 tokens/sec
    # Drain bucket quickly
    ok = await limiter.acquire(6000)
    assert ok is True
    # Should refill ~50 tokens in ~0.5s; allow up to 2s margin
    await asyncio.wait_for(limiter.wait_and_acquire(50), timeout=2.0)
