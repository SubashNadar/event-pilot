"""Manager-led LangGraph workflow with streamed steps and human-in-the-loop recovery.

    START ─┬─ logistics ──┐
           ├─ finance ────┤
           ├─ schedule ───┤
           ├─ requirements┼─▶ event_manager ─▶ review_plan ─┬─▶ recommendations ─▶ END
           ├─ marketing ──┤                      ▲          │
           └─ risk ───────┘                      └─ reflection (once, if review fails)

Every node reports progress through `emit()` (step_started → tool_call →
step_verifying → step_completed). When a step fails, the recovery assistant
explains why and the node pauses at `interrupt()`. The user's choice (an option
or their own words, already turned into a validated patch by the API) resumes
the node, which runs the step again with those inputs, or skips it.

Expensive work (LLM + tool calls, the failure explanation) runs inside
`@task`s. LangGraph saves task results in the checkpoint, so when a paused run
resumes and the node runs again from the top, earlier attempts are read back
instead of repeated. Attempts return errors as values: a task that raised
would be re-run on resume.
"""

from datetime import datetime, timezone
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.func import task
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.agents import llm
from app.agents.checks import CHECK_TEXT, verify
from app.agents.fmt import inr
from app.agents.recovery import RecoveryProposal, explain_failure
from app.agents.specialists import ROLES, run_specialist
from app.core.config import settings
from app.graphs.emit import emit
from app.graphs.state import EventPlanningState
from app.models.event import EventBrief, EventPlan
from app.services.azure_planner import abuild_plan_with_model
from app.services.planning import compose_rule_plan

SPECIALISTS = ["logistics_agent", "finance_agent", "schedule_agent", "requirements_agent", "marketing_agent", "risk_operations_agent"]

# What the UI shows in `plan_created`. ids are node names; kinds pick hints and icons.
STEPS: list[dict[str, Any]] = [
    {"id": "logistics_agent", "title": "Find a venue", "goal": "Shortlist venues that fit the guests, city and venue budget.", "kind": "logistics", "agent": "Logistics", "group": "parallel"},
    {"id": "finance_agent", "title": "Draft the budget", "goal": "Split the budget into six lines with a contingency reserve.", "kind": "finance", "agent": "Budget & Finance", "group": "parallel"},
    {"id": "schedule_agent", "title": "Build the agenda", "goal": "Plan the event-day agenda without clashes.", "kind": "schedule", "agent": "Schedule", "group": "parallel"},
    {"id": "requirements_agent", "title": "List operational needs", "goal": "Name what the event needs to run, and who owns it.", "kind": "requirements", "agent": "Requirements", "group": "parallel"},
    {"id": "marketing_agent", "title": "Plan guest communication", "goal": "Choose channels and send dates; nothing goes out without approval.", "kind": "marketing", "agent": "Marketing", "group": "parallel"},
    {"id": "risk_operations_agent", "title": "Assess risks", "goal": "Build a risk register with a fallback for every high risk.", "kind": "risk", "agent": "Risk & Operations", "group": "parallel"},
    {"id": "event_manager", "title": "Combine into one plan", "goal": "Merge the specialists' work into a single plan within budget.", "kind": "manager", "agent": "Event Manager", "group": "sequential"},
    {"id": "review_plan", "title": "Review the plan", "goal": "Check budget arithmetic, agenda times and risk coverage.", "kind": "review", "agent": "Event Manager", "group": "sequential"},
    {"id": "reflection_agent", "title": "Fix review issues", "goal": "Revise the plan once if the review finds problems.", "kind": "reflection", "agent": "Event Manager", "group": "sequential"},
    {"id": "recommendations", "title": "Write recommendations", "goal": "Summarise the plan and the top next steps for you.", "kind": "recommend", "agent": "Event Manager", "group": "sequential"},
]
STEP_BY_ID = {step["id"]: step for step in STEPS}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _event(state: EventPlanningState) -> EventBrief:
    return EventBrief.model_validate(state["event"])


