"""OpenAI-compatible LLM provider (OpenAI, Azure, Together.ai, etc.)."""

import json
import logging
import os
from typing import Optional

from app.services.llm.base_provider import BaseLLMProvider, LLMConfig, LLMResponse

logger = logging.getLogger(__name__)


class OpenAIProvider(BaseLLMProvider):
    """LLM provider using the OpenAI-compatible API."""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._client = None
        if not self.config.model:
            self.config.model = "gpt-4o"
        if not self.config.api_key:
            self.config.api_key = os.environ.get(
                "OPENAI_API_KEY", os.environ.get("LLM_API_KEY", "")
            )

    def _get_client(self):
        if self._client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError:
                raise ImportError("openai package is required. Install with: pip install openai")
            kwargs = {"api_key": self.config.api_key, "timeout": self.config.timeout}
            if self.config.base_url:
                kwargs["base_url"] = self.config.base_url
            self._client = AsyncOpenAI(**kwargs)
        return self._client

    async def complete(
        self, system_prompt: str, user_prompt: str, max_tokens: Optional[int] = None
    ) -> LLMResponse:
        client = self._get_client()
        response = await self._call_with_retry(
            lambda: client.chat.completions.create(
                model=self.config.model,
                temperature=self.config.temperature,
                max_completion_tokens=self._resolve_max_tokens(max_tokens),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            ),
            label="openai.complete",
        )
        choice = response.choices[0]
        usage = {}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }
        return LLMResponse(
            content=choice.message.content or "",
            model=response.model,
            provider="openai",
            usage=usage,
            raw_response=response,
        )

    async def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: Optional[dict] = None,
        max_tokens: Optional[int] = None,
    ) -> dict:
        client = self._get_client()
        json_instruction = "\n\nYou MUST respond with valid JSON only, no other text."
        response = await self._call_with_retry(
            lambda: client.chat.completions.create(
                model=self.config.model,
                temperature=self.config.temperature,
                max_completion_tokens=self._resolve_max_tokens(max_tokens),
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt + json_instruction},
                    {"role": "user", "content": user_prompt},
                ],
            ),
            label="openai.complete_json",
        )
        content = response.choices[0].message.content or "{}"
        return json.loads(content)

    async def is_available(self) -> bool:
        return bool(self.config.api_key)
