from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.models.event import BudgetRevisionRequest, EventBrief, EventBriefCreate, EventPlan
from app.services.planning import build_event_plan
from app.services.storage import load_event, load_plan, save_event, save_plan

router = APIRouter(prefix="/events", tags=["events"])
@router.post("", response_model=EventBrief, status_code=status.HTTP_201_CREATED)
def create_event(payload: EventBriefCreate) -> EventBrief:
    event = EventBrief(**payload.model_dump())
    save_event(event)
    return event


@router.get("/{event_id}", response_model=EventBrief)
def get_event(event_id: UUID) -> EventBrief:
    event = load_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.post("/{event_id}/plan", response_model=EventPlan)
def generate_plan(event_id: UUID) -> EventPlan:
    event = get_event(event_id)
    plan = build_event_plan(event)
    save_plan(plan)
    return plan


@router.get("/{event_id}/plan", response_model=EventPlan)
def get_plan(event_id: UUID) -> EventPlan:
    plan = load_plan(event_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan has not been generated")
    return plan


@router.post("/{event_id}/revisions/budget", response_model=EventPlan)
def revise_budget(event_id: UUID, payload: BudgetRevisionRequest) -> EventPlan:
    event = get_event(event_id)
    revised_event = event.model_copy(update={"budget": payload.budget})
    save_event(revised_event)
    plan = build_event_plan(revised_event, operation="budget-revision")
    save_plan(plan)
    return plan
