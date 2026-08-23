"""Tests for BaseLLMProvider retry + per-call max_tokens helpers."""

import pytest

from app.services.llm.base_provider import BaseLLMProvider, LLMConfig


class _Dummy(BaseLLMProvider):
    async def complete(self, *a, **k):  # pragma: no cover - not used
        ...

    async def complete_json(self, *a, **k):  # pragma: no cover - not used
        ...

    async def is_available(self):  # pragma: no cover - not used
        return True


class _RateLimitError(Exception):
    pass


class _AuthenticationError(Exception):
    pass


@pytest.fixture
def provider():
    return _Dummy(LLMConfig(max_retries=2, retry_base_delay=0.0))


@pytest.mark.asyncio
async def test_succeeds_first_try(provider):
    calls = {"n": 0}

    async def factory():
        calls["n"] += 1
        return "ok"

    assert await provider._call_with_retry(factory) == "ok"
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_retries_then_succeeds(provider):
    calls = {"n": 0}

    async def factory():
        calls["n"] += 1
        if calls["n"] < 3:
            raise _RateLimitError("429")
        return "recovered"

    assert await provider._call_with_retry(factory) == "recovered"
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_exhausts_retries(provider):
    calls = {"n": 0}

    async def factory():
        calls["n"] += 1
        raise _RateLimitError("429")

    with pytest.raises(_RateLimitError):
        await provider._call_with_retry(factory)
    assert calls["n"] == 3  # initial + 2 retries


@pytest.mark.asyncio
async def test_non_retryable_raises_immediately(provider):
    calls = {"n": 0}

    async def factory():
        calls["n"] += 1
        raise _AuthenticationError("bad key")

    with pytest.raises(_AuthenticationError):
        await provider._call_with_retry(factory)
    assert calls["n"] == 1


def test_resolve_max_tokens(provider):
    assert provider._resolve_max_tokens(None) == provider.config.max_tokens
    assert provider._resolve_max_tokens(16000) == 16000
