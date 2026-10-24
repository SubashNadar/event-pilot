"""LLM judge for the combined plan: checks what the rule checks can't see.

The rule review in `event_workflow._review` checks arithmetic and structure. This
judge reads the whole plan against the brief and says whether it is good enough
for the owner, and if not, which specialist should fix what. It only runs when
Azure OpenAI is configured; rule-based runs skip it.
"""

import json
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.agents import llm
from app.core.guard import DATA_RULE, wrap_user

OWNERS = Literal["logistics_agent", "finance_agent", "schedule_agent", "requirements_agent", "marketing_agent", "risk_operations_agent"]


class JudgedFeedback(BaseModel):
    owner: OWNERS = Field(description="The specialist who should fix this.")
    note: str = Field(max_length=300, description="What is wrong and what to change, in one or two sentences.")


class PlanJudgement(BaseModel):
    satisfied: bool = Field(description="True if the plan is good enough for the event owner to review.")
    feedback: list[JudgedFeedback] = Field(default_factory=list, max_length=6, description="Empty when satisfied.")


async def judge_plan(event: dict[str, Any], plan: dict[str, Any], reports: dict[str, Any]) -> tuple[PlanJudgement, dict[str, int]]:
    model = llm.get_chat_model().with_structured_output(PlanJudgement, method="function_calling", include_raw=True)
    prompt = (
        "You are the Event Manager. Judge this combined event plan before the owner sees it. "
        "Check what arithmetic can't: is the venue realistic for the guest count, does the agenda make sense for the event, "
        "are the risks specific with a usable fallback, is the guest communication suitable. "
        "Be strict about real problems and lenient about style. If the plan is good enough, return satisfied=true with no feedback. "
        "Otherwise name the specialist who should fix each problem and say what to change. "
        f"{DATA_RULE}\n"
        f"{wrap_user(json.dumps(event, default=str), 'brief')}\n"
        f"{wrap_user(json.dumps(plan, default=str), 'brief')}\n"
        f"{wrap_user(json.dumps(reports, default=str), 'brief')}"
    )
    async with llm.limited():
        output = await model.ainvoke([SystemMessage("You review event plans for quality. Respond only with the requested structure."), HumanMessage(prompt)])
    parsed = output.get("parsed") if isinstance(output, dict) else None
    if parsed is None:
        raise ValueError("The plan judge returned no verdict")
    return parsed, llm.usage_of(output)
