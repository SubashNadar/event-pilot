"""Planning-run models: step status, recovery proposals and API payloads.

Field names on the wire are camelCase so the frontend reducer (ported from the
Eventa mock's `types.ts`) can read events without translation.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

StepStatus = Literal["pending", "running", "verifying", "completed", "failed", "skipped"]
RunStatus = Literal["queued", "running", "paused", "completed", "cancelled", "error"]
RunOperation = Literal["plan-generation", "budget-revision", "plan-edit"]


class Verification(BaseModel):
    check: str
    passed: bool
    reason: str


class ToolCallRecord(BaseModel):
    id: str
    name: str
    input: dict[str, Any] = Field(default_factory=dict)
    resultSummary: str = ""
    latencyMs: int = 0
    status: Literal["running", "success", "error"] = "running"


class SpecialistReport(BaseModel):
    """What one specialist agent hands to the Event Manager."""

    recommendations: list[str] = Field(min_length=1, max_length=5, description="2-4 short recommendations in a warm, first-person planner voice, each with its reason, e.g. 'I shortlisted two venues that fit 200 guests comfortably; the rooftop one gives the best value.' Where a choice is open, end with one suggestion for the owner.")
    decisions: dict[str, Any] = Field(default_factory=dict, description="Key decisions as data, e.g. venue name, budget lines or agenda items.")
    assumptions: list[str] = Field(default_factory=list, description="Assumptions the plan depends on.")
    confidence: int = Field(default=75, ge=0, le=100)


class RecoveryOption(BaseModel):
    id: str = Field(description="Short slug, e.g. 'raise-venue-share'.")
    label: str = Field(max_length=60, description="Chip text, at most 40 characters, starts with a verb.")
    description: str = Field(default="", description="One line on what changes if the user picks this.")
    action: Literal["retry", "retry_with", "skip"] = "retry_with"
    patch: dict[str, Any] = Field(default_factory=dict, description="Step input overrides. Only keys from the allowed list.")


class RecoveryProposal(BaseModel):
    summary: str = Field(description="One plain sentence on what failed, naming the numbers involved.")
    cause: str = Field(default="", description="The raw error, quoted as it came in.")
    options: list[RecoveryOption] = Field(default_factory=list)
    customPrompt: str = Field(default="Tell me what to change", description="Placeholder text for the custom input field.")
    source: Literal["llm", "rules"] = "rules"
    preview: dict[str, Any] | None = Field(default=None, description="The generated plan, shown so the owner can review it before deciding.")
    changesLeft: int | None = Field(default=None, description="Approval only: change requests the owner has left for this plan.")

    def option(self, option_id: str) -> RecoveryOption | None:
        return next((option for option in self.options if option.id == option_id), None)


class StartRunRequest(BaseModel):
    operation: RunOperation = "plan-generation"
    budget: int | None = Field(default=None, ge=0, description="New budget for a budget-revision run.")
    session_id: str | None = None


class StartRunResponse(BaseModel):
    run_id: str
    status: RunStatus


class ResolveStepRequest(BaseModel):
    option_id: str | None = None
    custom_text: str | None = Field(default=None, max_length=500)


class ResolveStepResponse(BaseModel):
    status: Literal["resumed", "queued", "needs_clarification", "answered", "edit_started", "attempts_exhausted"]
    question: str | None = None  # a clarifying question, or the answer when status is 'answered'
    option: RecoveryOption | None = None
    run_id: str | None = None  # set when the owner's change started a plan-edit run
    changes: list[str] = Field(default_factory=list)


class RunRecord(BaseModel):
    id: str
    event_id: str
    session_id: str | None = None
    operation: str
    status: RunStatus
    trace_id: str | None = None
    trace_url: str | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime
    last_seq: int = 0


class RunSnapshot(BaseModel):
    """A run plus every event so far: enough to rebuild the UI after a refresh."""

    run: RunRecord
    events: list[dict[str, Any]]
