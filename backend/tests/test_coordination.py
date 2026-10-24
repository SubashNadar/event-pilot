"""Coordination, budget fitting, replan routing and the review-driven replan loop."""

from datetime import date

from app.agents.specialists import _finance_report, fit_lines_to_budget
from app.graphs.event_workflow import _coordinate_items, _reconcile_manager_plan, owners_for
from app.models.event import EventBrief
from conftest import approve_plan, create_event, of_type, wait_for


def _event(budget=1_000_000, attendees=200):
    return EventBrief(name="Coordination test", event_date=date(2027, 2, 14), location="Pune", attendees=attendees, budget=budget, objective="A calm, well-run family wedding reception.")


def test_budget_line_must_match_logistics_quote():
    state = {
        "event": {"budget": 1_000_000},
        "logistics": {"decisions": {"venue": "Hall A", "rental_inr": 400_000}},
        "finance": {"decisions": {"budget_lines": [{"category": "Venue", "amount": 300_000}, {"category": "Catering", "amount": 500_000}]}},
    }
    items = _coordinate_items(state)
    assert [item["id"] for item in items] == ["venue-rent"] and items[0]["owner"] == "finance_agent"
    state["finance"]["decisions"]["budget_lines"][0]["amount"] = 400_000
    assert _coordinate_items(state) == []


def test_budget_total_above_approved_is_flagged():
    state = {
        "event": {"budget": 100_000},
        "logistics": {},
        "finance": {"decisions": {"budget_lines": [{"category": "Catering", "amount": 150_000}]}},
    }
    assert [item["id"] for item in _coordinate_items(state)] == ["budget-total"]


def test_manager_plan_keeps_verified_venue_budget_and_agenda_handoffs():
    plan = {
        "venue": "Model Hall", "venue_detail": "Model detail", "budget_forecast": 490_000,
        "budget_lines": [{"category": "Venue", "amount": 150_000, "share_percent": 31}],
        "agenda": [{"time": "10:00 AM", "activity": "Model opening", "owner": "Host"}],
    }
    context = {
        "logistics": {"decisions": {"venue": "Verified Hall", "venue_detail": "Pune · 200 seats", "rental_inr": 180_000}},
        "finance": {"decisions": {"budget_lines": [{"category": "Venue", "amount": 180_000}, {"category": "Catering", "amount": 220_000}, {"category": "Contingency", "amount": 40_000}]}},
        "schedule": {"decisions": {"agenda": [{"time": "9:30 AM", "activity": "Guest arrival"}]}},
    }
    result = _reconcile_manager_plan(plan, context, 500_000)
    assert result["venue"] == "Verified Hall" and result["venue_detail"] == "Pune · 200 seats"
    assert result["budget_forecast"] == 440_000 and result["budget_lines"][0]["amount"] == 180_000
    assert result["agenda"] == [{"time": "9:30 AM", "activity": "Guest arrival", "owner": "Event operations"}]


def test_coordination_ignores_malformed_model_budget_lines():
    state = {
        "event": {"budget": 100_000},
        "logistics": {"decisions": {"venue": "Hall A", "rental_inr": 30_000}},
        "finance": {"decisions": {"budget_lines": ["Venue: 30000", "Catering: 70000"]}},
    }
    assert _coordinate_items(state) == []


def test_fit_keeps_the_venue_and_trims_the_rest():
    lines = [{"category": "Venue", "amount": 400_000}, {"category": "Catering", "amount": 500_000}, {"category": "Contingency", "amount": 100_000}]
    fitted, note = fit_lines_to_budget(lines, 800_000)
    assert fitted[0]["amount"] == 400_000
    assert sum(line["amount"] for line in fitted) <= 800_000
    assert note and "Trimmed" in note
    assert fit_lines_to_budget(lines, 2_000_000) == (lines, None)


def test_finance_uses_the_logistics_quote_for_the_venue_line():
    result = {"_lines": [{"category": "Venue", "amount": 300_000}, {"category": "Catering", "amount": 300_000}, {"category": "Contingency", "amount": 50_000}]}
    overrides = {"handoff": {"venue": "Hall A", "rental_inr": 450_000}}
    report = _finance_report(_event(), overrides, result).model_dump()
    lines = {line["category"]: line["amount"] for line in report["decisions"]["budget_lines"]}
    assert lines["Venue"] == 450_000
    assert sum(lines.values()) <= 1_000_000
    assert any("Hall A" in rec for rec in report["recommendations"])