def _summary(did: list[str], verification: dict[str, Any], usage: dict[str, int], tool_results: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    sources = []
    for index, result in enumerate(tool_results or []):
        for venue in (result.get("recommendations") or [])[:3]:
            sources.append({"id": f"venue-{index}-{venue['name']}", "label": venue["name"], "kind": "tool"})
    return {
        "did": did,
        "sources": sources,
        "verification": verification,
        "metrics": {"tokensIn": usage.get("tokens_in", 0), "tokensOut": usage.get("tokens_out", 0), "costUsd": llm.cost_usd(usage.get("tokens_in", 0), usage.get("tokens_out", 0)), "model": llm.model_name() if llm.llm_enabled() else "rules"},
    }


# ------------------------------------------------------------------ tasks

@task
async def specialist_attempt(step_id: str, event: dict[str, Any], overrides: dict[str, Any], attempt: int) -> dict[str, Any]:
    try:
        result = await run_specialist(step_id, EventBrief.model_validate(event), overrides, attempt)
        return {"ok": True, **result}
    except Exception as error:  # returned, not raised: failed tasks are not cached
        return {"ok": False, "error": str(error) or error.__class__.__name__}


@task
async def manager_attempt(event: dict[str, Any], context: dict[str, Any], overrides: dict[str, Any], operation: str) -> dict[str, Any]:
    brief = EventBrief.model_validate(event)
    try:
        if overrides.get("use_fallback") or not llm.llm_enabled() or operation == "plan-edit":
            # Plan edits merge in code so the owner's change is the only thing that moves.
            plan = compose_rule_plan(brief, context)
            return {"ok": True, "plan": plan.model_dump(mode="json"), "usage": {}, "mode": "rules"}
        async with llm.limited():
            plan, raw = await abuild_plan_with_model(llm.get_chat_model(), brief, context, None)
        return {"ok": True, "plan": plan.model_dump(mode="json"), "usage": llm.usage_of(raw), "mode": "llm"}
    except Exception as error:
        return {"ok": False, "error": str(error) or error.__class__.__name__}


@task
async def reflection_attempt(event: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    brief = EventBrief.model_validate(event)
    try:
        if not llm.llm_enabled():
            return {"ok": True, "plan": compose_rule_plan(brief, context).model_dump(mode="json"), "usage": {}}
        async with llm.limited():
            plan, raw = await abuild_plan_with_model(llm.get_chat_model(), brief, context, None)
        return {"ok": True, "plan": plan.model_dump(mode="json"), "usage": llm.usage_of(raw)}
    except Exception as error:
        return {"ok": False, "error": str(error) or error.__class__.__name__}


@task
async def explain_attempt(step_id: str, error: str, event: dict[str, Any], overrides: dict[str, Any], attempt: int, context: dict[str, Any] | None = None) -> dict[str, Any]:
    proposal = await explain_failure(step_id, STEP_BY_ID[step_id]["goal"], error, EventBrief.model_validate(event), overrides, attempt, context=context)
    return proposal.model_dump()


# ------------------------------------------------------------------ step runner

async def run_with_recovery(step_id: str, state: EventPlanningState, attempt_fn, check_fn, *, on_success, on_skip, initial_overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run a step; on failure explain it, pause for the user's choice, then retry or skip."""
    overrides: dict[str, Any] = dict(initial_overrides or {})
    interactive = state.get("interactive", True)
    for attempt in range(1, settings.max_step_attempts + 1):
        emit({"type": "step_started", "stepId": step_id, "attempt": attempt, "at": _now()}, dedupe=f"started:{step_id}:{attempt}")
        result = await attempt_fn(overrides, attempt)
        if result.get("ok"):
            emit({"type": "step_verifying", "stepId": step_id, "check": CHECK_TEXT.get(step_id, "Checking the result…")}, dedupe=f"verifying:{step_id}:{attempt}")
            verification = check_fn(result, overrides)
            if verification["passed"]:
                return on_success(result, verification, overrides, attempt)
            error = f"Check failed: {verification['reason']}"
        else:
            error = result.get("error", "Unknown error")

        if not interactive:  # legacy blocking API: never pause
            break
        context = ((result.get("tool_results") or [{}])[-1] or {}).get("near_misses") if result.get("ok") else None
        proposal = RecoveryProposal.model_validate(await explain_attempt(step_id, error, state["event"], overrides, attempt, context))
        emit({"type": "step_failed", "stepId": step_id, "error": error, "attempt": attempt, "retryable": True, "recovery": proposal.model_dump()}, dedupe=f"failed:{step_id}:{attempt}")
        choice = interrupt({"step_id": step_id, "attempt": attempt, "error": error, "proposal": proposal.model_dump(), "overrides": overrides})
        emit({"type": "run_resumed", "stepId": step_id, "action": choice.get("action"), "label": choice.get("label", "")}, dedupe=f"resumed:{step_id}:{attempt}")
        if choice.get("action") == "skip":
            return on_skip(choice.get("label") or "Skipped by you")
        overrides = {**overrides, **(choice.get("patch") or {})}
    return on_skip(f"Stopped after {settings.max_step_attempts} attempts" if interactive else "Skipped automatically after a failure")


def specialist_node(step_id: str):
    role = ROLES[step_id]

    async def node(state: EventPlanningState) -> dict[str, Any]:
        event = _event(state)
        kept = (state.get("reuse") or {}).get(step_id)
        if kept:  # plan edit: this step isn't affected, keep its report
            emit({"type": "step_started", "stepId": step_id, "attempt": 1, "at": _now()}, dedupe=f"started:{step_id}:1")
            verification = {"check": "Not affected by your change", "passed": True, "reason": "Kept from the current plan"}
            emit({"type": "step_completed", "stepId": step_id, "summary": _summary(["Kept from the current plan; your change doesn't affect this step"], verification, {}), "at": _now()}, dedupe=f"completed:{step_id}")
            return {role.state_key: kept, "steps": {step_id: {"status": "completed", "kept": True}}}

        def on_success(result, verification, overrides, attempt):
            report = {**result["report"], "agent": role.agent, "user_adjustments": overrides, "tool_results": [{k: v for k, v in r.items() if k != "_args"} for r in result["tool_results"]], "mode": result.get("mode")}
            emit({"type": "step_completed", "stepId": step_id, "summary": _summary(result["report"]["recommendations"], verification, result.get("usage", {}), result["tool_results"]), "at": _now()}, dedupe=f"completed:{step_id}")
            return {role.state_key: report, "steps": {step_id: {"status": "completed", "attempts": attempt}}, "usage": result.get("usage", {})}

        def on_skip(reason):
            emit({"type": "step_skipped", "stepId": step_id, "reason": reason}, dedupe=f"skipped:{step_id}")
            return {role.state_key: {"skipped": True, "agent": role.agent, "reason": reason}, "steps": {step_id: {"status": "skipped", "reason": reason}}}

        return await run_with_recovery(
            step_id, state,
            lambda overrides, attempt: specialist_attempt(step_id, state["event"], overrides, attempt),
            lambda result, overrides: verify(step_id, result, event, overrides).model_dump(),
            on_success=on_success, on_skip=on_skip,
            initial_overrides=(state.get("step_overrides") or {}).get(step_id),
        )

    node.__name__ = step_id
    return node


def _context(state: EventPlanningState) -> dict[str, Any]:
    return {role.state_key: state.get(role.state_key, {}) for role in ROLES.values()}


async def event_manager(state: EventPlanningState) -> dict[str, Any]:
    context = _context(state)

    def check(result, overrides):
        try:
            plan = EventPlan.model_validate(result["plan"])
        except Exception as error:
            return {"check": "Plan matches the schema", "passed": False, "reason": str(error)[:200]}
        return {"check": "Plan matches the schema", "passed": True, "reason": f"{len(plan.budget_lines)} budget lines, {len(plan.agenda)} agenda items, {len(plan.risks)} risks"}

    def on_success(result, verification, overrides, attempt):
        plan = result["plan"]
        skipped = [ctx.get("agent") for ctx in context.values() if ctx.get("skipped")]
        did = [f"Combined {6 - len(skipped)} specialist reports" + (f" ({', '.join(skipped)} skipped)" if skipped else ""), f"Venue: {plan['venue']}", f"Forecast {inr(plan['budget_forecast'])} of {inr(state['event']['budget'])}"]
        if result.get("mode") == "rules":
            did.append("Built with the rule-based planner")
        emit({"type": "step_completed", "stepId": "event_manager", "summary": _summary(did, verification, result.get("usage", {})), "at": _now()}, dedupe="completed:event_manager")
        return {"final_plan": plan, "steps": {"event_manager": {"status": "completed", "attempts": attempt}}, "usage": result.get("usage", {})}

    def on_skip(reason):  # not offered to users; only reached when attempts run out
        plan = compose_rule_plan(_event(state), context).model_dump(mode="json")
        emit({"type": "notice", "message": f"The Event Manager failed ({reason}); the plan was built with the rule-based planner."})
        emit({"type": "step_completed", "stepId": "event_manager", "summary": _summary(["Built with the rule-based planner after repeated failures"], {"check": "Plan matches the schema", "passed": True, "reason": "Rule-based plan"}, {}), "at": _now()}, dedupe="completed:event_manager")
        return {"final_plan": plan, "steps": {"event_manager": {"status": "completed", "fallback": True}}}

    return await run_with_recovery(
        "event_manager", state,
        lambda overrides, attempt: manager_attempt(state["event"], context, overrides, state.get("operation", "plan-generation")),
        check, on_success=on_success, on_skip=on_skip,
    )


def _review(event: dict[str, Any], plan: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if plan["budget_forecast"] > event["budget"]:
        issues.append("Budget forecast exceeds the approved budget.")
    if sum(line["amount"] for line in plan["budget_lines"]) != plan["budget_forecast"]:
        issues.append("Budget lines do not sum to the forecast.")
    if any("AM" not in item["time"] and "PM" not in item["time"] for item in plan["agenda"]):
        issues.append("Agenda includes a time outside the required 12-hour format.")
    if not 2 <= len(plan["risks"]) <= 5:
        issues.append("The plan needs between two and five risks.")
    return issues


async def review_plan(state: EventPlanningState) -> dict[str, Any]:
    pass_number = state.get("revision_count", 0) + 1
    emit({"type": "step_started", "stepId": "review_plan", "attempt": pass_number, "at": _now()}, dedupe=f"started:review_plan:{pass_number}")
    emit({"type": "step_verifying", "stepId": "review_plan", "check": CHECK_TEXT["review_plan"]}, dedupe=f"verifying:review_plan:{pass_number}")
    issues = _review(state["event"], state["final_plan"])
    approved = not issues
    verification = {"check": "Budget sums, 12-hour times, 2–5 risks", "passed": approved, "reason": "All checks passed" if approved else " ".join(issues)}
    did = ["Checked budget arithmetic, agenda times and risk count"] + (["Found issues; sending back for one revision"] if issues and pass_number == 1 else [])
    emit({"type": "step_completed", "stepId": "review_plan", "summary": _summary(did, verification, {}), "at": _now()}, dedupe=f"completed:review_plan:{pass_number}")
    if approved and pass_number == 1:
        emit({"type": "step_skipped", "stepId": "reflection_agent", "reason": "Not needed — the review passed"}, dedupe="skipped:reflection_agent")
    return {"review": {"approved": approved, "issues": issues}, "steps": {"review_plan": {"status": "completed", "passes": pass_number}}}


async def reflection_agent(state: EventPlanningState) -> dict[str, Any]:
    emit({"type": "step_started", "stepId": "reflection_agent", "attempt": 1, "at": _now()}, dedupe="started:reflection_agent:1")
    context = {**_context(state), "previous_plan": state["final_plan"], "review_feedback": state["review"]}
    result = await reflection_attempt(state["event"], context)
    revision = state.get("revision_count", 0) + 1
    if not result.get("ok"):
        reason = f"Kept the first plan: {result.get('error')}"
        emit({"type": "step_skipped", "stepId": "reflection_agent", "reason": reason}, dedupe="skipped:reflection_agent")
        return {"revision_count": revision, "steps": {"reflection_agent": {"status": "skipped", "reason": reason}}}
    verification = {"check": "Revised plan addresses the review", "passed": True, "reason": "Revised plan sent back to review"}
    emit({"type": "step_completed", "stepId": "reflection_agent", "summary": _summary(["Revised the plan to fix: " + " ".join(state["review"]["issues"])], verification, result.get("usage", {})), "at": _now()}, dedupe="completed:reflection_agent")
    return {"final_plan": result["plan"], "revision_count": revision, "steps": {"reflection_agent": {"status": "completed"}}, "usage": result.get("usage", {})}


def route_after_review(state: EventPlanningState) -> str:
    if not state["review"]["approved"] and state.get("revision_count", 0) < 1:
        return "reflection_agent"
    return "recommendations"


def _rule_recommendations(event: dict[str, Any], plan: dict[str, Any], context: dict[str, Any]) -> str:
    reserve = event["budget"] - plan["budget_forecast"]
    lines = [
        f"## {event['name']}",
        "",
        f"The plan keeps the forecast at {inr(plan['budget_forecast'])} of {inr(event['budget'])}, leaving {inr(max(reserve, 0))} in reserve. The venue is **{plan['venue']}**.",
        "",
        "**Next steps**",
        "",
    ]
    high = [risk for risk in plan["risks"] if risk["level"] == "High"]
    unverified = "(to be confirmed)" in plan["venue"] or "unverified" in plan.get("venue_detail", "")
    steps = ["Find and confirm a venue: none in the EventPilot catalog fit, so get two quotes before booking." if unverified else f"Confirm {plan['venue']} availability and get a written quote."]
    if high:
        steps.append(f"Decide the fallback for “{high[0]['title']}”: {high[0]['detail']}")
    steps.append(f"Review the agenda starting at {plan['agenda'][0]['time']} with your programme owner.")
    skipped = [ctx.get("agent") for ctx in context.values() if ctx.get("skipped")]
    if skipped:
        steps.append(f"Cover the skipped areas yourself: {', '.join(skipped)}.")
    lines += [f"{index}. {step}" for index, step in enumerate(steps, 1)]
    return "\n".join(lines)


async def recommendations(state: EventPlanningState, config: RunnableConfig) -> dict[str, Any]:
    emit({"type": "step_started", "stepId": "recommendations", "attempt": 1, "at": _now()}, dedupe="started:recommendations:1")
    plan, event, context = state["final_plan"], state["event"], _context(state)
    text = ""
    usage: dict[str, int] = {}
    if llm.llm_enabled():
        prompt = (
            "Write the event owner a short markdown summary of this plan: a heading with the event name, one sentence on budget and venue, "
            "then '**Next steps**' and 3-4 numbered, specific actions (use ₹ and Indian number formatting). No preamble, no emoji.\n"
            f"Brief: {event}\nPlan: {plan}\nSkipped specialists: {[c.get('agent') for c in context.values() if c.get('skipped')]}"
        )
        try:
            async with llm.limited():
                async for chunk in llm.get_chat_model().astream(prompt, config=config):
                    piece = chunk.content if isinstance(chunk.content, str) else ""
                    if piece:
                        text += piece
                        emit({"type": "token", "content": piece})
                    if getattr(chunk, "usage_metadata", None):
                        usage = llm.usage_of(chunk)
        except Exception:
            text = ""
    if not text:
        text = _rule_recommendations(event, plan, context)
        for index in range(0, len(text), 24):
            emit({"type": "token", "content": text[index:index + 24]})
    emit({"type": "step_completed", "stepId": "recommendations", "summary": _summary(["Wrote the summary and next steps"], {"check": "Summary written", "passed": True, "reason": f"{len(text.split())} words"}, usage), "at": _now()}, dedupe="completed:recommendations")
    return {"recommendations": text, "final_plan": {**plan, "recommendations": text}, "steps": {"recommendations": {"status": "completed"}}, "usage": usage}


def build_graph():
    workflow = StateGraph(EventPlanningState)
    for step_id in SPECIALISTS:
        workflow.add_node(step_id, specialist_node(step_id))
        workflow.add_edge(START, step_id)
    workflow.add_node("event_manager", event_manager)
    workflow.add_node("review_plan", review_plan)
    workflow.add_node("reflection_agent", reflection_agent)
    workflow.add_node("recommendations", recommendations)
    workflow.add_edge(SPECIALISTS, "event_manager")  # waits for all six (completed or skipped)
    workflow.add_edge("event_manager", "review_plan")
    workflow.add_conditional_edges("review_plan", route_after_review, {"reflection_agent": "reflection_agent", "recommendations": "recommendations"})
    workflow.add_edge("reflection_agent", "review_plan")
    workflow.add_edge("recommendations", END)
    return workflow
