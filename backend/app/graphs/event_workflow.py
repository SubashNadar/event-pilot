"""Manager-led LangGraph workflow with streamed steps and human-in-the-loop recovery.

    START ─▶ receptionist ─▶ manager_intake ─▶ logistics ─┬─ finance ────┐
    (takes the brief)        (splits the work)           ├─ schedule ───┤
                                          ├─ requirements┼─▶ coordination ─▶ event_manager ─▶ review_plan ─▶ plan_judge
                                          ├─ marketing ──┤                        ▲                            │
                                          └─ risk ───────┘                        │      rules or judge fail   │ judge satisfied
                                                                                  └──── replan ◀───────────────┤ (feedback to the
                                                                                        (up to max_replans)    │  flagged specialists)
                                                                                                               ▼
                 manager_intake ◀── revise ── approval ◀── recommendations
       (re-splits the owner's feedback)          │
                 │                               └── approve ──▶ END
                 └──────────▶ replan ──▶ coordination ─▶ ... (until the owner approves)

The Event Manager splits the work, the specialists complete their parts, and the
manager reviews them: it approves, or sends feedback to the owning specialist and
re-runs only that part. When the manager is satisfied, the owner reviews the plan.
If the owner sends it back, the manager reads the feedback, re-splits it to the
right specialists, and the loop repeats until the owner and the manager are both
satisfied.

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

import re
from datetime import datetime, timezone
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.func import task
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.agents import llm
from app.agents.checks import CHECK_TEXT, verify
from app.agents.feedback import rule_owners, with_dependents
from app.agents.fmt import inr
from app.agents.judge import judge_plan
from app.agents.recovery import RecoveryProposal, explain_failure, fresh_options
from app.agents.specialists import ROLES, normalise_budget_lines, run_specialist
from app.core.guard import DATA_RULE, wrap_user
from app.core.config import settings
from app.graphs.emit import emit
from app.graphs.state import EventPlanningState
from app.models.event import EventBrief, EventPlan
from app.models.run import RecoveryOption
from app.services import ui_state
from app.services.azure_planner import abuild_plan_with_model
from app.services.planning import compose_rule_plan

SPECIALISTS = ["logistics_agent", "finance_agent", "schedule_agent", "requirements_agent", "marketing_agent", "risk_operations_agent"]

# What the UI shows in `plan_created`. ids are node names; kinds pick hints and icons.
# `lane` groups steps for the UI: reception -> split (manager) -> specialists -> review (manager) -> owner.
STEPS: list[dict[str, Any]] = [
    {"id": "receptionist", "title": "Receive the brief", "goal": "Check the brief is complete and hand it to the Event Manager.", "kind": "intake", "agent": "Receptionist", "group": "sequential", "lane": "reception"},
    {"id": "manager_intake", "title": "Split the work", "goal": "Turn the brief into the team's plan: what each specialist must cover.", "kind": "manager", "agent": "Event Manager", "group": "sequential", "lane": "split"},
    {"id": "logistics_agent", "title": "Find a venue", "goal": "Shortlist venues that fit the guests, city and venue budget.", "kind": "logistics", "agent": "Logistics", "group": "parallel", "lane": "specialists"},
    {"id": "finance_agent", "title": "Draft the budget", "goal": "Split the budget into six lines with a contingency reserve.", "kind": "finance", "agent": "Budget & Finance", "group": "parallel", "lane": "specialists"},
    {"id": "schedule_agent", "title": "Build the agenda", "goal": "Plan the event-day agenda without clashes.", "kind": "schedule", "agent": "Schedule", "group": "parallel", "lane": "specialists"},
    {"id": "requirements_agent", "title": "List operational needs", "goal": "Name what the event needs to run, and who owns it.", "kind": "requirements", "agent": "Requirements", "group": "parallel", "lane": "specialists"},
    {"id": "marketing_agent", "title": "Plan guest communication", "goal": "Choose channels and send dates; nothing goes out without approval.", "kind": "marketing", "agent": "Marketing", "group": "parallel", "lane": "specialists"},
    {"id": "risk_operations_agent", "title": "Assess risks", "goal": "Build a risk register with a fallback for every high risk.", "kind": "risk", "agent": "Risk & Operations", "group": "parallel", "lane": "specialists"},
    {"id": "coordination", "title": "Compare the team's plans", "goal": "Check that the venue, its rent and the budget agree across the specialists.", "kind": "coordinate", "agent": "Event Manager", "group": "sequential", "lane": "review"},
    {"id": "event_manager", "title": "Combine into one plan", "goal": "Merge the specialists' work into a single plan within budget.", "kind": "manager", "agent": "Event Manager", "group": "sequential", "lane": "review"},
    {"id": "review_plan", "title": "Review the plan", "goal": "Check budget arithmetic, agenda times and risk coverage.", "kind": "review", "agent": "Event Manager", "group": "sequential", "lane": "review"},
    {"id": "replan", "title": "Re-plan the flagged parts", "goal": "Re-run only the specialists the review points to, using its feedback.", "kind": "reflection", "agent": "Event Manager", "group": "sequential", "lane": "review"},
    {"id": "approval", "title": "Approve the plan", "goal": "Nothing is final until you approve it, or send it back to the Event Manager.", "kind": "approve", "agent": "Event owner", "group": "sequential", "lane": "owner"},
    {"id": "recommendations", "title": "Write recommendations", "goal": "Summarise the plan and the top next steps for you.", "kind": "recommend", "agent": "Event Manager", "group": "sequential", "lane": "owner"},
]
STEP_BY_ID = {step["id"]: step for step in STEPS}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _event(state: EventPlanningState) -> EventBrief:
    return EventBrief.model_validate(state["event"])


def _summary(did: list[str], verification: dict[str, Any], usage: dict[str, int], tool_results: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    sources = []
    for index, result in enumerate(tool_results or []):
        if not isinstance(result, dict):
            continue
        for venue in (result.get("recommendations") or [])[:3]:
            if isinstance(venue, dict) and venue.get("name"):
                sources.append({"id": f"venue-{index}-{venue['name']}", "label": venue["name"], "kind": "tool"})
    return {
        "did": did,
        "sources": sources,
        "verification": verification,
        "metrics": {"tokensIn": usage.get("tokens_in", 0), "tokensOut": usage.get("tokens_out", 0), "costUsd": llm.cost_usd(usage.get("tokens_in", 0), usage.get("tokens_out", 0)), "model": llm.model_name() if llm.llm_enabled() else "rules"},
    }


def _reconcile_manager_plan(plan: dict[str, Any], context: dict[str, Any], budget: int) -> dict[str, Any]:
    """Keep an LLM manager draft aligned with facts verified by specialists.

    The manager remains responsible for synthesis and narrative choices, while
    tool-backed specialist decisions remain the source of truth for venue,
    venue rent and agenda timing. This prevents a plausible-looking LLM draft
    from undoing a verified handoff and triggering avoidable reflection loops.
    """
    reconciled = dict(plan)
    logistics = context.get("logistics") if isinstance(context.get("logistics"), dict) else {}
    logistics_decisions = logistics.get("decisions") if isinstance(logistics.get("decisions"), dict) else {}
    if logistics_decisions.get("venue"):
        reconciled["venue"] = logistics_decisions["venue"]
    if logistics_decisions.get("venue_detail"):
        reconciled["venue_detail"] = logistics_decisions["venue_detail"]

    finance = context.get("finance") if isinstance(context.get("finance"), dict) else {}
    finance_decisions = finance.get("decisions") if isinstance(finance.get("decisions"), dict) else {}
    raw_lines = finance_decisions.get("budget_lines")
    if isinstance(raw_lines, list):
        lines = [
            {"category": str(line["category"]), "amount": int(line["amount"])}
            for line in raw_lines
            if isinstance(line, dict) and line.get("category") and isinstance(line.get("amount"), (int, float))
        ]
        total = sum(line["amount"] for line in lines)
        if lines and total <= budget:
            reconciled["budget_lines"] = [
                {**line, "share_percent": round(line["amount"] / total * 100) if total else 0}
                for line in lines
            ]
            reconciled["budget_forecast"] = total

    schedule = context.get("schedule") if isinstance(context.get("schedule"), dict) else {}
    schedule_decisions = schedule.get("decisions") if isinstance(schedule.get("decisions"), dict) else {}
    raw_agenda = schedule_decisions.get("agenda")
    if isinstance(raw_agenda, list) and raw_agenda:
        owners = {(item.get("time"), item.get("activity")): item.get("owner", "Event operations") for item in plan.get("agenda", []) if isinstance(item, dict)}
        agenda = [
            {"time": str(item["time"]), "activity": str(item["activity"]), "owner": owners.get((item.get("time"), item.get("activity")), "Event operations")}
            for item in raw_agenda
            if isinstance(item, dict) and item.get("time") and item.get("activity")
        ]
        if agenda:
            reconciled["agenda"] = agenda
    return reconciled


# ------------------------------------------------------------------ tasks

@task
async def specialist_attempt(step_id: str, event: dict[str, Any], overrides: dict[str, Any], attempt: int) -> dict[str, Any]:
    try:
        result = _normalise_result(await run_specialist(step_id, EventBrief.model_validate(event), overrides, attempt))
        return {"ok": True, **result}
    except Exception as error:  # returned, not raised: failed tasks are not cached
        return {"ok": False, "error": str(error) or error.__class__.__name__}


def _normalise_result(result: dict[str, Any]) -> dict[str, Any]:
    """Models may shape decisions differently: budget lines must be {category, amount}, and the venue a name."""
    decisions = (result.get("report") or {}).get("decisions") or {}
    if "budget_lines" in decisions:
        decisions["budget_lines"] = normalise_budget_lines(decisions["budget_lines"])
    venue = decisions.get("venue")
    if isinstance(venue, dict):  # the model returned the venue as an object; the plan and checks compare names
        decisions["venue"] = str(venue.get("name") or "")
        decisions["rental_inr"] = decisions.get("rental_inr") or venue.get("rental_inr")
        decisions.setdefault("venue_detail", ", ".join(str(venue[key]) for key in ("location", "capacity") if venue.get(key)))
    return result


def _attach_sections(plan: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Carry Marketing's guest communication and the Requirements list into the plan, so the review judges what exists."""
    marketing = (context.get("marketing") or {}) if not (context.get("marketing") or {}).get("skipped") else {}
    decisions = marketing.get("decisions") or {}
    if decisions.get("channels"):
        draft = decisions.get("invite_draft") or {}
        plan["communications"] = {
            "channels": list(decisions["channels"]),
            "checkpoints": list(decisions.get("checkpoints") or []),
            "invite_draft": draft.get("text", "") if isinstance(draft, dict) else "",
            "approval": "Every send waits for the owner's approval",
        }
    requirements = ((context.get("requirements") or {}).get("decisions") or {}).get("requirements")
    if isinstance(requirements, list) and requirements:
        plan["requirements"] = [str(item) for item in requirements][:12]
    return plan


