import os
import re
import math
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

CHUNKS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "chunks.json"


def tokenize(text: str) -> List[str]:
    """Tokenize and normalize text into lowercase alphanumeric words."""
    return re.findall(r"\b[a-zA-Z0-9_\-\.\"]+\b", text.lower())


class CX02Retriever:
    def __init__(self, chunks_path: Path = CHUNKS_PATH, similarity_threshold: float = 0.15):
        self.chunks_path = chunks_path
        self.similarity_threshold = similarity_threshold
        self.chunks: List[Dict[str, Any]] = []
        self.doc_freqs: Dict[str, int] = {}
        self.avg_dl: float = 0.0
        self.load_chunks()

    def load_chunks(self):
        """Loads chunks from JSON and builds the BM25 index."""
        if not self.chunks_path.exists():
            from app.rag.ingest import ingest
            self.chunks = ingest()
        else:
            with open(self.chunks_path, "r", encoding="utf-8") as f:
                self.chunks = json.load(f)

        # Hard metadata filter: only keep chunks where model == 'CX-02'
        self.chunks = [c for c in self.chunks if c.get("model") == "CX-02"]

        # Build term frequencies and document frequencies
        total_tokens = 0
        self.doc_freqs = {}

        for chunk in self.chunks:
            # Combine section title (weighted) and text
            tokens = tokenize(f"{chunk['section']} {chunk['section']} {chunk['text']}")
            chunk["_tokens"] = tokens
            total_tokens += len(tokens)
            unique_terms = set(tokens)
            for term in unique_terms:
                self.doc_freqs[term] = self.doc_freqs.get(term, 0) + 1

        self.avg_dl = (total_tokens / len(self.chunks)) if self.chunks else 1.0

    def score_bm25(self, query_tokens: List[str], chunk: Dict[str, Any], k1: float = 1.5, b: float = 0.75) -> float:
        """Calculates BM25 score for a chunk against query tokens."""
        doc_tokens = chunk["_tokens"]
        doc_len = len(doc_tokens)
        N = len(self.chunks)
        score = 0.0

        tf_dict: Dict[str, int] = {}
        for t in doc_tokens:
            tf_dict[t] = tf_dict.get(t, 0) + 1

        for qt in query_tokens:
            tf = tf_dict.get(qt, 0)
            if tf == 0:
                continue

            df = self.doc_freqs.get(qt, 0)
            idf = math.log((N - df + 0.5) / (df + 0.5) + 1.0)
            numerator = tf * (k1 + 1)
            denominator = tf + k1 * (1 - b + b * (doc_len / self.avg_dl))
            score += idf * (numerator / denominator)

        # Normalize score against length of query to obtain comparable similarity
        if query_tokens:
            normalized_score = score / (len(query_tokens) * 2.0)
        else:
            normalized_score = 0.0

        return normalized_score

    def search(self, query: str, top_k: int = 4, filter_model: str = "CX-02") -> List[Dict[str, Any]]:
        """
        Filtered retrieve for CX-02 knowledge chunks.
        Strictly applies model == filter_model ('CX-02').
        Returns empty list if top score is below similarity_threshold.
        """
        if not self.chunks:
            self.load_chunks()

        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        scored_chunks = []
        for chunk in self.chunks:
            # Enforce hard filter on model
            if chunk.get("model") != filter_model:
                continue

            score = self.score_bm25(query_tokens, chunk)
            if score > 0.0:
                scored_chunks.append({
                    "chunk_id": chunk["chunk_id"],
                    "model": chunk["model"],
                    "source": chunk["source"],
                    "section": chunk["section"],
                    "text": chunk["text"],
                    "score": round(score, 4)
                })

        # Sort by highest score descending
        scored_chunks.sort(key=lambda x: x["score"], reverse=True)

        if not scored_chunks:
            return []

        # Check against similarity threshold
        best_score = scored_chunks[0]["score"]
        if best_score < self.similarity_threshold:
            # Below confidence threshold -> return empty to trigger handoff
            return []

        return scored_chunks[:top_k]


# Singleton instance for quick access
_default_retriever = None

def retrieve(query: str, top_k: int = 4) -> List[Dict[str, Any]]:
    global _default_retriever
    if _default_retriever is None:
        _default_retriever = CX02Retriever()
    return _default_retriever.search(query, top_k=top_k)
