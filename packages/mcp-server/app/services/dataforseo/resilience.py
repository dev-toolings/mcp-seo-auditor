"""Rate limiting and response caching for the (billed) DataForSEO API.

The sliding-window limiter mirrors the one guarding Google Search Console in
``app/services/google_search_console.py``; it additionally caps in-flight
requests, because DataForSEO bills per call and unbounded fan-out from a
site-wide audit is the fastest way to burn the quota.
"""

import asyncio
import logging
import time
from collections import OrderedDict, deque
from typing import Any, Optional

logger = logging.getLogger(__name__)


class RateLimiter:
    """Sliding-window (per-minute) limiter with a concurrency ceiling."""

    def __init__(self, rpm: int, max_concurrent: int):
        self._rpm = max(1, rpm)
        self._timestamps: deque[float] = deque()
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(max(1, max_concurrent))

    async def _throttle(self) -> None:
        async with self._lock:
            now = time.monotonic()
            window = now - 60.0
            while self._timestamps and self._timestamps[0] <= window:
                self._timestamps.popleft()
            if len(self._timestamps) >= self._rpm:
                sleep_for = self._timestamps[0] - window
                logger.debug("DataForSEO rate limit: sleeping %.1fs", sleep_for)
                await asyncio.sleep(sleep_for)
                window = time.monotonic() - 60.0
                while self._timestamps and self._timestamps[0] <= window:
                    self._timestamps.popleft()
            self._timestamps.append(time.monotonic())

    def slot(self) -> "_Slot":
        """Async context manager holding one concurrency slot for the call."""
        return _Slot(self)


class _Slot:
    """Acquire a concurrency slot, then respect the per-minute window."""

    def __init__(self, limiter: RateLimiter):
        self._limiter = limiter

    async def __aenter__(self) -> None:
        await self._limiter._semaphore.acquire()
        try:
            await self._limiter._throttle()
        except BaseException:
            self._limiter._semaphore.release()
            raise

    async def __aexit__(self, *exc_info: object) -> None:
        self._limiter._semaphore.release()


class TTLCache:
    """Small in-memory TTL cache with LRU eviction.

    Keyed on the full request (endpoint + payload), so identical calls issued
    within the TTL are served without re-billing.
    """

    def __init__(self, ttl: int, max_entries: int = 512):
        self._ttl = ttl
        self._max_entries = max(1, max_entries)
        self._entries: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    @property
    def enabled(self) -> bool:
        return self._ttl > 0

    def get(self, key: str) -> Optional[Any]:
        """Return the cached value, or None when absent or expired."""
        if not self.enabled:
            return None
        entry = self._entries.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() >= expires_at:
            del self._entries[key]
            return None
        self._entries.move_to_end(key)
        return value

    def set(self, key: str, value: Any) -> None:
        if not self.enabled:
            return
        self._entries[key] = (time.monotonic() + self._ttl, value)
        self._entries.move_to_end(key)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def clear(self) -> None:
        self._entries.clear()
