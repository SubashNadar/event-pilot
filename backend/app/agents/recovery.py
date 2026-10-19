"""Recovery assistant: explain a failed step and offer ways forward.

When a step fails, `explain_failure` turns the raw error into a short summary and
2-3 concrete options (each a validated patch to the step's inputs). Skip is
always added by code, never left to the model. `interpret_custom` maps the
user's free text to the same allowed inputs, or returns a clarifying question.
Custom text is only ever converted into validated patch fields: it is never
passed to a tool or used as an instruction.
"""

import re
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.agents.voice import PLANNER_VOICE
from app.agents.fmt import inr
from app.core.guard import DATA_RULE, wrap_user
from app.agents.llm import get_chat_model, limited, llm_enabled
from app.models.event import EventBrief
from app.models.run import RecoveryOption, RecoveryProposal


class _Patch(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LogisticsPatch(_Patch):
    location: str | None = Field(default=None, min_length=2, max_length=120, description="City or area to search instead")
    attendees: int | None = Field(default=None, ge=1, le=100_000, description="Guest count to plan for")
    venue_share_pct: int | None = Field(default=None, ge=10, le=60, description="Share of the total budget for venue rent, percent (default 30)")
    venue_type: str | None = Field(default=None, max_length=60, description="Kind of venue, e.g. 'banquet hall', 'beach resort'")
    allow_unverified: bool | None = Field(default=None, description="Accept a venue that is not in the catalog, flagged as unverified")


class FinancePatch(_Patch):
    contingency_pct: int | None = Field(default=None, ge=0, le=20, description="Contingency share, percent")
    budget_ceiling: int | None = Field(default=None, gt=0, description="Budget limit in INR to validate against")


class SchedulePatch(_Patch):
    start_time: str | None = Field(default=None, description="First agenda time, e.g. '10:00 AM'")
    end_time: str | None = Field(default=None, description="Last agenda time, e.g. '6:00 PM'")
    session_count: int | None = Field(default=None, ge=3, le=10, description="Number of agenda items")

    @field_validator("start_time", "end_time")
    @classmethod
    def twelve_hour(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"(1[0-2]|[1-9]):[0-5]\d (AM|PM)", value.strip().upper()):
            raise ValueError("use a 12-hour time like '9:30 AM'")
        return value.strip().upper() if value else value


class MarketingPatch(_Patch):
    channels: list[str] | None = Field(default=None, max_length=6, description="Communication channels to use")
    lead_days: int | None = Field(default=None, ge=1, le=180, description="Days before the event to send the first invite")


class RequirementsPatch(_Patch):
    event_type: str | None = Field(default=None, max_length=60, description="Event type to plan requirements for")


class RiskPatch(_Patch):
    risk_appetite: Literal["low", "medium", "high"] | None = Field(default=None, description="How cautious the risk register should be")


class ManagerPatch(_Patch):
    use_fallback: bool | None = Field(default=None, description="Build the plan with the rule-based planner from the specialists' results")


class RecommendPatch(_Patch):
    pass


PATCH_MODELS: dict[str, type[_Patch]] = {
    "logistics_agent": LogisticsPatch,
    "finance_agent": FinancePatch,
    "schedule_agent": SchedulePatch,
    "marketing_agent": MarketingPatch,
    "requirements_agent": RequirementsPatch,
    "risk_operations_agent": RiskPatch,
    "event_manager": ManagerPatch,
    "recommendations": RecommendPatch,
}

SKIP_LABELS = {
    "logistics_agent": "Skip — I'll book the venue myself",
    "finance_agent": "Skip the budget check",
    "schedule_agent": "Skip — I'll set the agenda",
    "requirements_agent": "Skip requirements",
    "marketing_agent": "Skip guest communication",
    "risk_operations_agent": "Skip the risk register",
    "recommendations": "Skip the summary",
}
NOT_SKIPPABLE = {"event_manager"}


def allowed_fields(step_id: str) -> dict[str, str]:
    model = PATCH_MODELS.get(step_id, RecommendPatch)
    return {name: (field.description or name) for name, field in model.model_fields.items()}


def validate_patch(step_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    """Raises ValueError for unknown keys or invalid values."""
    model = PATCH_MODELS.get(step_id, RecommendPatch)
    try:
        return model.model_validate(patch or {}).model_dump(exclude_none=True)
    except ValidationError as error:
        raise ValueError("; ".join(f"{'.'.join(map(str, e['loc'])) or 'patch'}: {e['msg']}" for e in error.errors())) from error


def _skip_option(step_id: str) -> RecoveryOption:
    return RecoveryOption(id="skip", label=SKIP_LABELS.get(step_id, "Skip this step"), description="Continue without this step; the plan flags the gap as a risk.", action="skip")


def _finalise(step_id: str, options: list[RecoveryOption]) -> list[RecoveryOption]:
    cleaned: list[RecoveryOption] = []
    seen: set[str] = set()
    for option in options:
        if option.action == "skip" or option.id in seen:
            continue
        try:
            option.patch = validate_patch(step_id, option.patch)
        except ValueError:
            continue
        if option.action == "retry_with" and not option.patch:
            option.action = "retry"
        option.label = option.label[:40]
        seen.add(option.id)
        cleaned.append(option)
    if not any(option.action == "retry" for option in cleaned):
        cleaned.append(RecoveryOption(id="retry", label="Try again as is", description="Run the step again with the same inputs.", action="retry"))
    cleaned = cleaned[:4]
    if step_id not in NOT_SKIPPABLE:
        cleaned.append(_skip_option(step_id))
    return cleaned


def rule_proposal(step_id: str, error: str, event: EventBrief, overrides: dict[str, Any], context: dict[str, Any] | None = None) -> RecoveryProposal:
    options: list[RecoveryOption] = []
    agent = {"logistics_agent": "Logistics", "finance_agent": "Finance", "schedule_agent": "Schedule", "requirements_agent": "Requirements", "marketing_agent": "Marketing", "risk_operations_agent": "Risk & Operations", "event_manager": "The Event Manager", "recommendations": "The summary writer"}.get(step_id, "This step")
    check_failed = error.startswith("Check failed")
    if not check_failed:
        # A tool or model error, not a bad result: retrying usually works.
        short = error.split(". Simulated")[0]
        proposal = RecoveryProposal(summary=f"I couldn't finish the {agent.lower()} step: {short}.", cause=error, options=[], customPrompt="Tell me what to change", source="rules")
        extra = [RecoveryOption(id="use-fallback", label="Use the rule-based planner", description="Build the plan from the specialists' results without the LLM.", patch={"use_fallback": True})] if step_id == "event_manager" else []
        proposal.options = _finalise(step_id, [RecoveryOption(id="retry", label="Try again as is", description="Run the step again; temporary errors usually clear.", action="retry"), *extra])
        return proposal
    summary = f"I couldn't confirm the {agent.lower()} step: {error.removeprefix('Check failed: ')}"
    if step_id == "logistics_agent":
        share = int(overrides.get("venue_share_pct") or 30)
        location = overrides.get("location") or event.location
        guests = overrides.get("attendees") or event.attendees
        summary = f"Logistics couldn't confirm a venue in {location} for {guests} guests."
        near = context or {}
        if near.get("reason") == "over_budget" and near.get("venue_share_needed_pct", 100) <= 60:
            fit, needed = near["cheapest_fit"], near["venue_share_needed_pct"]
            summary = f"No venue in {location} fits {guests} guests within {share}% of the budget. {fit['name']} fits for {inr(fit['rental_inr'])}, which needs {needed}%."
            options.append(RecoveryOption(id="raise-venue-share", label=f"Raise venue share to {needed}%", description=f"Allow {inr(fit['rental_inr'])} for venue rent so {fit['name']} fits.", patch={"venue_share_pct": needed}))
        elif near.get("reason") == "too_small":
            biggest = near["largest"]
            summary = f"No venue in {location} holds {guests} guests; the largest, {biggest['name']}, takes {biggest['capacity']}."
            options.append(RecoveryOption(id="fewer-guests", label=f"Plan for {biggest['capacity']} guests", description=f"Fits {biggest['name']} in {biggest['area']}.", patch={"attendees": biggest["capacity"]}))
        elif near.get("reason") == "city_not_in_catalog":
            summary = f"The venue catalogue doesn't cover {location} yet."
            for city in [c for c in near.get("known_cities", []) if c.lower() not in location.lower()][:2]:
                options.append(RecoveryOption(id=f"city-{city.lower().replace(' ', '-')}", label=f"Search {city} instead", description=f"Look for venues in {city}.", patch={"location": city}))
        elif share < 45:
            options.append(RecoveryOption(id="raise-venue-share", label=f"Raise venue share to {share + 10}%", description=f"Allow up to {share + 10}% of {inr(event.budget)} for venue rent.", patch={"venue_share_pct": share + 10}))
        options.append(RecoveryOption(id="accept-unverified", label="Use an unverified venue", description="Continue with a venue outside the catalog; it is flagged in the plan.", patch={"allow_unverified": True}))
    elif step_id == "finance_agent":
        options.append(RecoveryOption(id="contingency-8", label="Use 8% contingency", description="Rebuild the lines with an 8% contingency reserve.", patch={"contingency_pct": 8}))
    elif step_id == "schedule_agent":
        options.append(RecoveryOption(id="five-sessions", label="Plan five sessions", description="Rebuild the agenda with five items.", patch={"session_count": 5}))
    elif step_id == "event_manager":
        summary = "The Event Manager couldn't combine the specialist results into a valid plan."
        options.append(RecoveryOption(id="use-fallback", label="Use the rule-based planner", description="Build the plan from the specialists' results without the LLM.", patch={"use_fallback": True}))
    return RecoveryProposal(summary=summary, cause=error, options=_finalise(step_id, options), customPrompt="Tell me what to change", source="rules")


class _LlmProposal(BaseModel):
    summary: str = Field(description="One warm, plain sentence on what went wrong, naming the numbers involved, e.g. 'We couldn't find a venue for 500 guests within 30% of the budget.' No jargon, no apology.")
    options: list[RecoveryOption] = Field(description="2-3 concrete ways forward. Use action 'retry_with' with a patch, or 'retry'. Do not include a skip option.")
    custom_prompt: str = Field(description="Short placeholder for the free-text field, e.g. 'Try another city or a guest count'.")


async def explain_failure(step_id: str, goal: str, error: str, event: EventBrief, overrides: dict[str, Any], attempt: int, config: dict | None = None, context: dict[str, Any] | None = None) -> RecoveryProposal:
    if not llm_enabled():
        return rule_proposal(step_id, error, event, overrides, context)
    fields = allowed_fields(step_id)
    prompt = (
        f"A step in an event-planning run failed.\nStep: {step_id} — goal: {goal}\nAttempt: {attempt}\n"
        f"Error (verbatim): {error}\nBrief: {event.name}, {event.attendees} guests, {event.location}, budget INR {event.budget}, date {event.event_date}.\n"
        f"Current adjustments: {overrides or 'none'}\n"
        f"What the tools found (use these numbers in your options): {context or 'nothing more'}\n"
        f"Options may only change these inputs (patch keys): {fields or 'none — use action retry'}.\n"
        "Explain the failure in one sentence a non-technical event owner understands, then suggest 2-3 options that are likely to succeed. "
        "Labels start with a verb and are at most 40 characters."
    )
    try:
        model = get_chat_model().with_structured_output(_LlmProposal, method="function_calling")
        async with limited():
            draft = await model.ainvoke([SystemMessage(PLANNER_VOICE + " When a step fails, explain it in one friendly sentence, offer two or three options the owner can pick, and invite them to describe their own change."), HumanMessage(prompt)], config=config)
        return RecoveryProposal(summary=draft.summary, cause=error, options=_finalise(step_id, list(draft.options)), customPrompt=draft.custom_prompt or "Tell me what to change", source="llm")
    except Exception:
        return rule_proposal(step_id, error, event, overrides, context)


class _Interpretation(BaseModel):
    understood: bool = Field(description="True if the request maps to the allowed inputs or to skipping the step.")
    skip: bool = Field(default=False, description="True if the user wants to skip this step.")
    patch: dict[str, Any] = Field(default_factory=dict, description="Inputs to change; only allowed keys.")
    label: str = Field(default="", description="Short label for what will change, at most 40 characters.")
    question: str = Field(default="", description="If not understood: one short question naming what can be changed.")


def _rule_interpret(step_id: str, text: str) -> tuple[RecoveryOption | None, str | None]:
    lowered = text.lower().strip()
    if re.search(r"\bskip\b", lowered):
        return _skip_option(step_id), None
    patch: dict[str, Any] = {}
    if guests := re.search(r"(\d{1,6})\s*(guests|people|pax|attendees)", lowered):
        patch["attendees"] = int(guests.group(1))
    if pct := re.search(r"(\d{1,2})\s*%", lowered):
        patch["venue_share_pct" if step_id == "logistics_agent" else "contingency_pct"] = int(pct.group(1))
    if step_id == "logistics_agent":
        place = re.search(r"\b(?:in|at|near|around)\s+([a-z][a-z .'-]{1,40})", lowered) or re.search(r"\b(?:try|search)\s+([a-z][a-z .'-]{1,40})", lowered)
        if place:
            words = [w for w in place.group(1).strip(" .").split() if w not in {"instead", "please", "then", "maybe", "city", "area"}]
            if words:
                patch["location"] = " ".join(words).title()
    if "unverified" in lowered or "outside the catalog" in lowered:
        patch["allow_unverified"] = True
    allowed = set(allowed_fields(step_id))
    patch = {key: value for key, value in patch.items() if key in allowed}
    if not patch:
        names = ", ".join(field.replace("_", " ") for field in allowed) or "nothing; you can retry or skip"
        return None, f"I can adjust {names} for this step. What would you like to change? For example, 'try 450 guests' or 'move it to Pune'."
    return RecoveryOption(id="custom", label=text[:40], description="Your instruction", action="retry_with", patch=patch), None


async def interpret_custom(step_id: str, text: str, event: EventBrief, overrides: dict[str, Any], config: dict | None = None) -> tuple[RecoveryOption | None, str | None]:
    """Returns (option, None) when understood, else (None, clarifying question)."""
    if not llm_enabled():
        option, question = _rule_interpret(step_id, text)
    else:
        fields = allowed_fields(step_id)
        try:
            model = get_chat_model().with_structured_output(_Interpretation, method="function_calling")
            async with limited():
                result = await model.ainvoke([
                    SystemMessage(PLANNER_VOICE + " Map the owner's instruction for a failed step to input changes, using only the allowed keys. If it is unclear, ask one friendly question with a short example. " + DATA_RULE),
                    HumanMessage(f"Step: {step_id}\nAllowed keys: {fields}\nBrief: {event.attendees} guests, {event.location}, budget INR {event.budget}\nCurrent adjustments: {overrides or 'none'}\nInstruction:\n{wrap_user(text)}"),
                ], config=config)
            if result.skip:
                return (_skip_option(step_id), None) if step_id not in NOT_SKIPPABLE else (None, "This step can't be skipped. What should I change?")
            if not result.understood or not result.patch:
                return None, result.question or f"I can adjust {', '.join(fields)} for this step. What would you like to change?"
            option = RecoveryOption(id="custom", label=(result.label or text)[:40], description=f"Your instruction: {text[:120]}", action="retry_with", patch=result.patch)
            question = None
        except Exception:
            option, question = _rule_interpret(step_id, text)
    if option and option.action != "skip":
        try:
            option.patch = validate_patch(step_id, option.patch)
        except ValueError as error:
            return None, f"I couldn't use that ({error}). Try another value."
    if option and option.action == "skip" and step_id in NOT_SKIPPABLE:
        return None, "This step can't be skipped. What should I change?"
    return option, question
