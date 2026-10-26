"""Deterministic, read-only tools exposed through the EventPilot MCP server."""

from datetime import datetime
from typing import Any


# Kept for reference and the eventpilot://venue-catalog resource; search uses app/data/venues.json.
VENUES = [
    {"name": "Whitefield Garden Pavilion", "location": "Whitefield, Bengaluru", "capacity": 450, "rental_inr": 220_000, "features": ["covered ceremony space", "dining hall", "parking"]},
    {"name": "Koramangala Workshop Studio", "location": "Koramangala, Bengaluru", "capacity": 100, "rental_inr": 65_000, "features": ["projector", "breakout rooms", "reliable Wi-Fi"]},
    {"name": "Indiranagar Terrace Hall", "location": "Indiranagar, Bengaluru", "capacity": 220, "rental_inr": 120_000, "features": ["indoor hall", "standard AV", "metro access"]},
    {"name": "Electronic City Convention Centre", "location": "Electronic City, Bengaluru", "capacity": 700, "rental_inr": 340_000, "features": ["stage", "green rooms", "large parking area"]},
]


def search_venues(location: str, attendees: int, total_budget_inr: int, venue_type: str = "", preferences: str = "") -> dict[str, Any]:
    """Hybrid (BM25 + semantic) search over the sample venue catalogue.

    Filters by city, capacity and a venue budget of 30% of the total, ranks the
    matches by keywords, meaning, area and value, and explains near misses when
    nothing fits. No third-party service is contacted.
    """
    from app.search.venues import search

    return search(location, attendees, total_budget_inr, venue_type=venue_type, preferences=preferences)


async def weather_outlook(location: str, event_date: str) -> dict[str, Any]:
    """Weather risk for the event day from Open-Meteo, or climate notes offline."""
    from app.integrations.weather import weather_outlook as outlook

    return await outlook(location, event_date)


def holiday_check(event_date: str, location: str = "", window_days: int = 3) -> dict[str, Any]:
    """Public holidays, big festivals and long weekends on or near the date."""
    from app.integrations.holidays import holiday_check as check

    return check(event_date, location, window_days)


async def travel_access(location: str) -> dict[str, Any]:
    """Road distance and time from a venue to the city's airport and main station."""
    from app.integrations.geo import travel_access as access

    return await access(location)


def vendor_search(city: str, category: str, budget_inr: int, guests: int = 0, event_type: str = "", preferences: str = "") -> dict[str, Any]:
    """Shortlist vendors from the sample catalogue that fit one budget line."""
    from app.integrations.vendors import search_vendors

    return search_vendors(city, category, budget_inr, guests, event_type, preferences)


def guest_message_draft(kind: str, event_name: str, event_date: str, location: str, venue: str = "", start_time: str = "", host: str = "", rsvp_by: str = "", event_type: str = "") -> dict[str, Any]:
    """Draft a guest invite, reminder or venue-change message. Never sends."""
    from app.integrations.messages import draft_guest_message

    return draft_guest_message(kind, event_name, event_date, location, venue, start_time, host, rsvp_by, event_type)


def validate_budget(budget_lines: list[dict[str, Any]], total_budget_inr: int) -> dict[str, Any]:
    """Check an allocation against the approved total without performing spending."""
    allocated = sum(int(line.get("amount", 0)) for line in budget_lines)
    negative_categories = [str(line.get("category", "Unlabelled")) for line in budget_lines if int(line.get("amount", 0)) < 0]
    return {
        "approved_budget_inr": total_budget_inr,
        "allocated_inr": allocated,
        "remaining_inr": total_budget_inr - allocated,
        "within_budget": allocated <= total_budget_inr and not negative_categories,
        "negative_categories": negative_categories,
        "recommendation": "Keep the remaining amount as contingency." if allocated <= total_budget_inr else "Reduce lower-priority categories before approval.",
    }


