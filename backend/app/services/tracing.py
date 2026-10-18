"""Optional Langfuse instrumentation for AI planning calls."""

import os
from typing import Any

from app.core.config import settings
from app.models.event import EventBrief


def configure_langfuse_env() -> None:
    """The SDK reads standard environment variables. Populate them from Settings so
    both LANGFUSE_BASE_URL and the existing LANGFUSE_HOST configuration work."""
    os.environ.setdefault("LANGFUSE_PUBLIC_KEY", settings.langfuse_public_key or "")
    os.environ.setdefault("LANGFUSE_SECRET_KEY", settings.langfuse_secret_key or "")
    os.environ.setdefault("LANGFUSE_BASE_URL", settings.resolved_langfuse_base_url)
    os.environ.setdefault("LANGFUSE_TRACING_ENVIRONMENT", settings.langfuse_tracing_environment)


def get_langfuse_config(event: EventBrief, operation: str) -> dict[str, Any]:
    """Return LangChain callbacks and trace attributes for one planning request."""
    if not settings.langfuse_enabled:
        return {}
    configure_langfuse_env()

    try:
        from langfuse.langchain import CallbackHandler
    except ImportError:
        return {}

    return {
        "callbacks": [CallbackHandler()],
        "run_name": f"eventpilot-{operation}",
        "metadata": {
            "langfuse_session_id": str(event.id),
            "langfuse_tags": ["eventpilot", operation, "azure-openai"],
            "event_id": str(event.id),
            "event_type": event.name,
        },
    }
