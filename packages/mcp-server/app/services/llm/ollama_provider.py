"""Ollama local LLM provider."""

import json
import logging
from typing import Optional

import httpx

from app.services.llm.base_provider import BaseLLMProvider, LLMConfig, LLMResponse

logger = logging.getLogger(__name__)

DEFAULT_OLLAMA_URL = "http://localhost:11434"


class OllamaProvider(BaseLLMProvider):
    """LLM provider using a local Ollama instance."""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        if not self.config.base_url:
            self.config.base_url = DEFAULT_OLLAMA_URL
        if not self.config.model:
            self.config.model = "llama3.1"

    async def complete(
        self, system_prompt: str, user_prompt: str, max_tokens: Optional[int] = None
    ) -> LLMResponse:
        async with httpx.AsyncClient(timeout=self.config.timeout) as client:

            async def _do():
                resp = await client.post(
                    f"{self.config.base_url}/api/chat",
                    json={
                        "model": self.config.model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "stream": False,
                        "options": {
                            "temperature": self.config.temperature,
                            "num_predict": self._resolve_max_tokens(max_tokens),
                        },
                    },
                )
                resp.raise_for_status()
                return resp

            response = await self._call_with_retry(_do, label="ollama.complete")
            data = response.json()

        message = data.get("message", {})
        usage = {}
        if "eval_count" in data:
            usage = {
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
                "total_tokens": data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
            }
        return LLMResponse(
            content=message.get("content", ""),
            model=self.config.model,
            provider="ollama",
            usage=usage,
            raw_response=data,
        )

    async def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: Optional[dict] = None,
        max_tokens: Optional[int] = None,
    ) -> dict:
        json_instruction = (
            "\n\nYou MUST respond with valid JSON only, no markdown, "
            "no explanation, no code blocks. Only raw JSON."
        )
        async with httpx.AsyncClient(timeout=self.config.timeout) as client:

            async def _do():
                resp = await client.post(
                    f"{self.config.base_url}/api/chat",
                    json={
                        "model": self.config.model,
                        "messages": [
                            {
                                "role": "system",
                                "content": system_prompt + json_instruction,
                            },
                            {"role": "user", "content": user_prompt},
                        ],
                        "stream": False,
                        "format": "json",
                        "options": {
                            "temperature": self.config.temperature,
                            "num_predict": self._resolve_max_tokens(max_tokens),
                        },
                    },
                )
                resp.raise_for_status()
                return resp

            response = await self._call_with_retry(_do, label="ollama.complete_json")
            data = response.json()

        content = data.get("message", {}).get("content", "{}")
        return json.loads(content)

    async def is_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.config.base_url}/api/tags")
                return response.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException):
            return False
