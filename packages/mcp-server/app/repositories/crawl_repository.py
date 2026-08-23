"""SQLite repository for crawl tracking."""

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import aiosqlite

from app.core.config import settings

logger = logging.getLogger(__name__)


class CrawlRepository:
    """Async SQLite repository for crawl session persistence."""

    _SCHEMA = """
        CREATE TABLE IF NOT EXISTS crawl_sessions (
            id TEXT PRIMARY KEY,
            site_url TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT NOT NULL DEFAULT 'running',
            total_urls INTEGER DEFAULT 0,
            crawled_urls INTEGER DEFAULT 0,
            errors_count INTEGER DEFAULT 0,
            score INTEGER,
            current_url TEXT,
            metadata TEXT
        );

        CREATE TABLE IF NOT EXISTS crawl_pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            crawl_id TEXT NOT NULL REFERENCES crawl_sessions(id) ON DELETE CASCADE,
            url TEXT NOT NULL,
            status_code INTEGER NOT NULL,
            title TEXT,
            meta_description TEXT,
            h1 TEXT,
            word_count INTEGER DEFAULT 0,
            canonical_url TEXT,
            meta_robots TEXT,
            internal_links_count INTEGER DEFAULT 0,
            structured_data_count INTEGER DEFAULT 0,
            item_count INTEGER,
            error TEXT,
            crawled_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS crawl_issues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            crawl_id TEXT NOT NULL REFERENCES crawl_sessions(id) ON DELETE CASCADE,
            issue_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            description TEXT NOT NULL,
            recommendation TEXT NOT NULL,
            urls TEXT NOT NULL DEFAULT '[]'
        );

        CREATE TABLE IF NOT EXISTS url_inspections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site_url TEXT NOT NULL,
            page_url TEXT NOT NULL,
            verdict TEXT,
            coverage_state TEXT,
            last_crawl TEXT,
            page_fetch TEXT,
            robots_txt_state TEXT,
            indexing_state TEXT,
            google_canonical TEXT,
            user_canonical TEXT,
            rich_results TEXT,
            inspected_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            UNIQUE(site_url, page_url)
        );

        CREATE TABLE IF NOT EXISTS gsc_quota_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            site_url TEXT NOT NULL,
            requests_used INTEGER DEFAULT 0,
            UNIQUE(date, site_url)
        );

        CREATE INDEX IF NOT EXISTS idx_crawl_pages_crawl_id ON crawl_pages(crawl_id);
        CREATE INDEX IF NOT EXISTS idx_crawl_issues_crawl_id ON crawl_issues(crawl_id);
        CREATE INDEX IF NOT EXISTS idx_crawl_sessions_site_url ON crawl_sessions(site_url);
        CREATE INDEX IF NOT EXISTS idx_crawl_sessions_status ON crawl_sessions(status);
        CREATE INDEX IF NOT EXISTS idx_url_inspections_lookup ON url_inspections(site_url, page_url);
        CREATE INDEX IF NOT EXISTS idx_url_inspections_expires ON url_inspections(expires_at);
        CREATE INDEX IF NOT EXISTS idx_gsc_quota_date ON gsc_quota_usage(date, site_url);

        CREATE TABLE IF NOT EXISTS keyword_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site_url TEXT NOT NULL,
            keyword TEXT NOT NULL,
            position REAL,
            url TEXT,
            title TEXT,
            date TEXT NOT NULL,
            source TEXT DEFAULT 'serp_scrape',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_kp_lookup
            ON keyword_positions(site_url, keyword, date);
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or settings.SQLITE_DB_PATH
        self._initialized = False
        self._db: Optional[aiosqlite.Connection] = None

    async def initialize(self):
        """Create tables if they don't exist."""
        if self._initialized:
            return
        db = await self._get_db()
        await db.executescript(self._SCHEMA)
        await db.commit()
        self._initialized = True

    async def _get_db(self) -> aiosqlite.Connection:
        """Get or create a persistent database connection."""
        if self._db is None:
            from pathlib import Path

            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self._db = await aiosqlite.connect(self.db_path)
            await self._db.execute("PRAGMA journal_mode=WAL")
            await self._db.execute("PRAGMA foreign_keys=ON")
            self._db.row_factory = aiosqlite.Row
        return self._db

    async def close(self):
        """Close the database connection."""
        if self._db is not None:
            await self._db.close()
            self._db = None
            self._initialized = False

    async def create_session(
        self, site_url: str, total_urls: int, metadata: Optional[dict] = None
    ) -> str:
        """Create a new crawl session. Returns session ID."""
        session_id = str(uuid.uuid4())
        db = await self._get_db()
        await db.execute(
            """INSERT INTO crawl_sessions
               (id, site_url, started_at, status, total_urls, metadata)
               VALUES (?, ?, ?, 'running', ?, ?)""",
            (
                session_id,
                site_url,
                datetime.now(timezone.utc).isoformat(),
                total_urls,
                json.dumps(metadata or {}),
            ),
        )
        await db.commit()
        logger.info(f"Created crawl session {session_id} for {site_url}")
        return session_id

    async def update_progress(
        self, session_id: str, crawled_urls: int, current_url: Optional[str] = None
    ):
        """Update crawl progress."""
        db = await self._get_db()
        await db.execute(
            """UPDATE crawl_sessions
               SET crawled_urls = ?, current_url = ?
               WHERE id = ?""",
            (crawled_urls, current_url, session_id),
        )
        await db.commit()

    async def finish_session(
        self, session_id: str, score: Optional[int] = None, errors_count: int = 0
    ):
        """Mark a crawl session as completed."""
        db = await self._get_db()
        await db.execute(
            """UPDATE crawl_sessions
               SET status = 'completed', finished_at = ?, score = ?, errors_count = ?
               WHERE id = ?""",
            (datetime.now(timezone.utc).isoformat(), score, errors_count, session_id),
        )
        await db.commit()
        logger.info(f"Finished crawl session {session_id} with score {score}")

    async def fail_session(self, session_id: str, error: str):
        """Mark a crawl session as failed."""
        db = await self._get_db()
        await db.execute(
            """UPDATE crawl_sessions
               SET status = 'failed', finished_at = ?,
                   metadata = json_set(COALESCE(metadata, '{}'), '$.error', ?)
               WHERE id = ?""",
            (datetime.now(timezone.utc).isoformat(), error, session_id),
        )
        await db.commit()
        logger.warning(f"Crawl session {session_id} failed: {error}")

    async def save_page(self, crawl_id: str, page_data: dict):
        """Save a crawled page."""
        db = await self._get_db()
        await db.execute(
            """INSERT INTO crawl_pages
               (crawl_id, url, status_code, title, meta_description, h1,
                word_count, canonical_url, meta_robots, internal_links_count,
                structured_data_count, item_count, error, crawled_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                crawl_id,
                page_data["url"],
                page_data["status_code"],
                page_data.get("title"),
                page_data.get("meta_description"),
                page_data.get("h1"),
                page_data.get("word_count", 0),
                page_data.get("canonical_url"),
                page_data.get("meta_robots"),
                page_data.get("internal_links_count", 0),
                page_data.get("structured_data_count", 0),
                page_data.get("item_count"),
                page_data.get("error"),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        await db.commit()

    async def save_issues(self, crawl_id: str, issues: list[dict]):
        """Save crawl issues."""
        if not issues:
            return
        db = await self._get_db()
        await db.executemany(
            """INSERT INTO crawl_issues
               (crawl_id, issue_type, severity, description, recommendation, urls)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [
                (
                    crawl_id,
                    issue["issue_type"],
                    issue["severity"],
                    issue["description"],
                    issue["recommendation"],
                    json.dumps(issue.get("urls", [])),
                )
                for issue in issues
            ],
        )
        await db.commit()

    async def get_session(self, session_id: str) -> Optional[dict]:
        """Get a crawl session by ID."""
        db = await self._get_db()
        cursor = await db.execute("SELECT * FROM crawl_sessions WHERE id = ?", (session_id,))
        row = await cursor.fetchone()
        if not row:
            return None
        return self._row_to_dict(row)

    async def get_current(self) -> Optional[dict]:
        """Get the currently running crawl session."""
        db = await self._get_db()
        cursor = await db.execute(
            "SELECT * FROM crawl_sessions WHERE status = 'running' ORDER BY started_at DESC LIMIT 1"
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return self._row_to_dict(row)

    async def get_pages(self, crawl_id: str, page: int = 1, per_page: int = 50) -> dict[str, Any]:
        """Get pages for a crawl session with pagination."""
        offset = (page - 1) * per_page
        db = await self._get_db()

        cursor = await db.execute(
            "SELECT COUNT(*) FROM crawl_pages WHERE crawl_id = ?", (crawl_id,)
        )
        row = await cursor.fetchone()
        total = row[0] if row else 0

        cursor = await db.execute(
            """SELECT * FROM crawl_pages WHERE crawl_id = ?
               ORDER BY crawled_at ASC LIMIT ? OFFSET ?""",
            (crawl_id, per_page, offset),
        )
        rows = await cursor.fetchall()

        return {
            "pages": [self._row_to_dict(r) for r in rows],
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page,
        }

    async def get_issues(self, crawl_id: str, page: int = 1, per_page: int = 20) -> dict[str, Any]:
        """Get issues for a crawl session with pagination."""
        offset = (page - 1) * per_page
        db = await self._get_db()

        cursor = await db.execute(
            "SELECT COUNT(*) FROM crawl_issues WHERE crawl_id = ?", (crawl_id,)
        )
        row = await cursor.fetchone()
        total = row[0] if row else 0

        cursor = await db.execute(
            """SELECT * FROM crawl_issues WHERE crawl_id = ?
               ORDER BY severity ASC, id ASC LIMIT ? OFFSET ?""",
            (crawl_id, per_page, offset),
        )
        rows = await cursor.fetchall()
        result = []
        for r in rows:
            d = self._row_to_dict(r)
            d["urls"] = json.loads(d.get("urls", "[]"))
            result.append(d)

        return {
            "issues": result,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page,
        }

    async def list_sessions(self, site_url: Optional[str] = None, limit: int = 20) -> list[dict]:
        """List crawl sessions, optionally filtered by site_url."""
        db = await self._get_db()
        if site_url:
            cursor = await db.execute(
                """SELECT * FROM crawl_sessions WHERE site_url = ?
                   ORDER BY started_at DESC LIMIT ?""",
                (site_url, limit),
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM crawl_sessions ORDER BY started_at DESC LIMIT ?",
                (limit,),
            )
        rows = await cursor.fetchall()
        return [self._row_to_dict(r) for r in rows]

    async def get_trends(self, site_url: str, days: int = 90) -> list[dict]:
        """Get score trends over time for a site."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        db = await self._get_db()
        cursor = await db.execute(
            """SELECT id, started_at, finished_at, score, total_urls, errors_count
               FROM crawl_sessions
               WHERE site_url = ? AND status = 'completed'
                 AND started_at >= ? AND score IS NOT NULL
               ORDER BY started_at ASC""",
            (site_url, cutoff),
        )
        rows = await cursor.fetchall()
        return [self._row_to_dict(r) for r in rows]

    # ─── URL Inspection cache ────────────────────────

    async def get_cached_inspection(self, site_url: str, page_url: str) -> Optional[dict]:
        """Return cached inspection result if not expired, else None."""
        now = datetime.now(timezone.utc).isoformat()
        db = await self._get_db()
        cursor = await db.execute(
            """SELECT * FROM url_inspections
               WHERE site_url = ? AND page_url = ? AND expires_at > ?""",
            (site_url, page_url, now),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        if d.get("rich_results"):
            try:
                d["rich_results"] = json.loads(d["rich_results"])
            except (json.JSONDecodeError, TypeError):
                pass
        return d

    async def cache_inspection(self, site_url: str, page_url: str, result: dict) -> None:
        """Upsert an inspection result with 7-day TTL."""
        now = datetime.now(timezone.utc)
        inspected_at = now.isoformat()
        expires_at = (now + timedelta(days=7)).isoformat()
        rich_results = result.get("rich_results")
        if rich_results is not None:
            rich_results = json.dumps(rich_results)
        db = await self._get_db()
        await db.execute(
            """INSERT INTO url_inspections
               (site_url, page_url, verdict, coverage_state, last_crawl,
                page_fetch, robots_txt_state, indexing_state, google_canonical,
                user_canonical, rich_results, inspected_at, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(site_url, page_url) DO UPDATE SET
                verdict=excluded.verdict, coverage_state=excluded.coverage_state,
                last_crawl=excluded.last_crawl, page_fetch=excluded.page_fetch,
                robots_txt_state=excluded.robots_txt_state, indexing_state=excluded.indexing_state,
                google_canonical=excluded.google_canonical, user_canonical=excluded.user_canonical,
                rich_results=excluded.rich_results, inspected_at=excluded.inspected_at,
                expires_at=excluded.expires_at""",
            (
                site_url,
                page_url,
                result.get("verdict"),
                result.get("coverage_state"),
                result.get("last_crawl"),
                result.get("page_fetch"),
                result.get("robots_txt", result.get("robots_txt_state")),
                result.get("indexing_state"),
                result.get("google_canonical"),
                result.get("user_canonical"),
                rich_results,
                inspected_at,
                expires_at,
            ),
        )
        await db.commit()

    async def get_cached_inspections_batch(
        self, site_url: str, page_urls: list[str]
    ) -> dict[str, dict]:
        """Batch lookup of cached inspections — returns only non-expired entries."""
        if not page_urls:
            return {}
        now = datetime.now(timezone.utc).isoformat()
        db = await self._get_db()
        placeholders = ",".join("?" for _ in page_urls)
        cursor = await db.execute(
            f"""SELECT * FROM url_inspections
                WHERE site_url = ? AND page_url IN ({placeholders})
                  AND expires_at > ?""",
            (site_url, *page_urls, now),
        )
        rows = await cursor.fetchall()
        result: dict[str, dict] = {}
        for row in rows:
            d = dict(row)
            if d.get("rich_results"):
                try:
                    d["rich_results"] = json.loads(d["rich_results"])
                except (json.JSONDecodeError, TypeError):
                    pass
            result[d["page_url"]] = d
        return result

    async def get_quota_usage(self, site_url: str) -> int:
        """Return today's API request count for the given site."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        db = await self._get_db()
        cursor = await db.execute(
            "SELECT requests_used FROM gsc_quota_usage WHERE date = ? AND site_url = ?",
            (today, site_url),
        )
        row = await cursor.fetchone()
        return row[0] if row else 0

    async def increment_quota(self, site_url: str, count: int = 1) -> int:
        """Upsert today's quota counter and return new total."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        db = await self._get_db()
        await db.execute(
            """INSERT INTO gsc_quota_usage (date, site_url, requests_used)
               VALUES (?, ?, ?)
               ON CONFLICT(date, site_url) DO UPDATE SET
                requests_used = requests_used + excluded.requests_used""",
            (today, site_url, count),
        )
        await db.commit()
        cursor = await db.execute(
            "SELECT requests_used FROM gsc_quota_usage WHERE date = ? AND site_url = ?",
            (today, site_url),
        )
        row = await cursor.fetchone()
        return row[0] if row else count

    async def cleanup_expired_inspections(self) -> int:
        """Delete expired inspection rows. Returns count deleted."""
        now = datetime.now(timezone.utc).isoformat()
        db = await self._get_db()
        cursor = await db.execute("DELETE FROM url_inspections WHERE expires_at <= ?", (now,))
        await db.commit()
        return cursor.rowcount

    # ─── Keyword position tracking ─────────────────

    async def save_position(
        self,
        site_url: str,
        keyword: str,
        position: float | None,
        url: str | None = None,
        title: str | None = None,
        source: str = "serp_scrape",
    ) -> None:
        """Save a keyword position entry."""
        await self.initialize()
        db = await self._get_db()
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        await db.execute(
            """INSERT INTO keyword_positions
               (site_url, keyword, position, url, title, date, source)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (site_url, keyword, position, url, title, date, source),
        )
        await db.commit()

    async def get_position_history(
        self,
        site_url: str,
        keyword: str,
        days: int = 90,
    ) -> list[dict]:
        """Get position history for a keyword."""
        await self.initialize()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        db = await self._get_db()
        cursor = await db.execute(
            """SELECT date, position, url, title, source
               FROM keyword_positions
               WHERE site_url = ? AND keyword = ? AND date >= ?
               ORDER BY date ASC""",
            (site_url, keyword, cutoff),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_tracked_keywords(self, site_url: str) -> list[dict]:
        """Get all tracked keywords for a site with latest position."""
        await self.initialize()
        db = await self._get_db()
        cursor = await db.execute(
            """SELECT keyword,
                      MAX(date) as last_checked,
                      COUNT(*) as data_points
               FROM keyword_positions
               WHERE site_url = ?
               GROUP BY keyword
               ORDER BY keyword""",
            (site_url,),
        )
        rows = await cursor.fetchall()
        results = []
        for r in rows:
            d = dict(r)
            latest = await db.execute(
                """SELECT position, url FROM keyword_positions
                   WHERE site_url = ? AND keyword = ? AND date = ?""",
                (site_url, d["keyword"], d["last_checked"]),
            )
            latest_row = await latest.fetchone()
            if latest_row:
                d["current_position"] = latest_row[0]
                d["current_url"] = latest_row[1]
            results.append(d)
        return results

    async def get_position_dashboard(self, site_url: str, days: int = 90) -> dict:
        """Get a dashboard view of all keyword positions for a site."""
        await self.initialize()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        db = await self._get_db()

        cursor = await db.execute(
            """SELECT keyword,
                      MIN(position) as best_position,
                      AVG(position) as avg_position,
                      COUNT(*) as data_points,
                      MAX(date) as last_checked
               FROM keyword_positions
               WHERE site_url = ? AND date >= ?
                 AND position IS NOT NULL
               GROUP BY keyword
               ORDER BY avg_position ASC""",
            (site_url, cutoff),
        )
        rows = await cursor.fetchall()
        keywords = [dict(r) for r in rows]

        for kw in keywords:
            if kw.get("avg_position") is not None:
                kw["avg_position"] = round(kw["avg_position"], 1)

        top3 = sum(1 for k in keywords if k.get("best_position") and k["best_position"] <= 3)
        top10 = sum(1 for k in keywords if k.get("best_position") and k["best_position"] <= 10)
        top20 = sum(1 for k in keywords if k.get("best_position") and k["best_position"] <= 20)

        return {
            "site_url": site_url,
            "period_days": days,
            "total_tracked": len(keywords),
            "position_distribution": {
                "top_3": top3,
                "top_10": top10,
                "top_20": top20,
                "beyond_20": len(keywords) - top20,
            },
            "keywords": keywords,
        }

    def _row_to_dict(self, row) -> dict:
        """Convert a Row to a dict."""
        d = dict(row)
        if "metadata" in d and d["metadata"]:
            try:
                d["metadata"] = json.loads(d["metadata"])
            except (json.JSONDecodeError, TypeError):
                d["metadata"] = {}
        return d
