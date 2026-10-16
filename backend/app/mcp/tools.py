"""Deterministic, read-only tools exposed through the EventPilot MCP server."""

from datetime import datetime
from typing import Any


VENUES = [
    {"name": "Whitefield Garden Pavilion", "location": "Whitefield, Bengaluru", "capacity": 450, "rental_inr": 220_000, "features": ["covered ceremony space", "dining hall", "parking"]},
    {"name": "Koramangala Workshop Studio", "location": "Koramangala, Bengaluru", "capacity": 100, "rental_inr": 65_000, "features": ["projector", "breakout rooms", "reliable Wi-Fi"]},
    {"name": "Indiranagar Terrace Hall", "location": "Indiranagar, Bengaluru", "capacity": 220, "rental_inr": 120_000, "features": ["indoor hall", "standard AV", "metro access"]},
    {"name": "Electronic City Convention Centre", "location": "Electronic City, Bengaluru", "capacity": 700, "rental_inr": 340_000, "features": ["stage", "green rooms", "large parking area"]},
]


def search_venues(location: str, attendees: int, total_budget_inr: int) -> dict[str, Any]:
    """Return suitable local venue options without contacting a third-party service."""
    location_terms = {term.strip(",.").lower() for term in location.split() if len(term) > 2}
    venue_budget_limit = round(total_budget_inr * 0.3)
    matches = [
        venue for venue in VENUES
        if venue["capacity"] >= attendees
        and venue["rental_inr"] <= venue_budget_limit
        and (not location_terms or location_terms.intersection(venue["location"].lower().replace(",", "").split()))
    ]
    matches.sort(key=lambda venue: (venue["rental_inr"], venue["capacity"]))
    return {
        "location": location,
        "attendees": attendees,
        "venue_budget_limit_inr": venue_budget_limit,
        "recommendations": matches[:3],
        "note": "Demo catalog only. Confirm availability and quotations before booking.",
    }


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
        "checkpoints": ["Publish initial invitation", "Review RSVP count", "Send final logistics reminder"],
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