def merge_edit(base: dict[str, Any], context: dict[str, Any], changed: set[str]) -> dict[str, Any]:
    """An edit of an existing plan: replace only the sections owned by the specialists that re-ran (`changed`, state keys).

    Everything else stays exactly as the owner saw it: no planner rebuilds the risks or the agenda behind their back."""
    plan = {key: value for key, value in base.items() if key not in ("run_id", "generated_at", "recommendations", "approved_budget", "caveats", "open_issues")}
    logistics = (context.get("logistics") or {}).get("decisions") or {}
    if "logistics" in changed and logistics.get("venue"):
        plan["venue"] = logistics["venue"]
        plan["venue_detail"] = logistics.get("venue_detail", plan.get("venue_detail", "")) + (" (unverified)" if logistics.get("unverified") else "")
    lines = ((context.get("finance") or {}).get("decisions") or {}).get("budget_lines")
    if "finance" in changed and lines:
        total = sum(int(line["amount"]) for line in lines)
        plan["budget_lines"] = [{"category": line["category"], "amount": int(line["amount"]), "share_percent": round(int(line["amount"]) / total * 100) if total else 0} for line in lines]
        plan["budget_forecast"] = total
    agenda = ((context.get("schedule") or {}).get("decisions") or {}).get("agenda")
    if "schedule" in changed and agenda:
        owners = {item["activity"]: item.get("owner") for item in base.get("agenda", [])}
        plan["agenda"] = [{"time": item["time"], "activity": item["activity"], "owner": item.get("owner") or owners.get(item["activity"]) or "Event operations"} for item in agenda]
    risks = ((context.get("risks") or {}).get("decisions") or {}).get("risks")
    if "risks" in changed and risks:
        before = {risk["title"]: risk for risk in base.get("risks", [])}
        merged = [{"level": r["level"], "title": r["title"], "detail": r.get("action") or r.get("detail", ""), "recommended_action": before.get(r["title"], {}).get("recommended_action") or ("Set fallback" if r["level"] == "High" else "Monitor")} for r in risks[:5]]
        if len(merged) >= 2:
            plan["risks"] = merged
    for key in ("logistics", "finance", "schedule", "requirements", "marketing", "risks"):
        if key in changed and (context.get(key) or {}).get("skipped") and len(plan["risks"]) < 5:
            agent = context[key].get("agent", key)
            plan["risks"] = [*plan["risks"], {"level": "Medium", "title": f"{agent} step was skipped", "detail": f"The {agent} specialist was skipped while applying your change; review this area manually.", "recommended_action": "Review manually"}]
    return _attach_sections(plan, context)


