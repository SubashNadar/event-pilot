"""End-to-end run tests through the HTTP API, in rule-based mode (no Azure)."""

from conftest import create_event, of_type, wait_for

from app.core.config import settings


def test_full_run_streams_every_step_and_saves_the_plan(client):
    event = create_event(client)
    run_id = client.post(f"/api/v1/events/{event['id']}/runs", json={}).json()["run_id"]
    snap = wait_for(client, run_id, {"completed", "error", "paused"})
    assert snap["run"]["status"] == "completed", [e["type"] for e in snap["events"]]

    types = [e["type"] for e in snap["events"]]
    assert types[:2] == ["run_started", "plan_created"]
    assert len(of_type(snap, "plan_created")[0]["steps"]) == 11
    completed = {e["stepId"] for e in of_type(snap, "step_completed")}
    assert completed == {"logistics_agent", "finance_agent", "schedule_agent", "requirements_agent", "marketing_agent", "risk_operations_agent", "coordination", "event_manager", "review_plan", "recommendations"}
    assert [e["stepId"] for e in of_type(snap, "step_skipped")] == ["replan"]  # review passed first time
    assert of_type(snap, "token"), "recommendations should stream tokens"
    assert types[-2:] == ["plan_ready", "run_completed"]
    seqs = [e["seq"] for e in snap["events"]]
    assert seqs == sorted(seqs) and len(seqs) == len(set(seqs))

    # every specialist streamed a running + finished tool call, and verified
    main_tool = {"logistics_agent": "venue_search", "finance_agent": "budget_validation", "schedule_agent": "schedule_conflict_check"}
    for step in ("logistics_agent", "finance_agent", "schedule_agent"):
        tools = [t for t in of_type(snap, "tool_call", step) if t["tool"]["name"] == main_tool[step]]
        assert [t["tool"]["status"] for t in tools] == ["running", "success"]
        assert of_type(snap, "step_verifying", step)
        summary = of_type(snap, "step_completed", step)[0]["summary"]
        assert summary["verification"]["passed"] and summary["did"]

    plan = client.get(f"/api/v1/events/{event['id']}/plan").json()
    assert plan["run_id"] == run_id
    assert plan["venue"] == "Koramangala Workshop Studio"  # chosen by the Logistics agent's tool result
    assert plan["recommendations"].startswith("## AI Leadership Workshop")


def test_workflow_graph_png_endpoint_returns_the_compiled_graph(client):
    from app.api.routes import runs

    runs._workflow_graph_png.cache_clear()
    response = client.get("/api/v1/workflow/graph.png")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG\r\n\x1a\n")


def test_failed_step_offers_options_and_resumes_without_rerunning_others(client):
    event = create_event(client, location="Shillong", attendees=200, budget=1000000, name="Meera and Karthik Wedding Reception", objective="Elegant wedding reception with smooth guest hospitality.")
    run_id = client.post(f"/api/v1/events/{event['id']}/runs", json={}).json()["run_id"]
    snap = wait_for(client, run_id, {"paused", "completed", "error"})
    assert snap["run"]["status"] == "paused"
    assert of_type(snap, "run_paused")[-1]["pendingStepIds"] == ["logistics_agent"]

    failed = of_type(snap, "step_failed", "logistics_agent")[0]
    assert "No catalog venue fits 200 guests in Shillong" in failed["error"] and "isn't in the venue catalogue" in failed["error"]
    options = failed["recovery"]["options"]
    ids = [o["id"] for o in options]
    assert ids[-1] == "skip" and "accept-unverified" in ids and "city-bengaluru" in ids
    assert failed["recovery"]["summary"] == "The venue catalogue doesn't cover Shillong yet."

    # the other specialists wait for the venue, so none of them has started yet
    assert {e["stepId"] for e in of_type(snap, "step_started")} == {"logistics_agent"}

    response = client.post(f"/api/v1/runs/{run_id}/steps/logistics_agent/resolve", json={"option_id": "accept-unverified"})
    assert response.status_code == 200 and response.json()["status"] == "resumed", response.text
    snap = wait_for(client, run_id, {"completed", "error", "paused"})
    assert snap["run"]["status"] == "completed", [e["type"] for e in snap["events"]]

    assert of_type(snap, "recovery_chosen", "logistics_agent")[0]["label"] == "Use an unverified venue"
    assert [e["attempt"] for e in of_type(snap, "step_started", "logistics_agent")] == [1, 2]
    assert len(of_type(snap, "step_failed", "logistics_agent")) == 1  # replay did not duplicate it
    assert len(of_type(snap, "step_started", "finance_agent")) == 1  # started once, not re-run by the replay
    plan = of_type(snap, "plan_ready")[0]["plan"]
    assert "Shillong" in plan["venue"] and "unverified" in plan["venue_detail"]


def test_custom_text_needs_clarification_then_changes_the_rerun(client):
    event = create_event(client, location="Shillong", attendees=90)
    run_id = client.post(f"/api/v1/events/{event['id']}/runs", json={}).json()["run_id"]
    wait_for(client, run_id, {"paused"})

    vague = client.post(f"/api/v1/runs/{run_id}/steps/logistics_agent/resolve", json={"custom_text": "make it nicer"}).json()
    assert vague["status"] == "needs_clarification" and "location" in vague["question"]
    assert client.get(f"/api/v1/runs/{run_id}").json()["run"]["status"] == "paused"

    clear = client.post(f"/api/v1/runs/{run_id}/steps/logistics_agent/resolve", json={"custom_text": "Try in Koramangala instead"}).json()
    assert clear["status"] == "resumed" and clear["option"]["patch"] == {"location": "Koramangala"}
    snap = wait_for(client, run_id, {"completed", "error", "paused"})
    assert snap["run"]["status"] == "completed"
    assert of_type(snap, "plan_ready")[0]["plan"]["venue"] == "Koramangala Workshop Studio"


