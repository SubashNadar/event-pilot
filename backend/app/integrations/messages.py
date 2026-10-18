"""Guest message drafts (custom tool). Drafts only: nothing is ever sent.

Templates keep the wording consistent and cheap (no LLM call), and every draft
is checked before it reaches the owner: date and place present, no unfilled
fields, and short enough for WhatsApp or SMS.
"""

import re
from datetime import date
from typing import Any

WHATSAPP_LIMIT = 1000
SMS_LIMIT = 320
KINDS = ("invite", "reminder", "venue_change")


def _when(event_date: str, start_time: str) -> str:
    try:
        day = date.fromisoformat(str(event_date)[:10])
        text = f"{day:%A}, {day.day} {day:%B %Y}"
    except ValueError:
        text = str(event_date)
    return f"{text}, from {start_time}" if start_time else text


def draft_guest_message(kind: str, event_name: str, event_date: str, location: str, venue: str = "", start_time: str = "", host: str = "", rsvp_by: str = "", event_type: str = "") -> dict[str, Any]:
    kind = kind if kind in KINDS else "invite"
    place = f"{venue}, {location}" if venue else location
    when = _when(event_date, start_time)
    sign = f"\n\n{host}" if host else ""
    family = "wedding" in event_type.lower() or "reception" in event_name.lower() or "sangeet" in event_name.lower()
    rsvp = f"Please reply by {_when(rsvp_by, '')} to confirm how many of you will join." if rsvp_by else "Please reply to confirm how many of you will join."
    if kind == "invite":
        opener = "With joy, we invite you and your family to" if family else "You're invited to"
        text = f"{opener} {event_name}.\n\nWhen: {when}\nWhere: {place}\n\n{rsvp}" + ("" if venue else "\nWe'll share the venue address and directions soon.") + sign
    elif kind == "reminder":
        text = f"A reminder that {event_name} is on {when}.\n\nWhere: {place}\n\nReply if your plans have changed." + sign
    else:
        text = f"Change of venue for {event_name}.\n\nThe event is now at {place}, still on {when}.\n\nReply if this changes your plans." + sign

    checks = [
        {"check": "Date included", "passed": bool(re.search(r"\d{4}", when)), "detail": when},
        {"check": "Place included", "passed": bool(location.strip()), "detail": place or "missing"},
        {"check": "Venue confirmed", "passed": bool(venue), "detail": venue or "venue still to be confirmed; the draft says details follow"},
        {"check": "No unfilled fields", "passed": not re.search(r"\{|\}|\[|\]|TBD|XXX", text), "detail": "every field is filled"},
        {"check": "Fits one WhatsApp message", "passed": len(text) <= WHATSAPP_LIMIT, "detail": f"{len(text)} of {WHATSAPP_LIMIT} characters"},
    ]
    return {
        "kind": kind,
        "channel": "WhatsApp" if len(text) > SMS_LIMIT else "WhatsApp or SMS",
        "text": text,
        "characters": len(text),
        "checks": checks,
        "ready": all(c["passed"] for c in checks if c["check"] != "Venue confirmed"),
        "status": "draft - nothing is sent until the event owner approves it",
    }
