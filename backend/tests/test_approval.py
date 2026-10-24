"""The Event Manager starts the run, the owner approves or sends changes, and changes re-plan the named areas."""

import time

from conftest import approve_plan, create_event, of_type, wait_for


def _wait_for_pauses(client, run_id, count, timeout=90):
    """Poll until the run has paused `count` times and is waiting now, or has ended."""
    end = time.time() + timeout
    while True:
        snap = client.get(f"/api/v1/runs/{run_id}").json()
        waiting = snap["run"]["status"] == "paused" and len(of_type(snap, "run_paused")) >= count
        if waiting or snap["run"]["status"] in ("completed", "error", "cancelled") or time.time() > end:
            return snap
        time.sleep(0.5)


def test_manager_reads_the_brief_first_and_approval_comes_before_recommendations(client):
    event = create_event(client, location="Pune", attendees=120, budget=1500000)
    run_id = client.post(f"/api/v1/events/{event['id']}/runs", json={}).json()["run_id"]
    snap = wait_for(client, run_id, {"paused", "completed", "error"})

    first_step = next(e["stepId"] for e in snap["events"] if e["type"] == "step_started")
    assert first_step == "receptionist"
    assert of_type(snap, "run_paused")[-1]["pendingStepIds"] == ["approval"]
    assert not of_type(snap, "step_completed", "recommendations"), "the summary is written after the owner approves"

    snap = approve_plan(client, run_id)
    assert snap["run"]["status"] == "completed"
    order = [e["stepId"] for e in snap["events"] if e["type"] == "step_completed"]
    assert order.index("approval") < order.index("recommendations")


def test_change_request_replans_the_named_areas_and_asks_again(client):
    event = create_event(client, location="Pune", attendees=120, budget=1500000)
    run_id = client.post(f"/api/v1/events/{event['id']}/runs", json={}).json()["run_id"]
    wait_for(client, run_id, {"paused", "completed", "error"})

    response = client.post(f"/api/v1/runs/{run_id}/approval", json={"decision": "revise", "feedback": "Lower the budget for decor"})
    assert response.status_code == 200 and response.json()["status"] == "resumed", response.text

    snap = _wait_for_pauses(client, run_id, count=2)
    assert snap["run"]["status"] == "paused", [e["type"] for e in snap["events"]][-8:]
    assert of_type(snap, "run_paused")[-1]["pendingStepIds"] == ["approval"]
    assert of_type(snap, "step_completed", "replan"), "the change request starts a re-plan"
    assert any("Lower the budget for decor" in item for item in of_type(snap, "step_completed", "approval")[0]["summary"]["did"])
    assert len(of_type(snap, "step_started", "finance_agent")) >= 2, "the named area is re-run with the owner's words"

    snap = approve_plan(client, run_id)
    assert snap["run"]["status"] == "completed"


def test_owner_feedback_goes_back_through_the_manager_until_both_are_satisfied(client):
    event = create_event(client, location="Pune", attendees=120, budget=1500000)
    run_id = client.post(f"/api/v1/events/{event['id']}/runs", json={}).json()["run_id"]
    wait_for(client, run_id, {"paused", "completed", "error"})

    for round_number, request in enumerate(["Lower the budget for decor", "Move the agenda earlier"], start=1):
        response = client.post(f"/api/v1/runs/{run_id}/approval", json={"decision": "revise", "feedback": request})
        assert response.status_code == 200 and response.json()["status"] == "resumed", response.text
        snap = _wait_for_pauses(client, run_id, count=round_number + 1)
        assert snap["run"]["status"] == "paused"
        # The manager re-splits each send-back, after the first delegation, before the specialists re-run.
        delegations = of_type(snap, "step_completed", "manager_intake")
        assert len(delegations) == round_number + 1
        last = delegations[-1]["summary"]["did"]
        assert any(request in item for item in last), last
        assert any(item.startswith(("Re-split to:", "No specialist")) for item in last), last
        assert of_type(snap, "run_paused")[-1]["pendingStepIds"] == ["approval"]

    snap = approve_plan(client, run_id)
    assert snap["run"]["status"] == "completed"
    assert of_type(snap, "step_completed", "recommendations"), "the owner's approval is the last gate"


