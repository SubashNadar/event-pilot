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


class _Structured:
    def __init__(self, schema, include_raw):
        self.schema, self.include_raw = schema, include_raw

    async def ainvoke(self, messages, config=None):
        name = self.schema.__name__
        CALLS.append(name)
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
    assert "Lunch sits too late" in of_type(snap, "step_completed", "replan")[0]["summary"]["verification"]["reason"]


def test_llm_recovery_options_are_validated_and_custom_text_is_interpreted(client, fake_llm):
    event = create_event(client, location="Shillong", attendees=200, budget=1000000)
    TOOL_ARGS_BACKUP = dict(TOOL_ARGS)
    run_id = client.post(f"/api/v1/events/{event['id']}/runs", json={}).json()["run_id"]
    snap = wait_for(client, run_id, {"paused", "completed", "error"})
    assert snap["run"]["status"] == "paused"
    recovery = of_type(snap, "step_failed", "logistics_agent")[0]["recovery"]
    assert recovery["source"] == "llm" and recovery["customPrompt"] == "Try another area or guest count"
    assert [o["id"] for o in recovery["options"]] == ["nearby", "unverified", "retry", "skip"]  # 'bad' patch dropped, retry + skip added

    question = client.post(f"/api/v1/runs/{run_id}/steps/logistics_agent/resolve", json={"custom_text": "somewhere nice"}).json()
    assert question == {"status": "needs_clarification", "question": "Which area or guest count?", "option": None}

    resumed = client.post(f"/api/v1/runs/{run_id}/steps/logistics_agent/resolve", json={"custom_text": "Try a beach venue in Goa, keep 200 guests"}).json()
    assert resumed["status"] == "resumed" and resumed["option"]["patch"] == {"location": "Goa", "allow_unverified": True}
    snap = approve_plan(client, run_id)
    assert snap["run"]["status"] == "completed"
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
