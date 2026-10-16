"""Manager-led LangGraph workflow grounded by EventPilot MCP tools."""

import asyncio
from typing import Any, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from app.mcp.client import call_planning_tool
from app.models.event import EventBrief, EventPlan
from app.services.azure_planner import build_azure_plan
from app.services.tracing import get_langfuse_config


class EventPlanningState(TypedDict, total=False):
    event: EventBrief
    operation: str
    logistics: dict[str, Any]
    finance: dict[str, Any]
    schedule: dict[str, Any]
    requirements: dict[str, Any]
    marketing: dict[str, Any]
    risks: dict[str, Any]
    final_plan: EventPlan
    review: dict[str, Any]
    revision_count: int


async def logistics_agent(state: EventPlanningState) -> dict[str, Any]:
    event = state["event"]
    try:
        result = await call_planning_tool("venue_search", {"location": event.location, "attendees": event.attendees, "total_budget_inr": event.budget})
    except Exception as error:
        result = {"available": False, "note": f"Venue tool unavailable: {error}"}
    return {"logistics": result}


async def finance_agent(state: EventPlanningState) -> dict[str, Any]:
    event = state["event"]
    lines = [{"category": "Venue", "amount": round(event.budget * 0.28)}, {"category": "Catering", "amount": round(event.budget * 0.3)}, {"category": "Contingency", "amount": round(event.budget * 0.08)}]
    try:
        result = await call_planning_tool("budget_validation", {"budget_lines": lines, "total_budget_inr": event.budget})
    except Exception as error:
        result = {"available": False, "note": f"Budget tool unavailable: {error}"}
    return {"finance": result}


async def schedule_agent(state: EventPlanningState) -> dict[str, Any]:
    agenda = [{"time": "10:00 AM", "activity": "Guest arrival"}, {"time": "11:00 AM", "activity": "Main programme"}, {"time": "3:00 PM", "activity": "Closing"}]
    try:
        result = await call_planning_tool("schedule_conflict_check", {"agenda": agenda})
    except Exception as error:
        result = {"available": False, "note": f"Schedule tool unavailable: {error}"}
    return {"schedule": result}


async def requirements_agent(state: EventPlanningState) -> dict[str, Any]:
    event = state["event"]
    try:
        result = await call_planning_tool("event_requirements", {"event_type": event.name, "attendees": event.attendees})
    except Exception as error:
        result = {"available": False, "note": f"Requirements tool unavailable: {error}"}
    return {"requirements": result}


async def marketing_agent(state: EventPlanningState) -> dict[str, Any]:
    event = state["event"]
    try:
        result = await call_planning_tool("marketing_readiness", {"event_type": event.name, "attendees": event.attendees, "event_date": str(event.event_date)})
    except Exception as error:
        result = {"available": False, "note": f"Marketing tool unavailable: {error}"}
    return {"marketing": result}


async def risk_operations_agent(state: EventPlanningState) -> dict[str, Any]:
    event = state["event"]
    try:
        result = await call_planning_tool("operational_risk_assessment", {"event_type": event.name, "attendees": event.attendees, "location": event.location})
    except Exception as error:
        result = {"available": False, "note": f"Risk tool unavailable: {error}"}
    return {"risks": result}


async def event_manager_agent(state: EventPlanningState, config: RunnableConfig) -> dict[str, Any]:
    specialist_context = {
        name: state.get(name, {})
        for name in ("logistics", "finance", "schedule", "requirements", "marketing", "risks")
    }
    return {
        "final_plan": build_azure_plan(
            state["event"],
            operation=state["operation"],
            specialist_context=specialist_context,
            tracing_config=config,
        )
    }


def review_plan(state: EventPlanningState) -> dict[str, Any]:
    event = state["event"]
    plan = state.get("final_plan")
    if plan is None:
        return {"review": {"approved": False, "issues": ["Event Manager did not produce a final plan."]}, "revision_count": state.get("revision_count", 0)}
    issues: list[str] = []
    if plan.budget_forecast > event.budget:
        issues.append("Budget forecast exceeds the approved budget.")
    if sum(line.amount for line in plan.budget_lines) != plan.budget_forecast:
        issues.append("Budget lines do not sum to the forecast.")
    for item in plan.agenda:
        if "AM" not in item.time and "PM" not in item.time:
            issues.append("Agenda includes a time outside the required 12-hour format.")
            break
    return {"review": {"approved": not issues, "issues": issues}, "revision_count": state.get("revision_count", 0)}


async def reflection_agent(state: EventPlanningState, config: RunnableConfig) -> dict[str, Any]:
    specialist_context = {
        name: state.get(name, {})
        for name in ("logistics", "finance", "schedule", "requirements", "marketing", "risks")
    }
    specialist_context["review_feedback"] = state["review"]
    plan = build_azure_plan(
        state["event"],
        operation="plan-reflection",
        specialist_context=specialist_context,
        tracing_config=config,
    )
    return {"final_plan": plan, "revision_count": state.get("revision_count", 0) + 1}


def route_after_review(state: EventPlanningState) -> str:
    if not state["review"]["approved"] and state.get("revision_count", 0) < 1:
        return "reflection_agent"
    return END


def run_event_workflow(event: EventBrief, operation: str) -> EventPlan:
    workflow = StateGraph(EventPlanningState)
    for name, node in (("logistics_agent", logistics_agent), ("finance_agent", finance_agent), ("schedule_agent", schedule_agent), ("requirements_agent", requirements_agent), ("marketing_agent", marketing_agent), ("risk_operations_agent", risk_operations_agent), ("event_manager", event_manager_agent), ("review_plan", review_plan), ("reflection_agent", reflection_agent)):
        workflow.add_node(name, node)
    for agent in ("logistics_agent", "finance_agent", "schedule_agent", "requirements_agent", "marketing_agent", "risk_operations_agent"):
        workflow.add_edge(START, agent)
        workflow.add_edge(agent, "event_manager")
    workflow.add_edge("event_manager", "review_plan")
    workflow.add_conditional_edges("review_plan", route_after_review, {"reflection_agent": "reflection_agent", END: END})
    workflow.add_edge("reflection_agent", "review_plan")
    result = asyncio.run(workflow.compile().ainvoke({"event": event, "operation": operation, "revision_count": 0}, config=get_langfuse_config(event, operation)))
    return result["final_plan"]
