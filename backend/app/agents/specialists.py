"""The five specialist agents (plus Requirements), each a bounded tool-using LLM.

An agent reads the brief and any user-approved adjustments, decides the inputs
for its MCP tool, calls it (at most twice), and returns a `SpecialistReport`.
Inputs that come from the brief or from the user's recovery choice are enforced
in code, so the model can't drift from them. When Azure OpenAI is not configured,
the same tools run with rule-based inputs and a rule-based report.

After its main tool, each agent may run one or two context tools in code
(weather, holidays, travel, vendors, guest message draft). They add facts to the
report without another LLM round, and a context tool that fails never fails the
step: the report says what couldn't be checked.
"""

import json
from dataclasses import dataclass
from datetime import date
from typing import Any, Awaitable, Callable

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from app.agents.voice import PLANNER_VOICE
from app.agents.llm import get_chat_model, limited, llm_enabled, usage_of
from app.mcp.client import ToolCallError, call_planning_tool
from app.models.event import EventBrief
from app.models.run import SpecialistReport
from app.services.azure_planner import event_type_guidance
from app.services.planning import default_agenda, default_budget_lines


from app.agents.fmt import inr as money


def brief_text(event: EventBrief) -> str:
    event_type, _ = event_type_guidance(event)
    return (
        f"Event: {event.name}\nType: {event_type}\nDate: {event.event_date}\nLocation: {event.location}\n"
        f"Attendees: {event.attendees}\nBudget (INR): {event.budget}\nObjective: {event.objective}"
    )


def adjustments_text(overrides: dict[str, Any]) -> str:
    """What a specialist must take into account beyond the brief: the Logistics handoff, review feedback and owner adjustments."""
    parts = []
    if overrides.get("handoff"):
        parts.append("Handoff from Logistics (build on it; don't search for another venue): " + json.dumps(overrides["handoff"], default=str))
    if overrides.get("feedback"):
        parts.append("The review found these problems; fix them in this attempt: " + json.dumps(overrides["feedback"], default=str))
    owner = {key: value for key, value in overrides.items() if key not in ("handoff", "feedback")}
    if owner:
        parts.append("User-approved adjustments for this attempt (these override the brief): " + json.dumps(owner, default=str))
    return ("\n" + "\n".join(parts)) if parts else ""


@dataclass
class Role:
    step_id: str
    state_key: str
    agent: str
    tool: str
    description: str
    parameters: dict[str, Any]
    prompt: str
    enforce: Callable[[dict[str, Any], EventBrief, dict[str, Any]], dict[str, Any]]
    rule_report: Callable[[EventBrief, dict[str, Any], dict[str, Any]], SpecialistReport]
    context: Callable[..., Awaitable[SpecialistReport]] | None = None

    def tool_schema(self) -> dict[str, Any]:
        return {"type": "function", "function": {"name": self.tool, "description": self.description, "parameters": self.parameters}}


# ---------------------------------------------------------------- Logistics

def _logistics_args(args: dict, event: EventBrief, overrides: dict) -> dict:
    share = int(overrides.get("venue_share_pct") or 30)
    return {
        "location": str(overrides.get("location") or event.location),  # the brief wins over the model
        "attendees": int(overrides.get("attendees") or event.attendees),
        # venue_search caps rent at 30% of the total it receives; scale the total so the cap equals `share`.
        "total_budget_inr": round(event.budget * share / 30),
        # The model may choose a venue type and describe preferences; a user's choice wins.
        "venue_type": str(overrides.get("venue_type") or args.get("venue_type") or ""),
        "preferences": str(args.get("preferences") or event.objective)[:200],
    }


def pick_venue(result: dict, overrides: dict) -> dict | None:
    """The venue to recommend: the owner's choice when it fits, else the top result.

    A chosen venue may fit without being in the top results, so the catalogue is
    checked against the same limits the search used.
    """
    recs = result.get("recommendations", [])
    wanted = str(overrides.get("venue") or "").lower()
    if wanted:
        match = next((r for r in recs if r["name"].lower() == wanted), None)
        if match:
            return match
        from app.search.venues import catalog

        args = result.get("_args") or {}
        venue = next((v for v in catalog() if v["name"].lower() == wanted), None)
        if venue and venue["capacity"] >= int(args.get("attendees", 0)) and venue["rental_inr"] <= int(result.get("venue_budget_limit_inr", 0)):
            return {key: venue[key] for key in ("name", "location", "capacity", "rental_inr", "features")}
        if not overrides.get("venue_soft"):
            return None
    return recs[0] if recs else None


