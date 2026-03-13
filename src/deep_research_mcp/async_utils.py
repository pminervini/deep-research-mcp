# -*- coding: utf-8 -*-

"""
Async helpers for running blocking SDK calls without stalling the event loop.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, TypeVar

ResultT = TypeVar("ResultT")


async def run_blocking(
    func: Callable[..., ResultT], /, *args: Any, **kwargs: Any
) -> ResultT:
    """Run a blocking callable in a worker thread."""
    return await asyncio.to_thread(func, *args, **kwargs)
