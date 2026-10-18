"""Minimal SQLite persistence for EventPilot event briefs and plans."""

import sqlite3
from pathlib import Path
from uuid import UUID

from app.core.config import settings
from app.models.event import EventBrief, EventPlan

DB_PATH = Path(settings.data_dir) / "eventpilot.db"


def _connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def initialize_storage() -> None:
    with _connection() as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        connection.execute("CREATE TABLE IF NOT EXISTS plans (event_id TEXT PRIMARY KEY, payload TEXT NOT NULL)")


def save_event(event: EventBrief) -> None:
    with _connection() as connection:
        connection.execute("INSERT OR REPLACE INTO events (id, payload) VALUES (?, ?)", (str(event.id), event.model_dump_json()))


def load_event(event_id: UUID) -> EventBrief | None:
    with _connection() as connection:
        row = connection.execute("SELECT payload FROM events WHERE id = ?", (str(event_id),)).fetchone()
    return EventBrief.model_validate_json(row[0]) if row else None


def list_events() -> list[EventBrief]:
    with _connection() as connection:
        rows = connection.execute("SELECT payload FROM events").fetchall()
    return sorted(
        (EventBrief.model_validate_json(row[0]) for row in rows),
        key=lambda event: event.created_at,
        reverse=True,
    )


def save_plan(plan: EventPlan) -> None:
    with _connection() as connection:
        connection.execute("INSERT OR REPLACE INTO plans (event_id, payload) VALUES (?, ?)", (str(plan.event_id), plan.model_dump_json()))


def load_plan(event_id: UUID) -> EventPlan | None:
    with _connection() as connection:
        row = connection.execute("SELECT payload FROM plans WHERE event_id = ?", (str(event_id),)).fetchone()
    return EventPlan.model_validate_json(row[0]) if row else None
