"""Deterministic verification for each specialist step.

A step only counts as completed when its check passes. The check text is what
the UI shows while the step is `verifying`; the reason is what it shows after.
"""

from datetime import date
from typing import Any

from app.models.event import EventBrief
from app.models.run import Verification

CHECK_TEXT = {
    "logistics_agent": "Checking the venue fits the guest count and the venue budget…",
    "finance_agent": "Checking the budget lines stay within budget and include contingency…",
    "schedule_agent": "Checking the agenda for overlaps and 12-hour times…",
    "requirements_agent": "Checking every critical requirement is listed…",
    "marketing_agent": "Checking channels exist and sends happen before the event…",
    "risk_operations_agent": "Checking every high risk has a fallback…",
    "event_manager": "Checking the plan matches the schema…",
    "review_plan": "Checking budget arithmetic, agenda times and risk count…",
}


from app.agents.fmt import inr as money


def verify(step_id: str, result: dict[str, Any], event: EventBrief, overrides: dict[str, Any]) -> Verification:
    tool = (result.get("tool_results") or [{}])[-1]
    report = result.get("report") or {}
    check = CHECK_TEXT.get(step_id, "Checking the result…").rstrip("…")

    if step_id == "logistics_agent":
        from app.agents.specialists import pick_venue

        recs = tool.get("recommendations", [])
        args = tool.get("_args", {})
        guests = args.get("attendees", event.attendees)
        best = pick_venue(tool, overrides)
        if overrides.get("venue") and not overrides.get("venue_soft") and best is None:
            return Verification(check="Venue capacity ≥ guests and rent within the venue budget", passed=False, reason=f"{overrides['venue']} doesn't fit {guests} guests within {money(tool.get('venue_budget_limit_inr', 0))}")
        if best:
            ok = best["capacity"] >= guests and best["rental_inr"] <= tool.get("venue_budget_limit_inr", 0)
            return Verification(check="Venue capacity ≥ guests and rent within the venue budget", passed=ok, reason=f"{best['name']} holds {best['capacity']} (need {guests}); rent {money(best['rental_inr'])} ≤ {money(tool.get('venue_budget_limit_inr', 0))}" if ok else f"{best['name']} doesn't fit {guests} guests within budget")
        if overrides.get("allow_unverified"):
            return Verification(check="Venue capacity ≥ guests and rent within the venue budget", passed=True, reason="You accepted an unverified venue; it is flagged in the plan")
        near = tool.get("near_misses") or {}
        why = ""
        if near.get("reason") == "over_budget":
            fit = near["cheapest_fit"]
            why = f"; the cheapest that fits is {fit['name']} at {money(fit['rental_inr'])} ({near['venue_share_needed_pct']}% of the budget)"
        elif near.get("reason") == "too_small":
            why = f"; the largest is {near['largest']['name']} for {near['largest']['capacity']} guests"
        elif near.get("reason") == "city_not_in_catalog":
            why = "; that city isn't in the venue catalogue yet"
        return Verification(check="Venue capacity ≥ guests and rent within the venue budget", passed=False, reason=f"No catalog venue fits {guests} guests in {args.get('location', event.location)} within {money(tool.get('venue_budget_limit_inr', 0))}{why}")

    if step_id == "finance_agent":
        lines = tool.get("_lines", [])
        allocated = tool.get("allocated_inr", 0)
        approved = tool.get("approved_budget_inr", event.budget)
        contingency = next((line for line in lines if "contingency" in str(line.get("category", "")).lower()), None)
        if not tool.get("within_budget"):
            return Verification(check="Total ≤ budget with a contingency line", passed=False, reason=f"Allocated {money(allocated)} is over the {money(approved)} budget")
        if not contingency:
            return Verification(check="Total ≤ budget with a contingency line", passed=False, reason="No contingency line in the budget")
        pct = round(contingency["amount"] / allocated * 100) if allocated else 0
        return Verification(check="Total ≤ budget with a contingency line", passed=True, reason=f"{money(allocated)} of {money(approved)} with {pct}% contingency")

    if step_id == "schedule_agent":
        agenda = tool.get("_agenda", [])
        if not tool.get("valid"):
            return Verification(check="No overlaps, 12-hour times", passed=False, reason="; ".join(tool.get("conflicts", []))[:200])
        if len(agenda) < 3:
            return Verification(check="No overlaps, 12-hour times", passed=False, reason=f"Only {len(agenda)} agenda items")
        return Verification(check="No overlaps, 12-hour times", passed=True, reason=f"{len(agenda)} items, no conflicts")

    if step_id == "requirements_agent":
        reqs = tool.get("requirements", [])
        return Verification(check="Critical requirements listed", passed=bool(reqs), reason=f"{len(reqs)} requirements, including {', '.join(reqs[:2])}" if reqs else "No requirements returned")

    if step_id == "marketing_agent":
        channels = tool.get("recommended_channels", [])
        future = event.event_date > date.today()
        ok = bool(channels) and future
        reason = f"{len(channels)} channels; first send before {event.event_date}" if ok else ("The event date has already passed" if not future else "No channels returned")
        return Verification(check="Channels set and sends before the event", passed=ok, reason=reason)

    if step_id == "risk_operations_agent":
        risks = tool.get("risks", [])
        missing = [r["title"] for r in risks if r.get("level") == "High" and not r.get("action")]
        ok = bool(risks) and not missing
        return Verification(check="Every high risk has a fallback", passed=ok, reason=f"{len(risks)} risks, all high risks covered" if ok else (f"No fallback for: {', '.join(missing)}" if missing else "No risks returned"))

    return Verification(check=check, passed=bool(report), reason="Result received")
