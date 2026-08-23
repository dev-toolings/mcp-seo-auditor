"""Tests for PrioritiesService — quick_wins and priority_matrix."""

import pytest

from app.services.ai.priorities import (
    EXPECTED_CTR_BY_POSITION,
    PrioritiesService,
    _expected_ctr,
    _expected_page1_ctr,
)

# ─── Fixtures ──────────────────────────────────────────


class FakeAI:
    """Minimal AIAnalyzer stub."""

    @property
    def ai_available(self) -> bool:
        return False

    llm = None


class FakeGSC:
    """Mock GSC service returning controlled data."""

    def __init__(self, rows_current=None, rows_previous=None):
        self._rows_current = rows_current or []
        self._rows_previous = rows_previous or []
        self._call_count = 0

    @property
    def is_credentials_available(self) -> bool:
        return True

    async def get_advanced_search_analytics(self, **kwargs):
        self._call_count += 1
        # First call = current period, second call = previous period
        rows = self._rows_current if self._call_count <= 1 else self._rows_previous
        return {
            "site_url": kwargs.get("site_url", ""),
            "rows": rows,
            "count": len(rows),
        }


class FakeGSCUnavailable:
    """GSC stub with no credentials."""

    @property
    def is_credentials_available(self) -> bool:
        return False


MOCK_QUERIES_CURRENT = [
    # Striking distance: pos 12.3
    {
        "keys": ["seo audit tool", "https://example.com/audit"],
        "clicks": 50,
        "impressions": 1000,
        "ctr": 5.0,  # already in % from get_advanced_search_analytics
        "position": 12.3,
    },
    # Good position, decent CTR — not a problem
    {
        "keys": ["site audit", "https://example.com/site-audit"],
        "clicks": 200,
        "impressions": 5000,
        "ctr": 4.0,
        "position": 5.1,
    },
    # Striking distance: pos 18.7, low CTR
    {
        "keys": ["seo checker", "https://example.com/checker"],
        "clicks": 5,
        "impressions": 800,
        "ctr": 0.6,
        "position": 18.7,
    },
    # Top 10 with terrible CTR (meta opportunity)
    {
        "keys": ["best seo tool", "https://example.com/best"],
        "clicks": 10,
        "impressions": 2000,
        "ctr": 0.5,
        "position": 3.2,
    },
    # Low impressions, should be filtered out
    {
        "keys": ["obscure keyword", "https://example.com/obscure"],
        "clicks": 0,
        "impressions": 3,
        "ctr": 0.0,
        "position": 15.0,
    },
]

MOCK_QUERIES_PREVIOUS = [
    # "seo audit tool" had more clicks before → declining
    {
        "keys": ["seo audit tool", "https://example.com/audit"],
        "clicks": 100,
        "impressions": 1200,
        "ctr": 8.3,
        "position": 11.0,
    },
    {
        "keys": ["site audit", "https://example.com/site-audit"],
        "clicks": 180,
        "impressions": 4500,
        "ctr": 4.0,
        "position": 5.5,
    },
    {
        "keys": ["seo checker", "https://example.com/checker"],
        "clicks": 8,
        "impressions": 900,
        "ctr": 0.9,
        "position": 19.0,
    },
]


@pytest.fixture
def service_no_gsc():
    return PrioritiesService(ai_analyzer=FakeAI(), gsc_service=None)


@pytest.fixture
def service_gsc_unavailable():
    return PrioritiesService(ai_analyzer=FakeAI(), gsc_service=FakeGSCUnavailable())


@pytest.fixture
def service_with_gsc():
    gsc = FakeGSC(
        rows_current=MOCK_QUERIES_CURRENT,
        rows_previous=MOCK_QUERIES_PREVIOUS,
    )
    return PrioritiesService(ai_analyzer=FakeAI(), gsc_service=gsc)


@pytest.fixture
def service_with_gsc_no_previous():
    gsc = FakeGSC(
        rows_current=MOCK_QUERIES_CURRENT,
        rows_previous=[],
    )
    return PrioritiesService(ai_analyzer=FakeAI(), gsc_service=gsc)


# ─── Helper function tests ────────────────────────────


def test_expected_ctr_known_positions():
    assert _expected_ctr(1) == 0.30
    assert _expected_ctr(10) == 0.018
    assert _expected_ctr(20) == 0.002


def test_expected_ctr_out_of_range():
    # Clamps to 1-20 range
    assert _expected_ctr(0.5) == EXPECTED_CTR_BY_POSITION[1]
    assert _expected_ctr(25) == EXPECTED_CTR_BY_POSITION[20]


