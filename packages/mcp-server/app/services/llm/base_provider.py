"""Base LLM provider interface and shared data classes."""

import asyncio
import logging
import random
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Substrings of exception class names that should NOT be retried (client errors).
_NON_RETRYABLE = (
    "authentication",
    "permission",
    "notfound",
    "badrequest",
    "invalidrequest",
    "unprocessable",
    "importerror",
)


@dataclass
class LLMResponse:
    """Response from an LLM provider."""

    content: str
    model: str
    provider: str
    usage: dict[str, int] = field(default_factory=dict)
    raw_response: Any = None


@dataclass
class LLMConfig:
    """Configuration for an LLM provider."""

    provider: str = ""  # "anthropic", "openai", "ollama"
    model: str = ""
    api_key: str = ""
    base_url: str = ""
    temperature: float = 0.3
    max_tokens: int = 4096
    timeout: int = 120
    max_retries: int = 2
    retry_base_delay: float = 0.8


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, config: LLMConfig):
        self.config = config

    def _resolve_max_tokens(self, max_tokens: Optional[int]) -> int:
        """Per-call max_tokens override, falling back to the configured default.

        Passing this per call avoids mutating the shared config singleton (which races
        across concurrent completions)."""
        return max_tokens if max_tokens is not None else self.config.max_tokens

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        name = type(exc).__name__.lower()
        return not any(k in name for k in _NON_RETRYABLE)

    async def _call_with_retry(self, factory: Callable[[], Awaitable], label: str = "LLM call"):
        """Await ``factory()`` with exponential backoff + jitter on transient errors.

        ``factory`` must return a fresh awaitable each call (coroutines can't be re-awaited).
        """
        last_exc: Optional[Exception] = None
        for attempt in range(self.config.max_retries + 1):
            try:
                return await factory()
            except Exception as exc:  # noqa: BLE001 — re-raised below
                last_exc = exc
                if attempt >= self.config.max_retries or not self._is_retryable(exc):
                    raise
                delay = self.config.retry_base_delay * (2**attempt) + random.uniform(0, 0.4)
                logger.warning(
                    "%s failed (attempt %d/%d), retrying in %.1fs: %s",
                    label,
                    attempt + 1,
                    self.config.max_retries + 1,
                    delay,
                    exc,
                )
                await asyncio.sleep(delay)
        assert last_exc is not None
        raise last_exc

    @abstractmethod
    async def complete(
        self, system_prompt: str, user_prompt: str, max_tokens: Optional[int] = None
    ) -> LLMResponse:
        """Generate a text completion."""
        ...

    @abstractmethod
    async def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: Optional[dict] = None,
        max_tokens: Optional[int] = None,
    ) -> dict:
        """Generate a structured JSON response."""
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if the provider is configured and reachable."""
        ...
