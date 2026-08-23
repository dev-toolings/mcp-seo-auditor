"""Factory for creating LLM provider instances."""

import logging
from typing import Optional

from app.services.llm.base_provider import BaseLLMProvider, LLMConfig

logger = logging.getLogger(__name__)


class LLMProviderFactory:
    """Factory for creating LLM providers from configuration."""

    _registry: dict[str, type[BaseLLMProvider]] = {}

    @classmethod
    def register(cls, name: str, provider_class: type[BaseLLMProvider]):
        """Register a provider class by name."""
        cls._registry[name] = provider_class

    @classmethod
    def _ensure_registered(cls):
        """Lazy-register built-in providers."""
        if cls._registry:
            return
        from app.services.llm.anthropic_provider import AnthropicProvider
        from app.services.llm.ollama_provider import OllamaProvider
        from app.services.llm.openai_provider import OpenAIProvider

        cls._registry["anthropic"] = AnthropicProvider
        cls._registry["openai"] = OpenAIProvider
        cls._registry["ollama"] = OllamaProvider

    @classmethod
    def create(cls, config: LLMConfig) -> BaseLLMProvider:
        """Create a provider instance from a config."""
        cls._ensure_registered()
        provider_name = config.provider.lower()
        if provider_name not in cls._registry:
            raise ValueError(
                f"Unknown LLM provider: {provider_name}. Available: {list(cls._registry.keys())}"
            )
        return cls._registry[provider_name](config)

    @classmethod
    def create_from_settings(cls) -> Optional[BaseLLMProvider]:
        """Create a provider from application settings (env vars)."""
        from app.core.config import settings

        if not settings.LLM_PROVIDER:
            return None

        config = LLMConfig(
            provider=settings.LLM_PROVIDER,
            model=settings.LLM_MODEL,
            api_key=settings.LLM_API_KEY.get_secret_value(),
            base_url=settings.LLM_BASE_URL
            or (settings.OLLAMA_BASE_URL if settings.LLM_PROVIDER == "ollama" else ""),
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS,
        )
        try:
            return cls.create(config)
        except (ValueError, ImportError) as e:
            logger.warning("Failed to create LLM provider: %s", e)
            return None

    @classmethod
    async def create_best_available(cls) -> Optional[BaseLLMProvider]:
        """Try providers in priority order: anthropic > openai > ollama."""
        cls._ensure_registered()
        priority = ["anthropic", "openai", "ollama"]
        for name in priority:
            provider_class = cls._registry.get(name)
            if provider_class is None:
                continue
            config = LLMConfig(provider=name)
            try:
                provider = provider_class(config)
                if await provider.is_available():
                    logger.info("Auto-selected LLM provider: %s", name)
                    return provider
            except Exception:
                continue
        return None
