"""Places, distances and travel times.

Coordinates come from OpenStreetMap Nominatim when it is reachable, otherwise
from app/data/places.json (city centres, catalogue areas and transport hubs).
Road distance and time come from the OSRM demo server, otherwise from a
straight-line estimate with a road factor. Every answer says which it used.
"""

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.integrations.http import ServiceUnavailable, get_json
from app.search.benchmarks import resolve_city

DATA = Path(__file__).resolve().parents[1] / "data" / "places.json"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
OSRM = "https://router.project-osrm.org/route/v1/driving/{a_lon},{a_lat};{b_lon},{b_lat}"
OSM_ATTRIBUTION = "Map data © OpenStreetMap contributors (ODbL)"

ROAD_FACTOR = 1.35  # roads are longer than a straight line
CITY_SPEED_KMH = 25  # typical Indian metro traffic, door to door


@lru_cache
def places() -> dict[str, Any]:
    return json.loads(DATA.read_text(encoding="utf-8"))["cities"]


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def local_point(location: str) -> dict[str, Any] | None:
    """Best known point for a location from the bundled data (area first, then city)."""
    city = resolve_city(location)
    if not city or city not in places():
        return None
    info = places()[city]
    lowered = location.lower()
    for area, (lat, lon) in sorted(info["areas"].items(), key=lambda item: -len(item[0])):
        if area.lower() in lowered:
            return {"lat": lat, "lon": lon, "label": f"{area}, {city}", "city": city, "precision": "area", "source": "EventPilot place list (approximate)"}
    return {"lat": info["lat"], "lon": info["lon"], "label": city, "city": city, "precision": "city", "source": "EventPilot place list (approximate)"}


def nearest_city(point: tuple[float, float]) -> str | None:
    best = min(places().items(), key=lambda item: haversine_km(point, (item[1]["lat"], item[1]["lon"])), default=None)
    if best and haversine_km(point, (best[1]["lat"], best[1]["lon"])) <= 80:
        return best[0]
    return None


async def geocode(location: str) -> dict[str, Any] | None:
    """Coordinates for a venue or area. Live OpenStreetMap first, bundled list second."""
    try:
        results = await get_json(NOMINATIM, {"q": f"{location}, India", "format": "jsonv2", "limit": 1, "countrycodes": "in"}, ttl_s=30 * 86_400)
        if results:
            top = results[0]
            lat, lon = float(top["lat"]), float(top["lon"])
            return {"lat": lat, "lon": lon, "label": str(top.get("display_name", location))[:160], "city": resolve_city(location) or nearest_city((lat, lon)), "precision": "address", "source": "OpenStreetMap Nominatim"}
    except (ServiceUnavailable, KeyError, ValueError, TypeError):
        pass
    return local_point(location)


async def drive(a: tuple[float, float], b: tuple[float, float]) -> dict[str, Any]:
    """Road distance (km) and time (minutes) from a to b."""
    try:
        url = OSRM.format(a_lat=a[0], a_lon=a[1], b_lat=b[0], b_lon=b[1])
        payload = await get_json(url, {"overview": "false"}, ttl_s=7 * 86_400)
        route = (payload.get("routes") or [None])[0]
        if payload.get("code") == "Ok" and route:
            return {"km": round(route["distance"] / 1000, 1), "minutes": max(1, round(route["duration"] / 60)), "method": "OSRM road route (no live traffic)"}
    except (ServiceUnavailable, KeyError, TypeError, AttributeError):
        pass
    km = haversine_km(a, b) * ROAD_FACTOR
    return {"km": round(km, 1), "minutes": max(5, round(km / CITY_SPEED_KMH * 60)), "method": "estimate (straight line × 1.35 at 25 km/h)"}


async def travel_access(location: str) -> dict[str, Any]:
    """How far a venue is from the city's airport(s) and main railway station."""
    point = await geocode(location)
    if not point:
        return {"location": location, "found": False, "hubs": [], "summary": f"Couldn't place {location} on the map; add the city name."}
    city = point.get("city")
    hubs = []
    for hub in (places().get(city) or {}).get("hubs", []):
        leg = await drive((point["lat"], point["lon"]), (hub["lat"], hub["lon"]))
        hubs.append({"name": hub["name"], "kind": hub["kind"], **leg})
    hubs.sort(key=lambda h: h["minutes"])
    airport = next((h for h in hubs if h["kind"] == "airport"), None)
    summary = f"{point['label']} is about {airport['km']:g} km ({airport['minutes']} min by road) from {airport['name']}" if airport else f"No airport data for {point['label']}"
    sources = {point["source"]} | ({OSM_ATTRIBUTION} if point["source"].startswith("OpenStreetMap") or any(h["method"].startswith("OSRM") for h in hubs) else set())
    return {
        "location": location,
        "found": True,
        "place": point["label"],
        "city": city,
        "precision": point["precision"],
        "coordinates": {"lat": round(point["lat"], 5), "lon": round(point["lon"], 5)},
        "hubs": hubs,
        "summary": summary,
        "sources": sorted(sources),
    }
