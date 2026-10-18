"""Weather risk for the event day, from Open-Meteo (free, no key).

- Event within 15 days: the daily forecast for that date.
- Further out: what the same week was like in each of the last five years
  (historical archive), as a share of wet days, typical high and peak wind.
- Service unreachable: rule-of-thumb climate notes for the city and month.
"""

from datetime import date, timedelta
from typing import Any

from app.integrations.geo import local_point, places
from app.integrations.http import ServiceUnavailable, get_json

FORECAST = "https://api.open-meteo.com/v1/forecast"
ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
ATTRIBUTION = "Weather data by Open-Meteo.com (CC BY 4.0)"
DAILY = "precipitation_sum,temperature_2m_max,temperature_2m_min,wind_speed_10m_max"
WET_DAY_MM = 2.5
FORECAST_DAYS = 15
HISTORY_YEARS = 5
WINDOW_DAYS = 3
ORDER = {"Low": 0, "Medium": 1, "High": 2}


def _worst(*levels: str) -> str:
    return max(levels, key=lambda level: ORDER.get(level, 0))


def _same_day(day: date, year: int) -> date:
    try:
        return day.replace(year=year)
    except ValueError:  # 29 February
        return day.replace(year=year, day=28)


def climate_notes(city: str | None, month: int) -> list[dict[str, Any]]:
    return [note for note in (places().get(city or "") or {}).get("climate", []) if month in note["months"]]


async def _point(location: str) -> dict[str, Any] | None:
    point = local_point(location)
    if point:
        return point
    try:  # a city that isn't in the bundled list
        payload = await get_json(GEOCODE, {"name": location.split(",")[0].strip(), "count": 1, "country_code": "IN", "language": "en", "format": "json"}, ttl_s=30 * 86_400)
        top = (payload.get("results") or [None])[0]
        if top:
            return {"lat": top["latitude"], "lon": top["longitude"], "label": top.get("name", location), "city": None, "precision": "city", "source": "Open-Meteo geocoding"}
    except (ServiceUnavailable, KeyError, TypeError, AttributeError):
        pass
    return None


def _heat_risk(t_max: float | None) -> str:
    if t_max is None:
        return "Low"
    return "High" if t_max >= 40 else "Medium" if t_max >= 36 else "Low"


async def _forecast(point: dict[str, Any], day: date) -> dict[str, Any]:
    payload = await get_json(FORECAST, {"latitude": point["lat"], "longitude": point["lon"], "daily": DAILY + ",precipitation_probability_max", "start_date": day.isoformat(), "end_date": day.isoformat(), "timezone": "Asia/Kolkata"}, ttl_s=3 * 3600)
    daily = payload["daily"]
    rain = daily["precipitation_sum"][0] or 0
    chance = daily.get("precipitation_probability_max", [None])[0]
    t_max = daily["temperature_2m_max"][0]
    wind = daily["wind_speed_10m_max"][0] or 0
    rain_risk = "High" if (chance or 0) >= 60 or rain >= 10 else "Medium" if (chance or 0) >= 30 or rain >= WET_DAY_MM else "Low"
    wind_risk = "High" if wind >= 50 else "Medium" if wind >= 35 else "Low"
    chance_text = f"{chance}% chance of rain" if chance is not None else f"{rain:g} mm of rain forecast"
    return {
        "basis": "forecast",
        "risk": _worst(rain_risk, wind_risk, _heat_risk(t_max)),
        "metrics": {"rain_chance_pct": chance, "rain_mm": rain, "high_c": t_max, "low_c": daily["temperature_2m_min"][0], "wind_kmh": wind},
        "summary": f"Forecast for {day.day} {day:%b}: {chance_text}, high of {t_max:g} °C, wind up to {wind:g} km/h",
    }


