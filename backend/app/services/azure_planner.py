import json
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_openai import AzureChatOpenAI

from app.core.config import settings
from app.models.event import AiPlanDraft, EventBrief, EventPlan
from app.services.tracing import get_langfuse_config


def get_azure_model() -> AzureChatOpenAI:
    if not settings.azure_openai_enabled:
        raise RuntimeError("Azure OpenAI is not fully configured")

    return AzureChatOpenAI(
        api_key=settings.azure_openai_api_key,
        azure_endpoint=settings.azure_openai_endpoint,
        api_version=settings.azure_openai_api_version,
        azure_deployment=settings.azure_openai_deployment_name,
    )


def validate_azure_connection() -> None:
    """Send a minimal request to verify credentials and deployment access."""
    get_azure_model().invoke("Reply with exactly: ready")


def build_azure_plan(
    event: EventBrief,
    operation: str = "plan-generation",
    specialist_context: dict[str, Any] | None = None,
    tracing_config: RunnableConfig | None = None,
) -> EventPlan:
    structured_model = get_azure_model().with_structured_output(AiPlanDraft, method="function_calling")
    prompt = f"""
You are the Event Manager in an autonomous event-planning team.
Create a practical, concise event plan from this brief:

- Name: {event.name}
- Date: {event.event_date}
- Location: {event.location}
- Attendees: {event.attendees}
- Budget in INR: {event.budget}
- Objective: {event.objective}

Return a complete structured plan. Use only 12-hour time labels with AM or PM.
Keep the budget forecast at or below the budget. Include six budget lines whose
amounts add up to the forecast, five agenda items, and between two and five
practical risks scaled to the event size and complexity. Include three concise
agent activity entries. Use birthday-appropriate details when
the event is a birthday or celebration.
"""
    if specialist_context:
        prompt += "\nVerified specialist planning context:\n"
        prompt += json.dumps(specialist_context, separators=(",", ":"))
        prompt += "\nUse this context for venue, budget, schedule, marketing, and risk decisions."
    draft = structured_model.invoke(prompt, config=tracing_config or get_langfuse_config(event, operation))
    return EventPlan(event_id=event.id, source="azure", **draft.model_dump())
