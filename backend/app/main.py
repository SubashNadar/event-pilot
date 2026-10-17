from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.events import router as events_router
from app.api.routes.chat import router as chat_router
from app.api.routes.rag import router as rag_router
from app.core.config import settings
from app.services.storage import initialize_storage
from app.services.rag import initialize_rag_storage

app = FastAPI(title=settings.app_name, version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(events_router, prefix=settings.api_prefix)
app.include_router(chat_router, prefix=settings.api_prefix)
app.include_router(rag_router, prefix=settings.api_prefix)


@app.on_event("startup")
def startup() -> None:
    initialize_storage()
    initialize_rag_storage()


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok", "provider": settings.llm_provider}
