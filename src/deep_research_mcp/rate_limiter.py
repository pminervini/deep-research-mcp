# -*- coding: utf-8 -*-

"""
Rate limiting utilities for API calls.
"""

import asyncio
import time
from typing import Optional


class RateLimiter:
    """Token bucket rate limiter for API calls"""

    def __init__(self, tokens_per_minute: int = 100):
        self.capacity = tokens_per_minute
        self.tokens = tokens_per_minute
        self.refill_rate = tokens_per_minute / 60.0  # per second
        self.last_refill = time.time()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: int = 1) -> bool:
        """Acquire tokens for API call"""
        async with self._lock:
            now = time.time()
            # Refill tokens
            tokens_to_add = (now - self.last_refill) * self.refill_rate
            self.tokens = min(self.capacity, self.tokens + tokens_to_add)
            self.last_refill = now

            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False

    async def wait_and_acquire(self, tokens: int = 1) -> None:
        """Wait until tokens are available and acquire.

        This method blocks (async) until at least `tokens` are
        available in the bucket, then deducts them.
        """
        while True:
            if await self.acquire(tokens):
                return
            # Estimate time until enough tokens accumulate
            async with self._lock:
                needed = max(0.0, tokens - self.tokens)
                # Avoid division by zero and cap sleep to keep responsiveness
                sleep_for = 0.05 if self.refill_rate <= 0 else needed / self.refill_rate
            await asyncio.sleep(min(max(sleep_for, 0.05), 1.0))
