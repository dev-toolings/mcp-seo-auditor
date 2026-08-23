"""GitHub analyzer service for detecting open-source alternatives."""

import logging
import os
from datetime import datetime, timedelta, timezone

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


def _is_github_retryable(exc: BaseException) -> bool:
    """Return True for retryable GitHub API errors (403 rate limit, 429, 5xx)."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (403, 429, 500, 502, 503, 504)
    return isinstance(exc, httpx.RequestError)


GITHUB_API_BASE = "https://api.github.com"


class GitHubAnalyzerService:
    """Analyze GitHub for open-source alternatives to a SaaS concept."""

    def __init__(self):
        self.token = os.getenv("GITHUB_TOKEN")

    @property
    def _headers(self) -> dict:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "seo-auditor-market-intelligence",
        }
        if self.token:
            headers["Authorization"] = f"token {self.token}"
        return headers

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception(_is_github_retryable),
        reraise=True,
    )
    async def _fetch_repos(self, concept: str, max_repos: int) -> dict:
        """Fetch repositories from GitHub API with retry on transient errors."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{GITHUB_API_BASE}/search/repositories",
                params={
                    "q": concept,
                    "sort": "stars",
                    "order": "desc",
                    "per_page": min(max_repos, 100),
                },
                headers=self._headers,
            )
            response.raise_for_status()
            return response.json()

    async def analyze(self, concept: str, max_repos: int = 30) -> dict:
        """Search GitHub for repos related to a concept.

        Returns:
            dict with keys: total_repos, total_stars, avg_recent_activity, top_repos
        """
        try:
            data = await self._fetch_repos(concept, max_repos)
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 403:
                logger.warning("GitHub API rate limit reached, returning degraded results")
                return self._empty_result("Rate limit reached")
            logger.warning(f"GitHub API error: {status}")
            return self._empty_result(f"API error: {status}")
        except httpx.TimeoutException:
            logger.warning("GitHub API timeout")
            return self._empty_result("Timeout")
        except Exception as e:
            logger.warning(f"GitHub API error: {e}")
            return self._empty_result(str(e))

        total_count = data.get("total_count", 0)
        items = data.get("items", [])

        total_stars = sum(repo.get("stargazers_count", 0) for repo in items)

        # Compute average recent activity (pushed in last 6 months)
        now = datetime.now(timezone.utc)
        six_months_ago = now - timedelta(days=180)
        recent_repos = []
        for repo in items:
            pushed_at = repo.get("pushed_at", "")
            if pushed_at:
                try:
                    pushed = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
                    if pushed > six_months_ago:
                        recent_repos.append(repo)
                except (ValueError, TypeError):
                    pass

        avg_recent_activity = len(recent_repos) / max(len(items), 1) * 100

        top_repos = [
            {
                "name": repo.get("full_name", ""),
                "stars": repo.get("stargazers_count", 0),
                "forks": repo.get("forks_count", 0),
                "description": (repo.get("description") or "")[:200],
                "language": repo.get("language", ""),
                "updated_at": repo.get("pushed_at", ""),
                "url": repo.get("html_url", ""),
            }
            for repo in items[:10]
        ]

        return {
            "total_repos": total_count,
            "total_stars": total_stars,
            "avg_recent_activity": round(avg_recent_activity, 1),
            "top_repos": top_repos,
        }

    @staticmethod
    def _empty_result(reason: str = "") -> dict:
        return {
            "total_repos": 0,
            "total_stars": 0,
            "avg_recent_activity": 0.0,
            "top_repos": [],
            "note": f"GitHub data unavailable: {reason}" if reason else "",
        }
