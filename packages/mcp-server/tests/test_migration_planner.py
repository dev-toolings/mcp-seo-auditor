"""Tests for MigrationPlannerService."""

from app.services.migration_planner import MigrationPlannerService


class TestFindBestMatch:
    """Tests for _find_best_match URL matching logic."""

    def setup_method(self):
        self.service = MigrationPlannerService()

    def test_exact_path_match_returns_confidence_one(self):
        old = "https://old.example.com/blog/python-tips"
        candidates = ["https://new.example.com/blog/python-tips"]
        result = self.service._find_best_match(old, candidates)
        assert result is not None
        assert result["confidence"] == 1.0
        assert result["match_type"] == "exact_path"

    def test_slug_match_returns_confidence_09(self):
        old = "https://old.example.com/en/python-tips"
        candidates = ["https://new.example.com/fr/python-tips"]
        result = self.service._find_best_match(old, candidates)
        assert result is not None
        assert result["confidence"] == 0.9
        assert result["match_type"] == "slug_match"

    def test_fuzzy_match_returns_result_above_threshold(self):
        old = "https://old.example.com/blog/seo-guide"
        candidates = ["https://new.example.com/blog/seo-guide-2024"]
        result = self.service._find_best_match(old, candidates)
        # Similar enough path — should match via fuzzy
        assert result is not None
        assert result["confidence"] >= 0.6

    def test_no_match_returns_none_below_threshold(self):
        old = "https://old.example.com/product/xyz-123"
        candidates = ["https://new.example.com/about/team"]
        result = self.service._find_best_match(old, candidates)
        # Very different paths — should not match
        assert result is None

    def test_empty_candidates_returns_none(self):
        result = self.service._find_best_match("https://old.example.com/page", [])
        assert result is None

    def test_exact_path_match_returns_highest_confidence(self):
        """Exact path match returns confidence 1.0."""
        old = "https://old.example.com/blog/post"
        candidates = [
            "https://new.example.com/blog/post",  # exact path match
        ]
        result = self.service._find_best_match(old, candidates)
        assert result["match_type"] == "exact_path"
        assert result["confidence"] == 1.0
        assert result["url"] == "https://new.example.com/blog/post"

    def test_url_with_trailing_slash_matches_without(self):
        old = "https://old.example.com/blog/post/"
        candidates = ["https://new.example.com/blog/post"]
        result = self.service._find_best_match(old, candidates)
        assert result is not None
        assert result["match_type"] == "exact_path"


class TestGenerateRedirectRules:
    """Tests for _generate_redirect_rules Apache/Nginx output."""

    def setup_method(self):
        self.service = MigrationPlannerService()

    def test_generates_apache_redirect_for_each_mapping(self):
        mappings = [
            {
                "old_url": "https://old.example.com/page-a",
                "new_url": "https://new.example.com/page-a-new",
                "confidence": 1.0,
                "match_type": "exact_path",
            }
        ]
        result = self.service._generate_redirect_rules(mappings)
        assert len(result["apache_htaccess"]) == 1
        rule = result["apache_htaccess"][0]
        assert rule.startswith("Redirect 301")
        assert "/page-a" in rule
        assert "https://new.example.com/page-a-new" in rule

    def test_generates_nginx_rewrite_for_each_mapping(self):
        mappings = [
            {
                "old_url": "https://old.example.com/contact",
                "new_url": "https://new.example.com/nous-contacter",
                "confidence": 0.9,
                "match_type": "slug_match",
            }
        ]
        result = self.service._generate_redirect_rules(mappings)
        assert len(result["nginx_conf"]) == 1
        rule = result["nginx_conf"][0]
        assert "rewrite" in rule
        assert "permanent" in rule

    def test_empty_mappings_returns_empty_rules(self):
        result = self.service._generate_redirect_rules([])
        assert result["apache_htaccess"] == []
        assert result["nginx_conf"] == []
        assert result["total_rules"] == 0

    def test_total_rules_matches_mapping_count(self):
        mappings = [
            {
                "old_url": f"https://old.example.com/page-{i}",
                "new_url": f"https://new.example.com/page-{i}",
                "confidence": 1.0,
                "match_type": "exact_path",
            }
            for i in range(5)
        ]
        result = self.service._generate_redirect_rules(mappings)
        assert result["total_rules"] == 5
        assert len(result["apache_htaccess"]) == 5
        assert len(result["nginx_conf"]) == 5

    def test_caps_at_200_rules(self):
        """Rules are capped at 200 to avoid oversized configs."""
        mappings = [
            {
                "old_url": f"https://old.example.com/page-{i}",
                "new_url": f"https://new.example.com/page-{i}",
                "confidence": 1.0,
                "match_type": "exact_path",
            }
            for i in range(250)
        ]
        result = self.service._generate_redirect_rules(mappings)
        assert len(result["apache_htaccess"]) <= 200
        assert len(result["nginx_conf"]) <= 200