def _logistics_report(event: EventBrief, overrides: dict, result: dict) -> SpecialistReport:
    recs = result.get("recommendations", [])
    location = overrides.get("location") or event.location
    guests = overrides.get("attendees") or event.attendees
    best = pick_venue(result, overrides)
    if best:
        mode = (result.get("search") or {}).get("mode", "bm25")
        return SpecialistReport(
            recommendations=[
                f"Shortlisted {len(recs)} venue(s) in {location} that fit {guests} guests ({'keyword + semantic' if mode == 'hybrid' else 'keyword'} search)",
                f"Recommend {best['name']}: capacity {best['capacity']}, rent {money(best['rental_inr'])}",
                "Confirm availability and quotations before booking",
            ],
            decisions={"venue": best["name"], "venue_detail": f"{best['location']} · capacity {best['capacity']} · " + ", ".join(best["features"]), "rental_inr": best["rental_inr"], "alternatives": [r["name"] for r in recs if r["name"] != best["name"]]},
            confidence=85,
        )
    if overrides.get("allow_unverified"):
        kind = overrides.get("venue_type") or "venue"
        return SpecialistReport(
            recommendations=[f"No catalog venue matched, so I'm proposing an unverified {kind} in {location}", "Get two quotes and confirm capacity before booking"],
            decisions={"venue": f"{kind.capitalize()} in {location} (to be confirmed)", "venue_detail": f"{location} · {guests} guests · not in the EventPilot catalog", "unverified": True},
            assumptions=["Venue availability and price are not verified"],
            confidence=55,
        )
    return SpecialistReport(recommendations=[f"No catalog venue fits {guests} guests in {location} within {money(result.get('venue_budget_limit_inr', 0))}"], decisions={}, confidence=20)


LOGISTICS = Role(
    step_id="logistics_agent", state_key="logistics", agent="Logistics", tool="venue_search",
    description="Find suitable venues from the EventPilot catalog for a location, guest count and total event budget.",
    parameters={"type": "object", "properties": {"location": {"type": "string"}, "attendees": {"type": "integer"}, "total_budget_inr": {"type": "integer"}, "venue_type": {"type": "string", "description": "e.g. banquet hall, lawn, hotel ballroom, heritage, resort, beach resort, rooftop, workshop studio, convention centre, auditorium, private dining, farmhouse"}, "preferences": {"type": "string", "description": "What the venue should offer, in a few words, e.g. 'sea view, parking, in-house catering'"}}, "required": ["location", "attendees", "total_budget_inr"]},
    prompt="You are the Logistics agent in an event-planning team. Call venue_search with a venue_type and preferences that suit the event type and objective, then recommend one venue with a short reason. Never invent venues that the tool did not return. If nothing fits, say why using the tool's near_misses.",
    enforce=_logistics_args, rule_report=_logistics_report,
)


# ---------------------------------------------------------------- Finance

def apply_budget_sets(base: list[dict], sets: list[dict]) -> list[dict]:
    """Set lines to the owner's amounts. The difference comes out of (or goes into) Contingency first."""
    lines = [{"category": str(line["category"]), "amount": int(line["amount"])} for line in base]
    for change in sets or []:
        line = next((l for l in lines if l["category"] == change["category"]), None)
        if line is None:
            continue
        delta = int(change["amount"]) - line["amount"]
        line["amount"] = int(change["amount"])
        reserve = next((l for l in lines if "contingency" in l["category"].lower() and l is not line), None)
        if reserve is not None:
            taken = min(delta, reserve["amount"]) if delta > 0 else delta
            reserve["amount"] -= taken
    return lines


