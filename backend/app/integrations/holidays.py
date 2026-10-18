"""Custom India holiday and festival calendar (app/data/holidays.json).

Flags public holidays and big festivals on or near the event date, long
weekends and seasonal effects (wedding season, exam season). Works offline.
"""

import json
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.search.benchmarks import resolve_city

DATA = Path(__file__).resolve().parents[1] / "data" / "holidays.json"
SOURCE = "EventPilot holiday calendar (DoPT central government lists for 2026 and 2027)"


@lru_cache
def calendar() -> dict[str, Any]:
    return json.loads(DATA.read_text(encoding="utf-8"))


def _entry(item: dict[str, Any], day: date, city: str | None) -> dict[str, Any]:
    on = date.fromisoformat(item["date"])
    return {
        "date": item["date"],
        "weekday": f"{on:%A}",
        "name": item["name"],
        "type": item["type"],
        "days_from_event": (on - day).days,
        "big_here": bool(city and city in item.get("big_in", [])),
        **({"note": item["note"]} if item.get("note") else {}),
    }


def holiday_check(event_date: str, location: str = "", window_days: int = 3) -> dict[str, Any]:
    try:
        day = date.fromisoformat(str(event_date)[:10])
    except ValueError:
        return {"event_date": event_date, "risk": "Low", "on_the_day": [], "nearby": [], "summary": f"'{event_date}' isn't a date (use YYYY-MM-DD)"}
    window_days = max(0, min(int(window_days), 7))
    city = resolve_city(location or "")
    data = calendar()
    coverage = data["coverage"]
    covered = coverage["from"] <= day.isoformat() <= coverage["to"]
    on_day, nearby = [], []
    for item in data["holidays"]:
        delta = (date.fromisoformat(item["date"]) - day).days
        if delta == 0:
            on_day.append(_entry(item, day, city))
        elif abs(delta) <= window_days:
            nearby.append(_entry(item, day, city))
    nearby.sort(key=lambda h: abs(h["days_from_event"]))

    gazetted_dates = {date.fromisoformat(h["date"]) for h in data["holidays"] if h["type"] == "gazetted"}
    weekend_run = day.weekday() >= 4 or day.weekday() == 0
    long_weekend = weekend_run and any(d in gazetted_dates for d in (day - timedelta(days=1), day, day + timedelta(days=1), day + timedelta(days=2)) if d.weekday() in (0, 4))
    seasons = [s["note"] for s in data["seasons"] if day.month in s["months"]]

    if any(h["type"] == "gazetted" or h["big_here"] for h in on_day):
        risk = "High"
    elif on_day or any(h["big_here"] or h["type"] == "gazetted" for h in nearby) or long_weekend:
        risk = "Medium"
    else:
        risk = "Low"

    if not covered:
        summary = f"The holiday calendar covers {coverage['from'][:4]}–{coverage['to'][:4]}; check {day.year} dates locally"
    elif on_day:
        summary = f"{day:%a} {day.day} {day:%b %Y} is {', '.join(h['name'] for h in on_day)}"
    elif nearby:
        first = nearby[0]
        when = f"{abs(first['days_from_event'])} day{'s' if abs(first['days_from_event']) != 1 else ''} {'after' if first['days_from_event'] > 0 else 'before'}"
        summary = f"{first['name']} is {when} the event ({first['date']})"
    else:
        summary = f"{day:%a} {day.day} {day:%b %Y} is clear of public holidays and major festivals"

    return {
        "event_date": day.isoformat(),
        "weekday": f"{day:%A}",
        "city": city,
        "covered": covered,
        "on_the_day": on_day,
        "nearby": nearby,
        "long_weekend": long_weekend,
        "season_notes": seasons,
        "risk": risk,
        "summary": summary,
        "advice": {
            "High": "Expect higher venue and vendor rates, busy roads and guests travelling; consider another date or book early.",
            "Medium": "Book vendors early and allow extra travel time for guests.",
            "Low": "No holiday clash.",
        }[risk],
        "sources": [SOURCE, "State holidays differ; confirm locally"],
    }
