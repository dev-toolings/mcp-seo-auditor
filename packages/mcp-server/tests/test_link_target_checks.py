"""Broken internal links whose target is outside the crawled page set."""

from unittest.mock import MagicMock, patch

import httpx

from app.services.crawler_service import CrawledPage, CrawlerService
from app.services.internal_links_analyzer import InternalLinksAnalyzerService

SITE = "https://www.iautos.fr"


def _page(url: str, links: list[str] | None = None, status: int = 200) -> CrawledPage:
    return CrawledPage(url=url, status_code=status, title="t", internal_links=links or [])


class TestUncrawledTargets:
    """The analyzer knows which link targets it has no status for."""

    def test_lists_only_targets_the_crawl_did_not_visit(self):
        """Crawled pages are excluded; targets are normalized and deduplicated."""
        pages = [
            _page(f"{SITE}/a", [f"{SITE}/b/", f"{SITE}/en/missing#top", f"{SITE}/en/missing"]),
            _page(f"{SITE}/b"),
        ]

        assert InternalLinksAnalyzerService().uncrawled_targets(pages) == [f"{SITE}/en/missing"]

    def test_uncrawled_target_returning_404_is_a_broken_link(self):
        """A 404 from the target check is reported like a crawled 404."""
        pages = [_page(f"{SITE}/a", [f"{SITE}/en/missing"])]

        result = InternalLinksAnalyzerService().analyze(
            pages, target_statuses={f"{SITE}/en/missing/": 404}
        )

        assert result["broken_count"] == 1
        assert result["broken_internal_links"][0] == {
            "source": f"{SITE}/a",
            "target": f"{SITE}/en/missing",
            "status": 404,
        }


class TestCheckLinkStatuses:
    """CrawlerService.check_link_statuses fetches target statuses over plain HTTP."""

    async def test_bot_blocks_and_failures_are_unchecked_not_broken(self):
        """404 is kept; 403 and network errors map to 0 (check failed)."""
        codes = {f"{SITE}/gone": 404, f"{SITE}/ok": 200, f"{SITE}/blocked": 403}

        async def fake_safe_get(client, url, *, headers=None):
            if url == f"{SITE}/down":
                raise httpx.ConnectError("refused")
            return MagicMock(status_code=codes[url])

        with patch("app.services.crawler_service.safe_get", new=fake_safe_get):
            statuses = await CrawlerService().check_link_statuses([*codes, f"{SITE}/down"])

        assert statuses == {
            f"{SITE}/gone": 404,
            f"{SITE}/ok": 200,
            f"{SITE}/blocked": 0,
            f"{SITE}/down": 0,
        }

    async def test_limit_caps_the_number_of_requests(self):
        """Beyond the limit, targets are left unchecked."""

        async def fake_safe_get(client, url, *, headers=None):
            return MagicMock(status_code=200)

        with patch("app.services.crawler_service.safe_get", new=fake_safe_get):
            statuses = await CrawlerService().check_link_statuses(
                [f"{SITE}/1", f"{SITE}/2", f"{SITE}/3"], limit=2
            )

        assert len(statuses) == 2
