"""Planning-run endpoints: start, stream (SSE), snapshot, resolve a failed step, cancel."""

import asyncio
import json
from functools import lru_cache
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from fastapi.responses import Response
from sse_starlette.sse import EventSourceResponse

from app.agents.recovery import SKIP_LABELS, interpret_custom
from app.core.config import settings
from app.models.event import EventBrief
from app.core.guard import clean_text, screen
from app.graphs.event_workflow import STEPS, build_graph
from pydantic import BaseModel, Field

from app.models.run import RecoveryProposal, ResolveStepRequest, ResolveStepResponse, RunRecord, RunSnapshot, StartRunRequest, StartRunResponse
from app.runs import store
from app.runs.manager import REPLACED, TERMINAL, RunConflict, RunNotFound, run_manager
from app.services import ui_state
from app.services.storage import load_event, save_event
from app.services.workflow_diagram import render_workflow_png

router = APIRouter(tags=["runs"])


@lru_cache(maxsize=1)
def _workflow_graph_png() -> bytes:
    """Render the compiled graph locally once for the static UI view."""
    graph = build_graph().compile().get_graph()
    return render_workflow_png(graph.draw_mermaid(), STEPS)


@router.get("/workflow/graph.png", include_in_schema=False)
def workflow_graph_png() -> Response:
    try:
        # Revalidate on every view: a stale cached copy would show an old graph after the workflow changes.
        return Response(_workflow_graph_png(), media_type="image/png", headers={"Cache-Control": "no-cache"})
    except Exception as error:
        raise HTTPException(status_code=503, detail="The LangGraph diagram could not be rendered. Use the live Workflow graph instead.") from error


