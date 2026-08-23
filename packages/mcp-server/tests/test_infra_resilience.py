"""Tests for DataForSEO resilience (retry / rate limit / cache) and structured logging.

Every network call is mocked — no request ever reaches DataForSEO, which is a
billed API.
"""

import asyncio
import json
import logging
from unittest.mock import patch

import httpx
import pytest

from app.core.logging import (
    CorrelationIdFilter,
    JsonFormatter,
    correlation_scope,
    get_correlation_id,
    new_correlation_id,
    setup_logging,
)
from app.services.dataforseo.client import DataForSEOClient, _is_retryable
from app.services.dataforseo.resilience import RateLimiter, TTLCache

# ─── Helpers ─────────────────────────────────────────


def _ok_body() -> dict:
    """A minimal successful DataForSEO envelope."""
    return {"tasks": [{"status_code": 20000, "result": [{"keyword": "seo"}]}]}


def _response(status: int, body: dict | None = None) -> httpx.Response:
    return httpx.Response(
        status_code=status,
        json=body if body is not None else {},
        request=httpx.Request("POST", "https://api.dataforseo.com/v3/test"),
    )


class _FakeTransport:
    """Records POST calls and replays a scripted sequence of outcomes."""

    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.calls = 0

    async def post(self, url, json=None, headers=None):
        self.calls += 1
        outcome = self._outcomes[min(self.calls - 1, len(self._outcomes) - 1)]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _client(transport, **kwargs) -> DataForSEOClient:
    """Build a configured client whose httpx.AsyncClient is the fake transport."""
    client = DataForSEOClient(login="user", password="pass", **kwargs)

    class _CtxClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return transport

        async def __aexit__(self, *exc):
            return False

    patcher = patch("app.services.dataforseo.client.httpx.AsyncClient", _CtxClient)
    patcher.start()
    client._patcher = patcher  # type: ignore[attr-defined]
    return client


@pytest.fixture(autouse=True)
def _no_backoff_sleep():
    """Keep tenacity's exponential backoff from actually sleeping."""
    with patch("tenacity.nap.time.sleep", lambda _s: None):
        yield


# ─── Retry classification ────────────────────────────


class TestRetryPredicate:
    @pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
    def test_transient_statuses_are_retryable(self, status):
        exc = httpx.HTTPStatusError("boom", request=None, response=_response(status))
        assert _is_retryable(exc) is True

    @pytest.mark.parametrize("status", [400, 401, 402, 403, 404, 422])
    def test_client_errors_are_not_retryable(self, status):
        """Retrying a non-429 4xx cannot succeed and gets billed again."""
        exc = httpx.HTTPStatusError("boom", request=None, response=_response(status))
        assert _is_retryable(exc) is False

    def test_network_errors_are_retryable(self):
        assert _is_retryable(httpx.ConnectError("no route")) is True
        assert _is_retryable(httpx.ReadTimeout("slow")) is True

    def test_unrelated_exception_is_not_retryable(self):
        assert _is_retryable(ValueError("nope")) is False


# ─── Retry behaviour ─────────────────────────────────


class TestRetry:
    @pytest.mark.asyncio
    async def test_429_is_retried_then_succeeds(self):
        transport = _FakeTransport([_response(429), _response(200, _ok_body())])
        client = _client(transport, cache_ttl=0)
        try:
            result = await client._request("/v3/test", [{"q": "seo"}])
        finally:
            client._patcher.stop()

        assert transport.calls == 2, "the 429 should have been replayed once"
        assert result["source"] == "dataforseo"
        assert result["result"] == [{"keyword": "seo"}]

    @pytest.mark.asyncio
    async def test_400_is_not_retried(self):
        """A non-429 4xx must cost exactly one billed call."""
        transport = _FakeTransport([_response(400)])
        client = _client(transport, cache_ttl=0)
        try:
            result = await client._request("/v3/test", [{"q": "seo"}])
        finally:
            client._patcher.stop()

        assert transport.calls == 1, "a 400 must never be retried — it is billed"
        assert "error" in result
        assert "400" in result["error"]

    @pytest.mark.asyncio
    async def test_401_is_not_retried(self):
        transport = _FakeTransport([_response(401)])
        client = _client(transport, cache_ttl=0)
        try:
            result = await client._request("/v3/test", [{"q": "seo"}])
        finally:
            client._patcher.stop()

        assert transport.calls == 1
        assert "error" in result

    @pytest.mark.asyncio
    async def test_timeout_is_retried_then_succeeds(self):
        transport = _FakeTransport([httpx.ReadTimeout("slow"), _response(200, _ok_body())])
        client = _client(transport, cache_ttl=0)
        try:
            result = await client._request("/v3/test", [{"q": "seo"}])
        finally:
            client._patcher.stop()

        assert transport.calls == 2
        assert result["source"] == "dataforseo"

    @pytest.mark.asyncio
    async def test_retries_are_bounded(self):
        """Persistent 5xx stops at the configured attempt cap, then degrades."""
        transport = _FakeTransport([_response(503)])
        client = _client(transport, cache_ttl=0)
        try:
            result = await client._request("/v3/test", [{"q": "seo"}])
        finally:
            client._patcher.stop()

        assert transport.calls == 3
        assert "error" in result

    @pytest.mark.asyncio
    async def test_unconfigured_client_never_calls_network(self):
        transport = _FakeTransport([_response(200, _ok_body())])
        client = DataForSEOClient()  # no credentials
        result = await client._request("/v3/test", [{"q": "seo"}])

        assert transport.calls == 0
        assert "not configured" in result["error"].lower()


