"""Saved planner state: an unsaved brief comes back after leaving the page, and approval attempts are kept."""

from conftest import approve_plan, create_event, wait_for


def test_brief_draft_is_saved_returned_and_discarded(client):
    event = create_event(client, location="Pune", attendees=120, budget=1500000)
    eid = event["id"]
    assert client.get(f"/api/v1/events/{eid}/draft").json() == {"draft": None}

    saved = client.put(f"/api/v1/events/{eid}/draft", json={"location": "Indiranagar, Bengaluru", "budget": 1800000})
    assert saved.status_code == 200 and saved.json()["draft"] == {"location": "Indiranagar, Bengaluru", "budget": 1800000}
    assert client.get(f"/api/v1/events/{eid}/draft").json()["draft"]["location"] == "Indiranagar, Bengaluru", "the draft is there on return"

    assert client.delete(f"/api/v1/events/{eid}/draft").status_code == 204
    assert client.get(f"/api/v1/events/{eid}/draft").json() == {"draft": None}


def test_draft_rejects_values_the_brief_would_refuse(client):
    event = create_event(client, location="Pune", attendees=120, budget=1500000)
    response = client.put(f"/api/v1/events/{event['id']}/draft", json={"attendees": 0})
    assert response.status_code == 422


def test_change_requests_are_saved_per_event(client):
    event = create_event(client, location="Pune", attendees=120, budget=1500000)
    run_id = client.post(f"/api/v1/events/{event['id']}/runs", json={}).json()["run_id"]
    assert wait_for(client, run_id, {"paused", "completed", "error"})["run"]["status"] == "paused"
    sent = client.post(f"/api/v1/runs/{run_id}/steps/approval/resolve", json={"custom_text": "Lower the decor spend"}).json()
    assert sent["status"] == "resumed", sent
    from app.services import ui_state
    assert ui_state.attempts(event["id"]) == 1, "the count is saved, not only held in memory"
    approve_plan(client, run_id)
