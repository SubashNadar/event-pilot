"""Change the plan by chatting: "move dinner to 9 PM", "add a shehnai at 7 PM",
"make it 300 guests", "put ₹2 lakh into catering", "switch to Vashi Grand Ballroom".

1. `interpret` turns the message into a `PlanEdit` (LLM structured output, with
   a rule-based parser as fallback and for runs without Azure OpenAI).
2. `prepare` checks every requested change against the plan and the catalogue
   (the venue exists and holds the guests, the agenda item exists, the budget
   line exists, the date is in the future). Anything it can't apply becomes one
   clarifying question instead of a guess.
3. The result says which specialists must run again, with what inputs. Every
   other specialist's report is kept, so a small change costs one or two steps,
   not a whole new plan.
4. `plan_diff` describes what actually changed once the run finishes.
"""

import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.agents.brief_extract import _money, _parse_date, _parse_location
from app.agents.fmt import inr
from app.agents.llm import get_chat_model, limited, llm_enabled
from app.core.guard import DATA_RULE, wrap_user
from app.models.event import EventBrief
from app.search.benchmarks import resolve_city
from app.search.venues import catalog

AGENT_NAMES = {
    "logistics_agent": "Logistics", "finance_agent": "Budget & Finance", "schedule_agent": "Schedule",
    "requirements_agent": "Requirements", "marketing_agent": "Marketing", "risk_operations_agent": "Risk & Operations",
}
STATE_KEYS = {
    "logistics_agent": "logistics", "finance_agent": "finance", "schedule_agent": "schedule",
    "requirements_agent": "requirements", "marketing_agent": "marketing", "risk_operations_agent": "risks",
}
DEFAULT_VENUE_SHARE = 30
MAX_VENUE_SHARE = 60


class AgendaAdd(BaseModel):
    time: str = Field(description="12-hour time, e.g. '7:00 PM'")
    activity: str


class AgendaMove(BaseModel):
    activity: str = Field(description="Words from the existing agenda item, e.g. 'dinner'")
    time: str = Field(description="New 12-hour time, e.g. '9:00 PM'")


class BudgetSet(BaseModel):
    category: str = Field(description="An existing budget line, e.g. 'Catering'")
    amount_inr: int = Field(ge=0)


class PlanEdit(BaseModel):
    """What the event owner wants changed. Leave everything empty for a question."""

    name: str | None = Field(default=None, min_length=2, max_length=120, description="New event name")
    attendees: int | None = Field(default=None, ge=1, le=100_000)
    budget_inr: int | None = Field(default=None, ge=1_000, description="New TOTAL budget in rupees")
    event_date: str | None = Field(default=None, description="New date, YYYY-MM-DD")
    location: str | None = Field(default=None, description="New city or 'Area, City'")
    venue: str | None = Field(default=None, description="A specific venue the owner wants")
    venue_type: str | None = Field(default=None, description="e.g. banquet hall, lawn, hotel ballroom, rooftop")
    agenda_add: list[AgendaAdd] = Field(default_factory=list)
    agenda_move: list[AgendaMove] = Field(default_factory=list)
    agenda_remove: list[str] = Field(default_factory=list, description="Words from agenda items to remove")
    budget_set: list[BudgetSet] = Field(default_factory=list, description="Set one budget line to an amount")
    requirements_add: list[str] = Field(default_factory=list, description="Extra needs, e.g. 'wheelchair access'")
    answer: str | None = Field(default=None, description="If the message is only a question, a short answer from the plan")
    question: str | None = Field(default=None, description="If the request is unclear, one short clarifying question")

    def is_change(self) -> bool:
        return any([self.name, self.attendees, self.budget_inr, self.event_date, self.location, self.venue, self.venue_type,
                    self.agenda_add, self.agenda_move, self.agenda_remove, self.budget_set, self.requirements_add])


