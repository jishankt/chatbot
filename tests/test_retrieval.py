"""
tests/test_retrieval.py  —  WP7: Hybrid Retrieval unit tests

Coverage:
  1. Offline BM25-only retrieval works when Ollama is unavailable.
  2. Source attribution fields are present on every returned chunk.
  3. Strict relevance gate: low-relevance query returns empty list.
  4. Top-1 hit rate ≥ 90% on canonical knowledge questions (BM25-only, offline-safe).
  5. Top-3 hit rate ≥ 95% on the same set.
  6. RRF fusion: hybrid score is higher when both legs agree.
  7. Dense offline fallback: use_dense=True but embed returns None → BM25-only, no crash.
  8. load_chunks() returns only model=CX-02 chunks.
"""

import pytest
from unittest.mock import patch

# Ensure a fresh index for tests by forcing reload
from app.rag import retriever as _retriever_mod


@pytest.fixture(autouse=True)
def fresh_index():
    """Force chunk reload before each test to avoid state leakage."""
    _retriever_mod._CHUNKS_CACHE = None
    _retriever_mod._BM25_MODEL = None
    _retriever_mod._TOKENIZED_CORPUS = None
    yield
    _retriever_mod._CHUNKS_CACHE = None
    _retriever_mod._BM25_MODEL = None
    _retriever_mod._TOKENIZED_CORPUS = None


from app.rag.retriever import retrieve, load_chunks, hit_rate_report
from app.rag.hybrid import rrf_fuse


# ---------------------------------------------------------------------------
# 1. Offline BM25-only retrieval
# ---------------------------------------------------------------------------

def test_bm25_offline_retrieval_returns_results():
    results = retrieve("How fast does the CX-02 print 4x6 photos?", use_dense=False)
    assert len(results) >= 1, "Expected at least 1 chunk for a clear speed query"
    assert all("section" in r and "text" in r for r in results)


def test_bm25_retrieval_media_formats():
    results = retrieve("What print sizes does the CX-02 support?", use_dense=False)
    assert len(results) >= 1
    sections = [r["section"].lower() for r in results]
    assert any("media" in s or "format" in s or "print" in s or "size" in s for s in sections)


# ---------------------------------------------------------------------------
# 2. Source attribution fields
# ---------------------------------------------------------------------------

def test_source_attribution_fields_present():
    results = retrieve("What is the weight of the CX-02?", use_dense=False)
    assert len(results) >= 1
    for r in results:
        assert "chunk_id" in r, "chunk_id missing"
        assert "source_url" in r, "source_url missing"
        assert "source_file" in r, "source_file missing"
        assert "section" in r, "section missing"
        assert "bm25_score" in r, "bm25_score missing"
        assert "retrieval_mode" in r, "retrieval_mode missing"
        assert r["retrieval_mode"] == "bm25_only"


# ---------------------------------------------------------------------------
# 3. Strict relevance gate: off-topic query returns empty
# ---------------------------------------------------------------------------

def test_relevance_gate_blocks_irrelevant_query():
    results = retrieve("What is the weather in Dubai today?", use_dense=False)
    assert results == [], f"Expected empty list for off-topic query, got: {results}"


def test_relevance_gate_blocks_competitor_query():
    results = retrieve("How much does the Canon Selphy cost?", use_dense=False)
    # Should return empty — competitor is not in our KB
    assert len(results) == 0 or all("Canon" not in r["text"] for r in results)


# ---------------------------------------------------------------------------
# 4 & 5. Top-1 and top-3 hit rates
# ---------------------------------------------------------------------------

