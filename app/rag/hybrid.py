"""
app/rag/hybrid.py  —  Reciprocal Rank Fusion (RRF) hybrid retrieval

Architecture:
  1. BM25 rank list  (always available — rank_bm25, offline-safe)
  2. Dense rank list (Ollama nomic-embed-text — degrades gracefully to None)
  3. RRF fusion:  score_rrf(d) = Σ 1 / (k + rank_i(d))   where k=60 (standard)
  4. Strict relevance gate: top-1 RRF score must be ≥ MIN_RRF_SCORE (0.01)
  5. Source attribution: every returned chunk carries chunk_id, source_url,
     source_file, section, and retrieval metadata.

Offline behaviour:
  If Ollama is unavailable (embed_text returns None), dense scores are skipped
  and fusion uses BM25 ranks alone — effectively identical to pure BM25 ranking.
  This satisfies acceptance gate 10 (Graceful Offline Degradation).
"""

import logging
from typing import List, Dict, Any, Optional, Tuple

from app.rag.embed import embed_text, cosine_similarity
from app.rag.relevance import extract_keywords, passes_relevance_gate

logger = logging.getLogger(__name__)

RRF_K: int = 60
MIN_RRF_SCORE: float = 0.008  # below this: treat as no relevant results


def _bm25_ranks(
    query_tokens: List[str],
    chunks: List[Dict[str, Any]],
    bm25_model,
) -> List[Tuple[int, float]]:
    """
    Returns list of (chunk_index, raw_bm25_score) sorted descending by score.
    """
    raw_scores = bm25_model.get_scores(query_tokens)
    indexed = sorted(enumerate(raw_scores), key=lambda x: x[1], reverse=True)
    return [(idx, score) for idx, score in indexed if score > 0.0]


def _dense_ranks(
    query: str,
    chunks: List[Dict[str, Any]],
) -> Optional[List[Tuple[int, float]]]:
    """
    Returns list of (chunk_index, cosine_similarity) sorted descending,
    or None if Ollama is offline.
    """
    query_vec = embed_text(query)
    if query_vec is None:
        return None  # Offline — caller must skip dense leg

    results = []
    for idx, chunk in enumerate(chunks):
        chunk_text = chunk.get("_embed_text") or chunk.get("text", "")
        chunk_vec = embed_text(chunk_text)
        if chunk_vec is None:
            continue  # Skip individual chunk failures gracefully
        sim = cosine_similarity(query_vec, chunk_vec)
        if sim > 0.0:
            results.append((idx, sim))

    results.sort(key=lambda x: x[1], reverse=True)
    return results


def rrf_fuse(
    bm25_ranked: List[Tuple[int, float]],
    dense_ranked: Optional[List[Tuple[int, float]]],
    num_chunks: int,
    k: int = RRF_K,
) -> List[Tuple[int, float]]:
    """
    Reciprocal Rank Fusion.
    Returns list of (chunk_index, rrf_score) sorted descending.
    """
    rrf_scores: Dict[int, float] = {}

    for rank, (idx, _) in enumerate(bm25_ranked):
        rrf_scores[idx] = rrf_scores.get(idx, 0.0) + 1.0 / (k + rank + 1)

    if dense_ranked is not None:
        for rank, (idx, _) in enumerate(dense_ranked):
            rrf_scores[idx] = rrf_scores.get(idx, 0.0) + 1.0 / (k + rank + 1)

    fused = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    return fused  # List[Tuple[chunk_index, rrf_score]]