@dataclass
class PreparedEdit:
    brief: dict[str, Any] = field(default_factory=dict)          # fields to change on the event brief
    overrides: dict[str, dict[str, Any]] = field(default_factory=dict)  # step id -> inputs for that step
    changes: list[str] = field(default_factory=list)              # plain-English list of what was asked
    notes: list[str] = field(default_factory=list)                # side effects worth saying
    question: str | None = None                                   # set when something can't be applied

    @property
    def steps(self) -> list[str]:
        return [step for step in AGENT_NAMES if step in self.overrides]


# ------------------------------------------------------------------ helpers

def normalise_time(text: str | None) -> str | None:
    if not text:
        return None
    lowered = text.lower().strip()
    if "noon" in lowered:
        return "12:00 PM"
    if "midnight" in lowered:
        return "12:00 AM"
    match = re.search(r"\b(\d{1,2})(?:[:.](\d{2}))?\s*(a\.?m\.?|p\.?m\.?)", lowered)
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2) or 0)
    if not 1 <= hour <= 12 or minute > 59:
        return None
    return f"{hour}:{minute:02d} {'AM' if match.group(3).startswith('a') else 'PM'}"


def time_key(label: str) -> int:
    try:
        parsed = datetime.strptime(label.strip(), "%I:%M %p")
        return parsed.hour * 60 + parsed.minute
    except ValueError:
        return 24 * 60


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", text.lower()) if len(w) > 2 and w not in {"the", "and", "for", "with", "our", "this", "that"}}


def best_match(query: str, candidates: list[str], min_share: float = 0.0) -> str | None:
    """The candidate sharing the most words with the query; None when nothing, a tie,
    or fewer than `min_share` of the query's words match."""
    wanted = _words(query)
    scored = sorted(((len(wanted & _words(c)), c) for c in candidates), key=lambda pair: -pair[0])
    if not scored or scored[0][0] == 0 or (len(scored) > 1 and scored[1][0] == scored[0][0]):
        return None
    if wanted and scored[0][0] / len(wanted) < min_share:
        return None
    return scored[0][1]


def find_venue(name: str, city: str | None) -> dict[str, Any] | None:
    venues = [v for v in catalog() if city is None or v["city"] == city]
    lowered = name.lower()
    exact = [v for v in venues if v["name"].lower() in lowered or lowered in v["name"].lower()]
    if len(exact) == 1:
        return exact[0]
    picked = best_match(name, [v["name"] for v in venues], min_share=0.6)
    return next((v for v in venues if v["name"] == picked), None)


def _amount(text: str) -> int | None:
    match = re.search(r"(?:₹|rs\.?|inr)?\s*([\d,]+(?:\.\d+)?)\s*(lakhs?|lacs?|l|crores?|cr|k)?\b", text.lower())
    return _money(match.group(1), match.group(2)) if match else None


# ------------------------------------------------------------------ interpreting

MONEY = r"(?:₹|rs\.?|inr)?\s*[\d,]+(?:\.\d+)?\s*(?:lakhs?|lacs?|l|crores?|cr|k)?"
TIME = r"\d{1,2}(?:[:.]\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)|noon|midnight"


_NOT_A_PLACE = {"the", "a", "an", "my", "our", "it", "this", "that", "same", "another", "different", "one", "here", "there", "location", "city", "area", "venue", "evening", "morning", "night", "afternoon", "date", "time", "budget", "guests", "dinner", "lunch", "breakfast"}
_MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december")


def _named_city(text: str) -> str | None:
    """A city the owner names after 'to', 'into', 'in' or 'at', even when the catalogue doesn't cover it.
    Logistics then reports that no venue data exists for it, instead of the planner asking again."""
    for match in re.finditer(r"\b(?:to|into|in|at)\s+([A-Za-z]+(?:\s[A-Za-z]+)?)", text, re.IGNORECASE):
        words = match.group(1).split()
        if words[0].lower() in _NOT_A_PLACE or words[0][:3].lower() in {m[:3] for m in _MONTHS}:
            continue
        return " ".join(w.capitalize() for w in words)
    return None


