import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

# Isolate data and keep tests deterministic before the app reads its settings.
_TMP = tempfile.mkdtemp(prefix="eventpilot-tests-")
os.environ["DATA_DIR"] = _TMP
os.environ["MCP_URL"] = "http://127.0.0.1:9/mcp"  # nothing listens: tools run in-process
os.environ["FREE_APIS_ENABLED"] = "false"
os.environ["RATE_LIMIT_WRITES_PER_MINUTE"] = "100000"  # test_guard lowers these to check the limiter
os.environ["RATE_LIMIT_LLM_PER_MINUTE"] = "100000"
os.environ["RATE_LIMIT_LLM_PER_DAY"] = "100000"  # offline data only; test_free_tools turns it on with a mock transport
for key in ("AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT_NAME", "AZURE_OPENAI_CHAT_DEPLOYMENT", "AZURE_OPENAI_DEPLOYMENT", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "DB_USER"):
    os.environ[key] = ""
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.chdir(Path(__file__).resolve().parents[1])

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

TERMINAL = {"completed", "cancelled", "error"}


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


def create_event(client, **overrides):
    body = {"name": "AI Leadership Workshop", "event_date": "2027-03-11", "location": "Koramangala, Bengaluru", "attendees": 80, "budget": 500000, "objective": "Build practical AI leadership skills for emerging managers."}
    body.update(overrides)
    response = client.post("/api/v1/events", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def wait_for(client, run_id, statuses, timeout=30.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        snapshot = client.get(f"/api/v1/runs/{run_id}").json()
        if snapshot["run"]["status"] in statuses:
            return snapshot
        time.sleep(0.05)
    raise AssertionError(f"run stayed {snapshot['run']['status']}: {[e['type'] for e in snapshot['events']]}")


def of_type(snapshot, kind, step=None):
    return [e for e in snapshot["events"] if e["type"] == kind and (step is None or e.get("stepId") == step)]
