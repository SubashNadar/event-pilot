from typing import Literal

from pydantic import BaseModel, Field


class PlanningChatTurnRequest(BaseModel):
    field: Literal["eventType", "name", "date", "location", "attendees", "budget", "objective"]
    value: str = Field(min_length=1, max_length=1_000)
    answers: dict[str, str] = Field(default_factory=dict)


class PlanningChatTurnResponse(BaseModel):
    accepted: bool
    reply: str
    clarification: str | None = None
    missing_fields: list[str] = Field(default_factory=list)
