"""Site content score: mean of per-page scores, independent of site size."""

from app.models.issue import Issue
from app.services.content_validator import content_score


def _warning() -> Issue:
    return Issue(issue_type="title_too_long", severity="warning")


def test_score_does_not_collapse_on_large_sites():
    """159 pages, 68 of them with two warnings, score 97 instead of 0."""
    issues_by_page = [[_warning(), _warning()]] * 68 + [[]] * 91

    assert content_score(issues_by_page) == 97


def test_page_penalties_match_the_previous_single_page_scale():
    """One page keeps the historical 100 - 10/critical - 3/warning scale, floored at 0."""
    critical = Issue(issue_type="http_error", severity="critical")

    assert content_score([[critical, _warning()]]) == 87
    assert content_score([[critical] * 11]) == 0
    assert content_score([]) == 100