async def _history(point: dict[str, Any], day: date, today: date) -> dict[str, Any]:
    latest = today - timedelta(days=6)  # the archive lags by about five days
    years = [y for y in range(day.year - 1, day.year - 1 - 12, -1) if _same_day(day, y) + timedelta(days=WINDOW_DAYS) <= latest][:HISTORY_YEARS]
    if not years:
        raise ServiceUnavailable("no past years to compare with")
    windows = [(_same_day(day, y) - timedelta(days=WINDOW_DAYS), _same_day(day, y) + timedelta(days=WINDOW_DAYS)) for y in years]
    payload = await get_json(ARCHIVE, {"latitude": point["lat"], "longitude": point["lon"], "daily": DAILY, "start_date": min(w[0] for w in windows).isoformat(), "end_date": max(w[1] for w in windows).isoformat(), "timezone": "Asia/Kolkata"}, ttl_s=30 * 86_400)
    daily = payload["daily"]
    rows = []
    for index, label in enumerate(daily["time"]):
        current = date.fromisoformat(label)
        if any(start <= current <= end for start, end in windows):
            rows.append((daily["precipitation_sum"][index], daily["temperature_2m_max"][index], daily["wind_speed_10m_max"][index]))
    rows = [row for row in rows if row[0] is not None]
    if not rows:
        raise ServiceUnavailable("the archive returned no days for that week")
    wet_share = sum(1 for rain, _, _ in rows if rain >= WET_DAY_MM) / len(rows)
    highs = [high for _, high, _ in rows if high is not None]
    typical_high = round(sum(highs) / len(highs), 1) if highs else None
    peak_wind = max((wind or 0) for _, _, wind in rows)
    rain_risk = "High" if wet_share >= 0.5 else "Medium" if wet_share >= 0.2 else "Low"
    return {
        "basis": f"same week in {min(years)}–{max(years)}",
        "risk": _worst(rain_risk, _heat_risk(typical_high)),
        "metrics": {"wet_day_share_pct": round(wet_share * 100), "typical_high_c": typical_high, "peak_wind_kmh": peak_wind, "days_compared": len(rows)},
        "summary": f"In the same week over the last {len(years)} years it rained on {round(wet_share * 100)}% of days; typical high {typical_high:g} °C" if typical_high is not None else f"In the same week over the last {len(years)} years it rained on {round(wet_share * 100)}% of days",
    }


async def weather_outlook(location: str, event_date: str, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    try:
        day = date.fromisoformat(str(event_date)[:10])
    except ValueError:
        return {"location": location, "event_date": event_date, "risk": "Low", "basis": "none", "summary": f"'{event_date}' isn't a date (use YYYY-MM-DD)", "advice": ""}
    point = await _point(location)
    notes = climate_notes(point.get("city") if point else None, day.month)
    result: dict[str, Any] = {"location": location, "place": point["label"] if point else None, "event_date": day.isoformat(), "climate_notes": [n["note"] for n in notes]}
    live_error = ""
    if point:
        try:
            ahead = (day - today).days
            outlook = await (_forecast(point, day) if 0 <= ahead <= FORECAST_DAYS else _history(point, day, today))
            result.update(outlook, sources=[ATTRIBUTION])
        except (ServiceUnavailable, KeyError, IndexError, TypeError) as error:
            live_error = str(error)
    if "basis" not in result:
        risk = _worst("Low", *(n["risk"] for n in notes))
        result.update(
            basis="climate notes",
            risk=risk,
            metrics={},
            summary=(notes[0]["note"] if notes else f"No climate notes for {location} in {day:%B}"),
            sources=["EventPilot climate notes (rule of thumb)"],
            note=("Live weather unavailable: " + live_error) if live_error else ("Live weather unavailable" if point else f"Couldn't place {location}"),
        )
    result["advice"] = {
        "High": "Book a covered or indoor fallback now and confirm the vendor's rain plan.",
        "Medium": "Keep a covered fallback on hold and recheck the 15-day forecast.",
        "Low": "No weather action needed; recheck the forecast in the final two weeks.",
    }[result["risk"]]
    return result
