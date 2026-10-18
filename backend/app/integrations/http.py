"""HTTP for the free, no-key web services EventPilot uses.

- Open-Meteo (weather forecast, historical archive, place search): free for
  non-commercial use, no key, data under CC BY 4.0.
- OpenStreetMap Nominatim (geocoding): free, at most 1 request per second, and
  it asks for an identifying User-Agent.
- OSRM public demo server (road distance and time): free for light use.

Every response is cached in memory and on disk (data/http-cache.json) so a
replayed run or a retry does not call the service again. Calls to the same host
are serialised and spaced to respect each service's rate limit. Any failure
raises `ServiceUnavailable`, and every tool has an offline fallback.
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings

# Tests replace this with httpx.MockTransport.
TRANSPORT: httpx.AsyncBaseTransport | None = None

MIN_INTERVAL_S = {"nominatim.openstreetmap.org": 1.1, "router.project-osrm.org": 0.5}
MAX_CACHE_ENTRIES = 1000

_locks: dict[tuple[int, str], asyncio.Lock] = {}
_last_call: dict[str, float] = {}
_memory: dict[str, tuple[float, Any]] | None = None


class ServiceUnavailable(RuntimeError):
    """A free web service could not be reached or returned an unusable answer."""


def online() -> bool:
    return settings.free_apis_enabled


def _cache_file() -> Path:
    return Path(settings.data_dir) / "http-cache.json"


def _load() -> dict[str, tuple[float, Any]]:
    global _memory
    if _memory is None:
        try:
            raw = json.loads(_cache_file().read_text(encoding="utf-8"))
            _memory = {key: (float(value[0]), value[1]) for key, value in raw.items()}
        except (OSError, ValueError, TypeError, IndexError):
            _memory = {}
    return _memory


def _save() -> None:
    cache = _load()
    if len(cache) > MAX_CACHE_ENTRIES:
        for key in sorted(cache, key=lambda k: cache[k][0])[: len(cache) - MAX_CACHE_ENTRIES]:
            cache.pop(key, None)
    try:
        path = _cache_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cache), encoding="utf-8")
    except OSError:
        pass  # the cache is an optimisation, never a requirement


def clear_cache() -> None:
    global _memory
    _memory = {}
    _last_call.clear()


def _lock(host: str) -> asyncio.Lock:
    key = (id(asyncio.get_running_loop()), host)
    if key not in _locks:
        _locks[key] = asyncio.Lock()
    return _locks[key]


def user_agent() -> str:
    contact = f"; {settings.http_contact}" if settings.http_contact else ""
    return f"EventPilot/0.2 (event-planning course project{contact})"


async def get_json(url: str, params: dict[str, Any], *, ttl_s: int = 86_400) -> Any:
    if not online():
        raise ServiceUnavailable("free web services are switched off (FREE_APIS_ENABLED=false)")
    key = url + "?" + json.dumps(params, sort_keys=True, default=str)
    cached = _load().get(key)
    if cached and cached[0] > time.time():
        return cached[1]

    host = httpx.URL(url).host
    async with _lock(host):
        wait = MIN_INTERVAL_S.get(host, 0) - (time.monotonic() - _last_call.get(host, 0))
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            async with httpx.AsyncClient(timeout=settings.http_timeout_s, transport=TRANSPORT, headers={"User-Agent": user_agent()}) as client:
                response = await client.get(url, params=params)
        except httpx.HTTPError as error:
            raise ServiceUnavailable(f"{host} could not be reached ({error.__class__.__name__})") from error
        finally:
            _last_call[host] = time.monotonic()

    if response.status_code != 200:
        raise ServiceUnavailable(f"{host} returned HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError as error:
        raise ServiceUnavailable(f"{host} returned something that isn't JSON") from error
    _load()[key] = (time.time() + ttl_s, payload)
    _save()
    return payload
