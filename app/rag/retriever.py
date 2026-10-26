import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from rank_bm25 import BM25Okapi
from app.config import Config, BASE_DIR
from app.rag.chunker import build_chunks
from app.rag.relevance import extract_keywords, passes_relevance_gate

_CHUNKS_CACHE: Optional[List[Dict[str, Any]]] = None
_BM25_MODEL: Optional[BM25Okapi] = None
_TOKENIZED_CORPUS: Optional[List[List[str]]] = None


def load_chunks(force_reload: bool = False) -> List[Dict[str, Any]]:
    global _CHUNKS_CACHE, _BM25_MODEL, _TOKENIZED_CORPUS
    if _CHUNKS_CACHE is not None and not force_reload:
        return _CHUNKS_CACHE

    chunks_path = BASE_DIR / "data" / "chunks.json"
    if not chunks_path.exists() or force_reload:
        _CHUNKS_CACHE = build_chunks(Config.KB_DIR, chunks_path)
    else:
        with open(chunks_path, "r", encoding="utf-8") as f:
            _CHUNKS_CACHE = json.load(f)

    # Filter to model: CX-02
    _CHUNKS_CACHE = [c for c in _CHUNKS_CACHE if c.get("model") == "CX-02"]

    # Initialize BM25
    _TOKENIZED_CORPUS = [extract_keywords(c["text"]) for c in _CHUNKS_CACHE]
    _BM25_MODEL = BM25Okapi(_TOKENIZED_CORPUS)

    return _CHUNKS_CACHE


def retrieve(
    query: str,
    top_k: int = 3,
    score_threshold: float = 0.08,
    min_word_coverage: float = 0.35
) -> List[Dict[str, Any]]:
    """
    Hybrid / BM25 retriever with dual relevance gating (score + query word coverage).
    Returns list of relevant chunks strictly scoped to model=CX-02.
    If relevance check fails, returns empty list.
    """
    chunks = load_chunks()
    if not chunks or not _BM25_MODEL:
        return []

    tokens = extract_keywords(query)
    if not tokens:
        return []

    # Get BM25 scores
    raw_scores = _BM25_MODEL.get_scores(tokens)
    max_score = max(raw_scores) if len(raw_scores) > 0 and max(raw_scores) > 0 else 1.0

    scored_chunks = []
    for idx, raw_score in enumerate(raw_scores):
        norm_score = float(raw_score / max_score) if max_score > 0 else 0.0
        chunk = dict(chunks[idx])
        chunk["similarity_score"] = round(norm_score, 4)

        # Apply dual relevance gate
        if passes_relevance_gate(
            query=query,
            chunk_text=chunk["text"],
            score=norm_score,
            score_threshold=score_threshold,
            min_coverage=min_word_coverage
        ):
            scored_chunks.append(chunk)

    # Sort descending by score
    scored_chunks.sort(key=lambda x: x["similarity_score"], reverse=True)
    return scored_chunks[:top_k]