def rule_parse(message: str, today: date | None = None) -> PlanEdit:
    today = today or date.today()
    text = " " + message.strip() + " "
    edit = PlanEdit()

    if match := re.search(r"\b(?:change|rename|update|set)\s+(?:the\s+)?(?:event\s+)?name\s+(?:to|as)\s+[\"']?(?P<name>[^\"'\n.!?]+)[\"']?", message, re.I):
        name = " ".join(match.group("name").split()).strip(" '\"")
        if len(name) >= 2:
            edit.name = name[:120]

    def cut(match: re.Match) -> None:
        nonlocal text
        text = text[: match.start()] + " " + text[match.end():]

    for match in list(re.finditer(rf"\b(?:move|shift|push|pull|change|reschedule)\s+(?:the\s+)?(?P<what>[a-z][a-z \-']{{1,40}}?)\s+(?:to|at)\s+(?P<time>{TIME})", text, re.I))[::-1]:
        edit.agenda_move.insert(0, AgendaMove(activity=match.group("what").strip(), time=normalise_time(match.group("time")) or match.group("time")))
        cut(match)
    for match in list(re.finditer(rf"\b(?:add|include|schedule|have)\s+(?:an?\s+|the\s+|some\s+)?(?P<what>[a-z][a-z \-'&]{{1,60}}?)\s+(?:at|from|around)\s+(?P<time>{TIME})", text, re.I))[::-1]:
        edit.agenda_add.insert(0, AgendaAdd(activity=match.group("what").strip().capitalize(), time=normalise_time(match.group("time")) or match.group("time")))
        cut(match)
    for match in list(re.finditer(r"\b(?:remove|drop|cancel|skip|delete)\s+(?:the\s+)?(?P<what>[a-z][a-z \-']{2,40})", text, re.I))[::-1]:
        edit.agenda_remove.insert(0, match.group("what").strip())
        cut(match)
    for match in list(re.finditer(rf"\b(?:put|set|make|give|increase|raise|reduce|lower|cut|allocate)\s+(?:the\s+)?(?P<cat>[a-z][a-z &]{{2,30}}?)\s+(?:budget\s+|line\s+)?(?:to|at)\s+(?P<amount>{MONEY})", text, re.I)) + list(re.finditer(rf"\b(?:put|allocate|spend|give)\s+(?P<amount>{MONEY})\s+(?:into|on|for|to)\s+(?:the\s+)?(?P<cat>[a-z][a-z &]{{2,30}})", text, re.I)):
        category = match.group("cat").strip()
        amount = _amount(match.group("amount"))
        if amount and category.lower() not in {"budget", "the budget", "total", "total budget", "guests", "it"}:
            edit.budget_set.append(BudgetSet(category=category, amount_inr=amount))
            cut(match)
    if match := re.search(r"\b(?i:switch|swap|change|move)\s+(?i:the\s+venue\s+)?(?i:to)\s+(?P<venue>[A-Z][\w&' ]{3,60}?)(?i:\s+instead)?[.!?]?\s*$|\b(?i:use|book|go with|pick|choose)\s+(?P<venue2>[A-Z][\w&' ]{3,60}?)(?i:\s+instead)?[.!?]?\s*$", text):
        name = (match.group("venue") or match.group("venue2")).strip()
        if find_venue(name, None):
            edit.venue = name
            cut(match)
    for match in re.finditer(r"\b(?:we need|we'll need|need|please add|add|include)\s+(?:an?\s+|some\s+)?(?P<req>[a-z][a-z \-']{3,60}?)(?:[.!?,]|$)", text, re.I):
        req = match.group("req").strip()
        if req and not re.search(r"\b(guests?|people|budget|lakh|venue)\b", req):
            edit.requirements_add.append(req[0].upper() + req[1:])
    lowered = text.lower()
    if guests := re.search(r"\b(\d{1,6})\s*(?:guests|people|pax|attendees|persons)\b", lowered):
        edit.attendees = int(guests.group(1))
    if re.search(r"\bbudget\b", lowered) and (amount := _amount(re.sub(r".*?\bbudget\b", "", lowered, count=1))):
        edit.budget_inr = amount
    if re.search(r"\b(?:move|shift|postpone|prepone|change|reschedule)\b.*\b(?:date|day|to|on)\b", lowered) and (parsed := _parse_date(text, today)):
        edit.event_date = parsed
    if not edit.venue and re.search(r"\b(?:move|shift|relocate|change)\b.*\b(?:city|location|area|to|in)\b", message.lower()):
        place = _parse_location(message) or (_named_city(message) if re.search(r"\b(?:location|city|area)\b|\b(?:move|shift|relocate)\s+(?:the\s+)?(?:event|it|wedding|party|function|plan)\b", lowered) else None)
        if place:
            edit.location = place
    if not edit.is_change():
        if message.strip().endswith("?") or re.match(r"\s*(what|how|which|when|why|is|are|can|do|does|will)\b", message, re.I):
            edit.answer = ""  # filled from the plan by `answer_from_plan`
        else:
            edit.question = "What should I change? For example: “move dinner to 9 PM”, “add a shehnai at 7 PM”, “make it 300 guests”, or “put ₹2 lakh into catering”."
    return edit


