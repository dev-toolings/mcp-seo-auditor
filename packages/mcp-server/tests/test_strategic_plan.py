"""Tests for strategic plan service."""

import pytest

from app.services.ai.strategic_plan import StrategicPlanService


class TestStrategicPlanService:
    def setup_method(self):
        self.service = StrategicPlanService()

    @pytest.mark.asyncio
    async def test_generate_empty_data(self):
        result = await self.service.generate({})
        assert "roadmap" in result
        assert "cross_correlation" in result
        assert result["ai_enhanced"] is False

    @pytest.mark.asyncio
    async def test_generate_with_issues(self):
        data = {
            "sitemap": {
                "score": 60,
                "issues_critical": 3,
                "issues": [
                    {"type": "duplicate", "severity": "critical", "description": "Duplicate URLs"},
                ],
            },
            "content": {
                "score": 50,
                "pages_with_issues": 5,
                "pages": [
                    {
                        "url": "https://www.iautos.fr/thin",
                        "word_count": 20,
                        "status": 200,
                        "issues": [],
                    },
                ],
            },
            "technical": {
                "canonical_issues": [{"url": "https://www.iautos.fr/dup", "issue": "Mismatch"}],
                "meta_robots_issues": [],
            },
            "internal_links": {
                "orphan_pages": ["https://www.iautos.fr/orphan"],
                "broken_internal_links": [
                    {"target": "https://www.iautos.fr/404", "source": "https://www.iautos.fr/page"}
                ],
            },
            "structured_data": {
                "results": [
                    {"url": "https://www.iautos.fr", "valid_schemas": 0},
                ]
            },
        }
        result = await self.service.generate(data, business_context="E-commerce fashion")

        roadmap = result["roadmap"]
        assert "30_days" in roadmap
        assert "60_days" in roadmap
        assert "90_days" in roadmap

        # 30-day phase should have critical fixes
        phase_30 = roadmap["30_days"]
        assert phase_30["action_count"] > 0
        actions_30 = phase_30["actions"]
        assert any(a["priority"] == "critical" for a in actions_30)

        # Dependencies should exist
        assert len(result["dependency_map"]) > 0

        # Milestones
        assert len(result["milestones"]) > 0

    @pytest.mark.asyncio
    async def test_generate_healthy_site(self):
        """Healthy site should have fewer actions."""
        data = {
            "sitemap": {"score": 95, "issues_critical": 0, "issues": []},
            "content": {"score": 90, "pages_with_issues": 0, "pages": []},
            "technical": {"canonical_issues": [], "meta_robots_issues": []},
            "internal_links": {"orphan_pages": [], "broken_internal_links": []},
            "structured_data": {
                "results": [
                    {"url": "https://www.iautos.fr", "valid_schemas": 2},
                ]
            },
        }
        result = await self.service.generate(data)
        roadmap = result["roadmap"]

        # Should have fewer urgent actions
        phase_30 = roadmap["30_days"]
        critical_actions = [a for a in phase_30["actions"] if a.get("priority") == "critical"]
        assert len(critical_actions) == 0

    def test_check_action_relevance_critical(self):
        data = {
            "sitemap": {"issues_critical": 5},
        }
        action = {"id": "fix_critical_technical", "category": "technical"}
        result = self.service._check_action_relevance(action, data)
        assert result["relevant"] is True
        assert result["priority"] == "critical"

    def test_check_action_relevance_not_relevant(self):
        data = {
            "sitemap": {"issues_critical": 0},
        }
        action = {"id": "fix_critical_technical", "category": "technical"}
        result = self.service._check_action_relevance(action, data)
        assert result["relevant"] is False

    def test_check_action_relevance_broken_links(self):
        data = {
            "internal_links": {
                "broken_internal_links": [{"target": "https://www.leboncoin.fr/404"}],
            }
        }
        action = {"id": "fix_broken_links", "category": "links"}
        result = self.service._check_action_relevance(action, data)
        assert result["relevant"] is True

    def test_build_dependency_map(self):
        actions = [
            {"id": "a", "depends_on": []},
            {"id": "b", "depends_on": ["a"]},
            {"id": "c", "depends_on": ["a", "b"]},
        ]
        deps = self.service._build_dependency_map(actions)
        assert len(deps) == 3

    def test_calculate_milestones(self):
        roadmap = {
            "30_days": {"action_count": 3, "actions": []},
            "60_days": {"action_count": 2, "actions": []},
            "90_days": {"action_count": 2, "actions": []},
        }
        milestones = self.service._calculate_milestones({}, roadmap)
        assert len(milestones) == 3
        assert milestones[0]["phase"] == "30 days"
