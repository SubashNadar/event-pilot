"""PostgreSQL/pgvector document ingestion and grounded retrieval services."""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path

import psycopg
from langchain_openai import AzureOpenAIEmbeddings
from pgvector import Vector
from pgvector.psycopg import register_vector

from app.core.config import settings
from app.models.rag import RagCitation, RagQueryResponse
from app.services.azure_planner import get_azure_model

logger = logging.getLogger(__name__)
KNOWLEDGE_DIRECTORY = Path("knowledge")
TABLE_NAME = "eventpilot_knowledge_chunks"


class RagUnavailableError(RuntimeError):
    """Raised when RAG configuration or its backing services are unavailable."""


def _embeddings() -> AzureOpenAIEmbeddings:
    if not settings.azure_embeddings_enabled:
        raise RagUnavailableError("Azure embedding configuration is incomplete")
    return AzureOpenAIEmbeddings(api_key=settings.azure_openai_api_key, azure_endpoint=settings.azure_openai_endpoint, openai_api_version=settings.azure_openai_api_version, azure_deployment=settings.azure_openai_embedding_deployment)


def _connection() -> psycopg.Connection:
    if not settings.postgres_enabled:
        raise RagUnavailableError("PostgreSQL configuration is incomplete")
    connection = psycopg.connect(settings.postgres_dsn, connect_timeout=8)
    register_vector(connection)
    return connection


def _chunk_text(content: str, size: int = 900, overlap: int = 160) -> list[str]:
    normalized = re.sub(r"\s+", " ", content).strip()
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(start + size, len(normalized))
        if end < len(normalized):
            boundary = normalized.rfind(". ", start, end)
            if boundary > start + size // 2:
                end = boundary + 1
        chunks.append(normalized[start:end].strip())
        if end >= len(normalized):
            break
        start = max(end - overlap, start + 1)
    return chunks


def initialize_rag_storage() -> None:
    """Create schema without making application startup dependent on RAG availability."""
    if not settings.postgres_enabled:
        return
    try:
        with _connection() as connection, connection.cursor() as cursor:
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cursor.execute(f"CREATE TABLE IF NOT EXISTS {TABLE_NAME} (id TEXT PRIMARY KEY, collection_name TEXT NOT NULL, source TEXT NOT NULL, title TEXT NOT NULL, chunk_index INTEGER NOT NULL, content TEXT NOT NULL, embedding vector({settings.rag_embedding_dimensions}) NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now())")
            cursor.execute(f"CREATE INDEX IF NOT EXISTS {TABLE_NAME}_collection_idx ON {TABLE_NAME} (collection_name)")
            try:
                cursor.execute(f"CREATE INDEX IF NOT EXISTS {TABLE_NAME}_embedding_idx ON {TABLE_NAME} USING hnsw (embedding vector_cosine_ops)")
            except psycopg.Error:
                logger.warning("pgvector HNSW index could not be created; retrieval remains available")
    except Exception as error:
        logger.warning("RAG storage initialization skipped: %s", error)


def ingest_document(source: str, title: str, content: str) -> int:
    chunks = _chunk_text(content)
    vectors = _embeddings().embed_documents(chunks)
    if any(len(vector) != settings.rag_embedding_dimensions for vector in vectors):
        raise RagUnavailableError("Embedding dimensions do not match RAG_EMBEDDING_DIMENSIONS")
    with _connection() as connection, connection.cursor() as cursor:
        cursor.execute(f"DELETE FROM {TABLE_NAME} WHERE collection_name = %s AND source = %s", (settings.collection_name, source))
        for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
            identifier = hashlib.sha256(f"{settings.collection_name}:{source}:{index}:{chunk}".encode()).hexdigest()
            cursor.execute(f"INSERT INTO {TABLE_NAME} (id, collection_name, source, title, chunk_index, content, embedding) VALUES (%s, %s, %s, %s, %s, %s, %s)", (identifier, settings.collection_name, source, title, index, chunk, Vector(vector)))
    return len(chunks)


def ingest_local_knowledge() -> dict[str, int]:
    results: dict[str, int] = {}
    for path in sorted((*KNOWLEDGE_DIRECTORY.glob("*.md"), *KNOWLEDGE_DIRECTORY.glob("*.txt"))):
        results[path.name] = ingest_document(path.name, path.stem.replace("-", " ").title(), path.read_text(encoding="utf-8"))
    return results


def retrieve(question: str, top_k: int | None = None) -> list[RagCitation]:
    query_vector = _embeddings().embed_query(question)
    with _connection() as connection, connection.cursor() as cursor:
        vector = Vector(query_vector)
        cursor.execute(f"SELECT source, title, content, 1 - (embedding <=> %s) AS relevance FROM {TABLE_NAME} WHERE collection_name = %s ORDER BY embedding <=> %s LIMIT %s", (vector, settings.collection_name, vector, top_k or settings.rag_top_k))
        rows = cursor.fetchall()
    return [RagCitation(source=row[0], title=row[1], excerpt=row[2], relevance=round(float(row[3]), 3)) for row in rows if float(row[3]) >= settings.rag_min_relevance_score]


def answer_question(question: str, top_k: int | None = None) -> RagQueryResponse:
    citations = retrieve(question, top_k)
    if not citations:
        return RagQueryResponse(answer="I do not have a verified EventPilot knowledge source that answers that question yet.", grounded=False)
    context = "\n\n".join(f"Source: {citation.title}\n{citation.excerpt}" for citation in citations)
    if not settings.azure_openai_enabled:
        return RagQueryResponse(answer=citations[0].excerpt, grounded=True, citations=citations)
    response = get_azure_model().invoke("Answer only from the verified context below. Be concise. If the context does not answer the question, say so. " f"\n\nQuestion: {question}\n\nVerified context:\n{context}")
    return RagQueryResponse(answer=str(response.content).strip(), grounded=True, citations=citations)
