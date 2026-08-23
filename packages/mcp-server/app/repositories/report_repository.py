"""SQLite repository for audit reports."""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import aiosqlite
from pydantic import BaseModel

from app.models.report import AuditReport, AuditType

logger = logging.getLogger(__name__)


def _json_default(value):
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


class ReportRepository:
    """Async SQLite repository for audit report persistence."""

    _SCHEMA = """
        CREATE TABLE IF NOT EXISTS audit_reports (
            audit_id TEXT PRIMARY KEY,
            audit_type TEXT NOT NULL,
            score INTEGER DEFAULT 0,
            total_urls INTEGER DEFAULT 0,
            issues_critical INTEGER DEFAULT 0,
            issues_warning INTEGER DEFAULT 0,
            issues TEXT DEFAULT '[]',
            recommendations TEXT DEFAULT '[]',
            metadata TEXT DEFAULT '{}',
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_audit_reports_expires
            ON audit_reports(expires_at);
        CREATE INDEX IF NOT EXISTS idx_audit_reports_type
            ON audit_reports(audit_type);
    """

    def __init__(
        self,
        db_path: str = "data/seo_auditor.db",
        retention_hours: int = 24,
    ):
        self.db_path = db_path
        self._retention_hours = retention_hours
        self._initialized = False
        self._db: Optional[aiosqlite.Connection] = None

    async def _get_db(self) -> aiosqlite.Connection:
        """Get or create a persistent database connection."""
        if self._db is None:
            from pathlib import Path

            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self._db = await aiosqlite.connect(self.db_path)
            await self._db.execute("PRAGMA journal_mode=WAL")
            self._db.row_factory = aiosqlite.Row
        return self._db

    async def initialize(self):
        """Create tables if they don't exist."""
        if self._initialized:
            return
        db = await self._get_db()
        await db.executescript(self._SCHEMA)
        await db.commit()
        self._initialized = True

    async def close(self):
        """Close the database connection."""
        if self._db is not None:
            await self._db.close()
            self._db = None
            self._initialized = False

    async def save(self, report: AuditReport) -> str:
        """Save a report and return its ID."""
        await self.initialize()
        db = await self._get_db()
        now = report.created_at
        expires_at = now + timedelta(hours=self._retention_hours)
        await db.execute(
            """INSERT OR REPLACE INTO audit_reports
               (audit_id, audit_type, score, total_urls,
                issues_critical, issues_warning, issues,
                recommendations, metadata, created_at, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                report.audit_id,
                report.audit_type.value,
                report.score,
                report.total_urls,
                report.issues_critical,
                report.issues_warning,
                json.dumps(report.issues, default=_json_default),
                json.dumps(report.recommendations, default=_json_default),
                json.dumps(report.metadata, default=_json_default),
                report.created_at.isoformat(),
                expires_at.isoformat(),
            ),
        )
        await db.commit()
        logger.info(f"Report saved: {report.audit_id}")
        return report.audit_id

    async def get(self, audit_id: str) -> Optional[AuditReport]:
        """Get a report by ID."""
        await self.initialize()
        db = await self._get_db()
        cursor = await db.execute(
            "SELECT * FROM audit_reports WHERE audit_id = ?",
            (audit_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return self._row_to_report(row)

    async def delete(self, audit_id: str) -> bool:
        """Delete a report. Returns True if deleted."""
        await self.initialize()
        db = await self._get_db()
        cursor = await db.execute(
            "DELETE FROM audit_reports WHERE audit_id = ?",
            (audit_id,),
        )
        await db.commit()
        deleted = cursor.rowcount > 0
        if deleted:
            logger.info(f"Report deleted: {audit_id}")
        return deleted

    async def list_all(self) -> list[AuditReport]:
        """List all non-expired reports."""
        await self.initialize()
        now = datetime.now(timezone.utc).isoformat()
        db = await self._get_db()
        cursor = await db.execute(
            "SELECT * FROM audit_reports WHERE expires_at > ? ORDER BY created_at DESC",
            (now,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_report(row) for row in rows]

    def _row_to_report(self, row) -> AuditReport:
        """Convert a database row to an AuditReport."""
        d = dict(row)
        return AuditReport(
            audit_id=d["audit_id"],
            audit_type=AuditType(d["audit_type"]),
            score=d["score"],
            total_urls=d["total_urls"],
            issues_critical=d["issues_critical"],
            issues_warning=d["issues_warning"],
            issues=json.loads(d["issues"]),
            recommendations=json.loads(d["recommendations"]),
            metadata=json.loads(d["metadata"]),
            created_at=datetime.fromisoformat(d["created_at"]),
        )
