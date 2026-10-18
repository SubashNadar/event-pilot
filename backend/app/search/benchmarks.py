"""Planning benchmarks: what's typical for an event type in a city.

Used to frame the brief questions (suggested guest counts, budget bands, dates
and objectives) and to sanity-check answers. Event types are matched with BM25
over each type's keywords, so "sangeet", "hackathon" or "team retreat" map to
the right row without an LLM.
"""

import json
import math
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.agents.fmt import inr
from app.search.bm25 import BM25, tokenize

DATA = Path(__file__).resolve().parents[1] / "data" / "benchmarks.json"


@lru_cache
def _data() -> dict[str, Any]:
    return json.loads(DATA.read_text(encoding="utf-8"))


@lru_cache
def _type_index() -> BM25:
    return BM25([f"{t['label']} {t['keywords']}" for t in _data()["event_types"]])


def event_types() -> list[dict[str, Any]]:
    return _data()["event_types"]


def match_event_type(text: str) -> dict[str, Any] | None:
    """Best matching event type for free text, or None if no keyword matches."""
    if not text:
        return None
    ranked = _type_index().rank(text)
    return event_types()[ranked[0]] if ranked else None


def type_by_label(label: str | None) -> dict[str, Any] | None:
    if not label:
        return None
    for event_type in event_types():
        if event_type["label"].lower() == label.lower():
            return event_type
    return match_event_type(label)


def known_cities() -> list[str]:
    return list(_data()["city_aliases"].keys())


def resolve_city(text: str) -> str | None:
    """Canonical catalog city mentioned in `text` (aliases like Bombay or Gurgaon count)."""
    lowered = f" {(text or '').lower()} "
    best: tuple[int, str] | None = None
    for city, aliases in _data()["city_aliases"].items():
        for alias in [city.lower(), *aliases]:
            if f" {alias} " in lowered.replace(",", " ").replace(".", " "):
                if best is None or len(alias) > best[0]:
                    best = (len(alias), city)
    return best[1] if best else None


def city_tier(city: str | None) -> str:
    for tier, cities in _data()["city_tiers"].items():
        if city in cities:
            return tier
    return "other"


def cost_band(event_type: dict[str, Any] | None, city: str | None) -> tuple[int, int, int] | None:
    if not event_type:
        return None
    low, typical, high = event_type["cost_per_guest"][city_tier(city)]
    return low, typical, high


def nice_round(value: float) -> int:
    """Round budgets the way people say them: ₹2.5L, ₹8L, ₹12L, ₹1.2Cr."""
    if value <= 0:
        return 0
    step = 10_000 if value < 200_000 else 50_000 if value < 2_000_000 else 500_000
    return int(math.ceil(value / step) * step)


def budget_options(event_type: dict[str, Any] | None, city: str | None, attendees: int | None) -> list[dict[str, Any]]:
    band = cost_band(event_type, city)
    if not band:
        return [{"value": str(v), "label": label, "hint": ""} for v, label in [(250000, "₹2.5L"), (500000, "₹5L"), (1000000, "₹10L"), (1500000, "₹15L")]]
    guests = attendees or event_type["guest_options"][1]
    place = f" in {city}" if city else ""
    options = []
    for name, per_guest in zip(("Lean", "Typical", "Premium"), band):
        total = nice_round(per_guest * guests)
        options.append({"value": str(total), "label": format_lakh(total), "hint": f"{name} · about {inr(per_guest)}/guest for a {event_type['label'].lower()}{place}"})
    return options


def format_lakh(value: int) -> str:
    if value >= 10_000_000:
        return f"₹{value / 10_000_000:g}Cr"
    if value >= 100_000:
        return f"₹{value / 100_000:g}L"
    return f"₹{value:,}"


def guest_options(event_type: dict[str, Any] | None) -> list[dict[str, Any]]:
    counts = event_type["guest_options"] if event_type else [50, 100, 200, 350]
    label = event_type["label"].lower() if event_type else "event"
    return [{"value": str(c), "label": str(c), "hint": f"Typical for a {label}" if i == 1 else ""} for i, c in enumerate(counts)]


def date_options(event_type: dict[str, Any] | None, today: date | None = None) -> list[dict[str, Any]]:
    """Three Saturdays after the usual lead time for this event type."""
    today = today or date.today()
    lead = event_type["lead_weeks"] if event_type else 6
    start = today + timedelta(weeks=lead)
    first_saturday = start + timedelta(days=(5 - start.weekday()) % 7)
    options = []
    for weeks in (0, 2, 4):
        day = first_saturday + timedelta(weeks=weeks)
        options.append({"value": day.isoformat(), "label": day.strftime("Sat %d %b %Y").replace(" 0", " "), "hint": f"{(day - today).days // 7} weeks away"})
    return options


def objective_options(event_type: dict[str, Any] | None) -> list[dict[str, Any]]:
    objectives = event_type["objectives"] if event_type else ["Smooth operations and a great guest experience", "Engage attendees with a clear programme", "Stay within budget without cutting corners"]
    return [{"value": text, "label": text, "hint": ""} for text in objectives]


def location_options(event_type: dict[str, Any] | None) -> list[dict[str, Any]]:
    cities = known_cities()
    destination = _data()["city_tiers"]["destination"]
    if event_type and event_type["id"] in {"wedding", "offsite"}:
        cities = destination + [c for c in cities if c not in destination]
    return [{"value": c, "label": c, "hint": "Destination" if c in destination else ""} for c in cities[:6]]


def budget_check(event_type: dict[str, Any] | None, city: str | None, attendees: int | None, budget: int | None) -> dict[str, Any] | None:
    """A warning with quick fixes when the budget per guest is below the lean band."""
    band = cost_band(event_type, city)
    if not band or not attendees or not budget:
        return None
    low, typical, _ = band
    per_guest = budget / attendees
    if per_guest >= low * 0.9:
        return None
    place = f" in {city}" if city else ""
    raise_to = nice_round(low * attendees)
    fewer = max(10, int(budget // low // 10 * 10))
    return {
        "id": "budget_low",
        "message": f"{inr(budget)} for {attendees} guests is about {inr(per_guest)} a head. A {event_type['label'].lower()}{place} usually needs at least {inr(low)} a head (typical {inr(typical)}).",
        "options": [
            {"label": f"Raise budget to {format_lakh(raise_to)}", "patch": {"budget": str(raise_to)}},
            {"label": f"Plan for {fewer} guests", "patch": {"attendees": str(fewer)}},
        ],
    }


def lead_time_check(event_type: dict[str, Any] | None, event_date: date | None, today: date | None = None) -> dict[str, Any] | None:
    if not event_type or not event_date:
        return None
    today = today or date.today()
    weeks = (event_date - today).days / 7
    if weeks >= event_type["lead_weeks"] * 0.5:
        return None
    later = date_options(event_type, today)[0]
    return {
        "id": "lead_time_short",
        "message": f"That's about {max(0, int(weeks))} weeks away. A {event_type['label'].lower()} usually needs around {event_type['lead_weeks']} weeks to plan, so venues and vendors may be limited.",
        "options": [{"label": f"Move to {later['label']}", "patch": {"date": later["value"]}}],
    }


def type_tokens(event_type: dict[str, Any] | None) -> set[str]:
    return set(tokenize(event_type["keywords"])) if event_type else set()
