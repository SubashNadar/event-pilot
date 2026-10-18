"""MCP client used by the EventPilot specialist agents.

Every call streams two `tool_call` events (running, then success or error) so
the step drawer can show inputs, a result summary and latency. If the MCP server
is not reachable, the same read-only tool function runs in-process and the
result says so, which keeps local demos working when only the API is started.

Guardrails on every call:
- each agent may only call the tools on its allowlist (TOOLS_BY_STEP);
- a run may make at most MAX_TOOL_CALLS_PER_RUN tool calls;
- each call has a timeout;
- identical calls within TOOL_CACHE_TTL_S reuse the earlier result;
- results are treated as data: long strings are cut and control characters
  removed before any agent or prompt sees them.
"""

import asyncio
import inspect
import json
import re
import time
from collections import defaultdict
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from app.agents.fmt import inr
from app.core.config import settings
from app.graphs.emit import current_run_id, emit
from app.mcp import tools as local_tools

MCP_URL = settings.mcp_url

_LOCAL = {
    "venue_search": lambda a: local_tools.search_venues(a["location"], a["attendees"], a["total_budget_inr"], a.get("venue_type", ""), a.get("preferences", "")),
    "budget_validation": lambda a: local_tools.validate_budget(a["budget_lines"], a["total_budget_inr"]),
    "schedule_conflict_check": lambda a: local_tools.check_schedule_conflicts(a["agenda"]),
    "event_requirements": lambda a: local_tools.get_event_requirements(a["event_type"], a["attendees"]),
    "marketing_readiness": lambda a: local_tools.assess_marketing(a["event_type"], a["attendees"], a["event_date"]),
    "operational_risk_assessment": lambda a: local_tools.assess_operational_risks(a["event_type"], a["attendees"], a["location"]),
    "vendor_search": lambda a: local_tools.vendor_search(a["city"], a["category"], a["budget_inr"], a.get("guests", 0), a.get("event_type", ""), a.get("preferences", "")),
    "holiday_check": lambda a: local_tools.holiday_check(a["event_date"], a.get("location", ""), a.get("window_days", 3)),
    "guest_message_draft": lambda a: local_tools.guest_message_draft(a["kind"], a["event_name"], a["event_date"], a["location"], a.get("venue", ""), a.get("start_time", ""), a.get("host", ""), a.get("rsvp_by", ""), a.get("event_type", "")),
    "weather_outlook": lambda a: local_tools.weather_outlook(a["location"], a["event_date"]),
    "travel_access": lambda a: local_tools.travel_access(a["location"]),
}

# Which tools each agent may call. A step not listed here (e.g. a script) may call any tool.
TOOLS_BY_STEP: dict[str, set[str]] = {
    "logistics_agent": {"venue_search", "travel_access"},
    "finance_agent": {"budget_validation", "vendor_search"},
    "schedule_agent": {"schedule_conflict_check", "holiday_check"},
    "requirements_agent": {"event_requirements"},
    "marketing_agent": {"marketing_readiness", "guest_message_draft"},
    "risk_operations_agent": {"operational_risk_assessment", "weather_outlook"},
}

MAX_STRING = 1200
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

_failed_once: set[tuple[str, str]] = set()
_calls_per_run: dict[str, int] = defaultdict(int)
_result_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def as_data(value: Any) -> Any:
    """Tool output is data, never instructions: trim it and strip control characters."""
    if isinstance(value, str):
        cleaned = _CONTROL.sub("", value)
        return cleaned if len(cleaned) <= MAX_STRING else cleaned[:MAX_STRING] + "…"
    if isinstance(value, list):
        return [as_data(item) for item in value[:100]]
    if isinstance(value, dict):
        return {str(key)[:80]: as_data(item) for key, item in list(value.items())[:100]}
    return value


def _cache_key(name: str, arguments: dict[str, Any]) -> str:
    return name + ":" + json.dumps(arguments, sort_keys=True, default=str)


def reset_guardrails() -> None:
    _calls_per_run.clear()
    _result_cache.clear()


class ToolCallError(RuntimeError):
    """A planning tool failed. The step pauses and offers recovery options."""


