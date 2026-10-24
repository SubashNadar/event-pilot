"""Chat endpoints.

- Brief intake (`POST /chat/brief`): every turn is saved to a chat session, so a
  refresh or a restart picks the conversation up where it was.
- Sessions (`GET /chat/sessions/{id}`, `POST /chat/sessions/{id}/event`): restore
  a conversation; link it to the event it produced.
- Plan chat (`GET|POST /events/{event_id}/chat`): ask about the plan or change it
  in plain words. A change re-runs only the affected specialists; the result is
  posted back into the same conversation when the run finishes.
"""

import re
from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.agents.plan_edit import AGENT_NAMES, answer_from_plan, interpret, plan_diff, prepare, reports_matching_plan
from app.core.config import settings
from app.core.guard import REDIRECT, clean_text, screen
from app.graphs.brief_workflow import run_brief_turn
from app.graphs.chat_workflow import run_chat_turn
from app.models.chat import (
    BriefTurnRequest, BriefTurnResponse, ChatMessage, ChatSession, LinkSessionRequest, PlanChatRequest,
    PlanChatResponse, PlanningChatTurnRequest, PlanningChatTurnResponse,
)
from app.models.event import EventBrief, EventPlan
from app.runs import store
from app.runs.manager import run_manager
from app.services.storage import load_event, load_plan, save_event

router = APIRouter(prefix="/chat", tags=["chat"])
event_chat_router = APIRouter(tags=["chat"])

_EVENT_START_CUE = re.compile(
    r"\b(event|wedding|reception|birthday|party|celebration|conference|summit|workshop|training|seminar|"
    r"meetup|networking|offsite|retreat|ceremony|engagement|festival|fest|concert|launch|hackathon|"
    r"team[ -]?building|lunch|dinner)\b",
    re.IGNORECASE,
)
BRIEF_REDIRECT = "Out-of-scope request. EventPilot is designed only for event planning, so I cannot advise on that topic. Try an event-related request, such as 'Plan a wedding reception in Bengaluru for 200 guests.'"


@router.post("/planning-turn", response_model=PlanningChatTurnResponse)
def planning_turn(payload: PlanningChatTurnRequest) -> PlanningChatTurnResponse:
    return run_chat_turn(payload)


# ------------------------------------------------------------------ brief intake

@router.post("/brief", response_model=BriefTurnResponse)
async def brief_turn(payload: BriefTurnRequest) -> BriefTurnResponse:
    """Dynamic brief intake: extract fields from free text, check them against
    benchmarks and frame the next question with data-driven options."""
    message = clean_text(payload.message) if payload.message else payload.message
    flagged = screen(message)
    # Only the first free-text message needs an event cue. Later turns can be
    # concise answers such as a city, date, guest count, or budget.
    out_of_scope_start = bool(
        message and not payload.answers and not payload.field and not payload.ask
        and not payload.patch and not _EVENT_START_CUE.search(message)
    )
    result = await run_brief_turn(payload.model_copy(update={"message": None if flagged or out_of_scope_start else message}))
    if flagged:
        result.reply = REDIRECT
    elif out_of_scope_start:
        result.reply = BRIEF_REDIRECT
        result.next = None

    shown = clean_text(payload.display_text or payload.message or "", 300)
    session_id = payload.session_id if payload.session_id and store.get_chat_session(payload.session_id) else None
    if shown:  # the opening greeting isn't saved; the first real turn starts the session
        session_id = session_id or store.create_chat_session(None, "New event")
        store.append_chat_message(session_id, "user", shown)
        text = "\n".join(part for part in (result.reply, result.next.prompt if result.next else "") if part)
        store.append_chat_message(session_id, "assistant", text, meta={"kind": "brief", "turn": result.model_dump(exclude={"session_id"})})
        store.save_session_state(session_id, {"answers": result.answers, "dismissed": payload.dismissed})
    result.session_id = session_id
    return result


def _session_or_404(session_id: str) -> dict:
    session = store.get_chat_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return session


@router.get("/sessions/{session_id}", response_model=ChatSession)
def get_session(session_id: str) -> ChatSession:
    session = _session_or_404(session_id)
    return ChatSession(**session, messages=[ChatMessage(**m) for m in store.chat_messages(session_id)])


@router.post("/sessions/{session_id}/event", response_model=ChatSession)
def link_session(session_id: str, payload: LinkSessionRequest) -> ChatSession:
    _session_or_404(session_id)
    try:
        event = load_event(UUID(payload.event_id))
    except ValueError:
        event = None
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    store.link_session_to_event(session_id, str(event.id), event.name)
    return get_session(session_id)


# ------------------------------------------------------------------ plan chat

@event_chat_router.get("/events/{event_id}/chat", response_model=ChatSession)
def event_chat(event_id: UUID) -> ChatSession:
    session = store.session_for_event(str(event_id))
    if session is None:
        return ChatSession(id="", event_id=str(event_id))
    return ChatSession(**session, messages=[ChatMessage(**m) for m in store.chat_messages(session["id"])])


