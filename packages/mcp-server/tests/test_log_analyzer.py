"""Tests for LogAnalyzerService."""

from app.services.log_analyzer import LogAnalyzerService

# ── Fixtures ─────────────────────────────────────────────────────────


VALID_LOG_LINE = (
    "66.249.66.1 - - [12/Mar/2024:10:00:01 +0000] "
    '"GET /blog/seo-guide HTTP/1.1" 200 12345 '
    '"-" "Googlebot/2.1 (+http://www.google.com/bot.html)"'
)

VALID_HUMAN_LINE = (
    "192.168.1.1 - - [12/Mar/2024:10:01:00 +0000] "
    '"GET /blog/post HTTP/1.1" 200 5000 '
    '"https://google.com" "Mozilla/5.0 (compatible; Chrome/99)"'
)

VALID_GPTBOT_LINE = (
    "20.20.20.1 - - [12/Mar/2024:10:02:00 +0000] "
    '"GET /article/ai-seo HTTP/1.1" 200 8000 '
    '"-" "GPTBot/1.0"'
)

VALID_BINGBOT_LINE = (
    "40.77.167.1 - - [12/Mar/2024:10:03:00 +0000] "
    '"GET /products HTTP/1.1" 200 3000 '
    '"-" "bingbot/2.0 (+http://www.bing.com/bingbot.htm)"'
)


class TestParseLine:
    """Tests for _parse_line log parsing."""

    def setup_method(self):
        self.service = LogAnalyzerService()

    def test_parses_valid_combined_log_line(self):
        result = self.service._parse_line(VALID_LOG_LINE)
        assert result is not None
        assert result["ip"] == "66.249.66.1"
        assert result["method"] == "GET"
        assert result["path"] == "/blog/seo-guide"
        assert result["status"] == 200

    def test_parses_user_agent_from_valid_line(self):
        result = self.service._parse_line(VALID_LOG_LINE)
        assert result is not None
        assert "Googlebot" in result["user_agent"]

    def test_returns_none_for_empty_line(self):
        result = self.service._parse_line("")
        assert result is None

    def test_returns_none_for_invalid_format(self):
        result = self.service._parse_line("this is not a log line at all")
        assert result is None

    def test_returns_none_for_partial_line(self):
        result = self.service._parse_line("66.249.66.1 - - [12/Mar/2024:10:00:01 +0000]")
        assert result is None

    def test_parses_status_code_as_integer(self):
        result = self.service._parse_line(VALID_LOG_LINE)
        assert isinstance(result["status"], int)

    def test_parses_404_status_correctly(self):
        line = (
            "66.249.66.1 - - [12/Mar/2024:10:05:00 +0000] "
            '"GET /missing-page HTTP/1.1" 404 0 '
            '"-" "Googlebot/2.1"'
        )
        result = self.service._parse_line(line)
        assert result is not None
        assert result["status"] == 404
        assert result["path"] == "/missing-page"


class TestIdentifyBot:
    """Tests for _identify_bot user-agent matching."""

    def setup_method(self):
        self.service = LogAnalyzerService()

    def test_identifies_googlebot(self):
        ua = "Googlebot/2.1 (+http://www.google.com/bot.html)"
        assert self.service._identify_bot(ua) == "googlebot"

    def test_identifies_bingbot(self):
        ua = "Mozilla/5.0 (compatible; bingbot/2.0)"
        assert self.service._identify_bot(ua) == "bingbot"

    def test_identifies_gptbot(self):
        ua = "GPTBot/1.0"
        assert self.service._identify_bot(ua) == "gptbot"

    def test_identifies_claudebot(self):
        ua = "ClaudeBot/1.0"
        assert self.service._identify_bot(ua) == "claudebot"

    def test_identifies_claude_web(self):
        ua = "Claude-Web/1.0"
        assert self.service._identify_bot(ua) == "claudebot"

    def test_identifies_perplexitybot(self):
        ua = "PerplexityBot/1.0"
        assert self.service._identify_bot(ua) == "perplexitybot"

    def test_identifies_yandexbot(self):
        ua = "YandexBot/3.0"
        assert self.service._identify_bot(ua) == "yandexbot"

    def test_returns_empty_string_for_browser(self):
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0"
        assert self.service._identify_bot(ua) == ""

    def test_returns_empty_string_for_empty_ua(self):
        assert self.service._identify_bot("") == ""

    def test_case_insensitive_matching(self):
        assert self.service._identify_bot("googleBOT/2.1") == "googlebot"


