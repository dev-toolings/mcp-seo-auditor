"""Internal links analysis service with PageRank computation."""

import logging
from collections import defaultdict
from typing import Any
from urllib.parse import urlparse

from app.services.crawler_service import CrawledPage

logger = logging.getLogger(__name__)


class InternalLinksAnalyzerService:
    """Analyze internal link structure and compute PageRank."""

    def __init__(self, damping: float = 0.85, iterations: int = 50):
        self.damping = damping
        self.iterations = iterations

    def analyze(
        self,
        pages: list[CrawledPage],
        sitemap_urls: list[str] | None = None,
        target_statuses: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        """Analyze internal link structure from crawled pages.

        Args:
            pages: List of crawled pages with internal_links populated.
            sitemap_urls: Optional list of sitemap URLs to detect orphan pages.
            target_statuses: HTTP statuses of linked URLs outside ``pages``
                (see ``uncrawled_targets``). Without them, a broken link can only
                be detected when its target was itself crawled.

        Returns:
            Analysis report dict.
        """
        # Build link graph
        graph: dict[str, set[str]] = defaultdict(set)
        crawled_urls = set()
        all_linked_urls = set()
        page_statuses: dict[str, int] = {}

        for page in pages:
            if page.status_code != 200:
                page_statuses[self._normalize_url(page.url)] = page.status_code
                continue
            source_url = self._normalize_url(page.url)
            crawled_urls.add(source_url)
            page_statuses[source_url] = page.status_code
            for link in page.internal_links:
                # Normalize: strip fragments and trailing slashes
                normalized = self._normalize_url(link)
                graph[source_url].add(normalized)
                all_linked_urls.add(normalized)

        for url, status in (target_statuses or {}).items():
            page_statuses.setdefault(self._normalize_url(url), status)

        # Compute PageRank
        pagerank = self._compute_pagerank(graph, crawled_urls | all_linked_urls)

        # Detect orphan pages
        orphan_pages = []
        orphan_detection_skipped = False
        if sitemap_urls:
            normalized_sitemap_urls = {self._normalize_url(url) for url in sitemap_urls}
            if not normalized_sitemap_urls.issubset(crawled_urls):
                orphan_detection_skipped = True
            else:
                inbound_links: dict[str, int] = defaultdict(int)
                for source, targets in graph.items():
                    for target in targets:
                        inbound_links[target] += 1

                for normalized in normalized_sitemap_urls:
                    if inbound_links.get(normalized, 0) == 0:
                        orphan_pages.append(normalized)

        # Detect broken internal links (linked target crawled and returned an HTTP error)
        broken_links = []
        crawl_failed_internal_targets = []
        for source, targets in graph.items():
            for target in targets:
                status = page_statuses.get(target)
                if status is None or status == 200:
                    continue
                if status == 0:
                    crawl_failed_internal_targets.append({"source": source, "target": target})
                    continue
                if status >= 400:
                    broken_links.append(
                        {
                            "source": source,
                            "target": target,
                            "status": status,
                        }
                    )

        # Stats
        link_counts = [len(targets) for targets in graph.values()]
        avg_links = sum(link_counts) / len(link_counts) if link_counts else 0

        # Top pages by PageRank
        sorted_pagerank = sorted(pagerank.items(), key=lambda x: x[1], reverse=True)

        result = {
            "total_pages": len(crawled_urls),
            "total_internal_links": sum(link_counts),
            "avg_links_per_page": round(avg_links, 1),
            "max_links_on_page": max(link_counts) if link_counts else 0,
            "min_links_on_page": min(link_counts) if link_counts else 0,
            "orphan_pages": orphan_pages[:20],
            "orphan_count": len(orphan_pages),
            "broken_internal_links": broken_links[:20],
            "broken_count": len(broken_links),
            "crawl_failed_internal_targets": crawl_failed_internal_targets[:20],
            "crawl_failed_internal_target_count": len(crawl_failed_internal_targets),
            "top_pages_by_pagerank": [
                {"url": url, "pagerank": round(score, 6)} for url, score in sorted_pagerank[:20]
            ],
            "bottom_pages_by_pagerank": [
                {"url": url, "pagerank": round(score, 6)} for url, score in sorted_pagerank[-10:]
            ]
            if len(sorted_pagerank) > 10
            else [],
        }

        if orphan_detection_skipped:
            result["orphan_detection_skipped"] = True
            result["orphan_detection_reason"] = (
                "Skipped because the crawled page set does not cover every sitemap URL. "
                "A partial crawl cannot prove orphan pages."
            )

        return result

    def uncrawled_targets(self, pages: list[CrawledPage]) -> list[str]:
        """Internal link targets that no crawled page covers, so their status is unknown."""
        visited = {self._normalize_url(page.url) for page in pages}
        targets = {
            self._normalize_url(link)
            for page in pages
            if page.status_code == 200
            for link in page.internal_links
        }
        return sorted(targets - visited)

    def _compute_pagerank(self, graph: dict[str, set[str]], all_urls: set[str]) -> dict[str, float]:
        """Compute PageRank using iterative algorithm."""
        try:
            return self._compute_pagerank_numpy(graph, all_urls)
        except ImportError:
            return self._compute_pagerank_pure(graph, all_urls)

    def _compute_pagerank_numpy(
        self, graph: dict[str, set[str]], all_urls: set[str]
    ) -> dict[str, float]:
        """Compute PageRank using numpy for performance."""
        import numpy as np

        urls = sorted(all_urls)
        n = len(urls)
        if n == 0:
            return {}

        url_to_idx = {url: i for i, url in enumerate(urls)}

        # Build transition matrix
        transition = np.zeros((n, n))
        for source, targets in graph.items():
            if source not in url_to_idx:
                continue
            src_idx = url_to_idx[source]
            valid_targets = [t for t in targets if t in url_to_idx]
            if valid_targets:
                for target in valid_targets:
                    transition[url_to_idx[target]][src_idx] = 1.0 / len(valid_targets)

        # Handle dangling nodes
        dangling = np.where(transition.sum(axis=0) == 0)[0]
        for idx in dangling:
            transition[:, idx] = 1.0 / n

        # Power iteration
        rank = np.ones(n) / n
        for _ in range(self.iterations):
            new_rank = (1 - self.damping) / n + self.damping * transition @ rank
            if np.allclose(rank, new_rank, atol=1e-8):
                break
            rank = new_rank

        return {urls[i]: float(rank[i]) for i in range(n)}

    def _compute_pagerank_pure(
        self, graph: dict[str, set[str]], all_urls: set[str]
    ) -> dict[str, float]:
        """Pure Python PageRank fallback (no numpy)."""
        urls = sorted(all_urls)
        n = len(urls)
        if n == 0:
            return {}

        rank = {url: 1.0 / n for url in urls}

        for _ in range(self.iterations):
            new_rank = {}
            for url in urls:
                new_rank[url] = (1 - self.damping) / n

            for source, targets in graph.items():
                if source not in rank:
                    continue
                valid_targets = [t for t in targets if t in rank]
                if valid_targets:
                    share = rank[source] / len(valid_targets)
                    for target in valid_targets:
                        new_rank[target] = new_rank.get(target, 0) + self.damping * share
                else:
                    # Dangling node: distribute evenly
                    share = rank[source] / n
                    for url in urls:
                        new_rank[url] += self.damping * share

            rank = new_rank

        return rank

    def _normalize_url(self, url: str) -> str:
        """Normalize URL by stripping fragment and trailing slash."""
        parsed = urlparse(url)
        path = parsed.path.rstrip("/") or "/"
        normalized = f"{parsed.scheme}://{parsed.netloc}{path}"
        if parsed.query:
            normalized += f"?{parsed.query}"
        return normalized