def _run_or_404(run_id: str) -> RunRecord:
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.post("/events/{event_id}/runs", response_model=StartRunResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_run(event_id: UUID, payload: StartRunRequest) -> StartRunResponse:
    event = load_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    if payload.operation == "plan-edit":
        raise HTTPException(status_code=422, detail="Plan edits start from the plan chat")
    if store.active_run_for_event(str(event_id)) is not None:  # one live run per event
        raise HTTPException(status_code=409, detail="A plan is already being generated for this event. Wait for it to finish or stop it first.")
    if payload.operation == "budget-revision":
        if payload.budget is None:
            raise HTTPException(status_code=422, detail="A budget-revision run needs a budget")
        event = event.model_copy(update={"budget": payload.budget})
        save_event(event)
    ui_state.reset_attempts(str(event_id))  # a fresh plan from the brief: the owner gets their change requests again
    run_id = await run_manager.start(event, payload.operation, payload.session_id)
    return StartRunResponse(run_id=run_id, status="running")


@router.get("/events/{event_id}/runs/latest", response_model=RunRecord, responses={204: {"description": "The event has no planning run yet"}})
def latest_run(event_id: UUID) -> RunRecord | Response:
    run = store.latest_run_for_event(str(event_id))
    if run is None:
        return Response(status_code=204)  # not an error: nothing has been planned yet
    return run


@router.get("/runs/{run_id}", response_model=RunSnapshot)
def get_run(run_id: str) -> RunSnapshot:
    run = _run_or_404(run_id)
    return RunSnapshot(run=run, events=[{"seq": seq, **event} for seq, event in store.events_after(run_id)])


@router.get("/runs/{run_id}/stream")
async def stream_run(run_id: str, request: Request, after: int = Query(default=0, ge=0), last_event_id: str | None = Header(default=None)):
    _run_or_404(run_id)
    start = int(last_event_id) if last_event_id and last_event_id.isdigit() else after

    async def events():
        cursor = start
        while True:
            if await request.is_disconnected():
                return
            wakeup = run_manager.waiter(run_id)
            batch = store.events_after(run_id, cursor)
            for seq, event in batch:
                cursor = seq
                yield {"id": str(seq), "event": "message", "data": json.dumps(event, default=str)}
            run = store.get_run(run_id)
            if run is not None and run.status in TERMINAL and cursor >= run.last_seq:
                return
            try:
                await asyncio.wait_for(wakeup.wait(), timeout=15)
            except TimeoutError:
                pass

    return EventSourceResponse(events(), ping=15)


def _choice(option) -> dict:
    return {"action": option.action, "patch": option.patch, "label": option.label, "option_id": option.id}


MAX_APPROVAL_ATTEMPTS = settings.max_approval_attempts
EXHAUSTED = f"All {MAX_APPROVAL_ATTEMPTS} change requests at approval are used. You can still approve this plan, or restart the plan with your inputs."


def _exhausted(event_id: str) -> ResolveStepResponse | None:
    if run_manager.change_requests(event_id) >= MAX_APPROVAL_ATTEMPTS:
        return ResolveStepResponse(status="attempts_exhausted", question=EXHAUSTED)
    return None


async def _owner_message_at_approval(run_id: str, text: str) -> ResolveStepResponse:
    """The owner's own words on the plan at approval, read by intent (the LLM in LLM mode; rules offline):

    a question is answered, an unclear message gets one question back (neither uses a change request), a concrete
    change re-runs only the affected specialists in an edit run that comes back for approval, and feedback goes to the
    specialists the Event Manager assigned it to. Each change or feedback uses one of the owner's change requests."""
    from app.agents.feedback import assignment_notes, route_feedback
    from app.agents.plan_edit import prepare, reports_matching_plan

    run = _run_or_404(run_id)
    event = run_manager.event_for(run)
    plan = await run_manager.paused_plan(run_id)
    if plan is None:
        raise HTTPException(status_code=409, detail="This plan isn't ready for review yet")
    reports = await run_manager.previous_reports(run_id)
    route, _mode = await route_feedback(text, event, plan, reports)
    if route.kind == "question":
        return ResolveStepResponse(status="answered", question=route.answer)
    if route.kind == "unclear":
        return ResolveStepResponse(status="needs_clarification", question=route.question)
    if (exhausted := _exhausted(str(event.id))) is not None:
        return exhausted
    if route.kind == "edit":
        prepared = prepare(route.edit, event, plan, reports)
        if prepared.question:
            return ResolveStepResponse(status="needs_clarification", question=prepared.question)
        if not prepared.steps:
            return ResolveStepResponse(status="needs_clarification", question="That is already how the plan is, so there is nothing to change. What else should change?")
        try:
            new_event = EventBrief.model_validate({**event.model_dump(), **prepared.brief}) if prepared.brief else event
        except ValueError as error:
            return ResolveStepResponse(status="needs_clarification", question=f"I can't use that value: {error}")
        if new_event != event:
            save_event(new_event)
        run_manager.record_change_request(str(event.id))
        await run_manager.cancel(run_id, REPLACED)  # the paused plan is replaced by the edited one, which comes back for approval
        new_run = await run_manager.start_edit(new_event, reports_matching_plan(reports, plan), prepared.overrides, run.session_id, base_plan=plan, owner_review=True)
        return ResolveStepResponse(status="edit_started", run_id=new_run, changes=prepared.changes)
    run_manager.record_change_request(str(event.id))
    choice = {"action": "retry_with", "patch": {"decision": "revise"}, "label": f"Send back: {text[:60]}", "option_id": "revise", "feedback": text, "assignments": assignment_notes(route, text)}
    return ResolveStepResponse(status=await run_manager.resolve(run_id, "approval", choice))


async def _send_back_open_notes(run_id: str) -> ResolveStepResponse:
    """"Send back" with no words: fix what the review still has open. With nothing open there is nothing to re-run."""
    run = _run_or_404(run_id)
    values = await run_manager.paused_state(run_id)
    review = values.get("review") or {}
    if not (review.get("notes") or review.get("issues")):
        return ResolveStepResponse(status="needs_clarification", question="The review has nothing open. Tell me what should change, for example \u201cmove lunch to 1:30 PM\u201d or \u201clower the decor spend\u201d.")
    if (exhausted := _exhausted(run.event_id)) is not None:
        return exhausted
    run_manager.record_change_request(run.event_id)
    choice = {"action": "retry_with", "patch": {"decision": "revise"}, "label": "Fix the open notes", "option_id": "revise", "feedback": ""}
    return ResolveStepResponse(status=await run_manager.resolve(run_id, "approval", choice))


# Recovery choices that change the brief itself, not just one step's search.
BRIEF_FIELDS = {"attendees", "location"}


async def _replan_for_brief_change(run_id: str, run: Any, step_id: str, patch: dict[str, Any]) -> ResolveStepResponse:
    """Save the new guest count or location to the brief and re-plan from it, so the final plan and its preview match.
    Anything else in the choice (such as accepting an unverified venue) still applies to this step."""
    event = run_manager.event_for(run)
    brief_change = {key: value for key, value in patch.items() if key in BRIEF_FIELDS}
    step_change = {key: value for key, value in patch.items() if key not in BRIEF_FIELDS}
    try:
        new_event = EventBrief.model_validate({**event.model_dump(), **brief_change})
    except ValueError as error:
        return ResolveStepResponse(status="needs_clarification", question=f"I can't use that value: {error}")
    if new_event != event:
        save_event(new_event)
    await run_manager.cancel(run_id, REPLACED)  # the paused run is replaced by one planned from the new brief
    # Every specialist depends on the guest count or the city, so all of them run again; the plan still comes back for approval.
    new_run = await run_manager.start_edit(new_event, {}, {step_id: step_change} if step_change else {}, run.session_id, owner_review=True)
    names = {"attendees": "guest count", "location": "location"}
    return ResolveStepResponse(status="edit_started", run_id=new_run, changes=[f"{names[key]} to {value}" for key, value in brief_change.items()])


@router.post("/runs/{run_id}/steps/{step_id}/resolve", response_model=ResolveStepResponse)
async def resolve_step(run_id: str, step_id: str, payload: ResolveStepRequest) -> ResolveStepResponse:
    run = _run_or_404(run_id)
    if not payload.option_id and not (payload.custom_text and payload.custom_text.strip()):
        raise HTTPException(status_code=422, detail="Send option_id or custom_text")
    try:
        pending = await run_manager.pending_interrupt(run_id, step_id)
        proposal = RecoveryProposal.model_validate(pending["proposal"])
        if payload.option_id:
            option = proposal.option(payload.option_id)
            if option is None:  # the card is older than the step's latest failure, whose options are new
                raise HTTPException(status_code=409, detail="These options have changed. Pick one from the updated card.")
            if step_id == "approval" and option.id == "revise":
                return await _send_back_open_notes(run_id)
            # A tapped option was validated when it was offered: it runs as shown, with no second reading by the model.
        else:
            text = clean_text(payload.custom_text, 500)
            if screen(text):
                return ResolveStepResponse(status="needs_clarification", question="Tell me what to change for this step, e.g. a different area, guest count or budget share.")
            if step_id == "approval":  # the owner's own words on the plan, read by intent
                return await _owner_message_at_approval(run_id, text)
            option, question = await interpret_custom(step_id, text, run_manager.event_for(run), pending.get("overrides") or {})
            if option is None:
                return ResolveStepResponse(status="needs_clarification", question=question)
        if any(key in BRIEF_FIELDS for key in (option.patch or {})):  # a guest count or location is the brief itself: the whole plan must follow it
            return await _replan_for_brief_change(run_id, run, step_id, option.patch)
        result = await run_manager.resolve(run_id, step_id, _choice(option))
        return ResolveStepResponse(status=result, option=option)
    except RunNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except RunConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/runs/{run_id}/steps/{step_id}/retry", response_model=ResolveStepResponse)
async def retry_step(run_id: str, step_id: str) -> ResolveStepResponse:
    _run_or_404(run_id)
    try:
        result = await run_manager.resolve(run_id, step_id, {"action": "retry", "patch": {}, "label": "Try again as is"})
    except RunConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return ResolveStepResponse(status=result)


@router.post("/runs/{run_id}/steps/{step_id}/skip", response_model=ResolveStepResponse)
async def skip_step(run_id: str, step_id: str) -> ResolveStepResponse:
    _run_or_404(run_id)
    if step_id == "event_manager":
        raise HTTPException(status_code=422, detail="The Event Manager step can't be skipped")
    try:
        result = await run_manager.resolve(run_id, step_id, {"action": "skip", "patch": {}, "label": SKIP_LABELS.get(step_id, "Skipped by you")})
    except RunConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return ResolveStepResponse(status=result)


@router.post("/runs/{run_id}/continue")
async def continue_run(run_id: str) -> dict[str, str]:
    """Resume a stopped, errored or interrupted run from its checkpoint."""
    try:
        return {"status": await run_manager.continue_run(run_id)}
    except RunNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except RunConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/runs/{run_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_run(run_id: str) -> None:
    _run_or_404(run_id)
    await run_manager.cancel(run_id)


class ApprovalRequest(BaseModel):
    decision: str = Field(pattern="^(approve|revise)$")
    feedback: str | None = Field(default=None, max_length=500, description="What to change, in the owner's words.")


@router.post("/runs/{run_id}/approval", response_model=ResolveStepResponse)
async def decide_plan(run_id: str, payload: ApprovalRequest) -> ResolveStepResponse:
    """The owner's decision on the finished plan: approve it, or send it back with changes."""
    _run_or_404(run_id)
    feedback = clean_text(payload.feedback or "", 500).strip()
    try:
        await run_manager.pending_interrupt(run_id, "approval")
        if payload.decision == "approve":
            choice = {"action": "retry_with", "patch": {"decision": "approve"}, "label": "Approve the plan", "option_id": "approve"}
            return ResolveStepResponse(status=await run_manager.resolve(run_id, "approval", choice))
        # A send-back goes through the same reading and the same change limit as the approval card.
        return await (_owner_message_at_approval(run_id, feedback) if feedback else _send_back_open_notes(run_id))
    except RunNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except RunConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