# ─── TTL cache ───────────────────────────────────────


class TestResponseCache:
    @pytest.mark.asyncio
    async def test_identical_request_is_served_from_cache(self):
        transport = _FakeTransport([_response(200, _ok_body())])
        client = _client(transport, cache_ttl=60)
        try:
            first = await client._request("/v3/test", [{"q": "seo"}])
            second = await client._request("/v3/test", [{"q": "seo"}])
        finally:
            client._patcher.stop()

        assert transport.calls == 1, "the second identical call must not be billed"
        assert first == second

    @pytest.mark.asyncio
    async def test_different_payload_is_not_cached_together(self):
        transport = _FakeTransport([_response(200, _ok_body())])
        client = _client(transport, cache_ttl=60)
        try:
            await client._request("/v3/test", [{"q": "seo"}])
            await client._request("/v3/test", [{"q": "sea"}])
        finally:
            client._patcher.stop()

        assert transport.calls == 2

    @pytest.mark.asyncio
    async def test_errors_are_not_cached(self):
        transport = _FakeTransport([_response(400), _response(200, _ok_body())])
        client = _client(transport, cache_ttl=60)
        try:
            first = await client._request("/v3/test", [{"q": "seo"}])
            second = await client._request("/v3/test", [{"q": "seo"}])
        finally:
            client._patcher.stop()

        assert "error" in first
        assert second["source"] == "dataforseo"
        assert transport.calls == 2

    @pytest.mark.asyncio
    async def test_ttl_zero_disables_cache(self):
        transport = _FakeTransport([_response(200, _ok_body())])
        client = _client(transport, cache_ttl=0)
        try:
            await client._request("/v3/test", [{"q": "seo"}])
            await client._request("/v3/test", [{"q": "seo"}])
        finally:
            client._patcher.stop()

        assert transport.calls == 2

    def test_entry_expires_after_ttl(self):
        cache = TTLCache(ttl=60)
        cache.set("k", {"v": 1})
        assert cache.get("k") == {"v": 1}

        with patch("app.services.dataforseo.resilience.time.monotonic", return_value=1e9):
            assert cache.get("k") is None

    def test_lru_eviction_bounds_memory(self):
        cache = TTLCache(ttl=60, max_entries=2)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)

        assert cache.get("a") is None  # oldest evicted
        assert cache.get("b") == 2
        assert cache.get("c") == 3

    def test_disabled_cache_stores_nothing(self):
        cache = TTLCache(ttl=0)
        cache.set("k", 1)
        assert cache.enabled is False
        assert cache.get("k") is None


# ─── Rate limiter ────────────────────────────────────


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_concurrency_is_bounded(self):
        limiter = RateLimiter(rpm=1000, max_concurrent=2)
        in_flight = 0
        peak = 0

        async def worker():
            nonlocal in_flight, peak
            async with limiter.slot():
                in_flight += 1
                peak = max(peak, in_flight)
                await asyncio.sleep(0.01)
                in_flight -= 1

        await asyncio.gather(*(worker() for _ in range(10)))

        assert peak <= 2, f"concurrency ceiling breached: {peak} simultaneous calls"

    @pytest.mark.asyncio
    async def test_slot_is_released_on_exception(self):
        limiter = RateLimiter(rpm=1000, max_concurrent=1)

        with pytest.raises(RuntimeError):
            async with limiter.slot():
                raise RuntimeError("boom")

        # A leaked semaphore would deadlock this second acquisition.
        async with limiter.slot():
            pass

    @pytest.mark.asyncio
    async def test_window_sleeps_when_rpm_exceeded(self):
        limiter = RateLimiter(rpm=2, max_concurrent=5)
        slept: list[float] = []

        async def fake_sleep(duration):
            slept.append(duration)

        with patch("app.services.dataforseo.resilience.asyncio.sleep", fake_sleep):
            for _ in range(3):
                async with limiter.slot():
                    pass

        assert slept, "third call within the same minute should have been throttled"

    @pytest.mark.asyncio
    async def test_client_bounds_concurrent_billed_calls(self):
        """End-to-end: parallel client calls never exceed the concurrency cap."""
        limiter_state = {"in_flight": 0, "peak": 0}

        class _CountingTransport:
            calls = 0

            async def post(self, url, json=None, headers=None):
                _CountingTransport.calls += 1
                limiter_state["in_flight"] += 1
                limiter_state["peak"] = max(limiter_state["peak"], limiter_state["in_flight"])
                await asyncio.sleep(0.01)
                limiter_state["in_flight"] -= 1
                return _response(200, _ok_body())

        transport = _CountingTransport()
        client = _client(transport, cache_ttl=0)
        with patch.object(client, "_rate_limiter", RateLimiter(rpm=1000, max_concurrent=2)):
            try:
                await asyncio.gather(
                    *(client._request("/v3/test", [{"q": f"kw{i}"}]) for i in range(8))
                )
            finally:
                client._patcher.stop()

        assert limiter_state["peak"] <= 2


