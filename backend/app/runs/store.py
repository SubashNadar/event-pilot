"""SQLite persistence for planning runs, their event log and chat sessions.

`runs` is a projection of each LangGraph run (the checkpoint stays the source of
truth for graph state). `run_events` is an append-only log of every streamed
event: the SSE endpoint tails it, so a dropped connection or a page refresh can
replay from any sequence number.

Chat sessions get their own tables. One session holds many runs (first plan,
budget revisions, recovery retries), so runs carry a `session_id`.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.config import settings
from app.models.run import RunRecord

DB_PATH = Path(settings.data_dir) / "eventpilot.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_sessions (
    id TEXT PRIMARY KEY, event_id TEXT, user_id TEXT, title TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chat_messages (
    session_id TEXT NOT NULL, seq INTEGER NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL,
    run_id TEXT, created_at TEXT NOT NULL,
    PRIMARY KEY (session_id, seq)
);
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY, session_id TEXT, event_id TEXT NOT NULL, operation TEXT NOT NULL,
    status TEXT NOT NULL, trace_id TEXT, trace_url TEXT, error TEXT,
    pending TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS runs_by_event ON runs (event_id, created_at);
CREATE TABLE IF NOT EXISTS run_events (
    run_id TEXT NOT NULL, seq INTEGER NOT NULL, dedupe_key TEXT, payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (run_id, seq)
);
CREATE UNIQUE INDEX IF NOT EXISTS run_events_dedupe ON run_events (run_id, dedupe_key);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_run_storage() -> None:
    with _connection() as connection:
        connection.executescript(_SCHEMA)


def _to_record(row: sqlite3.Row, last_seq: int = 0) -> RunRecord:
    return RunRecord(
        id=row["id"], event_id=row["event_id"], session_id=row["session_id"], operation=row["operation"],
        status=row["status"], trace_id=row["trace_id"], trace_url=row["trace_url"], error=row["error"],
        created_at=datetime.fromisoformat(row["created_at"]), updated_at=datetime.fromisoformat(row["updated_at"]),
        last_seq=last_seq,
    )


def create_run(event_id: str, operation: str, session_id: str | None = None) -> str:
    run_id = uuid4().hex
    now = _now()
    with _connection() as connection:
        connection.execute(
            "INSERT INTO runs (id, session_id, event_id, operation, status, pending, created_at, updated_at) VALUES (?, ?, ?, ?, 'queued', '{}', ?, ?)",
            (run_id, session_id, event_id, operation, now, now),
        )
    return run_id


def update_run(run_id: str, **fields: Any) -> None:
    allowed = {"status", "trace_id", "trace_url", "error"}
    sets = {key: value for key, value in fields.items() if key in allowed}
    if not sets:
        return
    assignments = ", ".join(f"{key} = ?" for key in sets)
    with _connection() as connection:
        connection.execute(f"UPDATE runs SET {assignments}, updated_at = ? WHERE id = ?", (*sets.values(), _now(), run_id))


def get_run(run_id: str) -> RunRecord | None:
    with _connection() as connection:
        row = connection.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        last = connection.execute("SELECT COALESCE(MAX(seq), 0) FROM run_events WHERE run_id = ?", (run_id,)).fetchone()[0]
    return _to_record(row, last)


def latest_run_for_event(event_id: str) -> RunRecord | None:
    with _connection() as connection:
        row = connection.execute("SELECT id FROM runs WHERE event_id = ? ORDER BY created_at DESC LIMIT 1", (event_id,)).fetchone()
    return get_run(row["id"]) if row else None


INTERRUPTED_MESSAGE = "The server restarted while this run was in progress. Start a new run to continue."


def mark_interrupted_runs() -> list[str]:
    """Runs left 'running' by a stopped process can't continue: mark them as errors.

    Paused runs are fine: their state is in the checkpoint and they resume normally.
    """
    with _connection() as connection:
        rows = connection.execute("SELECT id FROM runs WHERE status IN ('queued', 'running')").fetchall()
        connection.execute(
            "UPDATE runs SET status = 'error', error = ?, updated_at = ? WHERE status IN ('queued', 'running')",
            (INTERRUPTED_MESSAGE, _now()),
        )
    return [row["id"] for row in rows]


# Pending recovery choices: when several steps fail in the same superstep, the
# graph can only resume once every pending step has an answer.

def get_pending_choices(run_id: str) -> dict[str, Any]:
    with _connection() as connection:
        row = connection.execute("SELECT pending FROM runs WHERE id = ?", (run_id,)).fetchone()
    return json.loads(row["pending"] or "{}") if row else {}


def set_pending_choices(run_id: str, pending: dict[str, Any]) -> None:
    with _connection() as connection:
        connection.execute("UPDATE runs SET pending = ?, updated_at = ? WHERE id = ?", (json.dumps(pending), _now(), run_id))


def append_event(run_id: str, payload: dict[str, Any], dedupe_key: str | None = None) -> int | None:
    """Append an event; returns its sequence number, or None if it was a duplicate.

    LangGraph re-runs a node's code from the top when a paused run resumes, so a
    node can emit the same event twice. The dedupe key drops the repeat.
    """
    with _connection() as connection:
        if dedupe_key and connection.execute(
            "SELECT 1 FROM run_events WHERE run_id = ? AND dedupe_key = ?", (run_id, dedupe_key)
        ).fetchone():
            return None
        seq = connection.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM run_events WHERE run_id = ?", (run_id,)).fetchone()[0]
        connection.execute(
            "INSERT INTO run_events (run_id, seq, dedupe_key, payload, created_at) VALUES (?, ?, ?, ?, ?)",
            (run_id, seq, dedupe_key, json.dumps(payload, default=str), _now()),
        )
    return seq


def events_after(run_id: str, after_seq: int = 0) -> list[tuple[int, dict[str, Any]]]:
    with _connection() as connection:
        rows = connection.execute(
            "SELECT seq, payload FROM run_events WHERE run_id = ? AND seq > ? ORDER BY seq", (run_id, after_seq)
        ).fetchall()
    return [(row["seq"], json.loads(row["payload"])) for row in rows]


# Chat sessions (persistence endpoints arrive with RemainingPlan step 3).

def create_chat_session(event_id: str | None, title: str, user_id: str | None = None) -> str:
    session_id = uuid4().hex
    now = _now()
    with _connection() as connection:
        connection.execute(
            "INSERT INTO chat_sessions (id, event_id, user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, event_id, user_id, title, now, now),
        )
    return session_id


def append_chat_message(session_id: str, role: str, content: str, run_id: str | None = None) -> int:
    with _connection() as connection:
        seq = connection.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM chat_messages WHERE session_id = ?", (session_id,)).fetchone()[0]
        connection.execute(
            "INSERT INTO chat_messages (session_id, seq, role, content, run_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, seq, role, content, run_id, _now()),
        )
        connection.execute("UPDATE chat_sessions SET updated_at = ? WHERE id = ?", (_now(), session_id))
    return seq
