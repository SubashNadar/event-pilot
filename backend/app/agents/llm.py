"""Shared LLM access for the planning agents.

All agent code gets its chat model through `get_chat_model()`, so tests can swap
in a fake model by setting `MODEL_FACTORY`. Azure calls are throttled with a
semaphore: six parallel specialists can otherwise exhaust a deployment's TPM.
"""

import asyncio
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any

from langchain_core.language_models import BaseChatModel

from app.core.config import settings

MODEL_FACTORY: Callable[[], BaseChatModel] | None = None

_semaphores: dict[int, asyncio.Semaphore] = {}


def llm_enabled() -> bool:
    return MODEL_FACTORY is not None or settings.azure_openai_enabled


def model_name() -> str:
    return settings.azure_openai_deployment_name or "azure-openai"


def get_chat_model() -> BaseChatModel:
    if MODEL_FACTORY is not None:
        return MODEL_FACTORY()
    from app.services.azure_planner import get_azure_model

    return get_azure_model()


@asynccontextmanager
async def limited():
    loop_id = id(asyncio.get_running_loop())
    semaphore = _semaphores.setdefault(loop_id, asyncio.Semaphore(max(1, settings.max_parallel_llm_calls)))
    async with semaphore:
        yield


def usage_of(message: Any) -> dict[str, int]:
    """Token usage from an AIMessage (or a with_structured_output include_raw dict)."""
    if isinstance(message, dict):
        message = message.get("raw")
    metadata = getattr(message, "usage_metadata", None) or {}
    return {"tokens_in": int(metadata.get("input_tokens", 0) or 0), "tokens_out": int(metadata.get("output_tokens", 0) or 0)}


def cost_usd(tokens_in: int, tokens_out: int) -> float:
    return round(tokens_in / 1000 * settings.llm_cost_per_1k_input + tokens_out / 1000 * settings.llm_cost_per_1k_output, 4)
