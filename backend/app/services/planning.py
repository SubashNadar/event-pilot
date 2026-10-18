"""Rule-based planning helpers.

`build_demo_plan` is the deterministic plan used when Azure OpenAI is not
configured. `compose_rule_plan` is the rule-based Event Manager: it starts from
that plan and replaces venue, budget, agenda and risks with what the specialist
agents actually decided, so the no-Azure mode still reflects the agents' work.
"""

from typing import Any

from app.models.event import AgendaItem, AgentActivity, BudgetLine, EventBrief, EventPlan, RiskItem


def is_birthday_event(event: EventBrief) -> bool:
    return any(keyword in f"{event.name} {event.objective}".lower() for keyword in ("birthday", "celebration", "party"))


_BIRTHDAY_CATEGORIES = [("Venue and music", 28), ("Food and beverages", 31), ("Cake and desserts", 8), ("Decor and lighting", 14), ("Photography", 11), ("Contingency", 8)]
_STANDARD_CATEGORIES = [("Venue and AV", 34), ("Catering", 21), ("Programme and speakers", 14), ("Promotion", 11), ("Operations", 10), ("Contingency", 10)]
_BIRTHDAY_AGENDA = [("6:00 PM", "Guest arrival and welcome drinks", "Operations"), ("6:30 PM", "Games and photo time", "Host"), ("7:15 PM", "Cake cutting and speeches", "Programme"), ("8:00 PM", "Dinner service", "Catering"), ("9:00 PM", "Music, dance, and closing", "Entertainment")]
_STANDARD_AGENDA = [("9:00 AM", "Registration and breakfast", "Operations"), ("10:00 AM", "Opening session", "Programme"), ("11:00 AM", "Interactive activity", "Facilitators"), ("2:00 PM", "Breakout sessions", "Programme"), ("4:30 PM", "Closing and feedback collection", "Marketing")]


def default_budget_lines(event: EventBrief, contingency_pct: int | None = None) -> list[dict[str, Any]]:
    forecast = round(event.budget * 0.928)
    categories = list(_BIRTHDAY_CATEGORIES if is_birthday_event(event) else _STANDARD_CATEGORIES)
    if contingency_pct is not None:
        others = categories[:-1]
        scale = (100 - contingency_pct) / sum(share for _, share in others)
        categories = [(name, round(share * scale)) for name, share in others] + [("Contingency", contingency_pct)]
    lines = [{"category": name, "amount": round(forecast * share / 100)} for name, share in categories]
    return lines


def default_agenda(event: EventBrief) -> list[dict[str, str]]:
    agenda = _BIRTHDAY_AGENDA if is_birthday_event(event) else _STANDARD_AGENDA
    return [{"time": time, "activity": activity} for time, activity, _ in agenda]


