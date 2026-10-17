"""Small LangGraph workflow for one conversational event-brief turn."""

from datetime import date
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.models.chat import PlanningChatTurnRequest, PlanningChatTurnResponse
from app.services.azure_planner import get_azure_model
from app.core.config import settings

FIELDS = ("eventType", "name", "date", "location", "attendees", "budget", "objective")


class ChatState(TypedDict, total=False):
    request: PlanningChatTurnRequest
    accepted: bool
    clarification: str | None
    reply: str


def validate_input(state: ChatState) -> ChatState:
    request = state["request"]
    value = request.value.strip()
    clarification: str | None = None
    if request.field == "name" and len(value) < 4:
        clarification = "Please use a more descriptive event name, such as 'Meera and Karthik Wedding Reception'."
    elif request.field == "date":
        try:
            if date.fromisoformat(value) <= date.today():
                clarification = "Please choose a future event date."
        except ValueError:
            clarification = "Please choose the event date using the date field."
    elif request.field == "location" and len(value) < 4:
        clarification = "Please provide a city, neighbourhood, or venue area."
    elif request.field in {"attendees", "budget"}:
        try:
            if int(value) <= 0:
                clarification = f"Please enter a positive {request.field} value."
        except ValueError:
            clarification = f"Please enter {request.field} as a whole number."
    elif request.field == "objective" and len(value) < 20:
        clarification = "Please add a little more detail about the outcome or experience you want to create."
    return {"accepted": clarification is None, "clarification": clarification}


def compose_reply(state: ChatState) -> ChatState:
    request = state["request"]
    if not state["accepted"]:
        return {"reply": state["clarification"] or "Please refine that answer."}

    confirmations = {
        "eventType": f"A {request.value} gives the planning team the right operational context.",
        "name": f"'{request.value}' is a clear event name.",
        "date": "Date noted. I will use it for schedule and communication planning.",
        "location": f"{request.value} noted. Venue and logistics recommendations will be location-aware.",
        "attendees": f"{request.value} attendees will shape capacity, catering, and risk planning.",
        "budget": f"INR {request.value} will be treated as the hard budget ceiling.",
        "objective": "That gives the Event Manager a clear outcome to optimize for.",
    }
    reply = confirmations[request.field]
    if settings.azure_openai_enabled and request.field in {"eventType", "objective"}:
        try:
            response = get_azure_model().invoke(
                f"You are EventPilot, a concise event-planning assistant. A user gave this {request.field}: {request.value}. "
                "Reply in one short supportive sentence. Do not invent venue availability, pricing, bookings, or facts."
            )
            reply = str(response.content).strip() or reply
        except Exception:
            pass
    return {"reply": reply}


def run_chat_turn(request: PlanningChatTurnRequest) -> PlanningChatTurnResponse:
    workflow = StateGraph(ChatState)
    workflow.add_node("validate_input", validate_input)
    workflow.add_node("compose_reply", compose_reply)
    workflow.add_edge(START, "validate_input")
    workflow.add_edge("validate_input", "compose_reply")
    workflow.add_edge("compose_reply", END)
    result = workflow.compile().invoke({"request": request})
    answers = {**request.answers, **({request.field: request.value} if result["accepted"] else {})}
    return PlanningChatTurnResponse(
        accepted=result["accepted"],
        reply=result["reply"],
        clarification=result.get("clarification"),
        missing_fields=[field for field in FIELDS if not answers.get(field)],
    )
