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

    snap = approve_plan(client, response.json()["run_id"])  # the edited plan comes back to the owner first
    assert snap["run"]["status"] == "completed", snap["run"].get("error")
    plan = client.get(f"/api/v1/events/{event['id']}/plan").json()
    assert "Chennai" in plan["venue_detail"], "the venue is searched again in the new city"


def test_location_without_venue_data_shows_the_error_on_the_run(client):
    event = create_event(client, location="Pune", attendees=120, budget=1500000)
    run_id = client.post(f"/api/v1/events/{event['id']}/runs", json={}).json()["run_id"]
    assert wait_for(client, run_id, {"paused", "completed", "error"})["run"]["status"] == "paused"

    response = client.post(f"/api/v1/runs/{run_id}/steps/approval/resolve", json={"custom_text": "change the location to Coimbatore"})
    snap = _wait_for_pauses(client, response.json()["run_id"], count=1)
    failure = next(e for e in of_type(snap, "step_failed") if e["stepId"] == "logistics_agent")
    assert "Coimbatore" in failure["error"] and "catalogue" in failure["error"], failure["error"]
    assert failure["recovery"]["options"], "the owner is offered a way forward"


def test_a_run_stopped_while_working_continues_and_completes(client):
    event = create_event(client, location="Pune", attendees=120, budget=1500000)
    run_id = client.post(f"/api/v1/events/{event['id']}/runs", json={}).json()["run_id"]
    end = time.time() + 30
    while time.time() < end and not any(e["type"] == "step_completed" for e in client.get(f"/api/v1/runs/{run_id}").json()["events"]):
        time.sleep(0.05)  # stop it once some progress is saved, while the agents are still working

    assert client.post(f"/api/v1/runs/{run_id}/cancel").status_code == 204
    response = client.post(f"/api/v1/runs/{run_id}/continue")
    assert response.status_code == 200, response.text
    snap = _wait_for_pauses(client, run_id, count=1)
    assert snap["run"]["status"] == "paused", [e["type"] for e in snap["events"]][-6:]
    response = client.post(f"/api/v1/runs/{run_id}/steps/approval/resolve", json={"option_id": "approve"})
    assert response.status_code == 200, response.text
    snap = wait_for(client, run_id, {"completed", "error"})
    assert snap["run"]["status"] == "completed", snap["run"].get("error")


def _paused_run(client):
    event = create_event(client, location="Pune", attendees=120, budget=1500000)
    run_id = client.post(f"/api/v1/events/{event['id']}/runs", json={}).json()["run_id"]
    assert wait_for(client, run_id, {"paused", "completed", "error"})["run"]["status"] == "paused"
    return event, run_id


def _answer(client, run_id, text):
    return client.post(f"/api/v1/runs/{run_id}/steps/approval/resolve", json={"custom_text": text}).json()


def test_questions_and_unclear_messages_dont_use_a_change_request(client):
    _, run_id = _paused_run(client)
    answer = _answer(client, run_id, "What is the budget split?")
    assert answer["status"] == "answered" and "forecast" in answer["question"].lower(), answer
    unclear = _answer(client, run_id, "make the wedding bigger")
    assert unclear["status"] == "needs_clarification", unclear
    snap = client.get(f"/api/v1/runs/{run_id}").json()
    assert snap["run"]["status"] == "paused", "nothing was re-planned"
    assert of_type(snap, "step_failed", "approval")[-1]["recovery"]["changesLeft"] == 3


def test_three_change_requests_at_approval_then_the_owner_approves_or_restarts(client):
    event, run_id = _paused_run(client)
    assert _answer(client, run_id, "Lower the decor spend")["status"] == "resumed"
    snap = _wait_for_pauses(client, run_id, count=2)
    card = of_type(snap, "step_failed", "approval")[-1]["recovery"]
    assert card["changesLeft"] == 2 and "2 of 3" in card["summary"], "a change that applies uses one, and the card says so"

    edit = _answer(client, run_id, "change the guest count to 150")
    assert edit["status"] == "edit_started", edit
    snap = _wait_for_pauses(client, edit["run_id"], count=1)
    assert of_type(snap, "step_failed", "approval")[-1]["recovery"]["changesLeft"] == 1, "the count follows the event into the edit run"

    assert _answer(client, edit["run_id"], "Lower the decor spend")["status"] == "resumed"
    snap = _wait_for_pauses(client, edit["run_id"], count=2)
    card = of_type(snap, "step_failed", "approval")[-1]["recovery"]
    assert card["changesLeft"] == 0 and [o["id"] for o in card["options"]] == ["approve"], "no send-back once they are used"

    used = _answer(client, edit["run_id"], "change the guest count to 180")
    assert used["status"] == "attempts_exhausted" and "still approve" in used["question"], used
    via_api = client.post(f"/api/v1/runs/{edit['run_id']}/approval", json={"decision": "revise", "feedback": "Lower the catering spend"}).json()
    assert via_api["status"] == "attempts_exhausted", "the approval endpoint has the same limit"
    assert approve_plan(client, edit["run_id"])["run"]["status"] == "completed", "approving is always possible"

    fresh = client.post(f"/api/v1/events/{event['id']}/runs", json={}).json()["run_id"]
    snap = wait_for(client, fresh, {"paused", "completed", "error"})
    assert of_type(snap, "step_failed", "approval")[-1]["recovery"]["changesLeft"] == 3, "a fresh plan from the brief starts again"