class TestAnalyzeCrawlBudget:
    """Tests for _analyze_crawl_budget waste detection."""

    def setup_method(self):
        self.service = LogAnalyzerService()

    def _make_entry(self, path, status=200, bot="googlebot"):
        return {"path": path, "status": status, "bot": bot, "user_agent": "Googlebot/2.1"}

    def test_static_asset_counted_as_waste(self):
        entries = [
            self._make_entry("/style.css"),
            self._make_entry("/app.js"),
            self._make_entry("/image.png"),
            self._make_entry("/blog/post"),
        ]
        result = self.service._analyze_crawl_budget(entries)
        assert result["crawl_waste"]["total_wasted"] == 3
        assert result["crawl_waste"]["by_type"]["static_assets"] == 3

    def test_admin_pages_counted_as_waste(self):
        entries = [
            self._make_entry("/wp-admin/options"),
            self._make_entry("/wp-login.php"),
        ]
        result = self.service._analyze_crawl_budget(entries)
        assert result["crawl_waste"]["total_wasted"] == 2
        assert result["crawl_waste"]["by_type"]["admin_pages"] == 2

    def test_utm_params_counted_as_waste(self):
        entries = [self._make_entry("/landing?utm_source=google&utm_medium=cpc")]
        result = self.service._analyze_crawl_budget(entries)
        assert result["crawl_waste"]["total_wasted"] == 1
        assert result["crawl_waste"]["by_type"]["utm_params"] == 1

    def test_pagination_counted_as_waste(self):
        entries = [self._make_entry("/category/seo/page/2")]
        result = self.service._analyze_crawl_budget(entries)
        assert result["crawl_waste"]["total_wasted"] == 1
        assert result["crawl_waste"]["by_type"]["pagination"] == 1

    def test_normal_page_not_counted_as_waste(self):
        entries = [
            self._make_entry("/blog/seo-guide"),
            self._make_entry("/about"),
            self._make_entry("/services/seo"),
        ]
        result = self.service._analyze_crawl_budget(entries)
        assert result["crawl_waste"]["total_wasted"] == 0

    def test_error_requests_counted_correctly(self):
        entries = [
            self._make_entry("/missing", status=404),
            self._make_entry("/error", status=500),
            self._make_entry("/page", status=200),
        ]
        result = self.service._analyze_crawl_budget(entries)
        assert result["errors"]["error_requests"] == 2

    def test_no_googlebot_entries_returns_zero_count_message(self):
        entries = [{"path": "/page", "status": 200, "bot": "bingbot"}]
        result = self.service._analyze_crawl_budget(entries)
        assert result["googlebot_requests"] == 0
        assert "message" in result

    def test_efficiency_score_is_100_for_clean_crawl(self):
        entries = [
            self._make_entry("/page1"),
            self._make_entry("/page2"),
        ]
        result = self.service._analyze_crawl_budget(entries)
        assert result["efficiency_score"] == 100.0


class TestCrossReferenceSitemap:
    """Tests for _cross_reference_sitemap coverage analysis."""

    def setup_method(self):
        self.service = LogAnalyzerService()

    def _make_entry(self, path):
        return {"path": path, "bot": "googlebot", "status": 200}

    def test_counts_urls_crawled_from_sitemap(self):
        sitemap_urls = [
            "https://example.com/page1",
            "https://example.com/page2",
            "https://example.com/page3",
        ]
        bot_entries = [
            self._make_entry("/page1"),
            self._make_entry("/page2"),
        ]
        result = self.service._cross_reference_sitemap(bot_entries, sitemap_urls)
        assert result["crawled_from_sitemap"] == 2
        assert result["not_crawled_from_sitemap"] == 1

    def test_counts_crawls_not_in_sitemap(self):
        sitemap_urls = ["https://example.com/page1"]
        bot_entries = [
            self._make_entry("/page1"),
            self._make_entry("/page-not-in-sitemap"),
        ]
        result = self.service._cross_reference_sitemap(bot_entries, sitemap_urls)
        assert result["crawled_not_in_sitemap"] == 1

    def test_100_percent_coverage_when_all_crawled(self):
        sitemap_urls = ["https://example.com/a", "https://example.com/b"]
        bot_entries = [self._make_entry("/a"), self._make_entry("/b")]
        result = self.service._cross_reference_sitemap(bot_entries, sitemap_urls)
        assert result["sitemap_coverage"] == 100.0

    def test_zero_percent_coverage_when_nothing_crawled(self):
        sitemap_urls = ["https://example.com/a", "https://example.com/b"]
        bot_entries = [self._make_entry("/c")]
        result = self.service._cross_reference_sitemap(bot_entries, sitemap_urls)
        assert result["sitemap_coverage"] == 0.0

    def test_returns_expected_keys(self):
        result = self.service._cross_reference_sitemap([], ["https://example.com/page"])
        for key in (
            "sitemap_urls",
            "crawled_from_sitemap",
            "not_crawled_from_sitemap",
            "crawled_not_in_sitemap",
            "sitemap_coverage",
        ):
            assert key in result


