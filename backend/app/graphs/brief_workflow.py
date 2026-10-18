"""LangGraph workflow for one turn of the planning chat (dynamic brief intake).

    intake ─▶ validate ─▶ check ─▶ frame ─▶ END

- intake:   apply a clicked option or quick-fix patch, or extract every field it
            can from the user's free text (LLM structured output + rules).
- validate: normalise each field (event type via BM25, city via aliases, Indian
            budget formats) and reject bad values with a clear reason.
- check:    compare the answers with the planning benchmarks: budget per guest
            for this event type in this city, and lead time before the date.
- frame:    choose the next missing field and word the question around what is
            already known, with options drawn from the benchmarks (budget bands for
            this guest count and city, typical guest counts, dates after the usual
            lead time, objectives for this event type).

The backend is stateless per turn: the client sends the answers so far.
"""

from datetime import date
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents.brief_extract import extract
from app.agents.fmt import inr
from app.models.chat import BRIEF_FIELDS, BriefItem, BriefOption, BriefQuestion, BriefTurnRequest, BriefTurnResponse, BriefWarning
from app.search import benchmarks as bench

LABELS = {"eventType": "Event type", "location": "Location", "attendees": "Guests", "budget": "Budget", "date": "Date", "objective": "Objective", "name": "Event name"}


class BriefState(TypedDict, total=False):
    request: BriefTurnRequest
    answers: dict[str, str]
    incoming: dict[str, str]
    filled: list[str]
    errors: dict[str, str]
    warnings: list[dict[str, Any]]
    mode: str
    next: dict[str, Any] | None


def _today() -> date:
    return date.today()


def _int(value: str | None) -> int | None:
    try:
        return int(float(str(value).replace(",", "").replace("₹", "")))
    except (TypeError, ValueError):
        return None


def _event_type(answers: dict[str, str]) -> dict[str, Any] | None:
    return bench.type_by_label(answers.get("eventType"))


async def intake(state: BriefState) -> dict[str, Any]:
    request = state["request"]
    incoming: dict[str, str] = {}
    mode = "rules"
    if request.patch:
        incoming.update(request.patch)
    if request.field and request.value is not None:
        incoming[request.field] = request.value
    elif request.message and request.message.strip():
        found, mode = await extract(request.message.strip(), request.answers, _today())
        asked = request.ask or _first_missing(request.answers)  # the question that was on screen
        new_info = {k: v for k, v in found.items() if not request.answers.get(k)}
        if asked in {"name", "objective"} and not new_info and len(request.message.strip()) >= 4:
            # "North East Tech Summit" names the event; it isn't a new event type.
            incoming[asked] = request.message.strip()
            found = {}
        incoming.update(found)
        # A plain reply to the question on screen ("200", "Pune", "14 Feb") answers that question.
        if asked == "attendees" and "attendees" not in found and (number := _int(request.message)):
            incoming["attendees"] = str(number)
        elif asked == "budget" and "budget" not in found and (number := _int(request.message)) and number >= 1000:
            incoming["budget"] = str(number)
        elif asked == "location" and not found and 2 <= len(request.message.strip()) <= 60:
            incoming["location"] = request.message.strip()
        elif asked == "eventType" and not found and 3 <= len(request.message.strip()) <= 60:
            incoming["eventType"] = request.message.strip()
    return {"incoming": incoming, "answers": dict(request.answers), "mode": mode}


