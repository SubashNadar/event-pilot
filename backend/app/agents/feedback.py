"""Reads what the owner writes at approval and decides what it means for the plan.

One structured LLM call classifies the message by intent, not keywords:

- `question`: answer it from the plan; nothing is re-planned and no change is used.
- `edit`: a concrete change (guest count, date, a budget line, an agenda time…),
  applied by `plan_edit.prepare` so only the affected specialists run again.
- `feedback`: a judgement about the plan ("feels too formal", "the risks are
  vague"). The model assigns it to the specialists who own that part, each with
  a note; code adds the teammates that depend on them (a new venue changes the
  rent line, so Finance follows Logistics).
- `unclear`: one short question back, and nothing changes.

Without Azure OpenAI the rule-based parser and a keyword table stand in, so the
app still works offline; with the LLM on, keywords are never used for routing.
"""

import re
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.agents.judge import OWNERS
from app.agents.llm import get_chat_model, limited, llm_enabled
from app.agents.plan_edit import PlanEdit, answer_from_plan, plan_context, rule_parse
from app.core.guard import DATA_RULE, wrap_user
from app.models.event import EventBrief

# Who owns which part of the plan, for the model and for the owner-facing summary.
OWNERSHIP = {
    "logistics_agent": "the venue, its location, capacity and rent",
    "finance_agent": "the budget lines, vendor spend (catering, decor, photography) and contingency",
    "schedule_agent": "the event-day agenda: order, timings and flow",
    "requirements_agent": "operational needs: staffing, equipment, accessibility, permits",
    "marketing_agent": "guest communication: invitations, RSVPs, reminders, tone of messages",
    "risk_operations_agent": "the risk register and the fallback for each risk",
}
# A change to the key's part makes these specialists' work stale too.
DEPENDENTS = {"logistics_agent": ["finance_agent"]}

# Offline fallback only: keyword owners for feedback when no model is configured.
RULE_OWNERS = [
    (("venue", "hall", "rent", "logistics", "location"), ["logistics_agent"]),
    (("budget", "cost", "contingency", "catering", "food", "decor", "photograph", "vendor", "spend", "cheaper", "expensive"), ["finance_agent"]),
    (("agenda", "schedule", "timing", "time", "session", "earlier", "later"), ["schedule_agent"]),
    (("requirement", "staff", "equipment", "accessib", "wheelchair", "permit", "security"), ["requirements_agent"]),
    (("invite", "invitation", "rsvp", "communication", "message", "reminder", "marketing", "promotion"), ["marketing_agent"]),
    (("risk", "fallback", "backup", "weather", "contingency plan"), ["risk_operations_agent"]),
]


class Assignment(BaseModel):
    owner: OWNERS = Field(description="The specialist who owns this part of the plan.")
    note: str = Field(max_length=300, description="What this specialist should change, in one sentence, faithful to the owner's words.")


class OwnerFeedback(BaseModel):
    """What the owner's message at approval means for the plan."""

    kind: Literal["question", "edit", "feedback", "unclear"] = Field(description=(
        "question: the owner asks something and wants an answer, not a change. "
        "edit: a concrete change with a value (guest count, budget, date, city, event name, a specific venue, an agenda item and time, "
        "an amount for a budget line, an added requirement), or an explicit request to change the event's objective. "
        "feedback: an opinion or direction about the plan's quality, tone, feel or completeness without exact values. "
        "unclear: you can't tell what should change."
    ))
    answer: str | None = Field(default=None, description="For a question: a short answer from the plan.")
    question: str | None = Field(default=None, description="For unclear: one short question naming what you need.")
    edit: PlanEdit | None = Field(default=None, description="For edit: only the fields the owner asked to change.")
    assignments: list[Assignment] = Field(default_factory=list, max_length=6, description="For feedback: one entry per specialist whose part must change. Fewest specialists that address it.")
    reason: str = Field(default="", max_length=200, description="One short sentence on how you read the message.")


