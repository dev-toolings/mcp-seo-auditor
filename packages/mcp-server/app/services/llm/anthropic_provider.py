"""Anthropic (Claude) LLM provider."""

import json
import logging
import os
from typing import Optional

from app.services.llm.base_provider import BaseLLMProvider, LLMConfig, LLMResponse

logger = logging.getLogger(__name__)


class AnthropicProvider(BaseLLMProvider):
    """LLM provider using the Anthropic API (Claude models)."""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._client = None
        if not self.config.model:
            self.config.model = "claude-sonnet-4-5-20250929"
        if not self.config.api_key:
            self.config.api_key = os.environ.get(
                "ANTHROPIC_API_KEY", os.environ.get("LLM_API_KEY", "")
            )

    def _get_client(self):
        if self._client is None:
            try:
                from anthropic import AsyncAnthropic
            except ImportError:
                raise ImportError(
                    "anthropic package is required. Install with: pip install anthropic"
                )
            self._client = AsyncAnthropic(
                api_key=self.config.api_key,
                timeout=self.config.timeout,
            )
        return self._client

    async def complete(
        self, system_prompt: str, user_prompt: str, max_tokens: Optional[int] = None
    ) -> LLMResponse:
        client = self._get_client()
        response = await self._call_with_retry(
            lambda: client.messages.create(
                model=self.config.model,
                max_tokens=self._resolve_max_tokens(max_tokens),
                temperature=self.config.temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            ),
            label="anthropic.complete",
        )
        content = ""
        for block in response.content:
            if block.type == "text":
                content += block.text
        return LLMResponse(
            content=content,
            model=response.model,
            provider="anthropic",
            usage={
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
            },
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
        tool_definition = {
            "name": "structured_output",
            "description": "Return the analysis as structured JSON.",
            "input_schema": schema
            or {
                "type": "object",
                "properties": {},
                "additionalProperties": True,
            },
        }
        response = await self._call_with_retry(
            lambda: client.messages.create(
                model=self.config.model,
                max_tokens=self._resolve_max_tokens(max_tokens),
                temperature=self.config.temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                tools=[tool_definition],
                tool_choice={"type": "tool", "name": "structured_output"},
            ),
            label="anthropic.complete_json",
        )
        for block in response.content:
            if block.type == "tool_use":
                return block.input
        # Fallback: try to parse text content as JSON
        for block in response.content:
            if block.type == "text":
                return json.loads(block.text)
        return {}

    async def is_available(self) -> bool:
        return bool(self.config.api_key)