@task
async def manager_attempt(event: dict[str, Any], context: dict[str, Any], overrides: dict[str, Any], operation: str, base: dict[str, Any] | None = None, changed: list[str] | None = None) -> dict[str, Any]:
    brief = EventBrief.model_validate(event)
    try:
        if base:
            # A re-plan or an edit merges the re-run specialists' sections into the existing plan, so only what they changed moves.
            plan = merge_edit(base, context, set(changed or []))
            return {"ok": True, "plan": EventPlan.model_validate({**plan, "event_id": brief.id}).model_dump(mode="json"), "usage": {}, "mode": "edit"}
        if overrides.get("use_fallback") or not llm.llm_enabled():
            plan = compose_rule_plan(brief, context)
            return {"ok": True, "plan": _attach_sections(plan.model_dump(mode="json"), context), "usage": {}, "mode": "rules"}
        async with llm.limited():
            plan, raw = await abuild_plan_with_model(llm.get_chat_model(), brief, context, None)
        return {"ok": True, "plan": _attach_sections(_reconcile_manager_plan(plan.model_dump(mode="json"), context, brief.budget), context), "usage": llm.usage_of(raw), "mode": "llm"}
    except Exception as error:
        return {"ok": False, "error": str(error) or error.__class__.__name__}


@task
async def judge_attempt(event: dict[str, Any], plan: dict[str, Any], reports: dict[str, Any], earlier: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        judgement, usage = await judge_plan(event, plan, reports, earlier)
        return {"ok": True, "judgement": judgement.model_dump(mode="json"), "usage": usage}
    except Exception as error:  # returned, not raised, as with the other tasks
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
    rev = state.get("revision_count", 0)
    attempt = 0
    while True:  # the owner can answer a failed step as many times as needed; only the approval changes are capped
        attempt += 1
        emit({"type": "step_started", "stepId": step_id, "attempt": attempt, "at": _now()}, dedupe=f"started:{step_id}:{rev}:{attempt}")
        result = await attempt_fn(overrides, attempt)
        if result.get("ok"):
            emit({"type": "step_verifying", "stepId": step_id, "check": CHECK_TEXT.get(step_id, "Checking the result…")}, dedupe=f"verifying:{step_id}:{rev}:{attempt}")
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
        # A specialist's check runs on a tool result: the same inputs give the same result, so a plain retry isn't offered.
        proposal.options = fresh_options(proposal.options, overrides, deterministic=step_id in ROLES and error.startswith("Check failed"))
        emit({"type": "step_failed", "stepId": step_id, "error": error, "attempt": attempt, "retryable": True, "recovery": proposal.model_dump()}, dedupe=f"failed:{step_id}:{rev}:{attempt}")
        choice = interrupt({"step_id": step_id, "attempt": attempt, "error": error, "proposal": proposal.model_dump(), "overrides": overrides})
        emit({"type": "run_resumed", "stepId": step_id, "action": choice.get("action"), "label": choice.get("label", "")}, dedupe=f"resumed:{step_id}:{rev}:{attempt}")
        if choice.get("action") == "skip":
            return on_skip(choice.get("label") or "Skipped by you")
        overrides = {**overrides, **(choice.get("patch") or {})}
    return on_skip("Skipped automatically after a failure")  # reached only without an owner: the loop above ends at the first failure


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
            report = {**result["report"], "agent": role.agent, "user_adjustments": {k: v for k, v in overrides.items() if k not in INTERNAL_KEYS}, "tool_results": [{k: v for k, v in r.items() if k != "_args"} for r in result["tool_results"]], "mode": result.get("mode")}
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
            initial_overrides=_specialist_overrides(state, step_id),
        )

    node.__name__ = step_id
    return node


def _context(state: EventPlanningState) -> dict[str, Any]:
    return {role.state_key: state.get(role.state_key, {}) for role in ROLES.values()}


async def event_manager(state: EventPlanningState) -> dict[str, Any]:
    context = {**_context(state), "conflicts": state.get("conflicts") or {"items": []}}

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
        items = (context.get("conflicts") or {}).get("items") or []
        if items:
            did.append(f"Checked {len(items)} cross-team mismatch(es) against Logistics' venue and rent")
        if result.get("mode") == "rules":
            did.append("Built with the rule-based planner")
        if result.get("mode") == "edit":
            did.append("Kept the rest of the plan as it was; only the re-run specialists' parts changed")
        emit({"type": "step_completed", "stepId": "event_manager", "summary": _summary(did, verification, result.get("usage", {})), "at": _now()}, dedupe=f"completed:event_manager:{state.get('revision_count', 0)}")
        return {"final_plan": plan, "steps": {"event_manager": {"status": "completed", "attempts": attempt}}, "usage": result.get("usage", {})}

    def on_skip(reason):  # not offered to users; only reached when attempts run out
        plan = _attach_sections(compose_rule_plan(_event(state), context).model_dump(mode="json"), context)
        emit({"type": "notice", "message": f"The Event Manager failed ({reason}); the plan was built with the rule-based planner."})
        emit({"type": "step_completed", "stepId": "event_manager", "summary": _summary(["Built with the rule-based planner after repeated failures"], {"check": "Plan matches the schema", "passed": True, "reason": "Rule-based plan"}, {}), "at": _now()}, dedupe=f"completed:event_manager:{state.get('revision_count', 0)}")
        return {"final_plan": plan, "steps": {"event_manager": {"status": "completed", "fallback": True}}}

    base, changed = _merge_base(state)
    return await run_with_recovery(
        "event_manager", state,
        lambda overrides, attempt: manager_attempt(state["event"], context, overrides, state.get("operation", "plan-generation"), base, changed),
        check, on_success=on_success, on_skip=on_skip,
    )