def test_guest_count_change_at_approval_comes_back_for_approval(client):
    event, run_id = _paused_run(client)
    answer = _answer(client, run_id, "change the guest count to 150")
    assert answer["status"] == "edit_started" and answer["changes"] == ["guests from 120 to 150"], answer
    assert client.get(f"/api/v1/events/{event['id']}").json()["attendees"] == 150, "the brief itself changes"
    old = client.get(f"/api/v1/runs/{run_id}").json()
    assert old["run"]["status"] == "cancelled" and of_type(old, "run_cancelled")[-1]["message"] != "You stopped the plan."
    snap = wait_for(client, answer["run_id"], {"completed", "error", "paused"})
    assert snap["run"]["status"] == "paused" and of_type(snap, "run_paused")[-1]["pendingStepIds"] == ["approval"], "nothing is final until the owner approves"
    assert not of_type(snap, "plan_ready"), "the edited plan isn't saved as final"
    assert of_type(snap, "step_started", "finance_agent"), "the affected agents run again"


def test_a_small_edit_at_approval_changes_only_its_own_part(client):
    _, run_id = _paused_run(client)
    before = of_type(client.get(f"/api/v1/runs/{run_id}").json(), "step_failed", "approval")[-1]["recovery"]["preview"]
    answer = _answer(client, run_id, "move the opening session to 10:30 AM")
    assert answer["status"] == "edit_started", answer
    snap = _wait_for_pauses(client, answer["run_id"], count=1)
    after = of_type(snap, "step_failed", "approval")[-1]["recovery"]["preview"]
    assert any(item["activity"] == "Opening session" and item["time"] == "10:30 AM" for item in after["agenda"])
    assert after["risks"] == before["risks"], "the risk register the owner saw is untouched"
    assert after["budget_lines"] == before["budget_lines"] and after["venue"] == before["venue"]
    assert not of_type(snap, "step_started", "risk_operations_agent") or of_type(snap, "step_completed", "risk_operations_agent")[0]["summary"]["did"][0].startswith("Kept")


def test_objective_change_at_approval_updates_the_brief(client):
    event, run_id = _paused_run(client)
    answer = _answer(client, run_id, "change the objective to a family celebration for close friends")
    assert answer["status"] == "edit_started", answer
    assert client.get(f"/api/v1/events/{event['id']}").json()["objective"] == "a family celebration for close friends"


def test_plan_feedback_at_approval_reaches_the_manager_with_the_owners_words(client):
    _, run_id = _paused_run(client)
    answer = _answer(client, run_id, "make the decor feel more elegant")
    assert answer["status"] == "resumed", answer
    snap = _wait_for_pauses(client, run_id, count=2)
    assert snap["run"]["status"] == "paused"
    assert any("decor feel more elegant" in item for item in of_type(snap, "step_completed", "manager_intake")[-1]["summary"]["did"])


def test_approval_card_shows_how_many_change_requests_are_left(client):
    event = create_event(client, location="Pune", attendees=120, budget=1500000)
    run_id = client.post(f"/api/v1/events/{event['id']}/runs", json={}).json()["run_id"]
    snap = wait_for(client, run_id, {"paused", "completed", "error"})
    assert snap["run"]["status"] == "paused"
    recovery = [e for e in snap["events"] if e["type"] == "step_failed" and e.get("stepId") == "approval"][-1]["recovery"]
    assert "Change requests left at approval: 3 of 3." in recovery["summary"], recovery["summary"]
    assert "restart the plan" not in recovery["summary"]
    assert recovery["cause"] == "", "an approval isn't shown as an error"