class TestAnalyzeAiBots:
    """Tests for _analyze_ai_bots AI crawler detection."""

    def setup_method(self):
        self.service = LogAnalyzerService()

    def test_returns_detected_false_when_no_ai_bots(self):
        entries = [{"bot": "googlebot", "path": "/page", "status": 200}]
        result = self.service._analyze_ai_bots(entries)
        assert result["detected"] is False

    def test_returns_detected_true_when_gptbot_present(self):
        entries = [{"bot": "gptbot", "path": "/article", "status": 200}]
        result = self.service._analyze_ai_bots(entries)
        assert result["detected"] is True

    def test_counts_requests_per_ai_bot(self):
        entries = [
            {"bot": "gptbot", "path": "/a", "status": 200},
            {"bot": "gptbot", "path": "/b", "status": 200},
            {"bot": "claudebot", "path": "/c", "status": 200},
        ]
        result = self.service._analyze_ai_bots(entries)
        assert result["by_bot"]["gptbot"] == 2
        assert result["by_bot"]["claudebot"] == 1

    def test_lists_top_crawled_pages(self):
        entries = [
            {"bot": "gptbot", "path": "/popular-article", "status": 200},
            {"bot": "perplexitybot", "path": "/popular-article", "status": 200},
        ]
        result = self.service._analyze_ai_bots(entries)
        assert "/popular-article" in result["top_crawled_pages"]

    def test_empty_entries_returns_not_detected(self):
        result = self.service._analyze_ai_bots([])
        assert result["detected"] is False


class TestFullAnalyze:
    """Tests for the full analyze() method with sample log content."""

    def setup_method(self):
        self.service = LogAnalyzerService()

    async def test_returns_error_for_empty_content(self):
        result = await self.service.analyze("")
        assert "error" in result

    async def test_parses_and_returns_summary(self):
        log_content = "\n".join([VALID_LOG_LINE, VALID_HUMAN_LINE, VALID_GPTBOT_LINE])
        result = await self.service.analyze(log_content)
        assert "summary" in result
        assert result["summary"]["total_entries"] == 3

    async def test_separates_bots_from_humans(self):
        log_content = "\n".join([VALID_LOG_LINE, VALID_HUMAN_LINE])
        result = await self.service.analyze(log_content)
        # Googlebot is 1 bot, human is 1 human
        assert result["summary"]["bot_requests"] == 1
        assert result["summary"]["human_requests"] == 1

    async def test_detects_ai_bot_in_full_analysis(self):
        log_content = "\n".join([VALID_LOG_LINE, VALID_GPTBOT_LINE])
        result = await self.service.analyze(log_content)
        assert result["ai_bot_activity"]["detected"] is True

    async def test_sitemap_coverage_included_when_provided(self):
        log_content = VALID_LOG_LINE
        sitemap_urls = ["https://www.iautos.fr/blog/seo-guide"]
        result = await self.service.analyze(log_content, sitemap_urls=sitemap_urls)
        assert "sitemap_coverage" in result
        assert result["sitemap_coverage"]["sitemap_coverage"] == 100.0

    async def test_returns_recommendations(self):
        log_content = "\n".join([VALID_LOG_LINE, VALID_HUMAN_LINE])
        result = await self.service.analyze(log_content)
        assert "recommendations" in result
        assert isinstance(result["recommendations"], list)
        assert len(result["recommendations"]) >= 1

    async def test_returns_error_when_all_lines_invalid(self):
        log_content = "garbage\nnot a log line\n\n  "
        result = await self.service.analyze(log_content)
        assert "error" in result

    async def test_respects_max_lines_limit(self):
        """Processing should not exceed max_lines."""
        lines = [VALID_LOG_LINE] * 200
        log_content = "\n".join(lines)
        result = await self.service.analyze(log_content, max_lines=50)
        assert result["summary"]["total_entries"] <= 50