def _finance_args(args: dict, event: EventBrief, overrides: dict) -> dict:
    if overrides.get("base_lines") or overrides.get("budget_set"):
        base = overrides.get("base_lines") or default_budget_lines(event, overrides.get("contingency_pct"))
        return {"budget_lines": apply_budget_sets(base, overrides.get("budget_set") or []), "total_budget_inr": int(overrides.get("budget_ceiling") or event.budget)}
    lines = []
    for line in args.get("budget_lines") or []:
        try:
            lines.append({"category": str(line.get("category", "Unlabelled")), "amount": int(float(line.get("amount", 0)))})
        except (TypeError, ValueError, AttributeError):
            continue
    if not lines:
        lines = default_budget_lines(event, overrides.get("contingency_pct"))
    return {"budget_lines": lines, "total_budget_inr": int(overrides.get("budget_ceiling") or event.budget)}


def fit_lines_to_budget(lines: list[dict[str, Any]], budget: int) -> tuple[list[dict[str, Any]], str | None]:
    """Keep the venue line as quoted; trim the other lines pro rata when the total is over budget."""
    total = sum(int(line["amount"]) for line in lines)
    if total <= budget:
        return lines, None
    is_venue = [("venue" in line["category"].lower()) for line in lines]
    venue = sum(int(line["amount"]) for line, flag in zip(lines, is_venue) if flag)
    others = total - venue
    room = budget - venue
    if room <= 0 or others <= 0:
        return lines, f"The venue alone uses most of the {money(budget)} budget, so the other lines can't be trimmed to fit"
    factor = room / others
    trimmed = [dict(line) if flag else {**line, "amount": int(int(line["amount"]) * factor)} for line, flag in zip(lines, is_venue)]
    return trimmed, f"Trimmed the other lines by {round((1 - factor) * 100)}% so the total fits {money(budget)}"


def _finance_report(event: EventBrief, overrides: dict, result: dict) -> SpecialistReport:
    lines = [dict(line) for line in result.get("_lines", [])]
    handoff = overrides.get("handoff") or {}
    notes = []
    if handoff.get("rental_inr"):  # Logistics' quote replaces the estimate for the venue line
        for line in lines:
            if "venue" in line["category"].lower():
                line["amount"] = int(handoff["rental_inr"])
        notes.append(f"Venue line uses {handoff.get('venue')}'s quoted rent of {money(int(handoff['rental_inr']))}")
    lines, trimmed = fit_lines_to_budget(lines, int(event.budget))
    if trimmed:
        notes.append(trimmed)
    total = sum(int(line["amount"]) for line in lines)
    contingency = next((line for line in lines if "contingency" in line["category"].lower()), None)
    recs = [f"Allocated {money(total)} across {len(lines)} categories against {money(event.budget)}", *notes]
    if contingency:
        recs.append(f"Kept {money(contingency['amount'])} as contingency")
    recs.append(result.get("recommendation", ""))
    return SpecialistReport(recommendations=[r for r in recs if r], decisions={"budget_lines": lines}, confidence=80)


FINANCE = Role(
    step_id="finance_agent", state_key="finance", agent="Budget & Finance", tool="budget_validation",
    description="Validate proposed budget lines (category and amount in INR) against the approved total budget.",
    parameters={"type": "object", "properties": {"budget_lines": {"type": "array", "items": {"type": "object", "properties": {"category": {"type": "string"}, "amount": {"type": "integer"}}, "required": ["category", "amount"]}}, "total_budget_inr": {"type": "integer"}}, "required": ["budget_lines", "total_budget_inr"]},
    prompt="You are the Budget & Finance agent. Draft exactly six budget lines suited to this event type (always include a 'Contingency' line of 5-10%), keep the total at or below the budget, and validate them with budget_validation. Use whole rupees.",
    enforce=_finance_args, rule_report=_finance_report,
)


# ---------------------------------------------------------------- Schedule

def apply_agenda_edits(base: list[dict], overrides: dict) -> list[dict]:
    from app.agents.plan_edit import time_key

    agenda = [{"time": str(item["time"]), "activity": str(item["activity"])} for item in base]
    removed = set(overrides.get("agenda_remove") or [])
    agenda = [item for item in agenda if item["activity"] not in removed]
    for move in overrides.get("agenda_move") or []:
        for item in agenda:
            if item["activity"] == move["activity"]:
                item["time"] = move["time"]
    agenda += [{"time": add["time"], "activity": add["activity"]} for add in overrides.get("agenda_add") or []]
    return sorted(agenda, key=lambda item: time_key(item["time"]))


