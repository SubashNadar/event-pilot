"""Semantic search with Azure OpenAI embeddings (optional).

Embeddings capture meaning rather than exact words, so "somewhere by the sea" can
match a venue described as "beachfront". Vectors are cached on disk so the catalog
is embedded once, not on every request. Without an embedding deployment the
search falls back to BM25 alone and says so in its result.
"""

import hashlib
import json
import logging
import math
import threading
from collections.abc import Callable
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)

# Tests (or another provider) can plug in a function: list[str] -> list[list[float]].
EMBED_FACTORY: Callable[[list[str]], list[list[float]]] | None = None

_lock = threading.Lock()
_cache: dict[str, list[float]] | None = None


def _cache_path() -> Path:
    return Path(settings.data_dir) / "embeddings-cache.json"


def enabled() -> bool:
    return EMBED_FACTORY is not None or settings.azure_embeddings_enabled


def _key(text: str) -> str:
    model = "custom" if EMBED_FACTORY else (settings.azure_openai_embedding_deployment or "")
    return hashlib.sha256(f"{model}\n{text}".encode()).hexdigest()


def _load() -> dict[str, list[float]]:
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(_cache_path().read_text()) if _cache_path().exists() and EMBED_FACTORY is None else {}
        except Exception:
            _cache = {}
    return _cache


def _embed_uncached(texts: list[str]) -> list[list[float]]:
    if EMBED_FACTORY is not None:
        return EMBED_FACTORY(texts)
    from langchain_openai import AzureOpenAIEmbeddings

    client = AzureOpenAIEmbeddings(api_key=settings.azure_openai_api_key, azure_endpoint=settings.azure_openai_endpoint, openai_api_version=settings.azure_openai_api_version, azure_deployment=settings.azure_openai_embedding_deployment)
    return client.embed_documents(texts)


def embed(texts: list[str]) -> list[list[float]] | None:
    """Vectors for `texts`, or None when semantic search is unavailable."""
    if not enabled() or not texts:
        return None
    with _lock:
        cache = _load()
        missing = [text for text in dict.fromkeys(texts) if _key(text) not in cache]
        if missing:
            try:
                for text, vector in zip(missing, _embed_uncached(missing), strict=True):
                    cache[_key(text)] = vector
                if EMBED_FACTORY is None:
                    _cache_path().parent.mkdir(parents=True, exist_ok=True)
                    _cache_path().write_text(json.dumps(cache))
            except Exception:
                logger.warning("Embedding request failed; falling back to keyword search", exc_info=True)
                return None
        return [cache[_key(text)] for text in texts]


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def rank(query: str, documents: list[str], candidates: list[int], min_similarity: float = 0.0) -> list[int] | None:
    """Candidate indices ordered by similarity to the query, or None if unavailable."""
    if not query.strip() or not candidates:
        return [] if enabled() else None
    vectors = embed([query] + [documents[i] for i in candidates])
    if vectors is None:
        return None
    query_vector, doc_vectors = vectors[0], vectors[1:]
    scored = [(cosine(query_vector, vector), index) for vector, index in zip(doc_vectors, candidates)]
    return [index for score, index in sorted(scored, reverse=True) if score > min_similarity]


def reset_cache() -> None:
    global _cache
    with _lock:
        _cache = None