def _merge_base(state: EventPlanningState) -> tuple[dict[str, Any] | None, list[str]]:
    """The plan to build on, and which specialists' sections changed since it was made.

    After a re-plan (the review's or the owner's), the latest plan stays and only the re-run specialists' parts are
    replaced. An edit run starts from the plan the owner was looking at, with the steps that ran again. A first plan
    has no base: the Event Manager composes it from all six reports."""
    if state.get("final_plan"):
        rev = state.get("revision_count", 0)
        return state["final_plan"], [ROLES[s].state_key for s in SPECIALISTS if (state.get(ROLES[s].state_key) or {}).get("replanned") == rev]
    if state.get("operation") == "plan-edit" and state.get("base_plan"):
        reuse = state.get("reuse") or {}
        return state["base_plan"], [ROLES[s].state_key for s in SPECIALISTS if s not in reuse]
    return None, []


def _review(event: dict[str, Any], plan: dict[str, Any], state: EventPlanningState | None = None) -> list[str]:
    issues: list[str] = []
    if plan["budget_forecast"] > event["budget"]:
        issues.append("Budget forecast exceeds the approved budget.")
    if sum(line["amount"] for line in plan["budget_lines"]) != plan["budget_forecast"]:
        issues.append("Budget lines do not sum to the forecast.")
    if any("AM" not in item["time"] and "PM" not in item["time"] for item in plan["agenda"]):
        issues.append("Agenda includes a time outside the required 12-hour format.")
    if not 2 <= len(plan["risks"]) <= 5:
        issues.append("The plan needs between two and five risks.")
    if state is not None:
        decisions = (state.get("logistics") or {}).get("decisions") or {}
        if decisions.get("venue") and plan.get("venue") != decisions["venue"]:
            issues.append(f"The plan names {plan.get('venue')} but Logistics chose {decisions['venue']}.")
        if decisions.get("rental_inr"):
            venue_line = next((line for line in plan["budget_lines"] if "venue" in line["category"].lower()), None)
            if venue_line and int(venue_line["amount"]) != int(decisions["rental_inr"]):
                issues.append("The venue rent in the budget doesn't match Logistics' quote.")
    return issues


async def review_plan(state: EventPlanningState) -> dict[str, Any]:
    pass_number = state.get("revision_count", 0) + 1
    emit({"type": "step_started", "stepId": "review_plan", "attempt": pass_number, "at": _now()}, dedupe=f"started:review_plan:{pass_number}")
    emit({"type": "step_verifying", "stepId": "review_plan", "check": CHECK_TEXT["review_plan"]}, dedupe=f"verifying:review_plan:{pass_number}")
    issues = _review(state["event"], state["final_plan"], state)
    approved = not issues
    verification = {"check": "Budget sums, 12-hour times, 2–5 risks", "passed": approved, "reason": "All checks passed" if approved else " ".join(issues)}
    manager_round = state.get("manager_round", 0)
    did = ["Checked budget arithmetic, agenda times and risk count"] + (["Found issues; the affected specialists will re-plan"] if issues and manager_round < settings.max_replans else [])
    emit({"type": "step_completed", "stepId": "review_plan", "summary": _summary(did, verification, {}), "at": _now()}, dedupe=f"completed:review_plan:{pass_number}")
    open_issues: list[str] = []
    if not approved and manager_round >= settings.max_replans:
        emit({"type": "notice", "message": f"Still open after {settings.max_replans} re-plans: " + " ".join(issues)})
        open_issues = [f"Plan check: {issue}" for issue in issues]  # the owner decides with these in front of them
    return {"review": {"approved": approved, "issues": issues}, "open_issues": open_issues, "steps": {"review_plan": {"status": "completed", "passes": pass_number}}}


# ------------------------------------------------------------------ coordination and replanning

INTERNAL_KEYS = {"handoff", "feedback"}  # passed between specialists, not owner adjustments

# Which specialists a review issue sends back, most specific first.
REPLAN_OWNERS = [
    (("venue", "rent", "logistics"), ["logistics_agent", "finance_agent"]),
    (("budget", "contingency", "exceeds", "add up"), ["finance_agent"]),
    (("agenda", "time", "12-hour"), ["schedule_agent"]),
    (("risk",), ["risk_operations_agent"]),
]


def _handoff(state: EventPlanningState) -> dict[str, Any]:
    """What Logistics settled: the venue, its quoted rent and any caveat. Teammates build on it."""
    decisions = (state.get("logistics") or {}).get("decisions") or {}
    if not decisions.get("venue"):
        return {"venue": None, "note": "Logistics has not chosen a venue"}
    return {
        "venue": decisions["venue"],
        "venue_detail": decisions.get("venue_detail", ""),
        "rental_inr": decisions.get("rental_inr"),
        "unverified": bool(decisions.get("unverified")),
    }


def _specialist_overrides(state: EventPlanningState, step_id: str) -> dict[str, Any]:
    """Owner adjustments for a step, plus the Logistics handoff for every other specialist."""
    overrides = dict((state.get("step_overrides") or {}).get(step_id) or {})
    if step_id != "logistics_agent":
        overrides["handoff"] = _handoff(state)
    return overrides