def test_expected_page1_ctr():
    # Position 12 should estimate target around pos 7
    ctr = _expected_page1_ctr(12.0)
    assert ctr > 0
    assert ctr >= _expected_ctr(10)  # Should be better than pos 10


# ─── quick_wins without GSC ───────────────────────────


@pytest.mark.asyncio
async def test_quick_wins_no_gsc(service_no_gsc):
    result = await service_no_gsc.quick_wins("https://example.com")
    assert "error" in result
    assert "GSC credentials" in result["error"]
    assert result["striking_distance"] == []
    assert result["low_ctr"] == []
    assert result["declining"] == []
    assert result["meta_opportunities"] == []
    assert result["total_opportunities"] == 0
    assert result["estimated_click_gain"] == 0
    assert result["ai_enhanced"] is False


@pytest.mark.asyncio
async def test_quick_wins_gsc_unavailable(service_gsc_unavailable):
    result = await service_gsc_unavailable.quick_wins("https://example.com")
    assert "error" in result
    assert result["ai_enhanced"] is False


# ─── quick_wins with mock GSC data ────────────────────


@pytest.mark.asyncio
async def test_quick_wins_striking_distance(service_with_gsc, monkeypatch):
    # Bypass gsc_resolve
    async def mock_resolve(url):
        return url

    monkeypatch.setattr(
        "app.services.ai.priorities.PrioritiesService._resolve_site_url",
        lambda self, url: mock_resolve(url),
    )

    result = await service_with_gsc.quick_wins("https://example.com")

    assert "error" not in result
    assert len(result["striking_distance"]) >= 1

    # "seo audit tool" at pos 12.3 should be in striking distance
    queries = [s["query"] for s in result["striking_distance"]]
    assert "seo audit tool" in queries

    # "seo checker" at pos 18.7 should also be there
    assert "seo checker" in queries

    # "site audit" at pos 5.1 should NOT be in striking distance
    assert "site audit" not in queries

    # Each entry should have expected keys
    entry = result["striking_distance"][0]
    assert "query" in entry
    assert "page" in entry
    assert "position" in entry
    assert "estimated_click_gain" in entry
    assert entry["estimated_click_gain"] >= 0


@pytest.mark.asyncio
async def test_quick_wins_declining(service_with_gsc, monkeypatch):
    async def mock_resolve(url):
        return url

    monkeypatch.setattr(
        "app.services.ai.priorities.PrioritiesService._resolve_site_url",
        lambda self, url: mock_resolve(url),
    )

    result = await service_with_gsc.quick_wins("https://example.com")

    # "seo audit tool" dropped from 100 to 50 clicks (-50%)
    declining_queries = [d["query"] for d in result["declining"]]
    assert "seo audit tool" in declining_queries

    entry = [d for d in result["declining"] if d["query"] == "seo audit tool"][0]
    assert entry["click_change"] < 0
    assert entry["click_change_pct"] <= -30


@pytest.mark.asyncio
async def test_quick_wins_meta_opportunities(service_with_gsc, monkeypatch):
    async def mock_resolve(url):
        return url

    monkeypatch.setattr(
        "app.services.ai.priorities.PrioritiesService._resolve_site_url",
        lambda self, url: mock_resolve(url),
    )

    result = await service_with_gsc.quick_wins("https://example.com")

    # "best seo tool" at pos 3.2 with CTR 0.5% (expected ~10%) should be flagged
    meta_queries = [m["query"] for m in result["meta_opportunities"]]
    assert "best seo tool" in meta_queries


@pytest.mark.asyncio
async def test_quick_wins_no_declining_without_previous(service_with_gsc_no_previous, monkeypatch):
    async def mock_resolve(url):
        return url

    monkeypatch.setattr(
        "app.services.ai.priorities.PrioritiesService._resolve_site_url",
        lambda self, url: mock_resolve(url),
    )

    result = await service_with_gsc_no_previous.quick_wins("https://example.com")
    assert result["declining"] == []


