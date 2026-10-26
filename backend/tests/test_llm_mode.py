"""The LLM code path, driven by a fake chat model that supports tools, structured output and streaming."""

from typing import Any

import pytest
from conftest import approve_plan, create_event, of_type, wait_for
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage

from app.agents import llm
from app.agents.judge import JudgedFeedback, PlanJudgement
from app.models.event import AiPlanDraft
from app.models.run import RecoveryOption, SpecialistReport
from app.services.azure_planner import _draft_from_output

TOOL_ARGS = {
    "venue_search": {"location": "Mumbai", "attendees": 999, "total_budget_inr": 1, "venue_type": "workshop studio", "preferences": "projector, breakout rooms"},  # brief values are enforced back in code
    "budget_validation": {"budget_lines": [{"category": "Venue", "amount": 150000}, {"category": "Catering", "amount": 200000}, {"category": "Decor", "amount": 50000}, {"category": "Photography", "amount": 30000}, {"category": "Operations", "amount": 20000}, {"category": "Contingency", "amount": 40000}], "total_budget_inr": 500000},
    "schedule_conflict_check": {"agenda": [{"time": "9:00 AM", "activity": "Arrival"}, {"time": "10:00 AM", "activity": "Keynote"}, {"time": "1:00 PM", "activity": "Lunch"}, {"time": "2:00 PM", "activity": "Workshops"}, {"time": "5:00 PM", "activity": "Close"}]},
    "event_requirements": {"event_type": "workshop", "attendees": 80},
    "marketing_readiness": {"event_type": "workshop", "attendees": 80, "event_date": "2027-03-11"},
    "operational_risk_assessment": {"event_type": "workshop", "attendees": 80, "location": "Bengaluru"},
}

CALLS: list[str] = []
JUDGE_VERDICTS: list[PlanJudgement] = []  # queued verdicts for the plan judge; empty means "satisfied"
OWNER_ROUTES: list[Any] = []  # queued readings of the owner's message at approval
PROMPTS: dict[str, list[str]] = {}  # the last messages each structured schema was called with


class _Structured:
    def __init__(self, schema, include_raw):
        self.schema, self.include_raw = schema, include_raw

    async def ainvoke(self, messages, config=None):
        name = self.schema.__name__
        CALLS.append(name)
        PROMPTS.setdefault(name, []).append(" ".join(str(getattr(m, "content", m)) for m in (messages if isinstance(messages, list) else [messages])))
        if self.schema is SpecialistReport:
            value = SpecialistReport(recommendations=["Checked the options with my tool", "Picked the best fit"], decisions={"note": "llm"}, confidence=81)
        elif self.schema is AiPlanDraft:
            value = AiPlanDraft(
                plan_type="workshop", venue="Koramangala Workshop Studio", venue_detail="Koramangala · 100 seats",
                budget_forecast=490000,
                budget_lines=[{"category": c, "amount": a, "share_percent": round(a / 4900)} for c, a in [("Venue", 150000), ("Catering", 200000), ("Decor", 50000), ("Photography", 30000), ("Operations", 20000), ("Contingency", 40000)]],
                agenda=[{"time": t, "activity": a, "owner": "Ops"} for t, a in [("9:00 AM", "Arrival"), ("10:00 AM", "Keynote"), ("1:00 PM", "Lunch"), ("2:00 PM", "Workshops"), ("5:00 PM", "Close")]],
                risks=[{"level": "High", "title": "Speaker no-show", "detail": "Line up a backup", "recommended_action": "Set fallback"}, {"level": "Medium", "title": "Low turnout", "detail": "Send reminders", "recommended_action": "Monitor"}],
                activity=[{"agent": "Event Manager", "detail": "Combined reports", "timestamp": "Now"}], confidence=88,
            )
        elif self.schema is PlanJudgement:
            value = JUDGE_VERDICTS.pop(0) if JUDGE_VERDICTS else PlanJudgement(satisfied=True, feedback=[])
        elif name == "OwnerFeedback":
            value = OWNER_ROUTES.pop(0)
        elif name == "_LlmProposal":
            value = self.schema(summary="No venue in the catalog fits 200 guests in Mumbai within ₹3,00,000.", options=[
                RecoveryOption(id="nearby", label="Search Navi Mumbai", description="Try a nearby area", patch={"location": "Navi Mumbai"}),
                RecoveryOption(id="bad", label="Change the date", patch={"event_date": "2027-04-01"}),  # not allowed: dropped
                RecoveryOption(id="unverified", label="Use an unverified venue", patch={"allow_unverified": True}),
            ], custom_prompt="Try another area or guest count")
        elif name == "_Interpretation":
            text = messages[-1].content
            value = self.schema(understood="goa" in text.lower(), patch={"location": "Goa", "allow_unverified": True} if "goa" in text.lower() else {}, label="Goa, keep 200 guests", question="Which area or guest count?")
        else:
            raise AssertionError(name)
        return {"raw": AIMessage(content="", usage_metadata={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}), "parsed": value} if self.include_raw else value