def plan_context(event: EventBrief, plan: dict[str, Any], reports: dict[str, Any]) -> str:
    """A compact view of the plan for the interpreter prompt (no raw tool output)."""
    logistics = (reports.get("logistics") or {}).get("decisions") or {}
    lines = [
        f"Event: {event.name}; {event.event_date}; {event.location}; {event.attendees} guests; budget {inr(event.budget)}",
        f"Venue: {plan.get('venue')} (alternatives: {', '.join(logistics.get('alternatives') or []) or 'none'})",
        "Agenda: " + "; ".join(f"{item['time']} {item['activity']}" for item in plan.get("agenda", [])),
        "Budget lines: " + "; ".join(f"{line['category']} {inr(line['amount'])}" for line in plan.get("budget_lines", [])),
        f"Forecast: {inr(plan.get('budget_forecast', 0))}",
        "Risks: " + "; ".join(f"{risk['level']} {risk['title']}" for risk in plan.get("risks", [])),
    ]
    return "\n".join(lines)


async def interpret(message: str, event: EventBrief, plan: dict[str, Any], reports: dict[str, Any], config: dict | None = None) -> tuple[PlanEdit, str]:
    """Returns (edit, mode)."""
    rule_edit = rule_parse(message)
    # A name change is unambiguous and must not depend on an LLM deciding to
    # populate an optional structured field.
    if rule_edit.name or not llm_enabled():
        return rule_edit, "rules"
    try:
        model = get_chat_model().with_structured_output(PlanEdit, method="function_calling")
        async with limited():
            edit = await model.ainvoke([
                SystemMessage(
                    "You turn an event owner's chat message into changes to their event plan. "
                    "Only fill the fields the message asks to change; leave the rest empty. Times are 12-hour like '9:00 PM'. "
                    "Amounts are whole rupees (2 lakh = 200000). If it is only a question, put a short answer from the plan in `answer`. "
                    "If it is unclear, ask one short question in `question`. Today is " + date.today().isoformat() + ". " + DATA_RULE
                ),
                HumanMessage("Current plan:\n" + wrap_user(plan_context(event, plan, reports), "brief") + "\n\nMessage:\n" + wrap_user(message)),
            ], config=config)
        return edit, "llm"
    except Exception:
        return rule_parse(message), "rules"


def answer_from_plan(message: str, event: EventBrief, plan: dict[str, Any]) -> str:
    lowered = message.lower()
    if re.search(r"budget|cost|spend|money|lakh|₹|catering|decor", lowered):
        lines = ", ".join(f"{line['category']} {inr(line['amount'])}" for line in plan.get("budget_lines", []))
        return f"The forecast is {inr(plan.get('budget_forecast', 0))} of {inr(event.budget)}: {lines}."
    if re.search(r"venue|where|hall|lawn|place", lowered):
        return f"The venue is {plan.get('venue')}. {plan.get('venue_detail', '')}".strip()
    if re.search(r"agenda|schedule|time|when|start|dinner|programme", lowered):
        return "The agenda: " + "; ".join(f"{item['time']} {item['activity']}" for item in plan.get("agenda", [])) + "."
    if re.search(r"risk|weather|rain|problem", lowered):
        return "The open risks: " + "; ".join(f"{risk['title']} ({risk['level'].lower()})" for risk in plan.get("risks", [])) + "."
    return f"{event.name} is on {event.event_date:%d %b %Y} in {event.location} for {event.attendees} guests, at {plan.get('venue')}, with a forecast of {inr(plan.get('budget_forecast', 0))}. Tell me what to change."