def test_parallel_failures_wait_for_every_answer(client, monkeypatch):
    monkeypatch.setattr(settings, "eventpilot_fail_once", "schedule_conflict_check")
    event = create_event(client, location="Shillong", attendees=90)
    run_id = client.post(f"/api/v1/events/{event['id']}/runs", json={}).json()["run_id"]
    snap = wait_for(client, run_id, {"paused"})
    assert of_type(snap, "run_paused")[-1]["pendingStepIds"] == ["logistics_agent"]  # schedule waits for the venue
    skipped = client.post(f"/api/v1/runs/{run_id}/steps/logistics_agent/skip").json()
    assert skipped["status"] == "resumed"
    snap = wait_for(client, run_id, {"paused"})
    assert sorted(of_type(snap, "run_paused")[-1]["pendingStepIds"]) == ["schedule_agent"]
    schedule_failure = of_type(snap, "step_failed", "schedule_agent")[0]
    assert "Simulated by EVENTPILOT_FAIL_ONCE" in schedule_failure["error"]
    assert of_type(snap, "tool_call", "schedule_agent")[-1]["tool"]["status"] == "error"

    first = client.post(f"/api/v1/runs/{run_id}/steps/schedule_agent/retry").json()
    assert first["status"] == "resumed"  # the only open question, so the retry runs at once

    snap = wait_for(client, run_id, {"completed", "error", "paused"})
    assert snap["run"]["status"] == "completed", [e["type"] for e in snap["events"]]
    assert of_type(snap, "step_completed", "schedule_agent")  # retry succeeded (fails only once)
    assert of_type(snap, "step_skipped", "logistics_agent")[0]["reason"] == "Skip — I'll book the venue myself"
    plan = of_type(snap, "plan_ready")[0]["plan"]
    assert any("Logistics step was skipped" in risk["title"] for risk in plan["risks"])


def test_stream_replays_from_last_event_id_and_ends_for_finished_runs(client):
    event = create_event(client)
    run_id = client.post(f"/api/v1/events/{event['id']}/runs", json={}).json()["run_id"]
    snap = wait_for(client, run_id, {"completed"})
    total = len(snap["events"])
    with client.stream("GET", f"/api/v1/runs/{run_id}/stream", headers={"Last-Event-ID": "5"}) as response:
        ids = [int(line.split(":", 1)[1]) for line in response.iter_lines() if line.startswith("id:")]
    assert ids == list(range(6, total + 1))


def test_cancel_and_conflicts(client):
    event = create_event(client, location="Shillong", attendees=90)
    run_id = client.post(f"/api/v1/events/{event['id']}/runs", json={}).json()["run_id"]
    wait_for(client, run_id, {"paused"})
    assert client.post(f"/api/v1/runs/{run_id}/steps/finance_agent/retry").status_code == 409  # not waiting
    assert client.post(f"/api/v1/runs/{run_id}/steps/logistics_agent/resolve", json={"option_id": "nope"}).status_code == 422
    assert client.post(f"/api/v1/runs/{run_id}/cancel").status_code == 204
    snap = client.get(f"/api/v1/runs/{run_id}").json()
    assert snap["run"]["status"] == "cancelled" and of_type(snap, "run_cancelled")


def test_budget_revision_run_and_legacy_endpoint(client):
    event = create_event(client)
    run_id = client.post(f"/api/v1/events/{event['id']}/runs", json={"operation": "budget-revision", "budget": 400000}).json()["run_id"]
    snap = wait_for(client, run_id, {"completed", "error", "paused"})
    assert snap["run"]["operation"] == "budget-revision" and snap["run"]["status"] == "completed"
    assert of_type(snap, "plan_ready")[0]["plan"]["budget_forecast"] <= 400000

    # legacy blocking endpoint never pauses: Mumbai logistics is skipped automatically
    mumbai = create_event(client, location="Shillong", attendees=90)
    response = client.post(f"/api/v1/events/{mumbai['id']}/plan")
    assert response.status_code == 200, response.text
    assert any("Logistics" in risk["title"] for risk in response.json()["risks"])


def test_over_budget_venue_offers_the_exact_share_needed(client):
    # Mumbai has venues, but ₹5,00,000 total leaves only ₹1,50,000 (30%) for rent.
    event = create_event(client, location="Mumbai", attendees=200, budget=500000)
    run_id = client.post(f"/api/v1/events/{event['id']}/runs", json={}).json()["run_id"]
    snap = wait_for(client, run_id, {"paused", "completed", "error"})
    failed = of_type(snap, "step_failed", "logistics_agent")[0]
    assert "the cheapest that fits is Andheri Skyline Banquets" in failed["error"]
    option = next(o for o in failed["recovery"]["options"] if o["id"] == "raise-venue-share")
    assert option["patch"] == {"venue_share_pct": 42} and option["label"] == "Raise venue share to 42%"
    assert failed["recovery"]["summary"].startswith("No venue in Mumbai fits 200 guests within 30% of the budget.")
    client.post(f"/api/v1/runs/{run_id}/steps/logistics_agent/resolve", json={"option_id": "raise-venue-share"})
    snap = wait_for(client, run_id, {"completed", "error", "paused"})
    assert of_type(snap, "plan_ready")[0]["plan"]["venue"] == "Andheri Skyline Banquets"