def check_schedule_conflicts(agenda: list[dict[str, str]]) -> dict[str, Any]:
    """Identify duplicate or invalid 12-hour agenda times."""
    seen_times: set[str] = set()
    conflicts: list[str] = []
    for item in agenda:
        time_label = item.get("time", "").strip()
        try:
            datetime.strptime(time_label, "%I:%M %p")
        except ValueError:
            conflicts.append(f"Invalid 12-hour time: {time_label or 'missing time'}")
            continue
        if time_label in seen_times:
            conflicts.append(f"Overlapping agenda time: {time_label}")
        seen_times.add(time_label)
    return {"valid": not conflicts, "conflicts": conflicts, "agenda_items_checked": len(agenda)}


def get_event_requirements(event_type: str, attendees: int) -> dict[str, Any]:
    """Return a compact operational checklist by event type and group size."""
    normalized_type = event_type.lower()
    requirements = ["event lead", "guest communication plan", "contingency budget"]
    if "wedding" in normalized_type:
        requirements += ["ceremony coordinator", "family contact sheet", "photography timeline", "catering service plan"]
    elif "workshop" in normalized_type:
        requirements += ["facilitator confirmation", "AV rehearsal", "participant materials", "feedback collection"]
    if attendees >= 200:
        requirements += ["crowd-flow plan", "medical support contact", "parking or transport guidance"]
    return {"event_type": event_type, "attendees": attendees, "requirements": requirements}


def _send_schedule(event_date: str, attendees: int) -> list[str]:
    """Dated sends counted back from the event: invite, RSVP deadline, reminder, final logistics. Larger events invite earlier."""
    from datetime import date, timedelta

    try:
        day = date.fromisoformat(str(event_date)[:10])
    except ValueError:
        return ["Publish initial invitation", "Review RSVP count", "Send final logistics reminder"]
    lead = 45 if attendees >= 500 else 30 if attendees >= 100 else 21
    room = max((day - date.today()).days - 1, 3)  # an event that is close compresses the schedule, never into the past
    steps = [(min(lead, room), "Send the invitation with an RSVP link"), (max(min(10, room * 2 // 3), 2), "RSVP deadline: confirm the head count for catering and seating"),
             (max(min(5, room // 2), 1), "Reminder to confirmed guests; one follow-up to anyone who hasn't replied"), (1, "Final logistics message: venue directions, timings, contact person")]
    return [f"{(day - timedelta(days=days)):%d %b %Y} ({days} day{'' if days == 1 else 's'} before): {what}" for days, what in steps]


def assess_marketing(event_type: str, attendees: int, event_date: str) -> dict[str, Any]:
    """Return a practical, read-only promotion readiness plan."""
    channels = ["event landing page", "WhatsApp invitation", "email reminder"]
    if attendees >= 200:
        channels += ["social media campaign", "registration dashboard"]
    if "wedding" in event_type.lower():
        channels = ["digital invitation", "family RSVP group", "guest reminder", "venue directions"]
    return {
        "event_type": event_type,
        "event_date": event_date,
        "recommended_channels": channels,
        "checkpoints": _send_schedule(event_date, attendees),
        "status": "draft - requires event owner approval before sending",
    }


def assess_operational_risks(event_type: str, attendees: int, location: str) -> dict[str, Any]:
    """Return an initial risk register without taking external action."""
    risks = [
        {"level": "Medium", "title": "RSVP or attendance variance", "action": "Confirm catering and seating after final RSVP cutoff."},
        {"level": "Medium", "title": "AV or power interruption", "action": "Complete a technical rehearsal and keep backup equipment."},
    ]
    if attendees >= 200:
        risks.append({"level": "High", "title": "Crowd-flow congestion", "action": "Assign entry, parking, and guest-flow coordinators."})
    if "wedding" in event_type.lower():
        risks.append({"level": "High", "title": "Ceremony timing delay", "action": "Assign a family liaison and hold a buffer before dining service."})
    return {"event_type": event_type, "location": location, "attendees": attendees, "risks": risks}