def _schedule_args(args: dict, event: EventBrief, overrides: dict) -> dict:
    if overrides.get("base_agenda") is not None:
        return {"agenda": apply_agenda_edits(overrides["base_agenda"], overrides)}
    agenda = [{"time": str(item.get("time", "")), "activity": str(item.get("activity", ""))} for item in (args.get("agenda") or []) if isinstance(item, dict)]
    return {"agenda": agenda or default_agenda(event)}


def _schedule_report(event: EventBrief, overrides: dict, result: dict) -> SpecialistReport:
    agenda = result.get("_agenda", [])
    first, last = (agenda[0], agenda[-1]) if agenda else ({"time": "?"}, {"time": "?"})
    return SpecialistReport(
        recommendations=[f"Built a {len(agenda)}-item agenda from {first['time']} to {last['time']}", "Checked every slot for overlaps and 12-hour format"],
        decisions={"agenda": agenda}, confidence=80,
    )


SCHEDULE = Role(
    step_id="schedule_agent", state_key="schedule", agent="Schedule", tool="schedule_conflict_check",
    description="Check an event agenda (12-hour 'h:mm AM/PM' times) for invalid or duplicate times.",
    parameters={"type": "object", "properties": {"agenda": {"type": "array", "items": {"type": "object", "properties": {"time": {"type": "string", "description": "e.g. 9:30 AM"}, "activity": {"type": "string"}}, "required": ["time", "activity"]}}}, "required": ["agenda"]},
    prompt="You are the Schedule agent. Draft a five-item event-day agenda that fits the objective, with realistic transitions and 12-hour times like '9:30 AM', then check it with schedule_conflict_check and fix any conflict.",
    enforce=_schedule_args, rule_report=_schedule_report,
)


# ---------------------------------------------------------------- Requirements, Marketing, Risk

def _event_type(event: EventBrief, overrides: dict) -> str:
    return str(overrides.get("event_type") or event_type_guidance(event)[0])


def _requirements_args(args: dict, event: EventBrief, overrides: dict) -> dict:
    return {"event_type": _event_type(event, overrides), "attendees": int(event.attendees)}


def _requirements_report(event: EventBrief, overrides: dict, result: dict) -> SpecialistReport:
    added = [r for r in overrides.get("requirements_add") or [] if r]
    reqs = list(result.get("requirements", [])) + [r for r in added if r not in result.get("requirements", [])]
    recs = [f"Listed {len(reqs)} operational requirements for a {result.get('event_type')}", "Critical: " + ", ".join(reqs[:3])]
    if added:
        recs.append("You added: " + ", ".join(added))
    return SpecialistReport(recommendations=recs, decisions={"requirements": reqs, "added": added}, confidence=80)


def _marketing_args(args: dict, event: EventBrief, overrides: dict) -> dict:
    return {"event_type": _event_type(event, overrides), "attendees": int(event.attendees), "event_date": str(event.event_date)}


def _marketing_report(event: EventBrief, overrides: dict, result: dict) -> SpecialistReport:
    channels = overrides.get("channels") or result.get("recommended_channels", [])
    return SpecialistReport(recommendations=[f"Planned guest communication over {len(channels)} channels: " + ", ".join(channels[:3]), "Every send waits for your approval"], decisions={"channels": channels, "checkpoints": result.get("checkpoints", [])}, confidence=80)


def _risk_args(args: dict, event: EventBrief, overrides: dict) -> dict:
    return {"event_type": _event_type(event, overrides), "attendees": int(event.attendees), "location": event.location}


def _risk_report(event: EventBrief, overrides: dict, result: dict) -> SpecialistReport:
    risks = result.get("risks", [])
    high = [r for r in risks if r["level"] == "High"]
    return SpecialistReport(recommendations=[f"Identified {len(risks)} risks, {len(high)} high", *(f"{r['title']}: {r['action']}" for r in high[:2])], decisions={"risks": risks}, confidence=80)


