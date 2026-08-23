"""Log File Analyzer — parse server logs and analyze crawl patterns.

Parses Apache/Nginx access logs to detect Googlebot crawl patterns,
crawl budget waste, and cross-reference with sitemap data.
"""

import logging
import re
from collections import Counter
from typing import Any, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Common log format patterns
COMBINED_LOG_PATTERN = re.compile(
    r"(?P<ip>[\d.]+)\s+"
    r"(?P<ident>\S+)\s+"
    r"(?P<user>\S+)\s+"
    r"\[(?P<time>[^\]]+)\]\s+"
    r'"(?P<method>\w+)\s+(?P<path>\S+)\s+(?P<protocol>[^"]+)"\s+'
    r"(?P<status>\d+)\s+"
    r"(?P<size>\S+)"
    r'(?:\s+"(?P<referer>[^"]*)"\s+"(?P<user_agent>[^"]*)")?'
)

# Bot user-agent patterns
BOT_PATTERNS = {
    "googlebot": re.compile(r"(?i)googlebot", re.IGNORECASE),
    "googlebot_mobile": re.compile(r"(?i)googlebot-mobile", re.IGNORECASE),
    "googlebot_image": re.compile(r"(?i)googlebot-image", re.IGNORECASE),
    "bingbot": re.compile(r"(?i)bingbot", re.IGNORECASE),
    "gptbot": re.compile(r"(?i)gptbot", re.IGNORECASE),
    "claudebot": re.compile(r"(?i)claude-web|claudebot", re.IGNORECASE),
    "perplexitybot": re.compile(r"(?i)perplexitybot", re.IGNORECASE),
    "yandexbot": re.compile(r"(?i)yandexbot", re.IGNORECASE),
    "baiduspider": re.compile(r"(?i)baiduspider", re.IGNORECASE),
}

# Waste patterns
WASTE_PATTERNS = [
    re.compile(r"(?i)\.(css|js|woff2?|ttf|eot|svg|png|jpg|jpeg|gif|ico|webp)$"),
    re.compile(r"(?i)(/wp-admin/|/wp-login|/xmlrpc\.php)"),
    re.compile(r"(?i)(\?.*utm_|&utm_)"),
    re.compile(r"(?i)(/tag/|/category/|/page/\d+)"),
]


