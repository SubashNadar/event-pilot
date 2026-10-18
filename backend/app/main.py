from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.chat import event_chat_router, router as chat_router
from app.api.routes.events import router as events_router
from app.api.routes.rag import router as rag_router
from app.api.routes.runs import router as runs_router
from app.core.config import settings
from app.core.guard import BodySizeMiddleware, RateLimitMiddleware
from app.runs.manager import run_manager
from app.services.rag import initialize_rag_storage
from app.services.storage import initialize_storage


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_storage()
    initialize_rag_storage()
    await run_manager.startup()
    yield
    await run_manager.shutdown()


app = FastAPI(title=settings.app_name, version="0.2.0", lifespan=lifespan)
# Added first so CORS (added last, outermost) still decorates 429 and 413 replies.
app.add_middleware(RateLimitMiddleware)
app.add_middleware(BodySizeMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(events_router, prefix=settings.api_prefix)
app.include_router(chat_router, prefix=settings.api_prefix)
app.include_router(event_chat_router, prefix=settings.api_prefix)
app.include_router(rag_router, prefix=settings.api_prefix)
app.include_router(runs_router, prefix=settings.api_prefix)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok", "provider": settings.llm_provider, "llm": "azure" if settings.azure_openai_enabled else "rules"}