def _coordinate_items(state: EventPlanningState) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    logistics = state.get("logistics") or {}
    finance = state.get("finance") or {}
    decisions = logistics.get("decisions") if isinstance(logistics, dict) else {}
    finance_decisions = finance.get("decisions") if isinstance(finance, dict) else {}
    decisions = decisions if isinstance(decisions, dict) else {}
    finance_decisions = finance_decisions if isinstance(finance_decisions, dict) else {}
    lines = finance_decisions.get("budget_lines") or []
    lines = [line for line in lines if isinstance(line, dict) and "amount" in line] if isinstance(lines, list) else []
    venue_line = next((line for line in lines if "venue" in str(line.get("category", "")).lower()), None)
    if decisions.get("rental_inr") and venue_line and int(venue_line["amount"]) != int(decisions["rental_inr"]):
        items.append({"id": "venue-rent", "owner": "finance_agent", "message": f"The budget has {inr(venue_line['amount'])} for the venue, but Logistics quoted {inr(decisions['rental_inr'])} for {decisions['venue']}."})
    total = sum(int(line["amount"]) for line in lines)
    if lines and total > int(state["event"]["budget"]):
        items.append({"id": "budget-total", "owner": "finance_agent", "message": f"The budget lines add up to {inr(total)}, above the {inr(state['event']['budget'])} approved."})
    return items


async def coordination(state: EventPlanningState) -> dict[str, Any]:
    """Cross-check the specialists against each other before the manager composes the plan."""
    rev = state.get("revision_count", 0)
    emit({"type": "step_started", "stepId": "coordination", "attempt": rev + 1, "at": _now()}, dedupe=f"started:coordination:{rev}")
    emit({"type": "step_verifying", "stepId": "coordination", "check": CHECK_TEXT["coordination"]}, dedupe=f"verifying:coordination:{rev}")
    items = _coordinate_items(state)
    reports = [key for key in ("logistics", "finance", "schedule", "requirements", "marketing", "risks") if state.get(key)]
    did = [f"Compared {len(reports)} specialist reports", "No mismatches between the specialists" if not items else f"Found {len(items)} mismatch(es) for the Event Manager to reconcile"]
    unverified = bool(((state.get("logistics") or {}).get("decisions") or {}).get("unverified"))
    agree = "The venue is unverified, so there is no quoted rent to compare: the venue line is an estimate" if unverified else "Venue, rent and budget agree"
    if unverified:
        did.append("The venue is outside the catalog: get a quote before relying on the venue budget line")
    verification = {"check": CHECK_TEXT["coordination"], "passed": not items, "reason": agree if not items else " ".join(item["message"] for item in items)}
    emit({"type": "step_completed", "stepId": "coordination", "summary": _summary(did, verification, {}), "at": _now()}, dedupe=f"completed:coordination:{rev}")
    return {"conflicts": {"items": items}, "steps": {"coordination": {"status": "completed"}}}


def owners_for(issues: list[str], default: tuple[str, ...] = ("finance_agent",)) -> list[str]:
    text = " ".join(issues).lower()
    owners: list[str] = []
    for keywords, steps in REPLAN_OWNERS:
        if any(word in text for word in keywords):
            owners += [step for step in steps if step not in owners]
    return owners or list(default)


async def receptionist(state: EventPlanningState) -> dict[str, Any]:
    """Receives the brief, checks it is complete, and hands it to the Event Manager. Rule-based: no model call."""
    event = _event(state)
    emit({"type": "step_started", "stepId": "receptionist", "attempt": 1, "at": _now()}, dedupe="started:receptionist")
    did = [
        f"Received the brief for {event.name}: {event.attendees} guests in {event.location} on {event.event_date:%d %b %Y}, budget {inr(event.budget)}",
        "Handed it to the Event Manager to split the work",
    ]
    verification = {"check": "Brief complete", "passed": True, "reason": "All required fields are present"}
    emit({"type": "step_completed", "stepId": "receptionist", "summary": _summary(did, verification, {}), "at": _now()}, dedupe="completed:receptionist")
    return {"steps": {"receptionist": {"status": "completed"}}}


def _sent_back(state: EventPlanningState) -> bool:
    return (state.get("approval") or {}).get("decision") == "revise"


def route_intake(state: EventPlanningState) -> str:
    """A plan the owner sent back goes to the manager's re-split, then straight to the affected specialists."""
    return "replan" if _sent_back(state) else "logistics_agent"


def _human_assignments(state: EventPlanningState) -> tuple[list[str], dict[str, list[str]]]:
    """The owner's send-back as specialist -> notes.

    The API reads the owner's message (the LLM in LLM mode) and stores its assignments in `feedback_notes`. A send-back
    without words re-runs the specialists the review still has open notes or issues for."""
    feedback = [text for text in (state.get("feedback") or []) if text]
    notes = {step: list(items) for step, items in (state.get("feedback_notes") or {}).items() if step in ROLES}
    if feedback and not notes:  # a run paused before assignments existed: keyword owners, never all six
        notes = {step: list(feedback) for step in with_dependents(rule_owners(" ".join(feedback)))}
    if not feedback and not notes:
        review = state.get("review") or {}
        notes = {step: list(items) for step, items in (review.get("notes") or {}).items() if step in ROLES}
        for issue in review.get("issues") or []:
            for step in owners_for([issue], default=()):
                notes.setdefault(step, []).append(issue)
    return feedback, notes


async def _resplit(state: EventPlanningState) -> dict[str, Any]:
    """The owner sent the plan back: the Event Manager assigns the feedback to the specialists who own each part."""
    human_rounds = state.get("human_rounds", 0)
    feedback, notes = _human_assignments(state)
    names = [ROLES[step_id].agent for step_id in notes]
    emit({"type": "step_started", "stepId": "manager_intake", "attempt": human_rounds + 1, "at": _now()}, dedupe=f"started:manager_intake:round{human_rounds}")
    did = [f"Your feedback: {' '.join(feedback)}"] if feedback else ["Address the review's open notes"]
    did += [f"Re-split to: {', '.join(names)}" if names else "No specialist needs to change"]
    did += [f"{ROLES[step_id].agent}: {'; '.join(items)}" for step_id, items in notes.items() if feedback and items != feedback][:4]
    verification = {"check": "Feedback assigned to the specialists", "passed": bool(names), "reason": f"{len(names)} specialist(s) assigned" if names else "Nothing to assign"}
    emit({"type": "step_completed", "stepId": "manager_intake", "summary": _summary(did, verification, {}), "at": _now()}, dedupe=f"completed:manager_intake:round{human_rounds}")
    return {"manager_round": 0, "feedback_notes": notes, "steps": {"manager_intake": {"status": "completed", "round": human_rounds}}}


