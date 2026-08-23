"""Shared, thread-safe rate limiter for pytrends calls.

pytrends (Google Trends) tolerates roughly 10 requests/minute before returning
HTTP 429. Each market service used to keep its OWN module-level ``_last_pytrends_call``
global, so the limit was enforced per-module instead of globally — concurrent calls
across services could still exceed the quota. This module centralizes the state behind
a single ``threading.Lock`` so every caller shares one budget.
"""

import threading
import time

# Max ~10 requests/min for pytrends.
PYTRENDS_MIN_INTERVAL = 6.0  # seconds between requests

_lock = threading.Lock()
_last_pytrends_call = 0.0


def rate_limit_pytrends() -> None:
    """Block until at least ``PYTRENDS_MIN_INTERVAL`` has elapsed since the last call.

    Thread-safe and shared across all market services.
    """
    global _last_pytrends_call
    with _lock:
        now = time.time()
        elapsed = now - _last_pytrends_call
        if elapsed < PYTRENDS_MIN_INTERVAL:
            time.sleep(PYTRENDS_MIN_INTERVAL - elapsed)
        _last_pytrends_call = time.time()
