"""Streamable HTTP MCP server for EventPilot's planning tools."""

from mcp.server.fastmcp import FastMCP

from app.mcp.tools import VENUES, assess_marketing, assess_operational_risks, check_schedule_conflicts, get_event_requirements, search_venues, validate_budget

mcp = FastMCP("EventPilot Planning Tools")


@mcp.tool()
def venue_search(location: str, attendees: int, total_budget_inr: int) -> dict:
    """Find suitable venue options from the EventPilot demonstration catalog."""
    return search_venues(location, attendees, total_budget_inr)


@mcp.tool()
def budget_validation(budget_lines: list[dict], total_budget_inr: int) -> dict:
    """Validate event budget allocations against the approved budget."""
    return validate_budget(budget_lines, total_budget_inr)


@mcp.tool()
def schedule_conflict_check(agenda: list[dict[str, str]]) -> dict:
    """Detect duplicate or invalid agenda times in a 12-hour event schedule."""
    return check_schedule_conflicts(agenda)


@mcp.tool()
def event_requirements(event_type: str, attendees: int) -> dict:
    """Return operational planning requirements for a given event type."""
    return get_event_requirements(event_type, attendees)


@mcp.tool()
def marketing_readiness(event_type: str, attendees: int, event_date: str) -> dict:
    """Create an approval-gated event communication readiness plan."""
    return assess_marketing(event_type, attendees, event_date)


@mcp.tool()
def operational_risk_assessment(event_type: str, attendees: int, location: str) -> dict:
    """Create an initial operational risk register for an event."""
    return assess_operational_risks(event_type, attendees, location)


@mcp.resource("eventpilot://venue-catalog")
def venue_catalog() -> list[dict]:
    """Read-only list of the demonstration venues used by venue_search."""
    return VENUES


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
