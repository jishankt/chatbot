"""
app/rag/retriever.py  —  Public retrieval interface (WP7: Hybrid BM25 + Dense)

Public API (unchanged):
    retrieve(query, top_k=3) -> List[Dict[str, Any]]

Internal:
    - Loads and caches chunks from data/chunks.json (built from data/kb/*.md).
    - Initialises rank_bm25 BM25Okapi index.
    - Delegates to hybrid_retrieve() which performs RRF fusion of BM25 + dense
      embeddings when Ollama is available, or BM25-only when offline.
    - Returns up to top_k chunks with full source attribution metadata.
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from rank_bm25 import BM25Okapi

from app.config import Config, BASE_DIR
from app.rag.chunker import build_chunks
from app.rag.relevance import extract_keywords
from app.rag.hybrid import hybrid_retrieve

logger = logging.getLogger(__name__)

# --- Module-level cache ---
_CHUNKS_CACHE: Optional[List[Dict[str, Any]]] = None
_BM25_MODEL: Optional[BM25Okapi] = None
_TOKENIZED_CORPUS: Optional[List[List[str]]] = None


def load_chunks(force_reload: bool = False) -> List[Dict[str, Any]]:
    """
    Load and index chunks from data/chunks.json (build from KB if absent).
    Filters to model == 'CX-02'.
    Initialises BM25 index and caches in module globals.
    """
    global _CHUNKS_CACHE, _BM25_MODEL, _TOKENIZED_CORPUS

    if _CHUNKS_CACHE is not None and not force_reload:
        return _CHUNKS_CACHE

    chunks_path = BASE_DIR / "data" / "chunks.json"

    if not chunks_path.exists() or force_reload:
        logger.info("retriever: building chunks from KB directory %s", Config.KB_DIR)
        _CHUNKS_CACHE = build_chunks(Config.KB_DIR, chunks_path)
    else:
        with open(chunks_path, "r", encoding="utf-8") as f:
            _CHUNKS_CACHE = json.load(f)

    # Hard metadata filter — only CX-02 chunks enter the index
    _CHUNKS_CACHE = [c for c in _CHUNKS_CACHE if c.get("model") == "CX-02"]

    import re as _re
    # Pre-compute embed text and normalize dimension formats for BM25 consistency:
    # "4 x 6" and "4x6" must tokenize identically so the Print Speeds section
    # ranks as well as sections that happen to use the compact form in their text.
    for chunk in _CHUNKS_CACHE:
        norm_text = _re.sub(r"(\d+)\s*[xX]\s*(\d+)", r"\1x\2", chunk.get("text", ""))
        chunk["_embed_text"] = f"{chunk.get('section', '')} {norm_text}"
        # Also update the text itself for the BM25 tokenizer (non-destructive copy)
        chunk["_norm_text"] = norm_text

    # Build BM25 index on normalised text so "4 x 6" and "4x6" are equivalent
    _TOKENIZED_CORPUS = [extract_keywords(c.get("_norm_text", c["text"])) for c in _CHUNKS_CACHE]
    _BM25_MODEL = BM25Okapi(_TOKENIZED_CORPUS)

    logger.info(
        "retriever: indexed %d CX-02 chunks (BM25 ready; dense via nomic-embed-text when Ollama is online).",
        len(_CHUNKS_CACHE),
    )
    return _CHUNKS_CACHE


def retrieve(
    query: str,
    top_k: int = 3,
    score_threshold: float = 0.08,
    min_word_coverage: float = 0.30,
    use_dense: bool = True,
) -> List[Dict[str, Any]]:
    """
    Hybrid BM25 + Dense retrieval for the CX-02 knowledge base.

    Args:
        query:             User query (already normalised by reader.py).
        top_k:             Maximum chunks to return (default 3).
        score_threshold:   Minimum normalised BM25 score for relevance gate.
        min_word_coverage: Minimum keyword coverage fraction.
        use_dense:         If False, skip dense leg (offline / test override).

    Returns:
        List of chunk dicts with keys: chunk_id, section, text, source_url,
        source_file, similarity_score, bm25_score, dense_score, retrieval_mode.
        Empty list if nothing passes the relevance gate.
    """
    chunks = load_chunks()

    if not chunks or _BM25_MODEL is None:
        return []

    return hybrid_retrieve(
        query=query,
        chunks=chunks,
        bm25_model=_BM25_MODEL,
        top_k=top_k,
        score_threshold=score_threshold,
        min_word_coverage=min_word_coverage,
        use_dense=use_dense,
    )


def hit_rate_report(test_queries: List[Dict[str, Any]], top_k: int = 3) -> Dict[str, Any]:
    """
    Offline evaluation helper: compute top-1 and top-3 hit rates.

    Args:
        test_queries: List of {"query": str, "expected_section": str} dicts.
        top_k:        Number of chunks to retrieve per query.

    Returns:
        Dict with top_1_hits, top_3_hits, total, top_1_rate, top_3_rate.
    """
    top1_hits = 0
    top3_hits = 0
    total = len(test_queries)

    for item in test_queries:
        query = item["query"]
        expected = item["expected_section"].lower()
        results = retrieve(query, top_k=top_k, use_dense=False)  # BM25 only for eval speed

        sections = [r["section"].lower() for r in results]
        if sections and expected in sections[0]:
            top1_hits += 1
        if any(expected in s for s in sections):
            top3_hits += 1

    return {
        "top_1_hits": top1_hits,
        "top_3_hits": top3_hits,
        "total": total,
        "top_1_rate": round(top1_hits / total, 3) if total else 0.0,
        "top_3_rate": round(top3_hits / total, 3) if total else 0.0,
    }
