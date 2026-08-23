"""Scoring behavior for optional audit dimensions."""

from app.core.scoring import AuditScorer
from app.services.ai.full_audit import FullAuditService


def test_overall_score_renormalizes_missing_dimensions():
    """Missing optional dimensions must not count as zero-score failures."""
    score = AuditScorer.calculate_overall_score(
        {
            "technical": 100,
            "content": 100,
        }
    )

    assert score == 100


def test_overall_score_uses_all_measured_dimensions():
    """Measured dimensions still use their configured relative weights."""
    score = AuditScorer.calculate_overall_score(
        {
            "technical": 100,
            "content": 50,
        }
    )

    # Renormalized over technical(0.15) + content(0.20):
    # (100*0.15 + 50*0.20) / 0.35 = 71.42
    assert score == 71


def test_full_audit_scores_skip_unavailable_cwv_and_geo():
    """Full audit dimensions should omit unavailable optional checks."""
    service = FullAuditService(orchestrator=None, geo_analyzer=None, ai_analyzer=None)
    scores = service._calculate_dimension_scores(
        {
            "sitemap": {"score": 100},
            "technical": {"canonical_issues": [], "meta_robots_issues": []},
            "content": {"score": 100},
            "internal_links": {"orphan_pages": [], "broken_internal_links": []},
            "structured_data": {"results": [{"url": "https://example.com", "valid_schemas": 1}]},
            "cwv": None,
            "geo": None,
        }
    )

    assert scores == {
        "technical": 100,
        "content": 100,
        "links": 100,
        "schema": 100,
    }
    assert service._calculate_overall_score(scores) == 100
