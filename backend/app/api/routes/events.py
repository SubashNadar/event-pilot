from datetime import date
from uuid import UUID

import re
from typing import Literal

from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Response, status

from app.models.event import BudgetRevisionRequest, EventBrief, EventBriefCreate, EventPlan, brief_rule_errors
from app.runs.manager import run_manager
from app.services.exports import build_pdf, build_pptx
from app.services import ui_state
from app.services.storage import list_events, load_event, load_plan, save_event

router = APIRouter(prefix="/events", tags=["events"])
@router.post("", response_model=EventBrief, status_code=status.HTTP_201_CREATED)
def create_event(payload: EventBriefCreate) -> EventBrief:
    if errors := brief_rule_errors(payload):
        raise RequestValidationError(errors)
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
    if errors := brief_rule_errors(payload):
        raise RequestValidationError(errors)
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


class BriefDraft(BaseModel):
    """Unsaved brief changes. Every field is optional: a draft may hold only what the owner has touched."""

    name: str | None = Field(default=None, min_length=2, max_length=120)
    event_date: date | None = None
    location: str | None = Field(default=None, min_length=2, max_length=120)
    attendees: int | None = Field(default=None, ge=1, le=100_000)
    budget: int | None = Field(default=None, ge=0)
    objective: str | None = Field(default=None, max_length=1_000)


@router.get("/{event_id}/draft")
def get_draft(event_id: UUID) -> dict:
    """The owner's unsaved brief changes for this event, if any. Kept until they save or discard them."""
    return {"draft": ui_state.get_draft(str(event_id))}


@router.put("/{event_id}/draft")
def save_draft(event_id: UUID, payload: BriefDraft) -> dict:
    draft = payload.model_dump(mode="json", exclude_none=True)
    ui_state.set_draft(str(event_id), draft)
    return {"draft": draft}


@router.delete("/{event_id}/draft", status_code=status.HTTP_204_NO_CONTENT)
def discard_draft(event_id: UUID) -> None:
    ui_state.clear_draft(str(event_id))


@router.get("/{event_id}/plan", response_model=EventPlan, responses={204: {"description": "The event has no approved plan yet"}})
def get_plan(event_id: UUID) -> EventPlan | Response:
    if load_event(event_id) is None:
        raise HTTPException(status_code=404, detail="Event not found")
    plan = load_plan(event_id)
    if plan is None:
        return Response(status_code=204)  # not an error: the event simply has no plan yet
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