# ─── Structured logging + correlation ID ─────────────


class TestCorrelationId:
    def test_unset_by_default(self):
        assert get_correlation_id() == ""

    def test_scope_binds_and_restores(self):
        assert get_correlation_id() == ""
        with correlation_scope("abc123"):
            assert get_correlation_id() == "abc123"
        assert get_correlation_id() == ""

    def test_scope_generates_an_id(self):
        with correlation_scope() as cid:
            assert cid
            assert get_correlation_id() == cid

    def test_nested_scopes_restore_outer(self):
        with correlation_scope("outer"):
            with correlation_scope("inner"):
                assert get_correlation_id() == "inner"
            assert get_correlation_id() == "outer"

    def test_ids_are_unique(self):
        assert new_correlation_id() != new_correlation_id()

    @pytest.mark.asyncio
    async def test_propagates_across_await_boundaries(self):
        """A nested async service call sees the caller's correlation ID."""
        seen = []

        async def deep_service_call():
            await asyncio.sleep(0)
            seen.append(get_correlation_id())

        async def audit():
            with correlation_scope("audit-42"):
                await deep_service_call()

        await audit()
        assert seen == ["audit-42"]

    @pytest.mark.asyncio
    async def test_concurrent_tasks_keep_separate_ids(self):
        results = {}

        async def run(name):
            with correlation_scope(name):
                await asyncio.sleep(0.01)
                results[name] = get_correlation_id()

        await asyncio.gather(run("a"), run("b"), run("c"))
        assert results == {"a": "a", "b": "b", "c": "c"}


class TestJsonLogging:
    def _render(self, record: logging.LogRecord) -> dict:
        CorrelationIdFilter().filter(record)
        return json.loads(JsonFormatter().format(record))

    def _record(self, msg="hello", **extra) -> logging.LogRecord:
        record = logging.LogRecord(
            name="app.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg=msg,
            args=(),
            exc_info=None,
        )
        for key, value in extra.items():
            setattr(record, key, value)
        return record

    def test_output_is_json_with_core_fields(self):
        payload = self._render(self._record())

        assert payload["level"] == "INFO"
        assert payload["logger"] == "app.test"
        assert payload["message"] == "hello"
        assert "timestamp" in payload

    def test_correlation_id_lands_in_log_output(self):
        with correlation_scope("trace-me"):
            payload = self._render(self._record())

        assert payload["correlation_id"] == "trace-me"

    def test_no_correlation_id_field_when_unset(self):
        payload = self._render(self._record())
        assert "correlation_id" not in payload

    def test_extra_fields_are_serialized(self):
        payload = self._render(self._record(url="https://example.com", pages=12))

        assert payload["url"] == "https://example.com"
        assert payload["pages"] == 12

    def test_non_serializable_extra_is_repr_ed(self):
        payload = self._render(self._record(obj=object()))
        assert isinstance(payload["obj"], str)

    def test_exception_is_captured(self):
        try:
            raise ValueError("kaboom")
        except ValueError:
            import sys

            record = self._record("failed")
            record.exc_info = sys.exc_info()
            payload = self._render(record)

        assert "ValueError: kaboom" in payload["exception"]

    def test_end_to_end_emits_json_line_with_correlation_id(self, capsys):
        setup_logging(level="INFO", json_output=True)
        try:
            with correlation_scope("e2e-1"):
                logging.getLogger("app.audit").info("audit done", extra={"score": 87})
            captured = capsys.readouterr().err.strip().splitlines()[-1]
            payload = json.loads(captured)
        finally:
            logging.getLogger().handlers.clear()

        assert payload["message"] == "audit done"
        assert payload["correlation_id"] == "e2e-1"
        assert payload["score"] == 87

    def test_setup_logging_is_idempotent(self):
        try:
            setup_logging(level="INFO", json_output=True)
            setup_logging(level="DEBUG", json_output=True)
            root = logging.getLogger()

            assert len(root.handlers) == 1
            assert root.level == logging.DEBUG
        finally:
            logging.getLogger().handlers.clear()

    def test_text_output_mode(self, capsys):
        setup_logging(level="INFO", json_output=False)
        try:
            with correlation_scope("text-1"):
                logging.getLogger("app.audit").info("plain line")
            err = capsys.readouterr().err
        finally:
            logging.getLogger().handlers.clear()

        assert "plain line" in err
        assert "text-1" in err
