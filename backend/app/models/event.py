from datetime import date, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


MIN_BUDGET_INR = 50_000
MIN_BUDGET_PER_GUEST_INR = 500


class EventBriefCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    event_date: date
    location: str = Field(min_length=2, max_length=120)
    attendees: int = Field(ge=1, le=100_000)
    budget: int = Field(ge=0)
    objective: str = Field(min_length=10, max_length=1_000)


def brief_rule_errors(brief: EventBriefCreate) -> list[dict]:
    """Checks for a brief the user is creating or changing. Saved events are not re-checked when they load."""
    errors: list[dict] = []
    if brief.event_date < date.today():
        errors.append({"loc": ("body", "event_date"), "msg": f"The event date {brief.event_date:%d %b %Y} has already passed. Pick a future date.", "type": "value_error"})
    if brief.budget < MIN_BUDGET_INR:
        errors.append({"loc": ("body", "budget"), "msg": f"The budget of ₹{brief.budget:,} is too low for an event. Plan with at least ₹{MIN_BUDGET_INR:,}.", "type": "value_error"})
    elif brief.budget < brief.attendees * MIN_BUDGET_PER_GUEST_INR:
        errors.append({"loc": ("body", "budget"), "msg": f"₹{brief.budget:,} is under ₹{MIN_BUDGET_PER_GUEST_INR} per guest for {brief.attendees} guests. Raise the budget or lower the guest count.", "type": "value_error"})
    return errors


class EventBrief(EventBriefCreate):
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class BudgetLine(BaseModel):
    category: str
    amount: int
    share_percent: int


class AgendaItem(BaseModel):
    time: str
    activity: str
    owner: str


class RiskItem(BaseModel):
    level: str
    title: str
    detail: str
    recommended_action: str


class AgentActivity(BaseModel):
    agent: str
    detail: str
    timestamp: str


class AiPlanDraft(BaseModel):
    plan_type: str
    venue: str
    venue_detail: str
    budget_forecast: int
    budget_lines: list[BudgetLine]
    agenda: list[AgendaItem]
    risks: list[RiskItem] = Field(min_length=2, max_length=5)
    activity: list[AgentActivity]
    confidence: int = Field(ge=0, le=100)


class EventPlan(BaseModel):
    event_id: UUID
    plan_type: str
    venue: str
    venue_detail: str
    budget_forecast: int
    budget_lines: list[BudgetLine]
    agenda: list[AgendaItem]
    risks: list[RiskItem] = Field(min_length=2, max_length=5)
    activity: list[AgentActivity]
    confidence: int
    # Marketing's guest communication and the Requirements list, carried into the plan so the review sees them.
    communications: dict | None = None
    requirements: list[str] = Field(default_factory=list)
    source: str = "deterministic"
    recommendations: str | None = None
    run_id: str | None = None
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class BudgetRevisionRequest(BaseModel):
    budget: int = Field(ge=0)