def summarize_result(name: str, payload: dict[str, Any]) -> str:
    if name == "venue_search":
        recs = payload.get("recommendations", [])
        if not recs:
            return f"No catalog venue fits within {inr(payload.get('venue_budget_limit_inr', 0))}"
        mode = (payload.get("search") or {}).get("mode", "")
        return f"{len(recs)} venue(s): " + ", ".join(r["name"] for r in recs) + (f" · {mode} search" if mode else "")
    if name == "budget_validation":
        return f"{inr(payload.get('allocated_inr', 0))} allocated · " + ("within budget" if payload.get("within_budget") else "over budget")
    if name == "schedule_conflict_check":
        conflicts = payload.get("conflicts", [])
        return "No conflicts" if not conflicts else f"{len(conflicts)} conflict(s): {conflicts[0]}"
    if name == "event_requirements":
        return f"{len(payload.get('requirements', []))} requirements"
    if name == "marketing_readiness":
        return f"{len(payload.get('recommended_channels', []))} channels · {payload.get('status', '')}"
    if name == "operational_risk_assessment":
        return f"{len(payload.get('risks', []))} risks identified"
    if name in ("weather_outlook", "holiday_check"):
        return f"{payload.get('risk', '?')} risk · {payload.get('summary', '')}"
    if name == "travel_access":
        return payload.get("summary", "Done")
    if name == "vendor_search":
        matches = payload.get("matches", [])
        return (f"{len(matches)} vendor(s): " + ", ".join(m["name"] for m in matches)) if matches else payload.get("summary", "No vendors")
    if name == "guest_message_draft":
        failing = [c["check"] for c in payload.get("checks", []) if not c["passed"]]
        return f"{payload.get('kind', 'message')} drafted, {payload.get('characters', 0)} characters" + (f" · check: {', '.join(failing)}" if failing else "")
    return "Done"


async def _call_mcp(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    async with streamablehttp_client(MCP_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments)
    if result.isError or not result.content:
        raise ToolCallError(f"MCP tool {name} did not return a usable result")
    return json.loads(result.content[0].text)


def _observation(name: str, arguments: dict[str, Any]):
    if not settings.langfuse_enabled:
        return None
    try:
        from langfuse import get_client

        return get_client().start_as_current_observation(
            as_type="tool", name=f"mcp.{name}", input=arguments, metadata={"mcp_server": "eventpilot", "mcp_url": MCP_URL}
        )
    except Exception:
        return None


async def call_planning_tool(name: str, arguments: dict[str, Any], *, step_id: str | None = None, call_id: str | None = None) -> dict[str, Any]:
    call_id = call_id or f"{name}-{int(time.time() * 1000)}"
    if step_id:
        emit({"type": "tool_call", "stepId": step_id, "tool": {"id": call_id, "name": name, "input": arguments, "resultSummary": "Running…", "latencyMs": 0, "status": "running"}}, dedupe=f"tool:{call_id}:running")
    started = time.perf_counter()
    observation = _observation(name, arguments)
    context = observation.__enter__() if observation else None
    try:
        run_id = current_run_id() or "no-run"
        if name not in _LOCAL:
            raise ToolCallError(f"{name} is not an EventPilot tool")
        allowed = TOOLS_BY_STEP.get(step_id or "")
        if allowed is not None and name not in allowed:
            raise ToolCallError(f"{step_id} is not allowed to call {name}")
        _calls_per_run[run_id] += 1
        if run_id != "no-run" and _calls_per_run[run_id] > settings.max_tool_calls_per_run:
            raise ToolCallError(f"This run reached its limit of {settings.max_tool_calls_per_run} tool calls")
        if name in settings.fail_once_tools and (run_id, name) not in _failed_once:
            _failed_once.add((run_id, name))
            raise ToolCallError(f"{name} timed out after 8.0 s (provider returned 504). Simulated by EVENTPILOT_FAIL_ONCE.")
        key = _cache_key(name, arguments)
        cached = _result_cache.get(key)
        if cached and cached[0] > time.time():
            payload, via = cached[1], " (cached)"
        else:
            try:
                payload = await asyncio.wait_for(_call_mcp(name, arguments), timeout=settings.tool_timeout_s)
                via = ""
            except ToolCallError:
                raise
            except asyncio.TimeoutError as error:
                raise ToolCallError(f"{name} timed out after {settings.tool_timeout_s:g} s") from error
            except Exception:
                # MCP server not running: same read-only logic, in-process.
                payload = _LOCAL[name](arguments)
                if inspect.isawaitable(payload):
                    payload = await asyncio.wait_for(payload, timeout=settings.tool_timeout_s)
                via = " (local tools; MCP server not reachable)"
            payload = as_data(payload)
            _result_cache[key] = (time.time() + settings.tool_cache_ttl_s, payload)
        latency = int((time.perf_counter() - started) * 1000)
        if context:
            context.update(output=payload)
        if step_id:
            emit({"type": "tool_call", "stepId": step_id, "tool": {"id": call_id, "name": name, "input": arguments, "resultSummary": summarize_result(name, payload) + via, "latencyMs": latency, "status": "success"}}, dedupe=f"tool:{call_id}:done")
        return payload
    except Exception as error:
        latency = int((time.perf_counter() - started) * 1000)
        if context:
            context.update(level="ERROR", status_message=str(error))
        if step_id:
            emit({"type": "tool_call", "stepId": step_id, "tool": {"id": call_id, "name": name, "input": arguments, "resultSummary": str(error), "latencyMs": latency, "status": "error"}}, dedupe=f"tool:{call_id}:done")
        raise ToolCallError(str(error)) from error
    finally:
        if observation:
            observation.__exit__(None, None, None)
