"""SQLite-backed workflow state for the orchestrator.

Two tables:
- ``workflows`` — one row per user request, keyed by ``correlation_id``.
  Stores the most recent envelope JSON, the current step, and a status
  in {pending, in_progress, completed, failed, poisoned}.
- ``poison`` — append-only dead-letter table for envelopes that exceeded
  the retry budget.

The schema is small on purpose: the audit trail lives in the ndjson event
log, not in SQLite. SQLite is here so a crash mid-workflow leaves enough
state to resume. See docs/topology-decision.md for why we picked
orchestration over choreography and what that buys us.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = REPO_ROOT / "orchestrator" / "state.db"

WORKFLOW_STATUSES = {"pending", "in_progress", "completed", "failed", "poisoned"}


class WorkflowStore:
    """Tiny wrapper around sqlite3. One connection per process, guarded by a lock.

    Not designed for concurrent writers across processes — the orchestrator is
    a single process. See PLAN.md (Person 3, P3.1).
    """

    def __init__(self, path: str | Path = DEFAULT_DB_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(
            str(self.path), check_same_thread=False, isolation_level=None
        )
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS workflows (
                    correlation_id TEXT PRIMARY KEY,
                    step TEXT NOT NULL,
                    status TEXT NOT NULL,
                    user_request TEXT,
                    last_envelope_json TEXT,
                    final_response_json TEXT,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS poison (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    correlation_id TEXT NOT NULL,
                    envelope_json TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    ts REAL NOT NULL
                )
                """
            )

    @contextmanager
    def _cursor(self) -> Iterator[sqlite3.Cursor]:
        with self._lock:
            cur = self._conn.cursor()
            try:
                yield cur
            finally:
                cur.close()

    # ---------- workflows ----------

    def create(
        self,
        *,
        correlation_id: str,
        user_request: str,
        step: str = "received",
        status: str = "pending",
    ) -> None:
        assert status in WORKFLOW_STATUSES, status
        now = time.time()
        with self._cursor() as cur:
            cur.execute(
                """INSERT OR REPLACE INTO workflows
                   (correlation_id, step, status, user_request,
                    last_envelope_json, final_response_json, attempts,
                    created_at, updated_at)
                   VALUES (?, ?, ?, ?, NULL, NULL, 0, ?, ?)""",
                (correlation_id, step, status, user_request, now, now),
            )

    def update(
        self,
        correlation_id: str,
        *,
        step: Optional[str] = None,
        status: Optional[str] = None,
        last_envelope: Optional[dict[str, Any]] = None,
        final_response: Optional[dict[str, Any]] = None,
        bump_attempt: bool = False,
    ) -> None:
        if status is not None:
            assert status in WORKFLOW_STATUSES, status
        sets: list[str] = []
        args: list[Any] = []
        if step is not None:
            sets.append("step = ?")
            args.append(step)
        if status is not None:
            sets.append("status = ?")
            args.append(status)
        if last_envelope is not None:
            sets.append("last_envelope_json = ?")
            args.append(json.dumps(last_envelope, default=str))
        if final_response is not None:
            sets.append("final_response_json = ?")
            args.append(json.dumps(final_response, default=str))
        if bump_attempt:
            sets.append("attempts = attempts + 1")
        sets.append("updated_at = ?")
        args.append(time.time())
        args.append(correlation_id)
        with self._cursor() as cur:
            cur.execute(
                f"UPDATE workflows SET {', '.join(sets)} WHERE correlation_id = ?",
                args,
            )

    def get(self, correlation_id: str) -> Optional[dict[str, Any]]:
        with self._cursor() as cur:
            row = cur.execute(
                "SELECT * FROM workflows WHERE correlation_id = ?",
                (correlation_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_in_progress(self) -> list[dict[str, Any]]:
        with self._cursor() as cur:
            rows = cur.execute(
                "SELECT * FROM workflows WHERE status IN ('pending','in_progress') "
                "ORDER BY created_at"
            ).fetchall()
        return [dict(r) for r in rows]

    def list_recent(self, limit: int = 25) -> list[dict[str, Any]]:
        with self._cursor() as cur:
            rows = cur.execute(
                "SELECT * FROM workflows ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ---------- poison ----------

    def add_poison(
        self, *, correlation_id: str, envelope: dict[str, Any], reason: str
    ) -> None:
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO poison (correlation_id, envelope_json, reason, ts) "
                "VALUES (?, ?, ?, ?)",
                (
                    correlation_id,
                    json.dumps(envelope, default=str),
                    reason,
                    time.time(),
                ),
            )

    def list_poison(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._cursor() as cur:
            rows = cur.execute(
                "SELECT * FROM poison ORDER BY ts DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        with self._lock:
            self._conn.close()


__all__ = ["WorkflowStore", "WORKFLOW_STATUSES", "DEFAULT_DB_PATH"]
