"""Planning-run endpoints: start, stream (SSE), snapshot, resolve a failed step, cancel."""

import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from sse_starlette.sse import EventSourceResponse

from app.agents.recovery import SKIP_LABELS, interpret_custom
from app.core.guard import clean_text, screen
from app.models.run import RecoveryProposal, ResolveStepRequest, ResolveStepResponse, RunRecord, RunSnapshot, StartRunRequest, StartRunResponse
from app.runs import store
from app.runs.manager import TERMINAL, RunConflict, RunNotFound, run_manager
from app.services.storage import load_event, save_event

router = APIRouter(tags=["runs"])


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
    run_id = await run_manager.start(event, payload.operation, payload.session_id)
    return StartRunResponse(run_id=run_id, status="running")


@router.get("/events/{event_id}/runs/latest", response_model=RunRecord)
def latest_run(event_id: UUID) -> RunRecord:
    run = store.latest_run_for_event(str(event_id))
    if run is None:
        raise HTTPException(status_code=404, detail="No runs for this event")
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
            if option is None:
                raise HTTPException(status_code=422, detail="Unknown option for this step")
        else:
            text = clean_text(payload.custom_text, 500)
            if screen(text):
                return ResolveStepResponse(status="needs_clarification", question="Tell me what to change for this step, e.g. a different area, guest count or budget share.")
            option, question = await interpret_custom(step_id, text, run_manager.event_for(run), pending.get("overrides") or {})
            if option is None:
                return ResolveStepResponse(status="needs_clarification", question=question)
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


@router.post("/runs/{run_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_run(run_id: str) -> None:
    _run_or_404(run_id)
    await run_manager.cancel(run_id)