@pytest.mark.asyncio
async def test_quick_wins_return_structure(service_with_gsc, monkeypatch):
    async def mock_resolve(url):
        return url

    monkeypatch.setattr(
        "app.services.ai.priorities.PrioritiesService._resolve_site_url",
        lambda self, url: mock_resolve(url),
    )

    result = await service_with_gsc.quick_wins("https://example.com")

    expected_keys = {
        "striking_distance",
        "low_ctr",
        "declining",
        "meta_opportunities",
        "summary",
        "total_opportunities",
        "estimated_click_gain",
        "ai_enhanced",
    }
    assert expected_keys.issubset(set(result.keys()))
    assert isinstance(result["total_opportunities"], int)
    assert isinstance(result["estimated_click_gain"], int)
    assert isinstance(result["summary"], str)
    assert result["ai_enhanced"] is False  # FakeAI has no LLM


# ─── priority_matrix without GSC ──────────────────────


@pytest.mark.asyncio
async def test_priority_matrix_no_gsc(service_no_gsc):
    result = await service_no_gsc.priority_matrix("https://example.com")
    assert "error" in result
    assert result["quick_wins"] == []
    assert result["strategic"] == []
    assert result["fill_ins"] == []
    assert result["deprioritize"] == []
    assert result["recommended_order"] == []
    assert result["ai_enhanced"] is False


# ─── priority_matrix with mock GSC data ───────────────


@pytest.mark.asyncio
async def test_priority_matrix_quadrants(service_with_gsc, monkeypatch):
    async def mock_resolve(url):
        return url

    monkeypatch.setattr(
        "app.services.ai.priorities.PrioritiesService._resolve_site_url",
        lambda self, url: mock_resolve(url),
    )

    result = await service_with_gsc.priority_matrix("https://example.com")

    assert "error" not in result

    # Should have opportunities classified
    total = (
        len(result["quick_wins"])
        + len(result["strategic"])
        + len(result["fill_ins"])
        + len(result["deprioritize"])
    )
    assert total > 0

    # "best seo tool" at pos 3.2 with bad CTR should be meta_optimization (effort=1)
    # → likely in quick_wins quadrant (low effort, high impact if impressions high)
    all_qw = result["quick_wins"]
    qw_queries = [o["query"] for o in all_qw]
    assert "best seo tool" in qw_queries, (
        f"Expected 'best seo tool' in quick_wins, got queries: {qw_queries}"
    )

    # Each opportunity should have effort_score and impact_score
    for quadrant_name in ["quick_wins", "strategic", "fill_ins", "deprioritize"]:
        for opp in result[quadrant_name]:
            assert "effort_score" in opp
            assert "impact_score" in opp
            assert "action" in opp
            assert 1 <= opp["effort_score"] <= 5
            assert 1 <= opp["impact_score"] <= 5


@pytest.mark.asyncio
async def test_priority_matrix_return_structure(service_with_gsc, monkeypatch):
    async def mock_resolve(url):
        return url

    monkeypatch.setattr(
        "app.services.ai.priorities.PrioritiesService._resolve_site_url",
        lambda self, url: mock_resolve(url),
    )

    result = await service_with_gsc.priority_matrix("https://example.com")

    expected_keys = {
        "quick_wins",
        "strategic",
        "fill_ins",
        "deprioritize",
        "recommended_order",
        "ai_enhanced",
    }
    assert expected_keys.issubset(set(result.keys()))
    assert isinstance(result["recommended_order"], list)
    assert result["ai_enhanced"] is False


@pytest.mark.asyncio
async def test_priority_matrix_recommended_order(service_with_gsc, monkeypatch):
    async def mock_resolve(url):
        return url

    monkeypatch.setattr(
        "app.services.ai.priorities.PrioritiesService._resolve_site_url",
        lambda self, url: mock_resolve(url),
    )

    result = await service_with_gsc.priority_matrix("https://example.com")

    # Recommended order should start with quick_wins actions
    if result["quick_wins"] and result["recommended_order"]:
        first_recommended = result["recommended_order"][0]
        qw_actions = [o["action"] for o in result["quick_wins"]]
        assert first_recommended in qw_actions


# ─── ai_enhanced flag ─────────────────────────────────


@pytest.mark.asyncio
async def test_ai_enhanced_false_when_no_llm(service_with_gsc, monkeypatch):
    async def mock_resolve(url):
        return url

    monkeypatch.setattr(
        "app.services.ai.priorities.PrioritiesService._resolve_site_url",
        lambda self, url: mock_resolve(url),
    )

    qw = await service_with_gsc.quick_wins("https://example.com")
    assert qw["ai_enhanced"] is False

    # Reset call count for second test
    service_with_gsc.gsc._call_count = 0
    pm = await service_with_gsc.priority_matrix("https://example.com")
    assert pm["ai_enhanced"] is False