def build_demo_plan(event: EventBrief) -> EventPlan:
    """Deterministic local plan used when Azure OpenAI is not configured."""
    birthday = is_birthday_event(event)
    forecast = round(event.budget * 0.928)
    categories = _BIRTHDAY_CATEGORIES if birthday else _STANDARD_CATEGORIES
    agenda = _BIRTHDAY_AGENDA if birthday else _STANDARD_AGENDA
    if birthday:
        risks = [
            ("High", "Weather disruption for an outdoor venue", "Reserve covered space or an indoor fallback.", "Set venue fallback"),
            ("Medium", "RSVP count changes close to the event", "Confirm final catering three days before the event.", "Monitor RSVP count"),
        ]
        if event.attendees >= 100:
            risks.append(("Medium", "Cake or catering delivery delay", "Confirm delivery windows and assign a vendor contact.", "Monitor vendor confirmation"))
        venue, plan_type = "Private celebration venue", "birthday"
        venue_detail = f"{event.location} · accommodates {event.attendees} guests"
    else:
        risks = [
            ("High", "Key contributor availability", "Confirm a substitute or remote fallback.", "Set fallback"),
            ("Medium", "Attendance below target", "Review registrations and activate outreach.", "Monitor registrations"),
        ]
        if event.attendees >= 150:
            risks.append(("High", "Crowd-flow congestion", "Assign registration, entry, and floor coordinators.", "Set operations fallback"))
        if event.attendees >= 300:
            risks.append(("Medium", "AV or power interruption", "Complete a technical rehearsal and hold backup equipment.", "Monitor technical readiness"))
        venue, plan_type = "Recommended venue", "standard"
        venue_detail = f"{event.location} · supports {event.attendees} attendees"

    lines = [BudgetLine(category=name, amount=round(forecast * share / 100), share_percent=share) for name, share in categories]
    return EventPlan(
        event_id=event.id,
        plan_type=plan_type,
        venue=venue,
        venue_detail=venue_detail,
        budget_forecast=sum(line.amount for line in lines),
        budget_lines=lines,
        agenda=[AgendaItem(time=time, activity=activity, owner=owner) for time, activity, owner in agenda],
        risks=[RiskItem(level=level, title=title, detail=detail, recommended_action=action) for level, title, detail, action in risks],
        activity=[
            AgentActivity(agent="Event Manager", detail=f"Created a {plan_type} plan from the event brief.", timestamp="Now"),
            AgentActivity(agent="Budget & Finance", detail="Prepared forecast and contingency allocation.", timestamp="Now"),
            AgentActivity(agent="Risk & Operations", detail="Created the initial risk register.", timestamp="Now"),
        ],
        confidence=84 if birthday else 86,
        source="deterministic",
    )


def compose_rule_plan(event: EventBrief, context: dict[str, Any]) -> EventPlan:
    """Rule-based Event Manager: merge specialist decisions into one plan."""
    plan = build_demo_plan(event)
    activity: list[AgentActivity] = []
    skipped: list[str] = []

    def decisions(key: str) -> dict[str, Any]:
        report = context.get(key) or {}
        if report.get("skipped"):
            skipped.append(report.get("agent", key))
            return {}
        if report.get("recommendations"):
            activity.append(AgentActivity(agent=report.get("agent", key), detail=report["recommendations"][0], timestamp="Now"))
        return report.get("decisions") or {}

    logistics = decisions("logistics")
    if logistics.get("venue"):
        plan.venue = logistics["venue"]
        plan.venue_detail = logistics.get("venue_detail", plan.venue_detail)
        if logistics.get("unverified"):
            plan.venue_detail += " (unverified)"

    finance = decisions("finance")
    lines = finance.get("budget_lines") or []
    if lines:
        total = sum(int(line["amount"]) for line in lines)
        plan.budget_lines = [BudgetLine(category=line["category"], amount=int(line["amount"]), share_percent=round(int(line["amount"]) / total * 100) if total else 0) for line in lines]
        plan.budget_forecast = total

    schedule = decisions("schedule")
    agenda = schedule.get("agenda") or []
    if agenda:
        owners = [item.owner for item in plan.agenda]
        plan.agenda = [AgendaItem(time=item["time"], activity=item["activity"], owner=item.get("owner") or owners[index % len(owners)]) for index, item in enumerate(agenda)]

    risk_decisions = decisions("risks").get("risks") or []
    if risk_decisions:
        plan.risks = [RiskItem(level=r["level"], title=r["title"], detail=r.get("action", ""), recommended_action="Set fallback" if r["level"] == "High" else "Monitor") for r in risk_decisions[:5]]
        if len(plan.risks) < 2:
            plan.risks.append(RiskItem(level="Medium", title="Attendance variance", detail="Confirm numbers after the RSVP cutoff.", recommended_action="Monitor"))

    decisions("requirements")
    decisions("marketing")
    for name in skipped:
        if len(plan.risks) < 5:
            plan.risks.append(RiskItem(level="Medium", title=f"{name} step was skipped", detail=f"The {name} specialist was skipped during planning; review this area manually.", recommended_action="Review manually"))

    plan.activity = (activity or plan.activity)[:6]
    plan.confidence = max(50, plan.confidence - 8 * len(skipped))
    plan.source = "rules"
    return plan