class LogAnalyzerService:
    """Analyze server access logs for SEO insights."""

    async def analyze(
        self,
        log_content: str,
        sitemap_urls: list[str] | None = None,
        max_lines: int = 100000,
    ) -> dict[str, Any]:
        """Parse and analyze server logs.

        Args:
            log_content: Raw log file content (combined format)
            sitemap_urls: Optional list of URLs from sitemap for cross-reference
            max_lines: Maximum lines to process

        Returns:
            Dict with bot activity, crawl budget analysis, recommendations
        """
        if not log_content:
            return {"error": "No log content provided"}

        lines = log_content.split("\n")[:max_lines]

        # Parse all entries
        entries = []
        parse_errors = 0
        for line in lines:
            entry = self._parse_line(line)
            if entry:
                entries.append(entry)
            elif line.strip():
                parse_errors += 1

        if not entries:
            return {
                "error": "No valid log entries found",
                "parse_errors": parse_errors,
                "hint": "Ensure logs are in Apache/Nginx combined format",
            }

        # Analyze bot vs human traffic
        bot_entries = []
        human_entries = []
        for entry in entries:
            bot = self._identify_bot(entry.get("user_agent", ""))
            if bot:
                entry["bot"] = bot
                bot_entries.append(entry)
            else:
                human_entries.append(entry)

        # Bot activity breakdown
        bot_activity = self._analyze_bot_activity(bot_entries)

        # Crawl budget analysis
        crawl_budget = self._analyze_crawl_budget(bot_entries)

        # Status code distribution for bots
        bot_status = self._status_distribution(bot_entries)

        # Cross-reference with sitemap
        sitemap_analysis = {}
        if sitemap_urls:
            sitemap_analysis = self._cross_reference_sitemap(bot_entries, sitemap_urls)

        # AI bot activity (GPTBot, ClaudeBot, PerplexityBot)
        ai_bots = self._analyze_ai_bots(bot_entries)

        return {
            "summary": {
                "total_entries": len(entries),
                "bot_requests": len(bot_entries),
                "human_requests": len(human_entries),
                "bot_ratio": round(len(bot_entries) / max(len(entries), 1) * 100, 1),
                "parse_errors": parse_errors,
            },
            "bot_activity": bot_activity,
            "crawl_budget": crawl_budget,
            "bot_status_codes": bot_status,
            "sitemap_coverage": sitemap_analysis,
            "ai_bot_activity": ai_bots,
            "recommendations": self._generate_recommendations(
                bot_activity, crawl_budget, bot_status, sitemap_analysis
            ),
        }

    def _parse_line(self, line: str) -> Optional[dict]:
        """Parse a single log line in combined format."""
        match = COMBINED_LOG_PATTERN.match(line.strip())
        if not match:
            return None

        return {
            "ip": match.group("ip"),
            "method": match.group("method"),
            "path": match.group("path"),
            "status": int(match.group("status")),
            "size": match.group("size"),
            "user_agent": match.group("user_agent") or "",
            "referer": match.group("referer") or "",
        }

    def _identify_bot(self, user_agent: str) -> str:
        """Identify bot from user agent string."""
        for bot_name, pattern in BOT_PATTERNS.items():
            if pattern.search(user_agent):
                return bot_name
        return ""

    def _analyze_bot_activity(self, bot_entries: list[dict]) -> dict:
        """Analyze bot crawl activity breakdown."""
        by_bot = Counter(e["bot"] for e in bot_entries)
        by_path_prefix: Counter[str] = Counter()

        for entry in bot_entries:
            path = entry.get("path", "")
            prefix = "/" + path.split("/")[1] if "/" in path[1:] else "/"
            by_path_prefix[prefix] += 1

        return {
            "by_bot": dict(by_bot.most_common(10)),
            "top_crawled_sections": dict(by_path_prefix.most_common(15)),
            "total_bot_requests": len(bot_entries),
        }

    def _analyze_crawl_budget(self, bot_entries: list[dict]) -> dict:
        """Analyze crawl budget usage and waste."""
        # Focus on Googlebot
        google_entries = [e for e in bot_entries if e.get("bot", "").startswith("googlebot")]

        if not google_entries:
            return {"googlebot_requests": 0, "message": "No Googlebot activity found"}

        total = len(google_entries)
        waste_count = 0
        waste_by_type: Counter[str] = Counter()

        for entry in google_entries:
            path = entry.get("path", "")
            for i, pattern in enumerate(WASTE_PATTERNS):
                if pattern.search(path):
                    waste_count += 1
                    waste_types = ["static_assets", "admin_pages", "utm_params", "pagination"]
                    waste_by_type[waste_types[i]] += 1
                    break

        # Unique pages crawled
        unique_paths = len(set(e.get("path", "") for e in google_entries))

        # 4xx/5xx errors
        error_count = sum(1 for e in google_entries if e["status"] >= 400)

        return {
            "googlebot_requests": total,
            "unique_pages_crawled": unique_paths,
            "crawl_waste": {
                "total_wasted": waste_count,
                "waste_percentage": round(waste_count / max(total, 1) * 100, 1),
                "by_type": dict(waste_by_type),
            },
            "errors": {
                "error_requests": error_count,
                "error_rate": round(error_count / max(total, 1) * 100, 1),
            },
            "efficiency_score": round((1 - waste_count / max(total, 1)) * 100, 1),
        }

    def _status_distribution(self, bot_entries: list[dict]) -> dict:
        """Get status code distribution for bot requests."""
        status_counts = Counter(e["status"] for e in bot_entries)
        return {
            "distribution": dict(status_counts.most_common()),
            "success_rate": round(
                sum(1 for e in bot_entries if 200 <= e["status"] < 300)
                / max(len(bot_entries), 1)
                * 100,
                1,
            ),
        }

    def _cross_reference_sitemap(
        self,
        bot_entries: list[dict],
        sitemap_urls: list[str],
    ) -> dict:
        """Cross-reference bot crawls with sitemap URLs."""
        sitemap_paths = set()
        for url in sitemap_urls:
            try:
                sitemap_paths.add(urlparse(url).path)
            except Exception:
                pass

        crawled_paths = set(e.get("path", "") for e in bot_entries)

        in_sitemap_crawled = sitemap_paths & crawled_paths
        in_sitemap_not_crawled = sitemap_paths - crawled_paths
        crawled_not_in_sitemap = crawled_paths - sitemap_paths

        return {
            "sitemap_urls": len(sitemap_paths),
            "crawled_from_sitemap": len(in_sitemap_crawled),
            "not_crawled_from_sitemap": len(in_sitemap_not_crawled),
            "crawled_not_in_sitemap": len(crawled_not_in_sitemap),
            "sitemap_coverage": round(
                len(in_sitemap_crawled) / max(len(sitemap_paths), 1) * 100, 1
            ),
            "uncrawled_sitemap_urls": sorted(in_sitemap_not_crawled)[:20],
            "non_sitemap_crawls": sorted(crawled_not_in_sitemap)[:20],
        }

    def _analyze_ai_bots(self, bot_entries: list[dict]) -> dict:
        """Analyze AI bot crawl activity (GPTBot, ClaudeBot, etc.)."""
        ai_bot_names = {"gptbot", "claudebot", "perplexitybot"}
        ai_entries = [e for e in bot_entries if e.get("bot", "") in ai_bot_names]

        if not ai_entries:
            return {
                "detected": False,
                "message": "No AI bot activity detected in logs",
            }

        by_bot = Counter(e["bot"] for e in ai_entries)
        top_pages = Counter(e.get("path", "") for e in ai_entries)

        return {
            "detected": True,
            "total_requests": len(ai_entries),
            "by_bot": dict(by_bot),
            "top_crawled_pages": dict(top_pages.most_common(10)),
        }

    def _generate_recommendations(
        self,
        bot_activity: dict,
        crawl_budget: dict,
        bot_status: dict,
        sitemap_analysis: dict,
    ) -> list[str]:
        """Generate actionable recommendations from log analysis."""
        recs = []

        # Crawl budget waste
        waste_pct = crawl_budget.get("crawl_waste", {}).get("waste_percentage", 0)
        if waste_pct > 20:
            recs.append(
                f"High crawl budget waste ({waste_pct}%). "
                "Block static assets and admin pages in robots.txt."
            )

        # Error rate
        error_rate = crawl_budget.get("errors", {}).get("error_rate", 0)
        if error_rate > 5:
            recs.append(
                f"Bot error rate is {error_rate}%. Fix 4xx/5xx errors to improve crawl efficiency."
            )

        # Sitemap coverage
        coverage = sitemap_analysis.get("sitemap_coverage", 100)
        if coverage < 80:
            recs.append(
                f"Only {coverage}% of sitemap URLs were crawled. "
                "Improve internal linking to boost discovery."
            )

        not_in_sitemap = sitemap_analysis.get("crawled_not_in_sitemap", 0)
        if not_in_sitemap > 50:
            recs.append(
                f"{not_in_sitemap} crawled URLs are not in the sitemap. "
                "Review for orphan content or add to sitemap."
            )

        # Success rate
        success = bot_status.get("success_rate", 100)
        if success < 90:
            recs.append(
                f"Bot success rate is only {success}%. "
                "Investigate failing requests to improve crawlability."
            )

        if not recs:
            recs.append(
                "Log analysis shows healthy crawl patterns. Continue monitoring for changes."
            )

        return recs