def _normalise(field: str, value: str, answers: dict[str, str]) -> tuple[str | None, str | None]:
    """Returns (normalised value, error)."""
    value = (value or "").strip()
    if field == "eventType":
        matched = bench.match_event_type(value)
        if matched:
            return matched["label"], None
        return (value[:60].capitalize(), None) if len(value) >= 3 else (None, "Tell me what kind of event it is, e.g. a wedding, workshop or birthday party.")
    if field == "location":
        if len(value) < 2:
            return None, "Which city or area will it be in?"
        city = bench.resolve_city(value)
        if city and city.lower() not in value.lower():
            return f"{value.title()}, {city}", None
        return (value if not city else value.replace(city.lower(), city)), None
    if field == "attendees":
        number = _int(value)
        return (str(number), None) if number and 1 <= number <= 100_000 else (None, "Please give the guest count as a number, e.g. 150.")
    if field == "budget":
        number = _int(value)
        return (str(number), None) if number and number >= 1_000 else (None, "Please give the total budget in rupees, e.g. ₹5 lakh or 500000.")
    if field == "date":
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            return None, "Please pick a date, e.g. 14 Feb 2027."
        return (parsed.isoformat(), None) if parsed > _today() else (None, "That date has passed. Please choose a future date.")
    if field == "objective":
        return (value, None) if len(value) >= 12 else (None, "Add a little more about what the event should achieve.")
    if field == "name":
        return (value[:120], None) if len(value) >= 4 else (None, "Use a slightly longer name, e.g. 'Meera and Karthik Reception'.")
    return value, None


def validate(state: BriefState) -> dict[str, Any]:
    answers = dict(state["answers"])
    filled: list[str] = []
    errors: dict[str, str] = {}
    # event type first: other fields' wording depends on it
    for field in sorted(state["incoming"], key=lambda f: BRIEF_FIELDS.index(f) if f in BRIEF_FIELDS else 99):
        if field not in BRIEF_FIELDS:
            continue
        normalised, error = _normalise(field, state["incoming"][field], answers)
        if error:
            errors[field] = error
            continue
        if answers.get(field) != normalised:
            filled.append(field)
        answers[field] = normalised
    return {"answers": answers, "filled": filled, "errors": errors}


def check(state: BriefState) -> dict[str, Any]:
    answers, dismissed = state["answers"], set(state["request"].dismissed)
    event_type = _event_type(answers)
    city = bench.resolve_city(answers.get("location", ""))
    warnings = []
    budget = bench.budget_check(event_type, city, _int(answers.get("attendees")), _int(answers.get("budget")))
    if budget:
        warnings.append(budget)
    if answers.get("date"):
        lead = bench.lead_time_check(event_type, date.fromisoformat(answers["date"]), _today())
        if lead:
            warnings.append(lead)
    if answers.get("location") and not city:
        warnings.append({"id": "city_not_in_catalog", "message": f"The sample venue catalogue doesn't cover {answers['location']} yet, so Logistics will suggest unverified venues there.", "options": [{"label": f"Use {c} instead", "patch": {"location": c}} for c in bench.known_cities()[:2]]})
    return {"warnings": [w for w in warnings if w["id"] not in dismissed]}


def _first_missing(answers: dict[str, str]) -> str | None:
    return next((field for field in BRIEF_FIELDS if not answers.get(field)), None)


def _name_options(answers: dict[str, str], event_type: dict[str, Any] | None) -> list[dict[str, str]]:
    label = event_type["label"] if event_type else (answers.get("eventType") or "Event")
    city = bench.resolve_city(answers.get("location", "")) or (answers.get("location") or "").split(",")[0]
    when = date.fromisoformat(answers["date"]).strftime("%b %Y") if answers.get("date") else ""
    names = [f"{city} {label}".strip(), f"{label} {when}".strip(), f"{when} {city} {label}".strip()]
    return [{"value": n, "label": n, "hint": ""} for n in dict.fromkeys(names) if len(n) >= 4]