def _simple(params: dict) -> dict:
    return {"type": "object", "properties": params, "required": list(params)}


REQUIREMENTS = Role("requirements_agent", "requirements", "Requirements", "event_requirements", "Return operational planning requirements for an event type and size.", _simple({"event_type": {"type": "string"}, "attendees": {"type": "integer"}}), "You are the Requirements agent. Use event_requirements to list what the event needs operationally, then name the three most critical items and who should own them.", _requirements_args, _requirements_report)
MARKETING = Role("marketing_agent", "marketing", "Marketing", "marketing_readiness", "Create an approval-gated guest communication plan for an event.", _simple({"event_type": {"type": "string"}, "attendees": {"type": "integer"}, "event_date": {"type": "string"}}), "You are the Marketing & Promotion agent. Use marketing_readiness, then recommend channels and send dates that suit the audience. Nothing is sent without the owner's approval.", _marketing_args, _marketing_report)
RISK = Role("risk_operations_agent", "risks", "Risk & Operations", "operational_risk_assessment", "Create an initial operational risk register for an event.", _simple({"event_type": {"type": "string"}, "attendees": {"type": "integer"}, "location": {"type": "string"}}), "You are the Risk & Operations agent. Use operational_risk_assessment, then add any risk specific to this brief (season, city, guest profile) with a practical fallback for every high risk.", _risk_args, _risk_report)

# ---------------------------------------------------------------- context tools

ToolCall = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


async def _try(call: ToolCall, report: SpecialistReport, name: str, args: dict[str, Any], what: str) -> dict[str, Any] | None:
    try:
        return await call(name, args)
    except ToolCallError as error:
        report.assumptions.append(f"Couldn't check {what}: {error}")
        return None


def _city(event: EventBrief, overrides: dict) -> str:
    return str(overrides.get("location") or event.location)


async def _logistics_context(event: EventBrief, overrides: dict, result: dict, report: SpecialistReport, call: ToolCall) -> SpecialistReport:
    recs = result.get("recommendations") or []
    if not recs:
        return report
    access = await _try(call, report, "travel_access", {"location": recs[0]["location"]}, "travel time to the airport")
    if access and access.get("found"):
        hubs = access.get("hubs", [])
        airport = next((h for h in hubs if h["kind"] == "airport"), None)
        station = next((h for h in hubs if h["kind"] == "railway station"), None)
        if airport:
            line = f"{recs[0]['name']} is about {airport['km']:g} km ({airport['minutes']} min by road) from {airport['name']}"
            if station:
                line += f" and {station['minutes']} min from {station['name']}"
            if airport["method"].startswith("estimate"):
                line += " (estimated; map service offline)"
            report.recommendations.append(line)
        report.decisions["access"] = {"hubs": hubs[:3], "method": hubs[0]["method"] if hubs else "", "sources": access.get("sources", [])}
    return report


VENDOR_LINES = ("catering", "decor", "photography")


async def _finance_context(event: EventBrief, overrides: dict, result: dict, report: SpecialistReport, call: ToolCall) -> SpecialistReport:
    from app.integrations.vendors import normalise_category

    shortlist: dict[str, list[dict[str, Any]]] = {}
    lines = result.get("_lines") or []
    picked = [(line, normalise_category(line["category"])) for line in lines]
    picked = [(line, kind) for line, kind in picked if kind in VENDOR_LINES][:2]
    for line, kind in picked:
        found = await _try(call, report, "vendor_search", {"city": _city(event, overrides), "category": kind, "budget_inr": int(line["amount"]), "guests": int(overrides.get("attendees") or event.attendees), "event_type": _event_type(event, overrides), "preferences": event.objective[:120]}, f"{kind} vendors")
        if not found:
            continue
        matches = found.get("matches") or []
        if matches:
            best = matches[0]
            price = f"{money(best['per_plate_inr'])} a plate" if best.get("per_plate_inr") else money(best["estimated_inr"])
            report.recommendations.append(f"{line['category']}: {best['name']} fits the {money(line['amount'])} line at {price} (sample vendor list)")
            shortlist[kind] = [{"name": m["name"], "estimated_inr": m["estimated_inr"], **({"per_plate_inr": m["per_plate_inr"]} if m.get("per_plate_inr") else {})} for m in matches]
        elif found.get("reason") == "over_budget" and found.get("cheapest"):
            report.recommendations.append(f"{line['category']}: no listed vendor fits {money(line['amount'])}; the cheapest is {found['cheapest']['name']} at {money(found['cheapest']['estimated_inr'])}")
    if shortlist:
        report.decisions["vendor_shortlist"] = shortlist
    return report