# ------------------------------------------------------------------ preparing

def _add(prepared: PreparedEdit, step: str, **values: Any) -> None:
    prepared.overrides.setdefault(step, {"edit_mode": True}).update(values)


def prepare(edit: PlanEdit, event: EventBrief, plan: dict[str, Any], reports: dict[str, Any], today: date | None = None) -> PreparedEdit:
    today = today or date.today()
    prepared = PreparedEdit()
    decisions = {key: ((reports.get(key) or {}).get("decisions") or {}) for key in STATE_KEYS.values()}
    attendees = edit.attendees or event.attendees
    budget = edit.budget_inr or event.budget
    location = event.location

    # Brief-level changes
    if edit.name and edit.name.strip() != event.name:
        name = " ".join(edit.name.split())[:120]
        prepared.brief["name"] = name
        prepared.changes.append(f"event name to {name}")
        # Re-run a small, relevant step so the manager re-synthesizes a plan
        # that carries the updated event identity without changing unrelated work.
        _add(prepared, "requirements_agent")
    if edit.attendees and edit.attendees != event.attendees:
        prepared.brief["attendees"] = edit.attendees
        prepared.changes.append(f"guests from {event.attendees} to {edit.attendees}")
        for step in AGENT_NAMES:
            _add(prepared, step)
    if edit.budget_inr and edit.budget_inr != event.budget:
        if edit.budget_inr > 1_000_000_000:
            prepared.question = "That budget looks too large. What total should I plan for?"
            return prepared
        prepared.brief["budget"] = edit.budget_inr
        prepared.changes.append(f"budget from {inr(event.budget)} to {inr(edit.budget_inr)}")
        _add(prepared, "finance_agent")  # the venue is only searched again if it no longer fits the new budget
    if edit.event_date:
        try:
            new_date = date.fromisoformat(edit.event_date[:10])
        except ValueError:
            prepared.question = "Which date should I move it to? For example “13 February 2027”."
            return prepared
        if new_date <= today:
            prepared.question = f"{new_date:%d %b %Y} has already passed. Which future date should I use?"
            return prepared
        if new_date != event.event_date:
            prepared.brief["event_date"] = new_date
            prepared.changes.append(f"date to {new_date:%a %d %b %Y}")
            for step in ("schedule_agent", "marketing_agent", "risk_operations_agent"):
                _add(prepared, step)
    moved = bool(edit.location and edit.location.strip().lower() != event.location.lower())
    if moved:
        location = edit.location.strip()
        prepared.brief["location"] = location
        prepared.changes.append(f"location to {location}")
        for step in ("logistics_agent", "finance_agent", "schedule_agent", "risk_operations_agent"):
            _add(prepared, step)

    # Venue
    city = resolve_city(location)
    if edit.venue:
        venue = find_venue(edit.venue, city)
        if venue is None:
            fitting = [decisions["logistics"].get("venue"), *(decisions["logistics"].get("alternatives") or [])]
            names = ", ".join(n for n in fitting if n) or "the shortlisted venues"
            prepared.question = f"I couldn't find “{edit.venue}” in the venue list for {city or location}. Did you mean one of these: {names}?"
            return prepared
        if venue["capacity"] < attendees:
            prepared.question = f"{venue['name']} holds {venue['capacity']}, but the plan is for {attendees} guests. Should I lower the guest count, or pick another venue?"
            return prepared
        share_needed = math.ceil(venue["rental_inr"] / budget * 100) if budget else 100
        values: dict[str, Any] = {"venue": venue["name"]}
        if share_needed > DEFAULT_VENUE_SHARE:
            if share_needed > MAX_VENUE_SHARE:
                prepared.question = f"{venue['name']} costs {inr(venue['rental_inr'])}, which is {share_needed}% of the {inr(budget)} budget. Should I raise the budget instead?"
                return prepared
            values["venue_share_pct"] = share_needed
            prepared.notes.append(f"{venue['name']} costs {inr(venue['rental_inr'])}, so the venue share of the budget goes from {DEFAULT_VENUE_SHARE}% to {share_needed}%")
        _add(prepared, "logistics_agent", **values)
        if decisions["logistics"].get("rental_inr") != venue["rental_inr"]:
            _add(prepared, "finance_agent")  # rent changed, so the budget lines are redone
        prepared.changes.append(f"venue to {venue['name']}")
    elif "logistics_agent" in prepared.overrides and decisions["logistics"].get("venue") and not moved:
        # Keep the chosen venue when it still fits; a new city means Logistics searches there again.
        _add(prepared, "logistics_agent", venue=decisions["logistics"]["venue"], venue_soft=True)
    if edit.venue_type:
        _add(prepared, "logistics_agent", venue_type=edit.venue_type)
        prepared.changes.append(f"venue type to {edit.venue_type}")

    # Agenda
    # The plan the owner sees is the base, so nothing they didn't ask about moves.
    base_agenda = [{"time": item["time"], "activity": item["activity"]} for item in plan.get("agenda", [])] or decisions["schedule"].get("agenda") or []
    activities = [item["activity"] for item in base_agenda]
    moves, removes, adds = [], [], []
    for move in edit.agenda_move:
        target = best_match(move.activity, activities)
        new_time = normalise_time(move.time)
        if not target or not new_time:
            prepared.question = f"Which agenda item should move, and to what time? The agenda has: {', '.join(activities)}."
            return prepared
        moves.append({"activity": target, "time": new_time})
        prepared.changes.append(f"{target} to {new_time}")
    for item in edit.agenda_remove:
        target = best_match(item, activities)
        if target:
            removes.append(target)
            prepared.changes.append(f"remove {target}")
        elif not (edit.agenda_add or edit.agenda_move or edit.budget_set or edit.requirements_add):
            prepared.question = f"I couldn't find “{item}” in the agenda. It has: {', '.join(activities)}."
            return prepared
    for add in edit.agenda_add:
        new_time = normalise_time(add.time)
        if not new_time:
            prepared.question = f"What time should “{add.activity}” be? For example 7:00 PM."
            return prepared
        adds.append({"time": new_time, "activity": add.activity.strip()[:80]})
        prepared.changes.append(f"add {add.activity.strip()} at {new_time}")
    if moves or removes or adds:
        _add(prepared, "schedule_agent", agenda_move=moves, agenda_remove=removes, agenda_add=adds)
    if "schedule_agent" in prepared.overrides:
        _add(prepared, "schedule_agent", base_agenda=base_agenda)

    # Budget lines
    base_lines = [{"category": line["category"], "amount": line["amount"]} for line in plan.get("budget_lines", [])] or decisions["finance"].get("budget_lines") or []
    sets = []
    for item in edit.budget_set:
        from app.integrations.vendors import normalise_category

        categories = [line["category"] for line in base_lines]
        target = best_match(item.category, categories) or next((c for c in categories if normalise_category(c) and normalise_category(c) == normalise_category(item.category)), None)
        if not target:
            prepared.question = f"Which budget line? The plan has: {', '.join(categories)}."
            return prepared
        sets.append({"category": target, "amount": int(item.amount_inr)})
        prepared.changes.append(f"{target} to {inr(item.amount_inr)}")
    if sets:
        _add(prepared, "finance_agent", budget_set=sets)
    if "finance_agent" in prepared.overrides and not ({"budget", "attendees", "location"} & set(prepared.brief)) and "venue" not in (prepared.overrides.get("logistics_agent") or {}):
        _add(prepared, "finance_agent", base_lines=base_lines)

    # Requirements
    if edit.requirements_add:
        _add(prepared, "requirements_agent")
        prepared.changes.extend(f"add {req}" for req in edit.requirements_add)
    if "requirements_agent" in prepared.overrides:
        kept = list(decisions["requirements"].get("added") or [])
        _add(prepared, "requirements_agent", requirements_add=[*kept, *(r.strip()[:80] for r in edit.requirements_add if r.strip())])
    return prepared