async def manager_intake(state: EventPlanningState) -> dict[str, Any]:
    """The Event Manager reads the brief first and sets what each specialist must cover; after an owner's send-back it re-splits the feedback."""
    if _sent_back(state):
        return await _resplit(state)
    rev = state.get("revision_count", 0)
    event = _event(state)
    emit({"type": "step_started", "stepId": "manager_intake", "attempt": 1, "at": _now()}, dedupe=f"started:manager_intake:{rev}")
    did = [
        f"Brief: {event.attendees} guests in {event.location} on {event.event_date:%d %b %Y}, budget {inr(event.budget)}",
        "Delegated to Logistics first, because the venue sets the budget and travel; then Budget, Schedule, Requirements, Marketing and Risk run in parallel",
        "After they report: coordination, plan review, a judge, then your approval",
    ]
    verification = {"check": "Brief read and work delegated", "passed": True, "reason": "Six specialists assigned"}
    emit({"type": "step_completed", "stepId": "manager_intake", "summary": _summary(did, verification, {}), "at": _now()}, dedupe=f"completed:manager_intake:{rev}")
    return {"steps": {"manager_intake": {"status": "completed"}}}


async def replan(state: EventPlanningState) -> dict[str, Any]:
    """Re-run only the specialists the review points to, giving each the review's feedback."""
    rev = state.get("revision_count", 0) + 1
    human = [text for text in (state.get("feedback") or []) if text]  # what the owner asked to change
    if human or state.get("feedback_notes"):  # the owner's round: only the specialists the Event Manager assigned
        notes = {step: list(items) for step, items in (state.get("feedback_notes") or {}).items() if step in ROLES}
        issues = human
        source = "your feedback"
    else:  # the review's round: rule issues and the judge's notes, each to its owner
        issues = list(state["review"]["issues"])
        notes = {step: list(items) for step, items in (state["review"].get("notes") or {}).items() if step in ROLES}
        for step_id in owners_for(issues) if issues else []:
            notes.setdefault(step_id, [])
        source = "the review's feedback"
    emit({"type": "step_started", "stepId": "replan", "attempt": rev, "at": _now()}, dedupe=f"started:replan:{rev}")
    event = _event(state)
    current: dict[str, Any] = {}
    rerun: list[str] = []
    kept: list[str] = []
    usage: dict[str, int] = {}
    for step_id in [step for step in SPECIALISTS if step in notes]:  # Logistics first: the others build on its handoff
        role = ROLES[step_id]
        view = {**state, **current}  # later owners build on the reports already re-run
        base = dict((state.get("step_overrides") or {}).get(step_id) or {})
        overrides = {**base, "feedback": issues + [note for note in notes[step_id] if note not in issues]}
        if step_id != "logistics_agent":
            overrides["handoff"] = _handoff(view)
        emit({"type": "step_started", "stepId": step_id, "attempt": rev, "at": _now()}, dedupe=f"started:{step_id}:{rev}:replan")
        emit({"type": "step_verifying", "stepId": step_id, "check": CHECK_TEXT.get(step_id, "Checking the result…")}, dedupe=f"verifying:{step_id}:{rev}:replan")
        try:
            result = _normalise_result(await run_specialist(step_id, event, overrides, rev))
            verification = verify(step_id, result, event, overrides).model_dump()  # the same check as the first pass
        except Exception as error:
            result, verification = None, {"passed": False, "reason": str(error) or error.__class__.__name__}
        if not verification["passed"]:  # the previous report stands, and the owner is told at approval
            kept.append(role.agent)
            emit({"type": "step_skipped", "stepId": step_id, "reason": f"Kept the previous version: the re-run didn't pass its check ({verification['reason']})"}, dedupe=f"skipped:{step_id}:{rev}:replan")
            continue
        emit({"type": "step_completed", "stepId": step_id, "summary": _summary(result["report"]["recommendations"], verification, result.get("usage", {}), result["tool_results"]), "at": _now()}, dedupe=f"completed:{step_id}:{rev}:replan")
        current[role.state_key] = {**result["report"], "agent": role.agent, "user_adjustments": base, "tool_results": [{k: v for k, v in r.items() if k != "_args"} for r in result["tool_results"]], "mode": result.get("mode"), "replanned": rev}
        rerun.append(role.agent)
        for key, value in (result.get("usage") or {}).items():
            usage[key] = usage.get(key, 0) + int(value or 0)
    did = [f"Re-ran {', '.join(rerun)} with {source}" if rerun else "Nothing could be re-run, so the current reports stand"]
    if kept:
        did.append(f"Kept the previous version for {', '.join(kept)}: the re-run didn't pass its check")
    # This step only says what was re-run; whether the notes are fixed is the next review's call, not this tick's.
    verification = {"check": "Re-ran the flagged specialists", "passed": bool(rerun), "reason": f"Re-ran {len(rerun)} of {len(notes)} assigned; the next review checks the result" if notes else "Nothing was assigned"}
    did += [f"Sent to {ROLES[step_id].agent}: {'; '.join(items)}" for step_id, items in notes.items() if items][:4]
    emit({"type": "step_completed", "stepId": "replan", "summary": _summary(did, verification, usage), "at": _now()}, dedupe=f"completed:replan:{rev}")
    return {**current, "revision_count": rev, "manager_round": state.get("manager_round", 0) + 1, "usage": usage, "feedback": [], "feedback_notes": {}, "stale_parts": kept, "steps": {"replan": {"status": "completed", "passes": rev}}}


_OUTSIDE_CHECK = re.compile(r"availab|confirm|quot|book|hold|contract|catalog", re.IGNORECASE)