def frame(state: BriefState) -> dict[str, Any]:
    answers = state["answers"]
    request = state["request"]
    # Re-ask an edited field until this turn changes it, then move on.
    field = request.ask if request.ask and request.ask not in state.get("filled", []) else _first_missing(answers)
    if field is None:
        return {"next": None}
    event_type = _event_type(answers)
    kind = (event_type["label"] if event_type else answers.get("eventType") or "event").lower()
    city = bench.resolve_city(answers.get("location", ""))
    place = f" in {answers['location']}" if answers.get("location") else ""
    guests = _int(answers.get("attendees"))
    if field == "eventType":
        prompt, options, placeholder = "What kind of event are you planning?", [{"value": t["label"], "label": t["label"], "hint": ""} for t in bench.event_types()[:6]], "e.g. Sangeet, hackathon, team retreat"
    elif field == "location":
        prompt, options, placeholder = f"Where will the {kind} be held?", bench.location_options(event_type), "City or area, e.g. Bandra or Whitefield"
    elif field == "attendees":
        prompt, options, placeholder = f"How many guests are you expecting{place}?", bench.guest_options(event_type), "Number of guests"
    elif field == "budget":
        who = f"{guests} guests" if guests else f"this {kind}"
        prompt, options, placeholder = f"What's the total budget for {who}{place}?", bench.budget_options(event_type, city, guests), "e.g. ₹8 lakh or 800000"
    elif field == "date":
        lead = event_type["lead_weeks"] if event_type else None
        prompt = f"When is it? A {kind} usually needs about {lead} weeks to plan." if lead else "When is the event?"
        options, placeholder = bench.date_options(event_type, _today()), "e.g. 14 Feb 2027"
    elif field == "objective":
        prompt, options, placeholder = f"What matters most for this {kind}?", bench.objective_options(event_type), "Describe the outcome you want"
    else:
        prompt, options, placeholder = "Last one: what should we call it?", _name_options(answers, event_type), "e.g. Meera and Karthik Reception"
    question = BriefQuestion(field=field, label=LABELS[field], prompt=prompt, options=[BriefOption(**o) for o in options], placeholder=placeholder)
    return {"next": question.model_dump()}


def _display(field: str, value: str) -> str:
    if field == "budget":
        number = _int(value) or 0
        return f"{bench.format_lakh(number)} ({inr(number)})"
    if field == "date":
        return date.fromisoformat(value).strftime("%a %d %b %Y").replace(" 0", " ")
    if field == "attendees":
        return f"{value} guests"
    return value


def _reply(filled: list[str], answers: dict[str, str], errors: dict[str, str], request: BriefTurnRequest, ready: bool) -> str:
    parts = []
    if filled:
        phrases = {
            "eventType": lambda v: f"a {v.lower()}", "location": lambda v: f"in {v}", "attendees": lambda v: f"for {v} guests",
            "date": lambda v: f"on {_display('date', v)}", "budget": lambda v: f"with a {bench.format_lakh(_int(v) or 0)} budget",
            "objective": lambda v: "your objective noted", "name": lambda v: f"called “{v}”",
        }
        parts.append("Got it: " + ", ".join(phrases[f](answers[f]) for f in BRIEF_FIELDS if f in filled) + ".")
    if errors:
        parts.append(" ".join(errors.values()))
    if not filled and not errors and request.message:
        parts.append("I couldn't find event details in that. You can answer the question below or describe the event in one sentence.")
    if ready:
        parts.append("That's everything I need. Check the brief, then generate the plan.")
    return " ".join(parts) or "Tell me about your event: type, city, guests, budget and date. One sentence is fine."


_graph = None


def _compiled():
    global _graph
    if _graph is None:
        workflow = StateGraph(BriefState)
        workflow.add_node("intake", intake)
        workflow.add_node("validate", validate)
        workflow.add_node("check", check)
        workflow.add_node("frame", frame)
        workflow.add_edge(START, "intake")
        workflow.add_edge("intake", "validate")
        workflow.add_edge("validate", "check")
        workflow.add_edge("check", "frame")
        workflow.add_edge("frame", END)
        _graph = workflow.compile()
    return _graph


async def run_brief_turn(request: BriefTurnRequest) -> BriefTurnResponse:
    result = await _compiled().ainvoke({"request": request})
    answers = {k: v for k, v in result["answers"].items() if k in BRIEF_FIELDS and v}
    missing = [field for field in BRIEF_FIELDS if not answers.get(field)]
    ready = not missing and result.get("next") is None
    return BriefTurnResponse(
        answers=answers,
        brief=[BriefItem(field=f, label=LABELS[f], value=answers[f], display=_display(f, answers[f])) for f in BRIEF_FIELDS if f in answers],
        filled=result.get("filled", []),
        missing=missing,
        errors=result.get("errors", {}),
        warnings=[BriefWarning(**w) for w in result.get("warnings", [])],
        next=BriefQuestion(**result["next"]) if result.get("next") else None,
        ready=ready,
        reply=_reply(result.get("filled", []), answers, result.get("errors", {}), request, ready),
        mode=result.get("mode", "rules"),
    )