async def _schedule_context(event: EventBrief, overrides: dict, result: dict, report: SpecialistReport, call: ToolCall) -> SpecialistReport:
    check = await _try(call, report, "holiday_check", {"event_date": str(event.event_date), "location": _city(event, overrides), "window_days": 3}, "holidays and festivals")
    if check:
        report.recommendations.append(check["summary"] + ("" if check["risk"] == "Low" else f". {check['advice']}"))
        if check.get("long_weekend"):
            report.recommendations.append("It's a long weekend: outstation guests may travel, and hotels fill early")
        report.decisions["date_check"] = {key: check.get(key) for key in ("risk", "summary", "on_the_day", "nearby", "long_weekend", "season_notes")}
    return report


async def _marketing_context(event: EventBrief, overrides: dict, result: dict, report: SpecialistReport, call: ToolCall) -> SpecialistReport:
    draft = await _try(call, report, "guest_message_draft", {"kind": "invite", "event_name": event.name, "event_date": str(event.event_date), "location": _city(event, overrides), "event_type": _event_type(event, overrides)}, "the invite draft")
    if draft:
        report.recommendations.append(f"Drafted the {draft['channel']} invite ({draft['characters']} characters); it waits for your approval")
        report.decisions["invite_draft"] = {"text": draft["text"], "checks": draft["checks"], "status": draft["status"]}
    return report


async def _risk_context(event: EventBrief, overrides: dict, result: dict, report: SpecialistReport, call: ToolCall) -> SpecialistReport:
    outlook = await _try(call, report, "weather_outlook", {"location": _city(event, overrides), "event_date": str(event.event_date)}, "the weather")
    if outlook:
        report.recommendations.append(f"Weather ({outlook['basis']}): {outlook['summary']}")
        report.decisions["weather"] = {key: outlook.get(key) for key in ("risk", "basis", "summary", "metrics", "advice", "sources")}
        if outlook["risk"] in ("High", "Medium"):
            risks = list(report.decisions.get("risks") or result.get("risks") or [])
            risks.append({"level": outlook["risk"], "title": "Weather on the day", "action": outlook["advice"]})
            report.decisions["risks"] = risks
    return report


LOGISTICS.context = _logistics_context
FINANCE.context = _finance_context
SCHEDULE.context = _schedule_context
MARKETING.context = _marketing_context
RISK.context = _risk_context

ROLES: dict[str, Role] = {role.step_id: role for role in (LOGISTICS, FINANCE, SCHEDULE, REQUIREMENTS, MARKETING, RISK)}


def _annotate(role: Role, args: dict, result: dict) -> dict:
    """Keep the inputs next to the result: checks and rule reports need both."""
    annotated = dict(result)
    if role.tool == "budget_validation":
        annotated["_lines"] = args["budget_lines"]
    if role.tool == "schedule_conflict_check":
        annotated["_agenda"] = args["agenda"]
    annotated["_args"] = args
    return annotated


def _keep_tool_shaped_decisions(report: SpecialistReport, fallback: SpecialistReport) -> SpecialistReport:
    """Keep model prose, but use verified tool data when a decision has the wrong shape.

    Structured output guarantees that ``decisions`` is a mapping, not the shape
    of every nested value. A model can still return e.g. a list of budget-line
    labels instead of budget-line objects. Those values must not reach the
    coordinator or Event Manager as if they were verified data.
    """
    decisions = report.decisions if isinstance(report.decisions, dict) else {}
    for key, verified in fallback.decisions.items():
        candidate = decisions.get(key)
        needs_fallback = candidate is None
        if isinstance(verified, dict):
            needs_fallback = needs_fallback or not isinstance(candidate, dict)
        elif isinstance(verified, list):
            needs_fallback = needs_fallback or not isinstance(candidate, list)
            if verified and isinstance(verified[0], dict):
                needs_fallback = needs_fallback or not all(isinstance(item, dict) for item in candidate)
        elif verified is not None:
            needs_fallback = needs_fallback or not isinstance(candidate, type(verified))
        if needs_fallback:
            decisions[key] = verified
    report.decisions = decisions
    return report


