"""Unit tests for the AI-crawler / robots.txt / llms.txt auditor."""

from app.services.geo.llms_txt_checker import LLMsTxtChecker


class TestLLMsTxtChecker:
    def setup_method(self):
        self.checker = LLMsTxtChecker()

    def test_empty_robots_allows_everything(self):
        r = self.checker.analyze("")
        assert r["score"] == 100
        assert r["blocked_citation_bots"] == []
        assert r["blocked_agents"] == []

    def test_block_all_zeroes_score(self):
        r = self.checker.analyze("User-agent: *\nDisallow: /\n")
        assert r["score"] == 0
        assert any("blocks all" in i.lower() for i in r["issues"])

    def test_training_block_is_not_flagged_as_citation_loss(self):
        robots = "User-agent: GPTBot\nDisallow: /\n"
        r = self.checker.analyze(robots)
        assert "GPTBot" in r["blocked_agents"]
        assert "GPTBot" not in r["blocked_citation_bots"]
        assert r["score"] == 100

    def test_search_bot_block_is_flagged(self):
        robots = "User-agent: PerplexityBot\nDisallow: /\n"
        r = self.checker.analyze(robots)
        assert "PerplexityBot" in r["blocked_citation_bots"]
        assert r["score"] < 100
        assert any("PerplexityBot" in i for i in r["issues"])

    def test_allow_override_in_group(self):
        robots = "User-agent: OAI-SearchBot\nDisallow: /\nAllow: /\n"
        r = self.checker.analyze(robots)
        assert "OAI-SearchBot" not in r["blocked_agents"]

    def test_classification_buckets(self):
        r = self.checker.analyze("")
        for bucket in ("training", "search", "user"):
            assert r["classification"][bucket]
        agents = {e["agent"] for e in r["classification"]["search"]}
        assert "PerplexityBot" in agents
        assert "OAI-SearchBot" in agents

    def test_llms_txt_presence(self):
        assert self.checker.analyze("", llms_txt="# llms.txt\n")["llms_txt_present"] is True
        assert self.checker.analyze("", llms_txt=None)["llms_txt_present"] is False

    def test_recommended_robots_embeds_sitemap(self):
        r = self.checker.analyze("", sitemap_url="https://x.com/sitemap.xml")
        assert "https://x.com/sitemap.xml" in r["recommended_robots_txt"]
        assert "OAI-SearchBot" in r["recommended_robots_txt"]
