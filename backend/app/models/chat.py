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


BRIEF_FIELDS = ("eventType", "location", "attendees", "budget", "date", "objective", "name")


class BriefOption(BaseModel):
    label: str
    value: str
    hint: str = ""


class BriefQuestion(BaseModel):
    field: str
    label: str
    prompt: str
    options: list[BriefOption] = Field(default_factory=list)
    placeholder: str = ""


class BriefWarningOption(BaseModel):
    label: str
    patch: dict[str, str]


class BriefWarning(BaseModel):
    id: str
    message: str
    options: list[BriefWarningOption] = Field(default_factory=list)


class BriefItem(BaseModel):
    field: str
    label: str
    value: str
    display: str


class BriefTurnRequest(BaseModel):
    """One turn of the planning chat. Send a free-text `message`, or a `field` + `value`
    (a clicked option), or a `patch` (a warning's quick fix). `ask` re-asks a field."""

    message: str | None = Field(default=None, max_length=2_000)
    field: Literal["eventType", "name", "date", "location", "attendees", "budget", "objective"] | None = None
    value: str | None = Field(default=None, max_length=1_000)
    patch: dict[str, str] = Field(default_factory=dict)
    answers: dict[str, str] = Field(default_factory=dict)
    dismissed: list[str] = Field(default_factory=list)
    ask: Literal["eventType", "name", "date", "location", "attendees", "budget", "objective"] | None = None
    session_id: str | None = Field(default=None, max_length=64, description="Saves the turn to this conversation; a new one starts when omitted.")
    display_text: str | None = Field(default=None, max_length=300, description="What the person typed or clicked, as shown in the chat.")


class BriefTurnResponse(BaseModel):
    answers: dict[str, str]
    brief: list[BriefItem]
    filled: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    errors: dict[str, str] = Field(default_factory=dict)
    warnings: list[BriefWarning] = Field(default_factory=list)
    next: BriefQuestion | None = None
    ready: bool = False
    reply: str
    mode: Literal["llm", "rules"] = "rules"
    session_id: str | None = None


class ChatMessage(BaseModel):
    seq: int
    role: Literal["user", "assistant"]
    content: str
    run_id: str | None = None
    created_at: str
    meta: dict | None = None


class ChatSession(BaseModel):
    id: str
    event_id: str | None = None
    title: str | None = None
    state: dict = Field(default_factory=dict)
    messages: list[ChatMessage] = Field(default_factory=list)


class LinkSessionRequest(BaseModel):
    event_id: str = Field(min_length=1, max_length=64)


class PlanChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1_000)
    session_id: str | None = Field(default=None, max_length=64)


class PlanChatResponse(BaseModel):
    session_id: str
    kind: Literal["edit_started", "answer", "clarify", "redirect", "busy", "no_plan"]
    reply: str
    run_id: str | None = None
    steps: list[str] = Field(default_factory=list)
    messages: list[ChatMessage] = Field(default_factory=list)