def _needs_outside_check(note: str) -> bool:
    """True for feedback that is about something the planner can't verify (availability, prices, bookings)."""
    return bool(_OUTSIDE_CHECK.search(note))


async def plan_judge(state: EventPlanningState) -> dict[str, Any]:
    """An LLM reads the whole plan. If it isn't good enough, its notes go to the specialists who own each problem."""
    rev = state.get("revision_count", 0)
    emit({"type": "step_verifying", "stepId": "review_plan", "check": "Judging the whole plan as the Event Manager"}, dedupe=f"judging:{rev}")
    earlier = state.get("judged_notes") or {}  # what the judge asked for last time: it re-checks those instead of moving the goalposts
    result = await judge_attempt(state["event"], state["final_plan"], _context(state), earlier)
    if not result.get("ok") and llm.llm_enabled():  # one retry: a judge that returns nothing once often answers the second time
        result = await judge_attempt(state["event"], state["final_plan"], _context(state), earlier)
    if not result.get("ok"):  # rule checks still stand; the judge is an extra check, not a gate that can break the run
        emit({"type": "notice", "message": f"The plan judge was unavailable ({result.get('error')}), so only the rule checks were applied."}, dedupe=f"notice:judge:{rev}")
        note = "An LLM review did not run, so this plan was checked with the rule-based checks only. Review it carefully before approving." if llm.llm_enabled() else "This plan was built with rule-based checks only. Review it carefully before approving."
        _replan_not_needed(rev)
        return {"caveats": [note], "open_issues": []}
    usage = result.get("usage", {})
    judgement = result["judgement"]
    flagged = [] if judgement["satisfied"] else judgement["feedback"]
    # Availability, quotes and bookings can't be checked from inside the planner: they become caveats, not blocking feedback.
    caveats = [item["note"] for item in flagged if _needs_outside_check(item["note"])]
    feedback = [item for item in flagged if not _needs_outside_check(item["note"])]
    out_of_scope: list[str] = []
    if state.get("operation") == "plan-edit" and state.get("base_plan"):
        # An edit changes only what the owner asked for. Notes about parts it didn't touch are shown to the owner, not acted on.
        edited = {ROLES[step].state_key for step in SPECIALISTS if step not in (state.get("reuse") or {})}
        out_of_scope = [f"Review note ({ROLES[item['owner']].agent}, not changed by your edit): {item['note']}" for item in feedback if ROLES[item["owner"]].state_key not in edited]
        feedback = [item for item in feedback if ROLES[item["owner"]].state_key in edited]
    if not feedback:
        verification = {"check": "Judged as a whole", "passed": True, "reason": "Good enough for the owner to review" + (f"; {len(out_of_scope)} note(s) for you to consider" if out_of_scope else "")}
        emit({"type": "step_completed", "stepId": "review_plan", "summary": _summary(["The Event Manager judged the whole plan: good enough for you to review"], verification, usage), "at": _now()}, dedupe=f"judged:{rev}")
        _replan_not_needed(rev)
        return {"usage": usage, "caveats": caveats, "open_issues": out_of_scope, "judged_notes": {}}
    notes: dict[str, list[str]] = {}
    for item in feedback:
        notes.setdefault(item["owner"], []).append(item["note"])
    reasons = " ".join(item["note"] for item in feedback)
    verification = {"check": "Judged as a whole", "passed": False, "reason": reasons}
    open_issues = list(out_of_scope)
    if state.get("manager_round", 0) >= settings.max_judge_replans:  # out of automatic re-plans: the owner sees what is still open
        emit({"type": "notice", "message": f"Still open after the automatic re-plan: {reasons}"}, dedupe=f"notice:judge:{rev}")
        open_issues += [f"Review note ({ROLES[item['owner']].agent}): {item['note']}" for item in feedback]
        did = [f"The Event Manager still has {len(feedback)} note(s); they're listed on the approval card for you to decide"]
    else:
        did = [f"The Event Manager sent {len(feedback)} change(s) back to the specialists"]
    emit({"type": "step_completed", "stepId": "review_plan", "summary": _summary(did, verification, usage), "at": _now()}, dedupe=f"judged:{rev}")
    return {"review": {"approved": False, "issues": [], "notes": notes}, "usage": usage, "caveats": caveats, "open_issues": open_issues, "judged_notes": notes}


def _replan_not_needed(rev: int) -> None:
    if rev == 0:  # said only once the judge is satisfied too, so the timeline never flips from "not needed" to running
        emit({"type": "step_skipped", "stepId": "replan", "reason": "Not needed — the review passed"}, dedupe="skipped:replan")


def changes_left(event_id: str | None) -> int:
    return max(settings.max_approval_attempts - (ui_state.attempts(event_id) if event_id else 0), 0)


def _approval_summary(event_id: str | None, open_issues: list[str]) -> str:
    """Says how many change requests are left, so the owner knows what happens if they use them all."""
    limit = settings.max_approval_attempts
    left = changes_left(event_id)
    note = f"Change requests left at approval: {left} of {limit}."
    if left == 0:
        note += " All of them are used: you can still approve this plan, or restart the plan with your inputs."
    ready = f"The plan is ready, with {len(open_issues)} review note(s) still open (listed below)." if open_issues else "The plan is ready."
    return f"{ready} Review it below, then approve it or send it back with what to change. {note}"