def test_review_issues_go_back_to_the_specialists_they_concern():
    assert owners_for(["The venue rent in the budget doesn't match Logistics' quote."]) == ["logistics_agent", "finance_agent"]
    assert owners_for(["Agenda includes a time outside the required 12-hour format."]) == ["schedule_agent"]
    assert owners_for(["The plan needs between two and five risks."]) == ["risk_operations_agent"]
    assert owners_for(["Budget forecast exceeds the approved budget."]) == ["finance_agent"]


def test_flagged_review_replans_only_the_affected_specialists(client, monkeypatch):
    from app.graphs import event_workflow

    real_review = event_workflow._review
    calls = {"n": 0}

    def review_once_with_a_mismatch(event, plan, state=None):
        issues = real_review(event, plan, state)
        calls["n"] += 1
        if calls["n"] == 1:
            issues = issues + ["The venue rent in the budget doesn't match Logistics' quote."]
        return issues

    monkeypatch.setattr(event_workflow, "_review", review_once_with_a_mismatch)
    event = create_event(client, location="Pune", attendees=120, budget=1500000)
    run_id = client.post(f"/api/v1/events/{event['id']}/runs", json={}).json()["run_id"]
    snap = approve_plan(client, run_id)
    assert snap["run"]["status"] == "completed", [e["type"] for e in snap["events"]]

    assert [e["stepId"] for e in of_type(snap, "step_completed") if e["stepId"] == "replan"]
    assert len(of_type(snap, "step_started", "logistics_agent")) == 2  # venue issue re-runs Logistics and Finance
    assert len(of_type(snap, "step_started", "finance_agent")) == 2
    assert len(of_type(snap, "step_started", "schedule_agent")) == 1  # not named by the review, so not re-run
    assert len(of_type(snap, "step_completed", "review_plan")) == 2
    assert len(of_type(snap, "step_started", "event_manager")) == 2  # the manager reconsolidates after the replan


def test_model_budget_lines_with_other_amount_names_are_accepted():
    from app.agents.specialists import normalise_budget_lines
    from app.graphs.event_workflow import _normalise_result

    lines = normalise_budget_lines([{"category": "Venue", "amount_inr": "1,50,000"}, {"name": "Catering", "inr": 300000}, {"category": "Odd", "amount": None}])
    assert lines == [{"category": "Venue", "amount": 150000}, {"category": "Catering", "amount": 300000}]

    result = {"report": {"decisions": {"budget_lines": [{"category": "Venue", "amount_inr": 400000}]}}}
    state = {
        "event": {"budget": 1_000_000},
        "logistics": {"decisions": {"venue": "Hall A", "rental_inr": 400_000}},
        "finance": _normalise_result(result)["report"],
    }
    assert _coordinate_items(state) == []  # no KeyError, and the venue matches the quote


def test_venue_returned_as_an_object_is_read_as_its_name():
    from app.graphs.event_workflow import _normalise_result

    result = {"report": {"decisions": {"venue": {"name": "Kharadi Grand Banquets", "location": "Kharadi, Pune", "capacity": 450, "rental_inr": 210000}}}}
    decisions = _normalise_result(result)["report"]["decisions"]
    assert decisions["venue"] == "Kharadi Grand Banquets"
    assert decisions["rental_inr"] == 210000


def test_unresolved_review_waits_for_the_owner_and_does_not_replace_plan(client, monkeypatch):
    from app.graphs import event_workflow
    from conftest import approve_plan

    event = create_event(client, location="Pune", attendees=120, budget=1500000)
    run_id = client.post(f"/api/v1/events/{event['id']}/runs", json={}).json()["run_id"]
    assert wait_for(client, run_id, {"completed", "error", "paused"})["run"]["status"] == "paused"
    assert approve_plan(client, run_id)["run"]["status"] == "completed"
    original = client.get(f"/api/v1/events/{event['id']}/plan").json()

    monkeypatch.setattr(event_workflow, "_review", lambda *args: ["Budget forecast exceeds the approved budget."])
    run_id = client.post(f"/api/v1/events/{event['id']}/runs", json={}).json()["run_id"]
    snapshot = wait_for(client, run_id, {"completed", "error", "paused"})
    # The owner decides on a plan the checks still flag: the run waits at approval, with the issue shown.
    assert snapshot["run"]["status"] == "paused"
    assert not of_type(snapshot, "plan_ready")
    assert any("Budget forecast exceeds" in e["message"] for e in of_type(snapshot, "notice"))
    assert client.get(f"/api/v1/events/{event['id']}/plan").json() == original