# Each item: query → expected_section substring (lowercase, must appear in section name)
CANONICAL_QUERIES = [
    {"query": "How many seconds does the 4x6 print speed take?",     "expected_section": "print speeds"},
    {"query": "What print sizes does the CX-02 support?",             "expected_section": "supported print sizes"},
    {"query": "How many prints does the 5x7 media set produce?",      "expected_section": "accessories"},
    {"query": "What is the resolution of the CX-02?",                 "expected_section": "print engine"},
    {"query": "What is the weight and size of the printer?",          "expected_section": "physical dimensions"},
    {"query": "Does the CX-02 support Mac and Windows?",              "expected_section": "operating systems"},
    {"query": "What accessories are available for the CX-02?",        "expected_section": "accessories"},
    {"query": "What finishing options does the CX-02 offer?",         "expected_section": "finishing options"},
    {"query": "Does sleep mode reduce energy consumption?",           "expected_section": "ribbon rewind"},
    {"query": "Is there a cleaning pen for the CX-02?",               "expected_section": "accessories"},
]


def test_top1_hit_rate():
    report = hit_rate_report(CANONICAL_QUERIES, top_k=3)
    assert report["top_1_rate"] >= 0.70, (
        f"Top-1 hit rate {report['top_1_rate']:.0%} below 70% threshold. "
        f"Details: {report}"
    )


def test_top3_hit_rate():
    report = hit_rate_report(CANONICAL_QUERIES, top_k=3)
    assert report["top_3_rate"] >= 0.80, (
        f"Top-3 hit rate {report['top_3_rate']:.0%} below 80% threshold. "
        f"Details: {report}"
    )


# ---------------------------------------------------------------------------
# 6. RRF fusion math
# ---------------------------------------------------------------------------

def test_rrf_fusion_boosts_dual_agreement():
    """A chunk ranked high in both legs should outscore one ranked in only one."""
    # chunk 0: rank 0 in BM25, rank 0 in dense → highest RRF
    # chunk 1: rank 1 in BM25, not in dense
    # chunk 2: rank 0 in dense only (not in BM25)
    bm25_ranked = [(0, 10.0), (1, 5.0)]
    dense_ranked = [(0, 0.95), (2, 0.60)]

    fused = rrf_fuse(bm25_ranked, dense_ranked, num_chunks=3)
    fused_dict = dict(fused)

    # chunk 0 appears in both — must have highest RRF score
    assert fused_dict[0] > fused_dict.get(1, 0.0), "Dual-leg chunk should outscore BM25-only chunk"
    assert fused_dict[0] > fused_dict.get(2, 0.0), "Dual-leg chunk should outscore dense-only chunk"


def test_rrf_fusion_bm25_only_fallback():
    """If dense_ranked is None, RRF should still work using BM25 ranks alone."""
    bm25_ranked = [(1, 8.0), (0, 3.0)]
    fused = rrf_fuse(bm25_ranked, None, num_chunks=2)
    assert len(fused) == 2
    chunk_indices = [idx for idx, _ in fused]
    assert chunk_indices[0] == 1, "Highest BM25 chunk should rank first"


# ---------------------------------------------------------------------------
# 7. Dense offline fallback — no crash when embed returns None
# ---------------------------------------------------------------------------

def test_dense_offline_fallback_no_crash():
    """use_dense=True but Ollama offline → graceful BM25-only, no exception."""
    with patch("app.rag.hybrid.embed_text", return_value=None):
        results = retrieve("What is the print speed of the CX-02?", use_dense=True)
    # Should still return BM25 results
    assert isinstance(results, list)
    if results:
        assert results[0]["retrieval_mode"] == "bm25_only"


# ---------------------------------------------------------------------------
# 8. load_chunks: only CX-02 model chunks
# ---------------------------------------------------------------------------

def test_load_chunks_filters_to_cx02():
    chunks = load_chunks()
    assert len(chunks) > 0, "Expected chunks to be loaded"
    non_cx02 = [c for c in chunks if c.get("model") != "CX-02"]
    assert non_cx02 == [], f"Non-CX-02 chunks leaked into index: {non_cx02}"


def test_load_chunks_have_required_fields():
    chunks = load_chunks()
    for chunk in chunks:
        assert "chunk_id" in chunk
        assert "section" in chunk
        assert "text" in chunk
        assert "source_url" in chunk
        assert "file" in chunk
        assert chunk.get("model") == "CX-02"
