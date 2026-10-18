"""Emit UI events from inside graph nodes and tasks.

Events travel through LangGraph's `custom` stream mode to the run manager, which
stores them in `run_events` and fans them out to SSE clients. Each event can
carry a dedupe key: when a paused run resumes, LangGraph re-runs the node's code
from the top, and the key stops the replayed events from reaching the UI twice.
"""

from typing import Any

from langgraph.config import get_config, get_stream_writer


def emit(event: dict[str, Any], dedupe: str | None = None) -> None:
    try:
        writer = get_stream_writer()
    except Exception:  # called outside a graph run (tests, legacy code paths)
        return
    writer({"event": event, "dedupe": dedupe})


def current_run_id() -> str | None:
    try:
        return get_config().get("configurable", {}).get("thread_id")
    except Exception:
        return None
