from datetime import date, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class EventBriefCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    event_date: date
    location: str = Field(min_length=2, max_length=120)
    attendees: int = Field(ge=1, le=100_000)
    budget: int = Field(ge=0)
    objective: str = Field(min_length=10, max_length=1_000)


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
    source: str = "deterministic"
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class BudgetRevisionRequest(BaseModel):
    budget: int = Field(ge=0)
