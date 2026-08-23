"""Core Web Vitals service via Google PageSpeed Insights API v5."""

import logging
from typing import Any, Optional

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.core.config import settings

logger = logging.getLogger(__name__)

PAGESPEED_API_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


def _is_retryable_status(exc: BaseException) -> bool:
    """Return True for retryable HTTP errors (429, 5xx) and network errors."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (429, 500, 502, 503, 504)
    return isinstance(exc, httpx.RequestError)


class CoreWebVitalsService:
    """Fetch Core Web Vitals and performance data from PageSpeed Insights API."""

    def __init__(self, api_key: Optional[str] = None, timeout: int = 60):
        self.api_key = api_key or settings.PAGESPEED_API_KEY.get_secret_value()
        self.timeout = timeout

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception(_is_retryable_status),
        reraise=True,
    )
    async def analyze(
        self,
        url: str,
        strategy: str = "mobile",
    ) -> dict[str, Any]:
        """Analyze a URL with PageSpeed Insights.

        Args:
            url: URL to analyze.
            strategy: "mobile" or "desktop".

        Returns:
            Dict with CWV metrics, score, opportunities, and diagnostics.
        """
        params: dict[str, str] = {
            "url": url,
            "strategy": strategy,
            "category": "performance",
        }
        if self.api_key:
            params["key"] = self.api_key

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(PAGESPEED_API_URL, params=params)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as e:
            return {
                "url": url,
                "error": f"PageSpeed API error: HTTP {e.response.status_code}",
                "detail": e.response.text[:500],
            }
        except httpx.RequestError as e:
            return {
                "url": url,
                "error": f"Request error: {str(e)}",
            }

        return self._parse_response(url, strategy, data)

    def _parse_response(self, url: str, strategy: str, data: dict) -> dict[str, Any]:
        """Parse PageSpeed Insights API response into structured report."""
        lighthouse = data.get("lighthouseResult", {})
        categories = lighthouse.get("categories", {})
        audits = lighthouse.get("audits", {})

        # Performance score
        perf = categories.get("performance", {})
        score = perf.get("score")
        performance_score = round(score * 100) if score is not None else None

        # Core Web Vitals metrics
        metrics = {}
        metric_keys = {
            "largest-contentful-paint": "LCP",
            "interaction-to-next-paint": "INP",
            "cumulative-layout-shift": "CLS",
            "first-contentful-paint": "FCP",
            "server-response-time": "TTFB",
            "speed-index": "Speed Index",
        }

        for audit_key, label in metric_keys.items():
            audit = audits.get(audit_key, {})
            if audit:
                metrics[label] = {
                    "value": audit.get("numericValue"),
                    "display": audit.get("displayValue", ""),
                    "score": audit.get("score"),
                }

        # CrUX field data
        field_data = {}
        loading_experience = data.get("loadingExperience", {})
        crux_metrics = loading_experience.get("metrics", {})
        for metric_name, metric_data in crux_metrics.items():
            field_data[metric_name] = {
                "percentile": metric_data.get("percentile"),
                "category": metric_data.get("category"),
            }

        # Opportunities
        opportunities = []
        for audit_id, audit in audits.items():
            if audit.get("details", {}).get("type") == "opportunity":
                savings = audit.get("details", {}).get("overallSavingsMs")
                if savings and savings > 0:
                    opportunities.append(
                        {
                            "audit": audit_id,
                            "title": audit.get("title", ""),
                            "description": audit.get("description", "")[:200],
                            "savings_ms": round(savings),
                            "score": audit.get("score"),
                        }
                    )

        opportunities.sort(key=lambda x: x.get("savings_ms", 0), reverse=True)

        # Diagnostics
        diagnostics = []
        for audit_id, audit in audits.items():
            if (
                audit.get("details", {}).get("type") in ("table", "list")
                and audit.get("score") is not None
                and audit.get("score", 1) < 0.9
            ):
                diagnostics.append(
                    {
                        "audit": audit_id,
                        "title": audit.get("title", ""),
                        "description": audit.get("description", "")[:200],
                        "score": audit.get("score"),
                    }
                )

        return {
            "url": url,
            "strategy": strategy,
            "performance_score": performance_score,
            "metrics": metrics,
            "field_data": field_data if field_data else None,
            "opportunities": opportunities[:10],
            "diagnostics": diagnostics[:10],
        }

    async def analyze_multiple(
        self,
        urls: list[str],
        strategy: str = "mobile",
    ) -> list[dict[str, Any]]:
        """Analyze multiple URLs sequentially (API rate limits apply)."""
        results = []
        for url in urls:
            result = await self.analyze(url, strategy=strategy)
            results.append(result)
        return results
