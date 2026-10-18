"""Hybrid venue search over the venue catalog.

1. Hard filters: the city (aliases like Bombay, Gurgaon or Navi Mumbai resolve to
   a catalog city), capacity ≥ guests, rent ≤ venue budget.
2. Ranking, fused with reciprocal rank fusion:
   - BM25 on the request words (venue type, preferences, area): exact matches
     for names like "Koramangala" or features like "parking";
   - semantic similarity on the same words (when an embedding deployment is set):
     "somewhere by the sea" finds "beachfront";
   - area match: venues in the area the user named come first;
   - value: cheaper venues break ties.
3. When nothing fits, `near_misses` explains why (over budget, too small, city not
   in the catalog), so the recovery assistant can offer concrete fixes.
"""

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.search import semantic
from app.search.benchmarks import known_cities, resolve_city
from app.search.bm25 import BM25, tokenize
from app.search.hybrid import rrf

DATA = Path(__file__).resolve().parents[1] / "data" / "venues.json"


@lru_cache
def catalog() -> list[dict[str, Any]]:
    return json.loads(DATA.read_text(encoding="utf-8"))["venues"]


def _document(venue: dict[str, Any]) -> str:
    return f"{venue['name']}. {venue['type']} in {venue['area']}, {venue['city']}. {', '.join(venue['features'])}. {venue['description']}"


@lru_cache
def _documents() -> tuple[str, ...]:
    return tuple(_document(venue) for venue in catalog())


@lru_cache
def _index() -> BM25:
    return BM25(list(_documents()))


def _area_terms(location: str, city: str | None) -> set[str]:
    city_words = set(tokenize(city or ""))
    return {term for term in tokenize(location) if term not in city_words and len(term) > 2}


def search(location: str, attendees: int, total_budget_inr: int, venue_type: str = "", preferences: str = "", top_k: int = 3) -> dict[str, Any]:
    venues = catalog()
    limit = round(total_budget_inr * 0.3)
    city = resolve_city(location)
    area_terms = _area_terms(location, city)

    if city:
        in_city = [i for i, v in enumerate(venues) if v["city"] == city]
    else:  # not a known city: try matching an area name directly
        in_city = [i for i, v in enumerate(venues) if area_terms & set(tokenize(f"{v['area']} {v['city']}"))]
        city = venues[in_city[0]]["city"] if in_city else None

    fits = [i for i in in_city if venues[i]["capacity"] >= attendees and venues[i]["rental_inr"] <= limit]
    query = " ".join(part for part in (venue_type, preferences, " ".join(sorted(area_terms))) if part).strip()

    rankings: list[list[int]] = []
    keyword = _index().rank(query, fits) if query else []
    rankings.append(keyword)
    meaning = semantic.rank(query, list(_documents()), fits, min_similarity=0.2) if query else ([] if semantic.enabled() else None)
    mode = "hybrid" if meaning is not None else "bm25"
    if meaning:
        rankings.append(meaning)
    area_first = [i for i in fits if area_terms & set(tokenize(venues[i]["area"]))]
    rankings.append(area_first)
    rankings.append(sorted(fits, key=lambda i: venues[i]["rental_inr"]))
    fused = rrf(rankings, weights=[1.0, 1.0, 1.5, 0.5][: len(rankings)] if meaning else [1.0, 1.5, 0.5])

    recommendations = []
    for index, score in fused[:top_k]:
        venue = venues[index]
        reasons = []
        if index in area_first:
            reasons.append(f"in {venue['area']}")
        if index in keyword[:3]:
            reasons.append("matches your keywords")
        if meaning and index in meaning[:3]:
            reasons.append("close to what you described")
        recommendations.append({
            "name": venue["name"], "location": venue["location"], "city": venue["city"], "area": venue["area"], "type": venue["type"],
            "capacity": venue["capacity"], "rental_inr": venue["rental_inr"], "features": venue["features"], "description": venue["description"],
            "match_reasons": reasons or ["fits guests and budget"], "score": round(score, 4),
        })

    result: dict[str, Any] = {
        "location": location, "attendees": attendees, "venue_budget_limit_inr": limit, "recommendations": recommendations,
        "search": {"mode": mode, "city": city, "query": query, "candidates_in_city": len(in_city), "fits": len(fits)},
        "note": "Sample catalogue for demos. Confirm availability and quotations before booking.",
    }
    if not recommendations:
        result["near_misses"] = near_misses(in_city, attendees, total_budget_inr, city)
    return result


def near_misses(in_city: list[int], attendees: int, total_budget_inr: int, city: str | None) -> dict[str, Any]:
    venues = catalog()
    if not in_city:
        return {"reason": "city_not_in_catalog", "known_cities": known_cities()}
    big_enough = sorted((venues[i] for i in in_city if venues[i]["capacity"] >= attendees), key=lambda v: v["rental_inr"])
    if big_enough:
        cheapest = big_enough[0]
        share = min(100, math.ceil(cheapest["rental_inr"] / max(total_budget_inr, 1) * 100))
        return {"reason": "over_budget", "city": city, "cheapest_fit": {"name": cheapest["name"], "area": cheapest["area"], "capacity": cheapest["capacity"], "rental_inr": cheapest["rental_inr"]}, "venue_share_needed_pct": share}
    largest = max((venues[i] for i in in_city), key=lambda v: v["capacity"])
    return {"reason": "too_small", "city": city, "largest": {"name": largest["name"], "area": largest["area"], "capacity": largest["capacity"], "rental_inr": largest["rental_inr"]}}