async def run_specialist(step_id: str, event: EventBrief, overrides: dict[str, Any], attempt: int, config: dict | None = None) -> dict[str, Any]:
    """One attempt of one specialist. Raises on tool or model failure."""
    role = ROLES[step_id]
    tool_results: list[dict[str, Any]] = []
    usage = {"tokens_in": 0, "tokens_out": 0}
    call_index = 0

    async def call(args: dict) -> dict:
        nonlocal call_index
        call_index += 1
        enforced = role.enforce(args, event, overrides)
        result = await call_planning_tool(role.tool, enforced, step_id=step_id, call_id=f"{step_id}-a{attempt}-{call_index}")
        annotated = _annotate(role, enforced, result)
        tool_results.append(annotated)
        return result

    async def context_call(name: str, args: dict) -> dict:
        nonlocal call_index
        call_index += 1
        return await call_planning_tool(name, args, step_id=step_id, call_id=f"{step_id}-a{attempt}-{call_index}")

    async def with_context(report: SpecialistReport) -> SpecialistReport:
        if role.context:
            report = await role.context(event, overrides, tool_results[-1], report, context_call)
            report.recommendations = report.recommendations[:5]  # the report schema allows five
        return report

    # Plan edits apply the owner's change to the current plan in code: no LLM
    # round, so nothing else drifts and the edit costs no tokens.
    if not llm_enabled() or overrides.get("edit_mode"):
        result = await call({})
        report = await with_context(role.rule_report(event, overrides, tool_results[-1]))
        return {"report": report.model_dump(), "tool_results": tool_results, "usage": usage, "mode": "edit" if overrides.get("edit_mode") else "rules"}

    model = get_chat_model()
    messages: list[Any] = [SystemMessage(f"{PLANNER_VOICE}\n\n{role.prompt}"), HumanMessage(brief_text(event) + adjustments_text(overrides))]
    tool_model = model.bind_tools([role.tool_schema()])
    for _ in range(2):  # bounded ReAct loop: at most two tool rounds
        async with limited():
            ai = await tool_model.ainvoke(messages, config=config)
        for key, value in usage_of(ai).items():
            usage[key] += value
        messages.append(ai)
        if not getattr(ai, "tool_calls", None):
            break
        for tool_call in ai.tool_calls:
            result = await call(tool_call.get("args") or {})
            messages.append(ToolMessage(json.dumps(result, default=str), tool_call_id=tool_call["id"]))
    if not tool_results:  # the model answered without checking: run the tool once so the step can be verified
        await call({})
        messages.append(HumanMessage("Tool result: " + json.dumps(tool_results[-1], default=str)))

    structured = model.with_structured_output(SpecialistReport, method="function_calling", include_raw=True)
    async with limited():
        output = await structured.ainvoke(messages + [HumanMessage("Summarise your work for the Event Manager as a SpecialistReport. Recommendations: 2-4 short first-person lines with real numbers. Put the key decisions (venue, budget lines, agenda, channels or risks) in `decisions`.")], config=config)
    for key, value in usage_of(output).items():
        usage[key] += value
    report = output.get("parsed") if isinstance(output, dict) else output
    if report is None:
        report = role.rule_report(event, overrides, tool_results[-1])
    else:
        report = _keep_tool_shaped_decisions(
            report,
            role.rule_report(event, overrides, tool_results[-1]),
        )
    report = await with_context(report)
    return {"report": report.model_dump(), "tool_results": tool_results, "usage": usage, "mode": "llm"}


def default_check_date(event: EventBrief) -> bool:
    return event.event_date > date.today()