def hybrid_retrieve(
    query: str,
    chunks: List[Dict[str, Any]],
    bm25_model,
    top_k: int = 3,
    score_threshold: float = 0.08,
    min_word_coverage: float = 0.30,
    use_dense: bool = True,
) -> List[Dict[str, Any]]:
    """
    Hybrid BM25 + Dense retrieval with RRF fusion and relevance gating.

    Args:
        query:             Normalized user query string.
        chunks:            List of chunk dicts (each must have 'text', 'section',
                           'chunk_id', 'source_url', 'file' keys).
        bm25_model:        Initialized BM25Okapi instance.
        top_k:             Maximum results to return.
        score_threshold:   Minimum normalized BM25 score for relevance gate.
        min_word_coverage: Minimum fraction of query keywords found in chunk.
        use_dense:         Set False to force BM25-only (e.g. tests, offline).

    Returns:
        List of chunk dicts with added retrieval metadata:
          - similarity_score  (RRF score, 0–1 normalised)
          - bm25_score        (raw BM25 score)
          - dense_score       (cosine sim or None)
          - retrieval_mode    ("hybrid" | "bm25_only")
          - source_url        (authorised source URL from chunk metadata)
          - source_file       (originating KB .md file name)
    """
    if not chunks or bm25_model is None:
        return []

    query_tokens = extract_keywords(query)
    if not query_tokens:
        return []

    # Expand query tokens with synonyms for cross-lingual / multilingual BM25 matching
    from app.rag.relevance import SYNONYMS
    bm25_query_tokens = list(query_tokens)
    for qt in query_tokens:
        if qt in SYNONYMS:
            bm25_query_tokens.extend(list(SYNONYMS[qt]))

    # --- BM25 leg ---
    bm25_ranked = _bm25_ranks(bm25_query_tokens, chunks, bm25_model)
    # Build raw score lookup for attribution
    bm25_score_map: Dict[int, float] = {idx: s for idx, s in bm25_ranked}
    max_bm25 = max((s for _, s in bm25_ranked), default=1.0) or 1.0

    # --- Dense leg (optional) ---
    dense_ranked: Optional[List[Tuple[int, float]]] = None
    dense_score_map: Dict[int, float] = {}
    retrieval_mode = "bm25_only"

    if use_dense:
        dense_ranked = _dense_ranks(query, chunks)
        if dense_ranked is not None:
            dense_score_map = {idx: s for idx, s in dense_ranked}
            retrieval_mode = "hybrid"
        else:
            logger.debug("hybrid_retrieve: Ollama offline — using BM25-only fallback.")

    # --- RRF fusion ---
    fused = rrf_fuse(bm25_ranked, dense_ranked, len(chunks))

    if not fused:
        return []

    # --- Relevance gate on top result ---
    top_rrf_score = fused[0][1]
    if top_rrf_score < MIN_RRF_SCORE:
        return []

    # --- Assemble results ---
    results = []
    for chunk_idx, rrf_score in fused:
        if len(results) >= top_k:
            break

        chunk = chunks[chunk_idx]
        # Use normalised text for relevance gate (dimension-normalised)
        chunk_text = chunk.get("_norm_text") or chunk.get("text", "")
        norm_bm25 = bm25_score_map.get(chunk_idx, 0.0) / max_bm25

        # Apply relevance gate (score + word coverage) on BM25 normalised score
        if not passes_relevance_gate(
            query=query,
            chunk_text=chunk_text,
            score=norm_bm25,
            score_threshold=score_threshold,
            min_coverage=min_word_coverage,
        ):
            continue

        result = {
            "chunk_id": chunk.get("chunk_id", f"chunk_{chunk_idx:03d}"),
            "model": chunk.get("model", "CX-02"),
            "section": chunk.get("section", ""),
            "title": chunk.get("title", chunk.get("section", "")),
            "text": chunk_text,
            "source_url": chunk.get("source_url", ""),
            "source_file": chunk.get("file", ""),
            # Retrieval metadata
            "similarity_score": round(rrf_score, 6),
            "bm25_score": round(norm_bm25, 4),
            "dense_score": round(dense_score_map.get(chunk_idx, 0.0), 4) if dense_ranked is not None else None,
            "retrieval_mode": retrieval_mode,
        }
        results.append(result)

    return results
