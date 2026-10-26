"""
app/rag/embed.py  —  Dense embedding via Ollama nomic-embed-text

Design:
- Calls Ollama /api/embeddings with a configurable timeout (default 2 s).
- In-process LRU cache (up to 2,048 texts) avoids redundant API calls.
- Returns None on any network or service error; callers must treat None as
  "offline" and fall back to BM25-only retrieval.
- Never raises: all errors are swallowed and logged at WARNING level.
"""

import logging
import hashlib
import threading
from functools import lru_cache
from typing import Optional, List

import requests

from app.config import Config

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS: float = 2.0
_EMBED_LOCK = threading.Lock()

# Thread-safe LRU cache keyed by text hash → embedding list
_EMBED_CACHE: dict = {}
_MAX_CACHE_SIZE = 2048


def _cache_key(text: str) -> str:
    """SHA-256 truncated to 16 hex chars — collision-safe for our corpus size."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def embed_text(text: str) -> Optional[List[float]]:
    """
    Fetch a dense embedding vector for *text* from Ollama nomic-embed-text.

    Returns:
        List[float]  — embedding vector on success.
        None         — if Ollama is unreachable, the model is not pulled, or
                       the response is malformed.
    """
    if not Config.OLLAMA_EMBED_MODEL or not Config.OLLAMA_BASE_URL:
        return None

    key = _cache_key(text)
    with _EMBED_LOCK:
        if key in _EMBED_CACHE:
            return _EMBED_CACHE[key]

    try:
        resp = requests.post(
            f"{Config.OLLAMA_BASE_URL}/api/embeddings",
            json={"model": Config.OLLAMA_EMBED_MODEL, "prompt": text},
            timeout=_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        payload = resp.json()
        vector = payload.get("embedding")
        if not vector or not isinstance(vector, list):
            logger.warning("embed_text: unexpected response shape from Ollama embeddings API.")
            return None

        with _EMBED_LOCK:
            if len(_EMBED_CACHE) >= _MAX_CACHE_SIZE:
                # Evict oldest quarter when cache is full (simple FIFO trim)
                evict_count = _MAX_CACHE_SIZE // 4
                for old_key in list(_EMBED_CACHE.keys())[:evict_count]:
                    del _EMBED_CACHE[old_key]
            _EMBED_CACHE[key] = vector

        return vector

    except requests.exceptions.ConnectionError:
        # Ollama not running — expected in offline / test environments
        return None
    except requests.exceptions.Timeout:
        logger.warning("embed_text: Ollama embedding request timed out (%.1fs).", _TIMEOUT_SECONDS)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("embed_text: unexpected error fetching embedding: %s", exc)
        return None


def embed_batch(texts: List[str]) -> List[Optional[List[float]]]:
    """
    Embed a list of texts. Returns a list of vectors (or None for failures).
    Individual failures do not abort the batch.
    """
    return [embed_text(t) for t in texts]


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """
    Cosine similarity between two equal-length vectors.
    Returns 0.0 if either vector is zero-norm.
    Pure-Python implementation; numpy not required.
    """
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def clear_cache() -> None:
    """Clear the in-process embedding cache (used in tests)."""
    with _EMBED_LOCK:
        _EMBED_CACHE.clear()
