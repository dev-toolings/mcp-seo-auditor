"""SQLite persistence for autonomous SEO agent runs."""

import json
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from app.core.config import settings
from app.models.agent_run import AgentRun, AgentRunState


class AgentRunRepository:
    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS agent_runs (
        run_id TEXT PRIMARY KEY,
        workspace_path TEXT NOT NULL,
        state TEXT NOT NULL,
        phase TEXT NOT NULL,
        progress INTEGER NOT NULL,
        plan_hash TEXT,
        payload TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_active_workspace
        ON agent_runs(workspace_path)
        WHERE state NOT IN ('completed', 'failed', 'cancelled');
    CREATE INDEX IF NOT EXISTS idx_agent_runs_state ON agent_runs(state);
    CREATE TABLE IF NOT EXISTS agent_command_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL,
        phase TEXT NOT NULL,
        argv TEXT NOT NULL,
        exit_code INTEGER,
        stdout TEXT NOT NULL DEFAULT '',
        stderr TEXT NOT NULL DEFAULT '',
        started_at TEXT NOT NULL,
        finished_at TEXT,
        FOREIGN KEY(run_id) REFERENCES agent_runs(run_id) ON DELETE CASCADE
    );
    """

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or settings.SQLITE_DB_PATH
        self._db: aiosqlite.Connection | None = None

    async def _get_db(self) -> aiosqlite.Connection:
        if self._db is None:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self._db = await aiosqlite.connect(self.db_path)
            self._db.row_factory = aiosqlite.Row
            await self._db.execute("PRAGMA journal_mode=WAL")
            await self._db.execute("PRAGMA foreign_keys=ON")
            await self._db.executescript(self._SCHEMA)
            await self._db.commit()
        return self._db

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    async def create(self, run: AgentRun) -> None:
        db = await self._get_db()
        payload = run.model_dump_json()
        await db.execute(
            """INSERT INTO agent_runs
               (run_id, workspace_path, state, phase, progress, plan_hash,
                payload, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run.run_id,
                run.workspace_path,
                run.state.value,
                run.phase,
                run.progress,
                run.plan_hash,
                payload,
                run.created_at.isoformat(),
                run.updated_at.isoformat(),
            ),
        )
        await db.commit()

    async def save(self, run: AgentRun) -> None:
        run.updated_at = datetime.now(timezone.utc)
        db = await self._get_db()
        await db.execute(
            """UPDATE agent_runs
               SET state=?, phase=?, progress=?, plan_hash=?, payload=?, updated_at=?
               WHERE run_id=?""",
            (
                run.state.value,
                run.phase,
                run.progress,
                run.plan_hash,
                run.model_dump_json(),
                run.updated_at.isoformat(),
                run.run_id,
            ),
        )
        await db.commit()

    async def get(self, run_id: str) -> AgentRun | None:
        db = await self._get_db()
        cursor = await db.execute("SELECT payload FROM agent_runs WHERE run_id=?", (run_id,))
        row = await cursor.fetchone()
        return AgentRun.model_validate_json(row["payload"]) if row else None

    async def active_for_workspace(self, workspace_path: str) -> AgentRun | None:
        db = await self._get_db()
        cursor = await db.execute(
            """SELECT payload FROM agent_runs
               WHERE workspace_path=? AND state NOT IN ('completed', 'failed', 'cancelled')
               ORDER BY created_at DESC LIMIT 1""",
            (workspace_path,),
        )
        row = await cursor.fetchone()
        return AgentRun.model_validate_json(row["payload"]) if row else None

    async def resumable(self) -> list[AgentRun]:
        db = await self._get_db()
        states = (
            AgentRunState.QUEUED.value,
            AgentRunState.AUDITING.value,
            AgentRunState.PLANNING.value,
            AgentRunState.IMPLEMENTING.value,
            AgentRunState.VALIDATING.value,
            AgentRunState.REAUDITING.value,
            AgentRunState.REVIEWING.value,
            AgentRunState.COMMITTING.value,
            AgentRunState.PUSHING.value,
            AgentRunState.OPENING_PR.value,
        )
        placeholders = ",".join("?" for _ in states)
        cursor = await db.execute(
            f"SELECT payload FROM agent_runs WHERE state IN ({placeholders})", states
        )
        return [AgentRun.model_validate_json(row["payload"]) for row in await cursor.fetchall()]

    async def add_command_log(
        self,
        run_id: str,
        phase: str,
        argv: list[str],
        exit_code: int | None,
        stdout: str,
        stderr: str,
        started_at: datetime,
        finished_at: datetime | None,
    ) -> None:
        db = await self._get_db()
        await db.execute(
            """INSERT INTO agent_command_logs
               (run_id, phase, argv, exit_code, stdout, stderr, started_at, finished_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id,
                phase,
                json.dumps(argv),
                exit_code,
                stdout[-20_000:],
                stderr[-20_000:],
                started_at.isoformat(),
                finished_at.isoformat() if finished_at else None,
            ),
        )
        await db.commit()