class _ToolModel:
    def __init__(self, tools):
        self.tool = tools[0]["function"]["name"]

    async def ainvoke(self, messages, config=None):
        CALLS.append(f"tools:{self.tool}")
        if isinstance(messages[-1], ToolMessage):
            return AIMessage(content="Done.", usage_metadata={"input_tokens": 50, "output_tokens": 5, "total_tokens": 55})
        return AIMessage(content="", tool_calls=[{"id": f"call-{self.tool}", "name": self.tool, "args": TOOL_ARGS[self.tool]}], usage_metadata={"input_tokens": 80, "output_tokens": 10, "total_tokens": 90})


class FakeModel:
    def bind_tools(self, tools):
        return _ToolModel(tools)

    def with_structured_output(self, schema, method=None, include_raw=False):
        return _Structured(schema, include_raw)

    async def astream(self, prompt, config=None):
        CALLS.append("stream")
        for piece in ["## AI Leadership Workshop\n\n", "Forecast ₹4,90,000. ", "**Next steps**\n\n1. Book the venue."]:
            yield AIMessageChunk(content=piece)


@pytest.fixture()
def fake_llm(monkeypatch):
    CALLS.clear()
    PROMPTS.clear()
    JUDGE_VERDICTS.clear()
    OWNER_ROUTES.clear()
    monkeypatch.setattr(llm, "MODEL_FACTORY", FakeModel)
    yield CALLS


def test_llm_specialists_call_tools_and_stream_recommendations(client, fake_llm):
    event = create_event(client)
    run_id = client.post(f"/api/v1/events/{event['id']}/runs", json={}).json()["run_id"]
    snap = approve_plan(client, run_id)
    assert snap["run"]["status"] == "completed", [(e["type"], e.get("error")) for e in snap["events"]]
    assert not of_type(snap, "notice")  # LLM mode: no rule-based notice

    # Logistics: the model asked for Mumbai/999 guests, code enforced the brief
    venue_call = of_type(snap, "tool_call", "logistics_agent")[0]["tool"]["input"]
    assert venue_call == {"location": "Koramangala, Bengaluru", "attendees": 80, "total_budget_inr": 500000, "venue_type": "workshop studio", "preferences": "projector, breakout rooms"}
    assert of_type(snap, "plan_ready")[0]["plan"]["venue"] == "Koramangala Workshop Studio"
    assert fake_llm.count("SpecialistReport") == 6 and fake_llm.count("AiPlanDraft") == 1 and "stream" in fake_llm

    summary = of_type(snap, "step_completed", "finance_agent")[0]["summary"]
    assert summary["did"][:2] == ["Checked the options with my tool", "Picked the best fit"]  # then lines from context tools
    assert summary["metrics"]["tokensIn"] == 80 + 50 + 100 and summary["metrics"]["model"] != "rules"

    tokens = "".join(e["content"] for e in of_type(snap, "token"))
    assert tokens.startswith("## AI Leadership Workshop")
    usage = of_type(snap, "run_completed")[0]["usage"]
    assert usage["tokensIn"] == 6 * 230 + 100 + 100  # the plan judge's call adds its own 100
    plan = of_type(snap, "plan_ready")[0]["plan"]
    assert plan["source"] == "azure" and plan["recommendations"] == tokens


def test_plan_judge_sends_its_note_only_to_the_specialist_it_names(client, fake_llm):
    JUDGE_VERDICTS.append(PlanJudgement(satisfied=False, feedback=[JudgedFeedback(owner="schedule_agent", note="Lunch sits too late; move it before 1 PM.")]))
    event = create_event(client)
    run_id = client.post(f"/api/v1/events/{event['id']}/runs", json={}).json()["run_id"]
    snap = approve_plan(client, run_id)
    assert snap["run"]["status"] == "completed", [(e["type"], e.get("error")) for e in snap["events"]]

    assert fake_llm.count("PlanJudgement") == 2  # judged once unsatisfied, then again after the re-run
    assert len(of_type(snap, "step_started", "schedule_agent")) == 2  # the named specialist re-ran
    assert len(of_type(snap, "step_started", "finance_agent")) == 1  # nobody else did
    replan = of_type(snap, "step_completed", "replan")[0]["summary"]
    assert any("Lunch sits too late" in line for line in replan["did"]), "the note is shown as what was sent"
    assert "Lunch sits too late" not in replan["verification"]["reason"], "the tick doesn't claim the note is fixed"