def with_dependents(owners: list[str]) -> list[str]:
    """The owners plus the specialists whose work builds on theirs, in a stable order."""
    result = list(dict.fromkeys(owners))
    for owner in list(result):
        result += [step for step in DEPENDENTS.get(owner, []) if step not in result]
    return result


def rule_owners(text: str) -> list[str]:
    lowered = text.lower()
    owners: list[str] = []
    for words, steps in RULE_OWNERS:
        if any(word in lowered for word in words):
            owners += [step for step in steps if step not in owners]
    return owners


def _rule_route(text: str, event: EventBrief, plan: dict) -> OwnerFeedback:
    edit = rule_parse(text)
    if edit.is_change():
        return OwnerFeedback(kind="edit", edit=edit, reason="A concrete change")
    if edit.answer is not None:
        return OwnerFeedback(kind="question", answer=answer_from_plan(text, event, plan), reason="A question about the plan")
    owners = rule_owners(text)
    if owners:
        return OwnerFeedback(kind="feedback", assignments=[{"owner": owner, "note": text} for owner in owners], reason="Feedback on the plan")
    return OwnerFeedback(kind="unclear", question="Which part should change: the venue, budget, agenda, requirements, guest communication or risks? For example: “lower the decor spend” or “guest count to 150”.")


async def route_feedback(text: str, event: EventBrief, plan: dict, reports: dict, config: dict | None = None) -> tuple[OwnerFeedback, str]:
    """Returns (route, mode). The LLM decides intent and owners; rules are the offline fallback."""
    if not llm_enabled():
        return _rule_route(text, event, plan), "rules"
    if re.search(r"\b(?:change|rename|update|set)\s+(?:the\s+)?(?:event\s+)?name\s+(?:to|as)\b", text, re.I):
        return _rule_route(text, event, plan), "rules"  # a name change is unambiguous; see plan_edit.interpret
    owners = "\n".join(f"- {step}: {what}" for step, what in OWNERSHIP.items())
    try:
        model = get_chat_model().with_structured_output(OwnerFeedback, method="function_calling")
        async with limited():
            route = await model.ainvoke([
                SystemMessage(
                    "You are the Event Manager. The event owner is reviewing the plan below before approving it and wrote a message. "
                    "Decide what they mean by its intent and context, not by the words it happens to use. "
                    "Never treat feedback about tone, feel, style or quality as a change to the brief: the objective changes only when the owner "
                    "explicitly asks to change the event's objective or purpose. A question gets an answer and changes nothing. "
                    "For feedback, assign it to the fewest specialists whose part of the plan must change:\n" + owners + "\n"
                    "Times are 12-hour like '9:00 PM'; amounts are whole rupees (2 lakh = 200000). " + DATA_RULE
                ),
                HumanMessage("Current plan:\n" + wrap_user(plan_context(event, plan, reports), "brief") + "\n\nOwner's message:\n" + wrap_user(text)),
            ], config=config)
    except Exception:
        return _rule_route(text, event, plan), "rules"
    if route.kind == "edit" and not (route.edit and route.edit.is_change()):
        route = OwnerFeedback(kind="unclear", question=route.question or "What exactly should change? For example: “guest count to 150” or “move lunch to 1:30 PM”.")
    if route.kind == "feedback" and not route.assignments:
        route = OwnerFeedback(kind="unclear", question=route.question or "Which part of the plan should change?")
    if route.kind == "question" and not route.answer:
        route.answer = answer_from_plan(text, event, plan)
    return route, "llm"


def assignment_notes(route: OwnerFeedback, text: str) -> dict[str, list[str]]:
    """Per-specialist notes for the re-plan, with each dependent told why it runs again."""
    notes: dict[str, list[str]] = {}
    for item in route.assignments:
        notes.setdefault(item.owner, []).append(item.note or text)
    for owner, dependents in DEPENDENTS.items():
        if owner in notes:
            for step in dependents:
                notes.setdefault(step, []).append("Logistics is revising the venue; keep your part consistent with its new handoff.")
    return notes