# ------------------------------------------------------------------ describing the result

def reports_matching_plan(reports: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    """Previous specialist reports with their key decisions set to what the plan shows.

    The Event Manager may have adjusted a specialist's proposal; kept steps must
    reproduce the plan the owner is looking at.
    """
    patched = {key: dict(value or {}) for key, value in reports.items()}
    def decisions(key: str) -> dict[str, Any]:
        report = patched.setdefault(key, {})
        report["decisions"] = dict(report.get("decisions") or {})
        return report["decisions"]
    if plan.get("agenda") and not (patched.get("schedule") or {}).get("skipped"):
        decisions("schedule")["agenda"] = [{"time": i["time"], "activity": i["activity"], "owner": i.get("owner")} for i in plan["agenda"]]
    if plan.get("budget_lines") and not (patched.get("finance") or {}).get("skipped"):
        decisions("finance")["budget_lines"] = [{"category": l["category"], "amount": l["amount"]} for l in plan["budget_lines"]]
    if plan.get("venue") and not (patched.get("logistics") or {}).get("skipped"):
        d = decisions("logistics")
        d["venue"], d["venue_detail"] = plan["venue"], plan.get("venue_detail", d.get("venue_detail", ""))
    if plan.get("risks") and not (patched.get("risks") or {}).get("skipped"):
        decisions("risks")["risks"] = [{"level": r["level"], "title": r["title"], "action": r.get("detail", "")} for r in plan["risks"]]
    for key, report in patched.items():
        report.setdefault("recommendations", ["Kept from the current plan"])
    return patched


def plan_diff(old: dict[str, Any], new: dict[str, Any], old_event: EventBrief, new_event: EventBrief) -> list[str]:
    lines: list[str] = []
    for label, a, b in (("Guests", old_event.attendees, new_event.attendees), ("Date", old_event.event_date, new_event.event_date), ("Location", old_event.location, new_event.location)):
        if a != b:
            lines.append(f"{label}: {a} → {b}")
    if old_event.budget != new_event.budget:
        lines.append(f"Budget: {inr(old_event.budget)} → {inr(new_event.budget)}")
    if old.get("venue") != new.get("venue"):
        lines.append(f"Venue: {old.get('venue')} → {new.get('venue')}")
    old_agenda = {item["activity"]: item["time"] for item in old.get("agenda", [])}
    new_agenda = {item["activity"]: item["time"] for item in new.get("agenda", [])}
    for activity, time_label in new_agenda.items():
        if activity not in old_agenda:
            lines.append(f"Added to the agenda: {activity} at {time_label}")
        elif old_agenda[activity] != time_label:
            lines.append(f"{activity}: {old_agenda[activity]} → {time_label}")
    for activity in old_agenda:
        if activity not in new_agenda:
            lines.append(f"Removed from the agenda: {activity}")
    old_lines = {line["category"]: line["amount"] for line in old.get("budget_lines", [])}
    for line in new.get("budget_lines", []):
        before = old_lines.get(line["category"])
        if before is None:
            lines.append(f"New budget line: {line['category']} {inr(line['amount'])}")
        elif before != line["amount"]:
            lines.append(f"{line['category']}: {inr(before)} → {inr(line['amount'])}")
    if old.get("budget_forecast") != new.get("budget_forecast"):
        lines.append(f"Forecast: {inr(old.get('budget_forecast', 0))} → {inr(new.get('budget_forecast', 0))} of {inr(new_event.budget)}")
    old_risks = {risk["title"] for risk in old.get("risks", [])}
    for risk in new.get("risks", []):
        if risk["title"] not in old_risks:
            lines.append(f"New risk: {risk['title']} ({risk['level'].lower()})")
    return lines