def test_llm_recovery_options_are_validated_and_custom_text_is_interpreted(client, fake_llm):
    event = create_event(client, location="Coimbatore", attendees=200, budget=1000000)
    TOOL_ARGS_BACKUP = dict(TOOL_ARGS)
    run_id = client.post(f"/api/v1/events/{event['id']}/runs", json={}).json()["run_id"]
    snap = wait_for(client, run_id, {"paused", "completed", "error"})
    assert snap["run"]["status"] == "paused"
    recovery = of_type(snap, "step_failed", "logistics_agent")[0]["recovery"]
    assert recovery["source"] == "llm" and recovery["customPrompt"] == "Try another area or guest count"
    assert [o["id"] for o in recovery["options"]] == ["nearby", "unverified", "skip"]  # 'bad' patch dropped, skip added; no plain retry for a failed check

    question = client.post(f"/api/v1/runs/{run_id}/steps/logistics_agent/resolve", json={"custom_text": "somewhere nice"}).json()
    assert question["status"] == "needs_clarification" and question["question"] == "Which area or guest count?" and question["option"] is None

    resumed = client.post(f"/api/v1/runs/{run_id}/steps/logistics_agent/resolve", json={"custom_text": "Try a beach venue in Goa, keep 200 guests"}).json()
    assert resumed["status"] == "edit_started" and resumed["changes"] == ["location to Goa"], resumed
    snap = approve_plan(client, resumed["run_id"], timeout=120)
    assert snap["run"]["status"] == "completed", snap["run"].get("error")
    second_call = [t for t in of_type(snap, "tool_call", "logistics_agent") if t["tool"]["name"] == "venue_search"][-1]["tool"]["input"]
    assert second_call["location"] == "Goa"
    assert TOOL_ARGS == TOOL_ARGS_BACKUP


def test_manager_repairs_missing_agenda_owners_from_raw_tool_output():
    payload = AiPlanDraft(
        plan_type="wedding reception", venue="Garden Pavilion", venue_detail="Whitefield",
        budget_forecast=500000,
        budget_lines=[{"category": "Venue", "amount": 500000, "share_percent": 100}],
        agenda=[{"time": "6:00 PM", "activity": "Guest arrival and welcome", "owner": "Guest Experience Lead"}],
        risks=[{"level": "Medium", "title": "Rain", "detail": "Outdoor venue", "recommended_action": "Monitor"}, {"level": "Low", "title": "Traffic", "detail": "Peak hour", "recommended_action": "Share routes"}],
        activity=[{"agent": "Event Manager", "detail": "Prepared plan", "timestamp": "Now"}], confidence=85,
    ).model_dump()
    del payload["agenda"][0]["owner"]

    output = {
        "parsed": None,
        "raw": AIMessage(content="", tool_calls=[{"id": "agenda-owner", "name": "AiPlanDraft", "args": payload}]),
        "parsing_error": ValueError("owner missing"),
    }

    draft = _draft_from_output(output)
    assert draft.agenda[0].owner == "Guest Experience Lead"


def _paused(client, **brief):
    event = create_event(client, **brief)
    run_id = client.post(f"/api/v1/events/{event['id']}/runs", json={}).json()["run_id"]
    assert wait_for(client, run_id, {"paused", "completed", "error"})["run"]["status"] == "paused"
    return event, run_id


def _pauses(client, run_id, count):
    import time

    end = time.time() + 60
    while time.time() < end:
        snap = client.get(f"/api/v1/runs/{run_id}").json()
        if snap["run"]["status"] != "running" and len(of_type(snap, "run_paused")) >= count or snap["run"]["status"] in ("completed", "error"):
            return snap
        time.sleep(0.1)
    raise AssertionError("the run didn't pause again")


def test_tone_feedback_is_routed_by_meaning_and_never_rewrites_the_brief(client, fake_llm):
    from app.agents.feedback import OwnerFeedback

    event, run_id = _paused(client)
    OWNER_ROUTES.append(OwnerFeedback(kind="feedback", assignments=[{"owner": "marketing_agent", "note": "Make the invitation and reminders warmer and more celebratory."}], reason="Feedback on tone"))
    sent = client.post(f"/api/v1/runs/{run_id}/steps/approval/resolve", json={"custom_text": "The tone feels too formal; make it feel more celebratory"}).json()
    assert sent["status"] == "resumed", sent
    snap = _pauses(client, run_id, 2)
    assert client.get(f"/api/v1/events/{event['id']}").json()["objective"] == event["objective"], "feedback isn't a brief change"
    assert len(of_type(snap, "step_started", "marketing_agent")) == 2, "the assigned specialist re-ran"
    for step in ("logistics_agent", "finance_agent", "schedule_agent", "requirements_agent", "risk_operations_agent"):
        assert len(of_type(snap, "step_started", step)) == 1, f"{step} wasn't assigned, so it didn't re-run"
    intake = of_type(snap, "step_completed", "manager_intake")[-1]["summary"]["did"]
    assert "Re-split to: Marketing" in intake and any("warmer" in line for line in intake)


