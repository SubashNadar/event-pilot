"""Saved planner state that must survive navigation and restarts: unsaved brief drafts, and how many
change requests the owner has made at approval. Kept in one JSON file next to the other local data."""

import json
import threading
from pathlib import Path
from typing import Any

from app.core.config import settings

_LOCK = threading.Lock()


def _path() -> Path:
    return Path(settings.data_dir) / "ui-state.json"


def _load() -> dict[str, Any]:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    data.setdefault("drafts", {})
    data.setdefault("attempts", {})
    return data


def _save(data: dict[str, Any]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def get_draft(event_id: str) -> dict[str, Any] | None:
    with _LOCK:
        return _load()["drafts"].get(event_id)


def set_draft(event_id: str, draft: dict[str, Any]) -> None:
    with _LOCK:
        data = _load()
        data["drafts"][event_id] = draft
        _save(data)


def clear_draft(event_id: str) -> None:
    with _LOCK:
        data = _load()
        if data["drafts"].pop(event_id, None) is not None:
            _save(data)


# Change requests at approval are counted per event, across the edit runs they start, so a change that starts a new
# run doesn't reset the count. A fresh plan from the brief starts the count again.

def attempts(event_id: str) -> int:
    with _LOCK:
        return int(_load()["attempts"].get(event_id, 0))


def bump_attempts(event_id: str) -> int:
    with _LOCK:
        data = _load()
        data["attempts"][event_id] = int(data["attempts"].get(event_id, 0)) + 1
        _save(data)
        return data["attempts"][event_id]


def reset_attempts(event_id: str) -> None:
    with _LOCK:
        data = _load()
        if data["attempts"].pop(event_id, None) is not None:
            _save(data)