class TestDetectChains:
    """Tests for _detect_chains redirect chain detection."""

    def setup_method(self):
        self.service = MigrationPlannerService()

    def test_detects_two_hop_chain(self):
        """A -> B -> C is a redirect chain of length 2."""
        mappings = [
            {
                "old_url": "https://example.com/a",
                "new_url": "https://example.com/b",
                "confidence": 1.0,
                "match_type": "exact_path",
            },
            {
                "old_url": "https://example.com/b",
                "new_url": "https://example.com/c",
                "confidence": 1.0,
                "match_type": "exact_path",
            },
        ]
        chains = self.service._detect_chains(mappings)
        assert len(chains) >= 1
        chain = chains[0]
        assert chain["length"] == 2
        assert "https://example.com/a" in chain["chain"]
        assert "https://example.com/c" in chain["chain"]

    def test_no_chain_when_no_cycle(self):
        """Distinct redirect targets produce no chains."""
        mappings = [
            {
                "old_url": "https://example.com/old1",
                "new_url": "https://example.com/new1",
                "confidence": 1.0,
                "match_type": "exact_path",
            },
            {
                "old_url": "https://example.com/old2",
                "new_url": "https://example.com/new2",
                "confidence": 1.0,
                "match_type": "exact_path",
            },
        ]
        chains = self.service._detect_chains(mappings)
        assert chains == []

    def test_empty_mappings_returns_no_chains(self):
        chains = self.service._detect_chains([])
        assert chains == []

    def test_chain_recommendation_mentions_direct_redirect(self):
        mappings = [
            {
                "old_url": "https://example.com/a",
                "new_url": "https://example.com/b",
                "confidence": 1.0,
                "match_type": "exact_path",
            },
            {
                "old_url": "https://example.com/b",
                "new_url": "https://example.com/c",
                "confidence": 1.0,
                "match_type": "exact_path",
            },
        ]
        chains = self.service._detect_chains(mappings)
        assert any("directly" in c["recommendation"].lower() for c in chains)

    def test_chain_capped_at_5_hops(self):
        """Chains with more than 5 hops are truncated."""
        # Create A -> B -> C -> D -> E -> F -> G (6 hops)
        urls = [f"https://example.com/{chr(ord('a') + i)}" for i in range(8)]
        mappings = [
            {
                "old_url": urls[i],
                "new_url": urls[i + 1],
                "confidence": 1.0,
                "match_type": "exact_path",
            }
            for i in range(7)
        ]
        chains = self.service._detect_chains(mappings)
        for chain in chains:
            assert len(chain["chain"]) <= 6  # max 5 hops = 6 URLs


class TestGenerateRecommendations:
    """Tests for _generate_recommendations output."""

    def setup_method(self):
        self.service = MigrationPlannerService()

    def test_mentions_unmatched_count_when_present(self):
        recs = self.service._generate_recommendations(
            mappings=[],
            unmatched=["https://example.com/page1", "https://example.com/page2"],
            chains=[],
            impact={},
        )
        assert any("2 URLs" in r or "2 URL" in r for r in recs)

    def test_mentions_low_confidence_mappings(self):
        mappings = [
            {
                "old_url": "https://example.com/a",
                "new_url": "https://example.com/b",
                "confidence": 0.5,
            }
        ]
        recs = self.service._generate_recommendations(
            mappings=mappings,
            unmatched=[],
            chains=[],
            impact={},
        )
        assert any("low confidence" in r.lower() for r in recs)

    def test_mentions_chains_when_detected(self):
        chains = [{"chain": ["a", "b", "c"], "length": 2, "recommendation": "fix chain"}]
        recs = self.service._generate_recommendations(
            mappings=[],
            unmatched=[],
            chains=chains,
            impact={},
        )
        assert any("chain" in r.lower() for r in recs)

    def test_always_includes_post_migration_monitoring_advice(self):
        recs = self.service._generate_recommendations(
            mappings=[],
            unmatched=[],
            chains=[],
            impact={},
        )
        assert any("GSC" in r or "monitor" in r.lower() or "sitemap" in r.lower() for r in recs)

    def test_critical_impact_generates_warning(self):
        impact = {
            "risk_level": "critical",
            "traffic_impact_percentage": 35.0,
        }
        recs = self.service._generate_recommendations(
            mappings=[],
            unmatched=[],
            chains=[],
            impact=impact,
        )
        assert any("critical" in r.lower() or "35" in r for r in recs)

    def test_low_impact_does_not_generate_risk_warning(self):
        impact = {"risk_level": "low", "traffic_impact_percentage": 1.0}
        recs = self.service._generate_recommendations(
            mappings=[],
            unmatched=[],
            chains=[],
            impact=impact,
        )
        risk_warnings = [r for r in recs if "critical" in r.lower() or "high" in r.lower()]
        assert len(risk_warnings) == 0
