from uuid import UUID

import re
from typing import Literal

from fastapi import APIRouter, HTTPException, Response, status

from app.models.event import BudgetRevisionRequest, EventBrief, EventBriefCreate, EventPlan
from app.runs.manager import run_manager
from app.services.exports import build_pdf, build_pptx
from app.services.storage import list_events, load_event, load_plan, save_event

router = APIRouter(prefix="/events", tags=["events"])
@router.post("", response_model=EventBrief, status_code=status.HTTP_201_CREATED)
def create_event(payload: EventBriefCreate) -> EventBrief:
    event = EventBrief(**payload.model_dump())
    save_event(event)
    return event


@router.get("", response_model=list[EventBrief])
def get_events() -> list[EventBrief]:
    return list_events()


@router.get("/{event_id}", response_model=EventBrief)
def get_event(event_id: UUID) -> EventBrief:
    event = load_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.put("/{event_id}", response_model=EventBrief)
def update_event(event_id: UUID, payload: EventBriefCreate) -> EventBrief:
    existing = get_event(event_id)
    event = EventBrief(**payload.model_dump(), id=existing.id, created_at=existing.created_at)
    save_event(event)
    return event


@router.post("/{event_id}/plan", response_model=EventPlan)
async def generate_plan(event_id: UUID) -> EventPlan:
    """Blocking variant kept for older clients: runs the workflow to the end,
    skipping (not pausing on) failed steps. New clients use POST /events/{id}/runs."""
    event = get_event(event_id)
    return await run_manager.run_to_completion(event, "plan-generation")


@router.get("/{event_id}/plan", response_model=EventPlan)
def get_plan(event_id: UUID) -> EventPlan:
    plan = load_plan(event_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan has not been generated")
    return plan


@router.post("/{event_id}/revisions/budget", response_model=EventPlan)
async def revise_budget(event_id: UUID, payload: BudgetRevisionRequest) -> EventPlan:
    event = get_event(event_id)
    revised_event = event.model_copy(update={"budget": payload.budget})
    save_event(revised_event)
    return await run_manager.run_to_completion(revised_event, "budget-revision")


@router.get("/{event_id}/exports/{fmt}")
def export_plan(event_id: UUID, fmt: Literal["pdf", "pptx"]) -> Response:
    """The saved plan as a PDF blueprint or a PPTX brochure."""
    event, plan = load_event(event_id), load_plan(event_id)
    if event is None or plan is None:
        raise HTTPException(status_code=404, detail="No saved plan for this event yet")
    if fmt == "pdf":
        body, media = build_pdf(event, plan), "application/pdf"
    else:
        body, media = build_pptx(event, plan), "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    slug = re.sub(r"[^a-z0-9]+", "-", event.name.lower()).strip("-") or "event"
    return Response(content=body, media_type=media, headers={"Content-Disposition": f'attachment; filename="{slug}-plan.{fmt}"'})