def _edit_hooks(session_id: str, run_id: str, before_plan: dict, before_event: EventBrief, after_event: EventBrief) -> dict:
    def completed(plan: EventPlan) -> None:
        if store.message_for_run(session_id, run_id, "edit_done"):
            return
        changes = plan_diff(before_plan, plan.model_dump(mode="json"), before_event, after_event)
        text = "Done. Here's what changed:\n" + "\n".join(f"- {line}" for line in changes) if changes else "Done. The checks passed and nothing else in the plan needed to change."
        store.append_chat_message(session_id, "assistant", text, run_id, {"kind": "edit_done", "changes": changes})

    def paused(waiting: list[dict]) -> None:
        for item in waiting:
            step = item.get("step_id", "")
            text = f"{AGENT_NAMES.get(step, 'A step')} couldn't apply that: {item.get('error', 'it failed a check')}. Pick one of the options in the steps panel, or tell me a different change."
            store.append_chat_message(session_id, "assistant", text, run_id, {"kind": "edit_paused", "step_id": step})

    def ended(status: str, message: str) -> None:
        if after_event != before_event:
            save_event(before_event)  # the plan didn't change, so the brief goes back too
        store.append_chat_message(session_id, "assistant", f"The update stopped ({message}). The plan is as it was.", run_id, {"kind": "edit_failed"})

    return {"completed": completed, "paused": paused, "ended": ended}


@event_chat_router.post("/events/{event_id}/chat", response_model=PlanChatResponse)
async def plan_chat(event_id: UUID, payload: PlanChatRequest) -> PlanChatResponse:
    event = load_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    session = store.get_chat_session(payload.session_id) if payload.session_id else None
    if session is None or session["event_id"] != str(event_id):
        session = store.session_for_event(str(event_id))
    session_id = session["id"] if session else store.create_chat_session(str(event_id), event.name)

    message = clean_text(payload.message, settings.max_chat_chars)
    first_seq = store.append_chat_message(session_id, "user", message or "(empty)")

    def reply(kind: str, text: str, run_id: str | None = None, steps: list[str] | None = None, meta: dict | None = None) -> PlanChatResponse:
        store.append_chat_message(session_id, "assistant", text, run_id, {"kind": kind, **(meta or {})})
        messages = [ChatMessage(**m) for m in store.chat_messages(session_id) if m["seq"] >= first_seq]
        return PlanChatResponse(session_id=session_id, kind=kind, reply=text, run_id=run_id, steps=steps or [], messages=messages)

    if not message:
        return reply("clarify", "What should I change in the plan?")
    if screen(message):
        return reply("redirect", REDIRECT)
    active = store.active_run_for_event(str(event_id), ("queued", "running", "paused"))
    if active is not None:
        if active.status == "paused":
            return reply("busy", "A step is waiting for your decision. Answer it in the steps panel first, then tell me the change again.", active.id)
        return reply("busy", "I'm still updating the plan. Send that again when this update finishes.", active.id)

    plan = load_plan(event_id)
    source_run = plan.run_id if plan and plan.run_id else None
    if plan is None or source_run is None or store.get_run(source_run) is None:
        return reply("no_plan", "There's no plan to change yet. Generate the plan first, then tell me what to change.")
    plan_dict = plan.model_dump(mode="json")
    reports = await run_manager.previous_reports(source_run)

    edit, _mode = await interpret(message, event, plan_dict, reports)
    if not edit.is_change():
        if edit.question:
            return reply("clarify", edit.question)
        return reply("answer", edit.answer or answer_from_plan(message, event, plan_dict))
    prepared = prepare(edit, event, plan_dict, reports)
    if prepared.question:
        return reply("clarify", prepared.question)
    if not prepared.steps:
        return reply("answer", "That's already how the plan is. Anything else to change?")

    try:
        new_event = EventBrief.model_validate({**event.model_dump(), **prepared.brief}) if prepared.brief else event
    except ValueError:
        return reply("clarify", "I can't use that value for the brief. What should it be instead?")
    if new_event != event:
        save_event(new_event)
    run_id = await run_manager.start_edit(new_event, reports_matching_plan(reports, plan_dict), prepared.overrides, session_id)
    run_manager.on_outcome(run_id, **_edit_hooks(session_id, run_id, plan_dict, event, new_event))

    agents = ", ".join(AGENT_NAMES[step] for step in prepared.steps)
    text = f"On it: {'; '.join(prepared.changes)}."
    if prepared.notes:
        text += " " + ". ".join(prepared.notes) + "."
    text += f" Re-running {agents}; everything else stays as it is."
    return reply("edit_started", text, run_id, prepared.steps, {"changes": prepared.changes, "steps": prepared.steps})
