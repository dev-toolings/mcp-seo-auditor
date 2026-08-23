"""DataForSEO API client — optional enrichment for keyword volumes and SERP data."""

import hashlib
import json
import logging
from base64 import b64encode
from typing import Optional

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
    wait_random,
)

from app.core.config import settings
from app.services.dataforseo.resilience import RateLimiter, TTLCache

logger = logging.getLogger(__name__)

# Transient HTTP statuses worth retrying. Every other 4xx is a client error:
# retrying it cannot succeed and DataForSEO bills each attempt, so we don't.
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


def _is_retryable(exc: BaseException) -> bool:
    """Return True for transient DataForSEO errors (429, 5xx, network/timeout)."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRYABLE_STATUS
    return isinstance(exc, httpx.RequestError)


class DataForSEOClient:
    """Optional DataForSEO API client. All methods return empty results if not configured."""

    def __init__(
        self,
        login: str = "",
        password: str = "",
        base_url: str = "https://api.dataforseo.com",
        timeout: Optional[int] = None,
        cache_ttl: Optional[int] = None,
    ):
        self.login = login
        self.password = password
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout if timeout is not None else settings.DATAFORSEO_TIMEOUT
        self._rate_limiter = RateLimiter(
            rpm=settings.DATAFORSEO_REQUESTS_PER_MINUTE,
            max_concurrent=settings.DATAFORSEO_MAX_CONCURRENT,
        )
        self._cache = TTLCache(
            ttl=cache_ttl if cache_ttl is not None else settings.DATAFORSEO_CACHE_TTL,
            max_entries=settings.DATAFORSEO_CACHE_MAX_ENTRIES,
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.login and self.password)

    def _get_auth_header(self) -> str:
        creds = b64encode(f"{self.login}:{self.password}".encode()).decode()
        return f"Basic {creds}"

    @staticmethod
    def _cache_key(endpoint: str, data: list[dict]) -> str:
        payload = json.dumps(data, sort_keys=True, default=str)
        return f"{endpoint}:{hashlib.sha256(payload.encode()).hexdigest()}"

    async def _post(self, url: str, data: list[dict], headers: dict) -> dict:
        """Single billed POST, retried only on transient failures."""

        @retry(
            stop=stop_after_attempt(settings.DATAFORSEO_MAX_RETRIES),
            # Exponential backoff plus jitter, so concurrent callers hitting the
            # same 429 don't retry in lockstep.
            wait=wait_exponential(multiplier=1, min=2, max=30) + wait_random(0, 1),
            retry=retry_if_exception(_is_retryable),
            reraise=True,
        )
        async def _attempt() -> dict:
            async with self._rate_limiter.slot():
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(url, json=data, headers=headers)
                    response.raise_for_status()
                    return response.json()

        return await _attempt()

    async def _request(self, endpoint: str, data: list[dict]) -> dict:
        """Make authenticated POST request to DataForSEO API."""
        if not self.is_configured:
            return {
                "error": "DataForSEO not configured. Set DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD."
            }

        cache_key = self._cache_key(endpoint, data)
        cached = self._cache.get(cache_key)
        if cached is not None:
            logger.debug("DataForSEO cache hit: %s", endpoint)
            return cached

        url = f"{self.base_url}{endpoint}"
        headers = {
            "Authorization": self._get_auth_header(),
            "Content-Type": "application/json",
        }

        try:
            body = await self._post(url, data, headers)

            # DataForSEO wraps results in tasks[0].result
            tasks = body.get("tasks", [])
            if not tasks:
                return {"error": "No tasks in DataForSEO response", "raw": body}

            task = tasks[0]
            status_code = task.get("status_code", 0)
            if status_code != 20000:
                msg = task.get("status_message", "Unknown error")
                return {"error": f"DataForSEO task error: {msg}", "status_code": status_code}

            result = {"result": task.get("result", []), "source": "dataforseo"}
            # Only successful responses are cached; errors must stay retryable.
            self._cache.set(cache_key, result)
            return result

        except httpx.TimeoutException:
            logger.warning("DataForSEO request timed out: %s", endpoint)
            return {"error": f"DataForSEO request timed out: {endpoint}"}
        except httpx.HTTPStatusError as exc:
            logger.warning("DataForSEO HTTP error %d: %s", exc.response.status_code, endpoint)
            return {"error": f"DataForSEO HTTP {exc.response.status_code}"}
        except Exception as exc:
            logger.warning("DataForSEO request failed: %s", exc)
            return {"error": f"DataForSEO request failed: {exc}"}

    async def get_search_volume(
        self,
        keywords: list[str],
        language_code: str = "fr",
        location_code: int = 2250,
    ) -> dict:
        """Get search volume data for keywords.

        Endpoint: /v3/keywords_data/google_ads/search_volume/live
        location_code 2250 = France, 2840 = USA

        Returns: {
            "keywords": [{
                "keyword": str, "search_volume": int,
                "competition": float, "cpc": float, "trend": list
            }, ...],
            "source": "dataforseo"
        }
        """
        if not self.is_configured:
            return {
                "error": "DataForSEO not configured. Set DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD."
            }

        data = [
            {
                "keywords": keywords,
                "language_code": language_code,
                "location_code": location_code,
            }
        ]
        raw = await self._request("/v3/keywords_data/google_ads/search_volume/live", data)
        if "error" in raw:
            return raw

        results = raw.get("result", [])
        keyword_data = []
        for item in results:
            keyword_data.append(
                {
                    "keyword": item.get("keyword", ""),
                    "search_volume": item.get("search_volume", 0),
                    "competition": item.get("competition", 0.0),
                    "cpc": item.get("cpc", 0.0),
                    "trend": [
                        m.get("search_volume", 0) for m in (item.get("monthly_searches") or [])
                    ],
                }
            )

        return {"keywords": keyword_data, "source": "dataforseo"}

    async def get_serp_results(
        self,
        keyword: str,
        language_code: str = "fr",
        location_code: int = 2250,
        depth: int = 10,
    ) -> dict:
        """Get live SERP results for a keyword.

        Endpoint: /v3/serp/google/organic/live

        Returns: {
            "keyword": str,
            "results": [{
                "position": int, "url": str, "title": str,
                "description": str, "domain": str
            }, ...],
            "serp_features": [str, ...],
            "source": "dataforseo"
        }
        """
        if not self.is_configured:
            return {
                "error": "DataForSEO not configured. Set DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD."
            }

        data = [
            {
                "keyword": keyword,
                "language_code": language_code,
                "location_code": location_code,
                "depth": depth,
            }
        ]
        raw = await self._request("/v3/serp/google/organic/live", data)
        if "error" in raw:
            return raw

        results_list = raw.get("result", [])
        organic_results = []
        serp_features = []

        for result_block in results_list:
            items = result_block.get("items", []) if isinstance(result_block, dict) else []
            for item in items:
                item_type = item.get("type", "")
                if item_type == "organic":
                    organic_results.append(
                        {
                            "position": item.get("rank_group", 0),
                            "url": item.get("url", ""),
                            "title": item.get("title", ""),
                            "description": item.get("description", ""),
                            "domain": item.get("domain", ""),
                        }
                    )
                elif item_type not in ("organic", ""):
                    if item_type not in serp_features:
                        serp_features.append(item_type)

        return {
            "keyword": keyword,
            "results": organic_results,
            "serp_features": serp_features,
            "source": "dataforseo",
        }

    async def get_keyword_suggestions(
        self,
        seed_keyword: str,
        language_code: str = "fr",
        location_code: int = 2250,
        limit: int = 50,
    ) -> dict:
        """Get keyword suggestions from a seed keyword.

        Endpoint: /v3/dataforseo_labs/google/keyword_suggestions/live

        Returns: {
            "seed": str,
            "suggestions": [{
                "keyword": str, "search_volume": int,
                "competition": float, "difficulty": int
            }, ...],
            "source": "dataforseo"
        }
        """
        if not self.is_configured:
            return {
                "error": "DataForSEO not configured. Set DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD."
            }

        data = [
            {
                "keyword": seed_keyword,
                "language_code": language_code,
                "location_code": location_code,
                "limit": limit,
            }
        ]
        raw = await self._request("/v3/dataforseo_labs/google/keyword_suggestions/live", data)
        if "error" in raw:
            return raw

        results = raw.get("result", [])
        suggestions = []
        for result_block in results:
            items = result_block.get("items", []) if isinstance(result_block, dict) else []
            for item in items:
                kw_data = item.get("keyword_data", item)
                ki = kw_data.get("keyword_info", {})
                suggestions.append(
                    {
                        "keyword": kw_data.get("keyword", ""),
                        "search_volume": ki.get("search_volume", 0),
                        "competition": ki.get("competition", 0.0),
                        "difficulty": kw_data.get("keyword_properties", {}).get(
                            "keyword_difficulty", 0
                        ),
                    }
                )

        return {"seed": seed_keyword, "suggestions": suggestions, "source": "dataforseo"}