def test_approval_pause_carries_the_plan_so_the_owner_can_review_it_first(client):
    event = create_event(client, location="Pune", attendees=120, budget=1500000)
    run_id = client.post(f"/api/v1/events/{event['id']}/runs", json={}).json()["run_id"]
    snap = wait_for(client, run_id, {"paused", "completed", "error"})
    assert snap["run"]["status"] == "paused"

    approval_failure = next(e for e in of_type(snap, "step_failed") if e["stepId"] == "approval")
    preview = approval_failure["recovery"]["preview"]
    assert preview["venue"], "the owner sees the venue"
    assert preview["budget_lines"] and preview["agenda"] and preview["risks"], "budget, agenda and risks are shown"
    assert preview["approved_budget"] == 1500000
    assert [o["id"] for o in approval_failure["recovery"]["options"]] == ["approve", "revise"]


def test_a_stopped_run_continues_from_where_it_left_off(client):
    event = create_event(client, location="Pune", attendees=120, budget=1500000)
    run_id = client.post(f"/api/v1/events/{event['id']}/runs", json={}).json()["run_id"]
    assert wait_for(client, run_id, {"paused", "completed", "error"})["run"]["status"] == "paused"

    # A paused run cannot be continued: the owner answers its decision instead.
    assert client.post(f"/api/v1/runs/{run_id}/continue").status_code == 409

    assert client.post(f"/api/v1/runs/{run_id}/cancel").status_code == 204
    assert client.get(f"/api/v1/runs/{run_id}").json()["run"]["status"] == "cancelled"

    response = client.post(f"/api/v1/runs/{run_id}/continue")
    assert response.status_code == 200 and response.json()["status"] == "resumed", response.text
    snap = _wait_for_pauses(client, run_id, count=2)
    assert snap["run"]["status"] == "paused", "the run comes back to the owner's decision"

    snap = approve_plan(client, run_id)
    assert snap["run"]["status"] == "completed"
    assert client.post(f"/api/v1/runs/{run_id}/continue").status_code == 409, "a finished run has nothing left"


def test_location_change_sent_back_from_approval_moves_the_venue(client):
    event = create_event(client, location="Pune", attendees=120, budget=1500000)
    run_id = client.post(f"/api/v1/events/{event['id']}/runs", json={}).json()["run_id"]
    assert wait_for(client, run_id, {"paused", "completed", "error"})["run"]["status"] == "paused"

    response = client.post(f"/api/v1/runs/{run_id}/steps/approval/resolve", json={"custom_text": "change the location to Chennai"})
    assert response.json()["status"] == "edit_started", response.text
    assert response.json()["changes"] == ["location to Chennai"]

    snap = _wait_for_pauses(client, response.json()["run_id"], count=1)
    plan = client.get(f"/api/v1/events/{event['id']}/plan").json()
    assert "Chennai" in plan["venue_detail"], "the venue is searched again in the new city"


def test_location_without_venue_data_shows_the_error_on_the_run(client):
    event = create_event(client, location="Pune", attendees=120, budget=1500000)
    run_id = client.post(f"/api/v1/events/{event['id']}/runs", json={}).json()["run_id"]
    assert wait_for(client, run_id, {"paused", "completed", "error"})["run"]["status"] == "paused"

    response = client.post(f"/api/v1/runs/{run_id}/steps/approval/resolve", json={"custom_text": "change the location to Shillong"})
    snap = _wait_for_pauses(client, response.json()["run_id"], count=1)
    failure = next(e for e in of_type(snap, "step_failed") if e["stepId"] == "logistics_agent")
    assert "Shillong" in failure["error"] and "catalogue" in failure["error"], failure["error"]
    assert failure["recovery"]["options"], "the owner is offered a way forward"
