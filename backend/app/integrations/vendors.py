"""Custom vendor catalogue search (app/data/vendors.json, sample data).

Filters by city, category and the budget line (per-plate catering is priced for
the guest count), then ranks by BM25 on the event type and preferences, how
well the vendor suits the event type, and value. Works offline.
"""

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.search.benchmarks import resolve_city
from app.search.bm25 import BM25
from app.search.hybrid import rrf

DATA = Path(__file__).resolve().parents[1] / "data" / "vendors.json"

CATEGORY_WORDS = [
    ("catering", r"cater|food|f&b|beverage|dinner|lunch|meal|buffet"),
    ("decor", r"decor|flower|floral|mandap|stage design|lighting decor"),
    ("photography", r"photo|video|film|camera"),
    ("av_production", r"\bav\b|audio.?visual|projector|stream|venue and av"),
    ("sound_light", r"sound|light|\bpa\b|led wall"),
    ("entertainment", r"music|band|\bdj\b|entertain|performer|programme"),
    ("mehendi", r"mehendi|mehndi|henna"),
]


@lru_cache
def catalog() -> dict[str, Any]:
    return json.loads(DATA.read_text(encoding="utf-8"))


def categories() -> list[str]:
    return list(catalog()["categories"])


def normalise_category(text: str) -> str | None:
    lowered = (text or "").lower().strip()
    if lowered in categories():
        return lowered
    for name, pattern in CATEGORY_WORDS:
        if re.search(pattern, lowered):
            return name
    return None


def _document(vendor: dict[str, Any]) -> str:
    return f"{vendor['name']}. {vendor['tier']} {vendor['category']}. Suits {', '.join(vendor['suits'])}. {', '.join(vendor['features'])}. {vendor['description']}"


def estimated_cost(vendor: dict[str, Any], guests: int) -> int:
    if "per_plate_inr" in vendor:
        return vendor["per_plate_inr"] * max(guests, vendor.get("min_guests", 0))
    return vendor["package_inr"]


def search_vendors(city: str, category: str, budget_inr: int, guests: int = 0, event_type: str = "", preferences: str = "", top_k: int = 3) -> dict[str, Any]:
    canonical = resolve_city(city or "")
    kind = normalise_category(category)
    base = {"city": canonical or city, "category": kind or category, "budget_inr": int(budget_inr), "guests": int(guests), "note": catalog()["_note"]}
    if not kind:
        return {**base, "matches": [], "reason": "unknown_category", "summary": f"'{category}' isn't a vendor category; use one of {', '.join(categories())}"}
    if not canonical:
        return {**base, "matches": [], "reason": "city_not_in_catalog", "summary": f"No vendors listed for {city} yet"}

    pool = [v for v in catalog()["vendors"] if v["city"] == canonical and v["category"] == kind]
    fits = [v for v in pool if estimated_cost(v, guests) <= budget_inr]
    if not fits:
        cheapest = min(pool, key=lambda v: estimated_cost(v, guests), default=None)
        near = {"name": cheapest["name"], "estimated_inr": estimated_cost(cheapest, guests)} if cheapest else None
        return {**base, "matches": [], "reason": "over_budget", "cheapest": near, "summary": f"No {kind.replace('_', ' ')} vendor in {canonical} fits the budget line"}

    query = f"{event_type} {preferences}".strip()
    docs = [_document(v) for v in fits]
    keyword = BM25(docs).rank(query) if query else list(range(len(fits)))
    suits = sorted(range(len(fits)), key=lambda i: -sum(1 for word in re.findall(r"[a-z]+", event_type.lower()) if any(word in s for s in fits[i]["suits"])))
    # Best use of the line: the most capable vendor that still fits (higher tiers first), then value.
    tier_order = {"premium": 0, "standard": 1, "value": 2}
    capability = sorted(range(len(fits)), key=lambda i: (tier_order.get(fits[i]["tier"], 3), estimated_cost(fits[i], guests)))
    ranked = [index for index, _ in rrf([keyword, suits, capability], weights=[1.0, 1.0, 0.8])]
    matches = []
    for index in ranked[:top_k]:
        vendor = fits[index]
        match = {"id": vendor["id"], "name": vendor["name"], "tier": vendor["tier"], "estimated_inr": estimated_cost(vendor, guests), "features": vendor["features"], "description": vendor["description"]}
        if "per_plate_inr" in vendor:
            match["per_plate_inr"] = vendor["per_plate_inr"]
        matches.append(match)
    return {**base, "matches": matches, "summary": f"{len(matches)} {kind.replace('_', ' ')} vendor(s) in {canonical} fit the line"}