async def approval(state: EventPlanningState) -> dict[str, Any]:
    """The owner's last check: nothing is final until they approve, or send the plan back to the Event Manager."""
    rev = state.get("revision_count", 0)
    # No owner to ask, or the owner made this change to an already approved plan in the chat. An edit of a plan the owner
    # never approved (sent back from the approval card or a failed step) pauses here like any new plan.
    if not state.get("interactive", True) or (state.get("operation") == "plan-edit" and not state.get("owner_review")):
        emit({"type": "step_completed", "stepId": "approval", "summary": _summary(["Applied your change from the plan chat"] if state.get("interactive", True) else ["Approved automatically: no owner was asked"], {"check": "Owner approval", "passed": True, "reason": "You asked for this change in the chat" if state.get("interactive", True) else "Not asked for this run"}, {}), "at": _now()}, dedupe=f"completed:approval:{rev}")
        return {"approval": {"decision": "approve"}, "review": {**state["review"], "approved": True}, "steps": {"approval": {"status": "completed"}}}
    emit({"type": "step_started", "stepId": "approval", "attempt": 1, "at": _now()}, dedupe=f"started:approval:{rev}")
    error = "Waiting for your approval"
    event_id = str(state["event"].get("id") or "") or None
    open_issues = list(state.get("open_issues") or []) + [f"{agent} couldn't apply the latest feedback, so its previous version is in the plan." for agent in state.get("stale_parts") or []]
    left = changes_left(event_id)
    proposal = RecoveryProposal(
        summary=_approval_summary(event_id, open_issues),
        cause="",  # an approval to review, not an error
        preview={**state["final_plan"], "approved_budget": state["event"]["budget"], "caveats": state.get("caveats", []), "open_issues": open_issues},
        options=[
            RecoveryOption(id="approve", label="Approve the plan", description="Mark the plan final and write the recommendations.", action="retry_with", patch={"decision": "approve"}),
            *([RecoveryOption(id="revise", label="Fix the open notes" if open_issues else "Send back with changes", description="The Event Manager sends the open notes to the specialists who own them, then checks and asks you again." if open_issues else "Say what to change below; the Event Manager assigns it to the right specialists, then checks and asks you again.", action="retry_with", patch={"decision": "revise"})] if left else []),
        ],
        customPrompt="What should change? For example: move lunch to 1:30 PM, lower the decor spend" if left else "",
        source="rules",
        changesLeft=left,
    )
    emit({"type": "step_failed", "stepId": "approval", "error": error, "attempt": 1, "retryable": True, "recovery": proposal.model_dump()}, dedupe=f"failed:approval:{rev}")
    choice = interrupt({"step_id": "approval", "attempt": 1, "error": error, "proposal": proposal.model_dump(), "overrides": {}})
    emit({"type": "run_resumed", "stepId": "approval", "action": choice.get("action"), "label": choice.get("label", "")}, dedupe=f"resumed:approval:{rev}")
    if (choice.get("patch") or {}).get("decision") == "revise":
        request = (choice.get("feedback") or "").strip()
        did = [f"Changes asked by you: {request}"] if request else ["Asked to fix the review's open notes"]
        verification = {"check": "Owner approval", "passed": False, "reason": "Sent back for changes"}
        emit({"type": "step_completed", "stepId": "approval", "summary": _summary(did, verification, {}), "at": _now()}, dedupe=f"completed:approval:{rev}")
        notes = {step: list(items) for step, items in (choice.get("assignments") or {}).items() if step in ROLES}
        return {"approval": {"decision": "revise", "feedback": request}, "feedback": [request] if request else [], "feedback_notes": notes, "human_rounds": state.get("human_rounds", 0) + 1, "steps": {"approval": {"status": "completed", "sent_back": True}}}
    verification = {"check": "Owner approval", "passed": True, "reason": "Approved by you"}
    emit({"type": "step_completed", "stepId": "approval", "summary": _summary(["Approved by you"], verification, {}), "at": _now()}, dedupe=f"completed:approval:{rev}")
    return {"approval": {"decision": "approve"}, "review": {**state["review"], "approved": True}, "steps": {"approval": {"status": "completed"}}}


def route_after_review(state: EventPlanningState) -> str:
    """Rule checks passed: the LLM judge reads the whole plan next. Otherwise re-plan, or move on at the limit."""
    if state["review"]["approved"]:
        return "plan_judge"
    return _route_revision(state)


def route_after_judge(state: EventPlanningState) -> str:
    return _route_revision(state)


def _route_revision(state: EventPlanningState) -> str:
    limit = settings.max_judge_replans if (state["review"].get("notes") and not state["review"].get("issues")) else settings.max_replans
    if not state["review"]["approved"] and state.get("manager_round", 0) < limit:
        return "replan"
    return "approval"  # out of automatic replans: the owner decides with the issues in front of them


def route_after_approval(state: EventPlanningState) -> str:
    return "manager_intake" if state["approval"]["decision"] == "revise" else "recommendations"


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
            f"{wrap_user(f'Brief: {event}', 'brief')}\n{wrap_user(f'Plan: {plan}', 'brief')}\n{DATA_RULE}\n"
            f"Skipped specialists: {[c.get('agent') for c in context.values() if c.get('skipped')]}"
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
    others = [step_id for step_id in SPECIALISTS if step_id != "logistics_agent"]
    for step_id in SPECIALISTS:
        workflow.add_node(step_id, specialist_node(step_id))
    workflow.add_node("coordination", coordination)
    workflow.add_node("event_manager", event_manager)
    workflow.add_node("review_plan", review_plan)
    workflow.add_node("replan", replan)
    workflow.add_node("plan_judge", plan_judge)
    workflow.add_node("recommendations", recommendations)
    workflow.add_node("approval", approval)
    workflow.add_node("manager_intake", manager_intake)
    workflow.add_node("receptionist", receptionist)
    workflow.add_edge(START, "receptionist")  # the receptionist takes the brief in
    workflow.add_edge("receptionist", "manager_intake")  # ...and hands it to the Event Manager, who splits the work
    # First pass: the venue comes first and everyone else builds on it. After the owner sends the plan back,
    # the manager's re-split goes straight to the affected specialists via replan.
    workflow.add_conditional_edges("manager_intake", route_intake, {"logistics_agent": "logistics_agent", "replan": "replan"})
    for step_id in others:
        workflow.add_edge("logistics_agent", step_id)
    workflow.add_edge(others, "coordination")  # waits for all five (completed or skipped)
    workflow.add_edge("coordination", "event_manager")
    workflow.add_edge("event_manager", "review_plan")
    workflow.add_conditional_edges("review_plan", route_after_review, {"plan_judge": "plan_judge", "replan": "replan", "approval": "approval"})
    workflow.add_conditional_edges("plan_judge", route_after_judge, {"replan": "replan", "approval": "approval"})
    workflow.add_edge("replan", "coordination")
    workflow.add_conditional_edges("approval", route_after_approval, {"manager_intake": "manager_intake", "recommendations": "recommendations"})
    workflow.add_edge("recommendations", END)
    return workflow
