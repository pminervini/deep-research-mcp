# -*- coding: utf-8 -*-

"""Tests for async helper utilities."""

import asyncio
import time

import pytest

from deep_research_mcp.async_utils import run_blocking


@pytest.mark.asyncio
async def test_run_blocking_keeps_event_loop_responsive():
    """Blocking work should run in a worker thread, not on the event loop."""
    observed: list[str] = []

    async def ticker():
        await asyncio.sleep(0.01)
        observed.append("tick")

    async def blocking_sleep():
        await run_blocking(time.sleep, 0.05)

    await asyncio.gather(blocking_sleep(), ticker())

    assert observed == ["tick"]
