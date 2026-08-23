"""Tests for CrawlRepository with temporary SQLite file."""

import os
import tempfile

import pytest

from app.repositories.crawl_repository import CrawlRepository


@pytest.fixture
async def repo():
    """Create a temporary file-based repository for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    r = CrawlRepository(db_path=path)
    await r.initialize()
    yield r
    await r.close()
    os.unlink(path)


async def test_create_session(repo):
    session_id = await repo.create_session("https://www.iautos.fr", total_urls=10)
    assert session_id
    session = await repo.get_session(session_id)
    assert session is not None
    assert session["site_url"] == "https://www.iautos.fr"
    assert session["status"] == "running"
    assert session["total_urls"] == 10
    assert session["crawled_urls"] == 0


async def test_update_progress(repo):
    session_id = await repo.create_session("https://www.iautos.fr", total_urls=5)
    await repo.update_progress(
        session_id, crawled_urls=3, current_url="https://www.iautos.fr/page3"
    )
    session = await repo.get_session(session_id)
    assert session["crawled_urls"] == 3
    assert session["current_url"] == "https://www.iautos.fr/page3"


async def test_finish_session(repo):
    session_id = await repo.create_session("https://www.iautos.fr", total_urls=5)
    await repo.finish_session(session_id, score=85, errors_count=1)
    session = await repo.get_session(session_id)
    assert session["status"] == "completed"
    assert session["score"] == 85
    assert session["errors_count"] == 1
    assert session["finished_at"] is not None


async def test_fail_session(repo):
    session_id = await repo.create_session("https://www.iautos.fr", total_urls=5)
    await repo.fail_session(session_id, "Connection timeout")
    session = await repo.get_session(session_id)
    assert session["status"] == "failed"
    assert session["finished_at"] is not None
    assert session["metadata"].get("error") == "Connection timeout"


async def test_save_and_get_pages(repo):
    session_id = await repo.create_session("https://www.iautos.fr", total_urls=2)
    await repo.save_page(
        session_id,
        {
            "url": "https://www.iautos.fr/",
            "status_code": 200,
            "title": "Home",
            "meta_description": "Welcome",
            "h1": "Homepage",
            "word_count": 500,
        },
    )
    await repo.save_page(
        session_id,
        {
            "url": "https://www.iautos.fr/about",
            "status_code": 200,
            "title": "About",
            "word_count": 300,
        },
    )

    result = await repo.get_pages(session_id)
    assert result["total"] == 2
    assert len(result["pages"]) == 2
    assert result["pages"][0]["url"] == "https://www.iautos.fr/"
    assert result["pages"][0]["title"] == "Home"


async def test_get_pages_pagination(repo):
    session_id = await repo.create_session("https://www.iautos.fr", total_urls=3)
    for i in range(3):
        await repo.save_page(
            session_id,
            {
                "url": f"https://www.iautos.fr/page{i}",
                "status_code": 200,
            },
        )

    result = await repo.get_pages(session_id, page=1, per_page=2)
    assert result["total"] == 3
    assert len(result["pages"]) == 2
    assert result["total_pages"] == 2

    result2 = await repo.get_pages(session_id, page=2, per_page=2)
    assert len(result2["pages"]) == 1


async def test_save_and_get_issues(repo):
    session_id = await repo.create_session("https://www.iautos.fr", total_urls=5)
    issues = [
        {
            "issue_type": "missing_title",
            "severity": "critical",
            "description": "2 pages missing title",
            "recommendation": "Add title tags",
            "urls": ["https://www.iautos.fr/a", "https://www.iautos.fr/b"],
        },
        {
            "issue_type": "thin_content",
            "severity": "warning",
            "description": "1 page with thin content",
            "recommendation": "Expand content",
            "urls": ["https://www.iautos.fr/a"],
        },
    ]
    await repo.save_issues(session_id, issues)

    result = await repo.get_issues(session_id)
    assert result["total"] == 2
    issues = result["issues"]
    assert len(issues) == 2
    # Sorted by severity ASC: critical < warning
    assert issues[0]["severity"] == "critical"
    assert issues[0]["urls"] == ["https://www.iautos.fr/a", "https://www.iautos.fr/b"]


async def test_list_sessions(repo):
    await repo.create_session("https://www.leboncoin.fr", total_urls=1)
    await repo.create_session("https://www.lacentrale.fr", total_urls=2)
    await repo.create_session("https://www.leboncoin.fr", total_urls=3)

    all_sessions = await repo.list_sessions()
    assert len(all_sessions) == 3

    filtered = await repo.list_sessions(site_url="https://www.leboncoin.fr")
    assert len(filtered) == 2

    limited = await repo.list_sessions(limit=1)
    assert len(limited) == 1


async def test_get_current(repo):
    # No running session
    current = await repo.get_current()
    assert current is None

    # Create a running session
    session_id = await repo.create_session("https://www.iautos.fr", total_urls=5)
    current = await repo.get_current()
    assert current is not None
    assert current["id"] == session_id

    # Finish it
    await repo.finish_session(session_id, score=90)
    current = await repo.get_current()
    assert current is None


async def test_get_trends(repo):
    # Create completed sessions with scores
    s1 = await repo.create_session("https://www.iautos.fr", total_urls=10)
    await repo.finish_session(s1, score=70)

    s2 = await repo.create_session("https://www.iautos.fr", total_urls=12)
    await repo.finish_session(s2, score=80)

    s3 = await repo.create_session("https://www.autoscout24.fr", total_urls=5)
    await repo.finish_session(s3, score=60)

    trends = await repo.get_trends("https://www.iautos.fr", days=90)
    assert len(trends) == 2
    assert trends[0]["score"] == 70
    assert trends[1]["score"] == 80


async def test_get_session_not_found(repo):
    result = await repo.get_session("nonexistent-id")
    assert result is None


async def test_save_issues_empty_list(repo):
    session_id = await repo.create_session("https://www.iautos.fr", total_urls=1)
    await repo.save_issues(session_id, [])
    result = await repo.get_issues(session_id)
    assert result["total"] == 0
    assert result["issues"] == []


async def test_session_metadata(repo):
    session_id = await repo.create_session(
        "https://www.iautos.fr", total_urls=5, metadata={"source": "mcp", "version": "1.0"}
    )
    session = await repo.get_session(session_id)
    assert session["metadata"]["source"] == "mcp"
    assert session["metadata"]["version"] == "1.0"
