"""Streamable HTTP MCP server for EventPilot's planning tools.

Every tool is read-only. Two groups:
- custom tools over EventPilot's own data: venues, vendors, holidays, budget,
  agenda, requirements, guest communication and risk;
- free web services that need no key: Open-Meteo weather, OpenStreetMap
  Nominatim geocoding and OSRM road routes, each with an offline fallback.
Nothing here books, pays or sends. Guest messages are drafts for approval.
"""

from mcp.server.fastmcp import FastMCP

from app.mcp import tools

mcp = FastMCP("EventPilot Planning Tools")


# ------------------------------------------------------------ custom tools

@mcp.tool()
def venue_search(location: str, attendees: int, total_budget_inr: int, venue_type: str = "", preferences: str = "") -> dict:
    """Find venues that fit a city or area, guest count and total budget. Optional venue_type
    (e.g. 'banquet hall', 'beach resort') and preferences (free text, e.g. 'sea view, parking')
    steer the ranking. Uses hybrid BM25 + semantic search over the sample catalogue."""
    return tools.search_venues(location, attendees, total_budget_inr, venue_type, preferences)


@mcp.tool()
def vendor_search(city: str, category: str, budget_inr: int, guests: int = 0, event_type: str = "", preferences: str = "") -> dict:
    """Shortlist vendors for one budget line. category is one of catering, decor, photography,
    sound_light, entertainment, mehendi, av_production (plain words like 'food' also work).
    Catering is priced per plate for the guest count. Sample catalogue, not real businesses."""
    return tools.vendor_search(city, category, budget_inr, guests, event_type, preferences)


@mcp.tool()
def holiday_check(event_date: str, location: str = "", window_days: int = 3) -> dict:
    """Check an event date (YYYY-MM-DD) for Indian public holidays, big festivals, long weekends
    and seasonal effects within window_days (0-7). Covers 2026-2027."""
    return tools.holiday_check(event_date, location, window_days)


@mcp.tool()
def guest_message_draft(kind: str, event_name: str, event_date: str, location: str, venue: str = "", start_time: str = "", host: str = "", rsvp_by: str = "", event_type: str = "") -> dict:
    """Draft a guest message (kind: invite, reminder or venue_change) and check it. Never sends;
    the event owner approves every message."""
    return tools.guest_message_draft(kind, event_name, event_date, location, venue, start_time, host, rsvp_by, event_type)


@mcp.tool()
def budget_validation(budget_lines: list[dict], total_budget_inr: int) -> dict:
    """Validate event budget allocations against the approved budget."""
    return tools.validate_budget(budget_lines, total_budget_inr)


@mcp.tool()
def schedule_conflict_check(agenda: list[dict[str, str]]) -> dict:
    """Detect duplicate or invalid agenda times in a 12-hour event schedule."""
    return tools.check_schedule_conflicts(agenda)


@mcp.tool()
def event_requirements(event_type: str, attendees: int) -> dict:
    """Return operational planning requirements for a given event type."""
    return tools.get_event_requirements(event_type, attendees)


@mcp.tool()
def marketing_readiness(event_type: str, attendees: int, event_date: str) -> dict:
    """Create an approval-gated event communication readiness plan."""
    return tools.assess_marketing(event_type, attendees, event_date)


@mcp.tool()
def operational_risk_assessment(event_type: str, attendees: int, location: str) -> dict:
    """Create an initial operational risk register for an event."""
    return tools.assess_operational_risks(event_type, attendees, location)


# ------------------------------------------------------- free web services

@mcp.tool()
async def weather_outlook(location: str, event_date: str) -> dict:
    """Weather risk for the event day (YYYY-MM-DD) from Open-Meteo: the forecast within 15 days,
    otherwise the same week over the last five years. Falls back to climate notes offline."""
    return await tools.weather_outlook(location, event_date)


@mcp.tool()
async def travel_access(location: str) -> dict:
    """Road distance and time from a venue or area to the city's airport(s) and main railway
    station, using OpenStreetMap Nominatim and the OSRM demo router (estimates offline)."""
    return await tools.travel_access(location)


# ---------------------------------------------------------------- resources

@mcp.resource("eventpilot://venue-catalog")
def venue_catalog() -> list[dict]:
    """Read-only list of the sample venues used by venue_search."""
    from app.search.venues import catalog

    return catalog()


@mcp.resource("eventpilot://vendor-catalog")
def vendor_catalog() -> list[dict]:
    """Read-only list of the sample vendors used by vendor_search."""
    from app.integrations.vendors import catalog

    return catalog()["vendors"]


@mcp.resource("eventpilot://holiday-calendar")
def holiday_calendar() -> list[dict]:
    """Read-only India holiday and festival calendar used by holiday_check."""
    from app.integrations.holidays import calendar

    return calendar()["holidays"]


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