def test_a_question_at_approval_is_answered_and_changes_nothing(client, fake_llm):
    from app.agents.feedback import OwnerFeedback

    _, run_id = _paused(client)
    OWNER_ROUTES.append(OwnerFeedback(kind="question", answer="I picked it because it fits 80 guests within the venue budget."))
    answer = client.post(f"/api/v1/runs/{run_id}/steps/approval/resolve", json={"custom_text": "Why did you pick this venue?"}).json()
    assert answer == {**answer, "status": "answered", "question": "I picked it because it fits 80 guests within the venue budget."}
    snap = client.get(f"/api/v1/runs/{run_id}").json()
    assert snap["run"]["status"] == "paused" and of_type(snap, "step_failed", "approval")[-1]["recovery"]["changesLeft"] == 3


def test_notes_still_open_after_the_automatic_replan_are_shown_at_approval(client, fake_llm):
    note = JudgedFeedback(owner="risk_operations_agent", note="The crowd-flow fallback names no owner.")
    JUDGE_VERDICTS.extend([PlanJudgement(satisfied=False, feedback=[note]), PlanJudgement(satisfied=False, feedback=[note])])
    _, run_id = _paused(client)
    snap = client.get(f"/api/v1/runs/{run_id}").json()
    card = of_type(snap, "step_failed", "approval")[-1]["recovery"]
    assert card["preview"]["open_issues"] == ["Review note (Risk & Operations): The crowd-flow fallback names no owner."]
    assert "1 review note(s) still open" in card["summary"]
    assert [o["label"] for o in card["options"]] == ["Approve the plan", "Fix the open notes"]
    assert not of_type(snap, "step_skipped", "replan"), "replan is never marked 'not needed' and then run"
    assert "earlier notes" in PROMPTS["PlanJudgement"][-1], "the re-check is told what it asked for before"

    fixed = client.post(f"/api/v1/runs/{run_id}/steps/approval/resolve", json={"option_id": "revise"}).json()
    assert fixed["status"] == "resumed", fixed
    snap = _pauses(client, run_id, 2)
    assert len(of_type(snap, "step_started", "risk_operations_agent")) == 3, "only the owner of the open note re-ran"
    assert len(of_type(snap, "step_started", "finance_agent")) == 1


def test_the_judge_sees_the_guest_communication_in_the_plan(client, fake_llm):
    _, run_id = _paused(client)
    plan = of_type(client.get(f"/api/v1/runs/{run_id}").json(), "step_failed", "approval")[-1]["recovery"]["preview"]
    assert plan["communications"]["channels"] and any("RSVP deadline" in step for step in plan["communications"]["checkpoints"])
    assert plan["requirements"]
    assert '"communications"' in PROMPTS["PlanJudgement"][0]


def test_logistics_summary_names_the_venue_it_chose():
    from app.agents.specialists import _align_with_verified

    tool = {"recommendations": [{"name": "Vashi Grand Ballroom"}, {"name": "Powai Lakeview"}]}
    model = SpecialistReport(recommendations=["I shortlisted Powai Lakeview at ₹3,80,000", "Parking is good"], decisions={"venue": "Powai Lakeview"})
    verified = SpecialistReport(recommendations=["Shortlisted 2 venue(s)", "Recommend Vashi Grand Ballroom: capacity 200, rent ₹3,00,000"], decisions={"venue": "Vashi Grand Ballroom", "rental_inr": 300000})
    report = _align_with_verified("logistics_agent", model, verified, tool)
    assert report.decisions["venue"] == "Vashi Grand Ballroom" and report.decisions["rental_inr"] == 300000
    assert not any("Powai" in line for line in report.recommendations)
    assert any("Vashi Grand Ballroom" in line for line in report.recommendations)


def test_an_unverified_venue_is_never_a_side_effect_of_another_option():
    from app.agents.recovery import _finalise

    options = _finalise("logistics_agent", [RecoveryOption(id="convention", label="Use a convention venue", patch={"venue_type": "convention centre", "allow_unverified": True})])
    convention = next(o for o in options if o.id == "convention")
    assert convention.patch == {"venue_type": "convention centre"}
    assert any(o.patch == {"allow_unverified": True} for o in options), "accepting an unverified venue stays its own choice"
