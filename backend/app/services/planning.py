from app.core.config import settings
from app.models.event import AgendaItem, AgentActivity, BudgetLine, EventBrief, EventPlan, RiskItem
from app.services.azure_planner import build_azure_plan


def is_birthday_event(event: EventBrief) -> bool:
    return any(keyword in f"{event.name} {event.objective}".lower() for keyword in ("birthday", "celebration", "party"))


def build_demo_plan(event: EventBrief) -> EventPlan:
    """Deterministic local plan used until the LangGraph workflow is connected."""
    birthday = is_birthday_event(event)
    forecast = round(event.budget * 0.928)

    if birthday:
        categories = [
            ("Venue and music", 28), ("Food and beverages", 31), ("Cake and desserts", 8),
            ("Decor and lighting", 14), ("Photography", 11), ("Contingency", 8),
        ]
        agenda = [
            ("6:00 PM", "Guest arrival and welcome drinks", "Operations"),
            ("6:30 PM", "Games and photo time", "Host"),
            ("7:15 PM", "Cake cutting and speeches", "Programme"),
            ("8:00 PM", "Dinner service", "Catering"),
            ("9:00 PM", "Music, dance, and closing", "Entertainment"),
        ]
        risks = [
            ("High", "Weather disruption for an outdoor venue", "Reserve covered space or an indoor fallback.", "Set venue fallback"),
            ("Medium", "RSVP count changes close to the event", "Confirm final catering three days before the event.", "Monitor RSVP count"),
        ]
        if event.attendees >= 100:
            risks.append(("Medium", "Cake or catering delivery delay", "Confirm delivery windows and assign a vendor contact.", "Monitor vendor confirmation"))
        venue = "Private celebration venue"
        venue_detail = f"{event.location} · accommodates {event.attendees} guests"
        plan_type = "birthday"
    else:
        categories = [
            ("Venue and AV", 34), ("Catering", 21), ("Programme and speakers", 14),
            ("Promotion", 11), ("Operations", 10), ("Contingency", 10),
        ]
        agenda = [
            ("9:00 AM", "Registration and breakfast", "Operations"),
            ("10:00 AM", "Opening session", "Programme"),
            ("11:00 AM", "Interactive activity", "Facilitators"),
            ("2:00 PM", "Breakout sessions", "Programme"),
            ("4:30 PM", "Closing and feedback collection", "Marketing"),
        ]
        risks = [
            ("High", "Key contributor availability", "Confirm a substitute or remote fallback.", "Set fallback"),
            ("Medium", "Attendance below target", "Review registrations and activate outreach.", "Monitor registrations"),
        ]
        if event.attendees >= 150:
            risks.append(("High", "Crowd-flow congestion", "Assign registration, entry, and floor coordinators.", "Set operations fallback"))
        if event.attendees >= 300:
            risks.append(("Medium", "AV or power interruption", "Complete a technical rehearsal and hold backup equipment.", "Monitor technical readiness"))
        venue = "Recommended venue"
        venue_detail = f"{event.location} · supports {event.attendees} attendees"
        plan_type = "standard"

    return EventPlan(
        event_id=event.id,
        plan_type=plan_type,
        venue=venue,
        venue_detail=venue_detail,
        budget_forecast=forecast,
        budget_lines=[BudgetLine(category=name, amount=round(forecast * share / 100), share_percent=share) for name, share in categories],
        agenda=[AgendaItem(time=time, activity=activity, owner=owner) for time, activity, owner in agenda],
        risks=[RiskItem(level=level, title=title, detail=detail, recommended_action=action) for level, title, detail, action in risks],
        activity=[
            AgentActivity(agent="Event Manager", detail=f"Created a {plan_type} plan from the event brief.", timestamp="Now"),
            AgentActivity(agent="Budget & Finance", detail="Prepared forecast and contingency allocation.", timestamp="Just now"),
            AgentActivity(agent="Risk & Operations", detail="Created the initial risk register.", timestamp="Just now"),
        ],
        confidence=84 if birthday else 86,
        source="deterministic",
    )


def build_event_plan(event: EventBrief, operation: str = "plan-generation") -> EventPlan:
    if not settings.azure_openai_enabled:
        return build_demo_plan(event)

    try:
        from app.graphs.event_workflow import run_event_workflow

        return run_event_workflow(event, operation)
    except Exception:
        try:
            return build_azure_plan(event, operation=operation)
        except Exception:
            fallback = build_demo_plan(event)
            fallback.source = "fallback"
            return fallback
