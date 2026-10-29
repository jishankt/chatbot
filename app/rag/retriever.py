"""
app/rag/retriever.py  —  Public retrieval interface (WP7 & WP0.6: Hybrid BM25 + Dense, Multi-Namespace)

Public API:
    retrieve(query, top_k=3, namespace="cx02") -> List[Dict[str, Any]]
    retrieve_company(query, top_k=3) -> List[Dict[str, Any]]

Internal:
    - Loads and caches chunks from data/chunks.json (CX-02) and data/company_chunks.json (Company).
    - Initialises BM25 indices per namespace.
    - Retrieval for company questions uses the company namespace; product questions use the CX-02 namespace.
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from rank_bm25 import BM25Okapi

from app.config import Config, BASE_DIR
from app.rag.chunker import build_chunks, build_company_chunks
from app.rag.relevance import extract_keywords
from app.rag.hybrid import hybrid_retrieve

logger = logging.getLogger(__name__)

# --- Module-level cache ---
_CHUNKS_CACHE: Optional[List[Dict[str, Any]]] = None
_BM25_MODEL: Optional[BM25Okapi] = None
_TOKENIZED_CORPUS: Optional[List[List[str]]] = None
_CATALOG_VOCABULARY: Optional[set] = None

_COMPANY_CHUNKS_CACHE: Optional[List[Dict[str, Any]]] = None
_COMPANY_BM25_MODEL: Optional[BM25Okapi] = None
_COMPANY_TOKENIZED_CORPUS: Optional[List[List[str]]] = None


COMMON_INQUIRY_TERMS = {
    "what", "is", "the", "price", "prices", "cost", "how", "much", "can", "i", "we", "get", "a", "an", "for",
    "quote", "quotation", "rate", "rates", "buy", "purchase", "order", "sell", "available", "availability",
    "stock", "in", "dubai", "uae", "abu", "dhabi", "sharjah", "gcc", "delivery", "shipping", "warranty",
    "guarantee", "time", "speed", "fast", "specs", "specifications", "technical", "details", "printer",
    "photo", "prints", "printing", "paper", "media", "roll", "rolls", "box", "boxes", "set", "sets",
    "tell", "me", "about", "give", "please", "do", "you", "have", "need", "looking", "want", "where",
    "does", "it", "this", "that", "unit", "machine", "device", "hardware", "consumables", "accessories",
    "help", "contact", "support", "sales", "team", "office", "showroom", "demo", "demonstration",
    "work", "support", "features", "options", "compare", "difference", "model", "brand", "official",
    "choose", "many", "part", "number", "often", "located", "khalid", "bin", "waleed", "road",
    "business", "hours", "ship", "deliver", "saudi", "arabia", "schedule", "live", "input", "voltage", "active",
    "explain", "process", "like", "there", "events", "produce", "count", "reducing", "percent", "mobility", "millimeters",
    "anything", "changing", "without", "normal", "bigger", "big", "clients", "busy", "run", "dont", "refill", "all",
    "suggest", "recommend", "do", "both", "framed", "weddings", "wedding", "small", "large", "different", "instead",
    "consumbles", "consumable", "supplies", "kiosk", "kiosks", "mall", "always", "keep", "prints", "photos",
    "سعر", "اسعار", "كم", "هل", "طابعة", "صور", "ورق", "دبي", "الامارات", "ضمان", "شحن", "توصيل",
    "رأس", "الطباعة", "الحراري", "حراري", "مدة", "الضمان", "لطابعة", "الصور", "الإمارات", "إمارات",
    "توفرون", "خدمة", "والشارقة", "شارقة", "يمكن", "تجربة", "المعرض", "معرض", "قبل", "الشراء", "شراء",
    "المتوفرة", "متوفرة", "نقطة", "تعمل", "الطابعة", "يندوز", "وماك",
    "مدعومة", "المدعومة", "تدعم", "خاصية", "لتوفير", "خيارات", "مثل", "توفر", "ميزة", "وضع",
    "يوجد", "تقنية", "تحمي", "طبقة", "الماء", "ماء", "عدد", "تتوفر", "حماية", "فعاليات",
    "بسهولة", "يتم", "تعتمد", "شرائط", "للبوث", "لبوث", "بالمليمتر", "والوزن", "الوزن",
    "بالكيلوجرام", "تستغرق", "التسامي", "والبصمات", "البصمات", "بصمات", "يو", "اس", "بي",
    "سائط", "وحماية", "الفعاليات", "الورق",
    "kam", "sur3at", "teba3at", "hal", "yeshteghel", "el", "3ala", "lama3",
    "ചെയ്യാൻ", "എത്ര", "എടുക്കും", "ഇവന്റുകൾക്ക്", "അനുയോജ്യമാണോ", "വാറന്റി", "ലഭിക്കുമോ"
}


def load_chunks(force_reload: bool = False, namespace: str = "cx02") -> List[Dict[str, Any]]:
    """
    Load and index chunks from data/chunks.json (CX-02) or data/company_chunks.json (Company).
    When namespace == 'cx02', filters to model == 'CX-02' (backward-compatible).
    Initialises BM25 index and caches in module globals.
    """
    global _CHUNKS_CACHE, _BM25_MODEL, _TOKENIZED_CORPUS
    global _COMPANY_CHUNKS_CACHE, _COMPANY_BM25_MODEL, _COMPANY_TOKENIZED_CORPUS

    if namespace == "company":
        if _COMPANY_CHUNKS_CACHE is not None and not force_reload:
            return _COMPANY_CHUNKS_CACHE

        comp_chunks_path = BASE_DIR / "data" / "company_chunks.json"
        if not comp_chunks_path.exists() or force_reload:
            logger.info("retriever: building company chunks from %s", Config.KB_DIR / "company")
            _COMPANY_CHUNKS_CACHE = build_company_chunks(Config.KB_DIR / "company", comp_chunks_path)
        else:
            with open(comp_chunks_path, "r", encoding="utf-8") as f:
                _COMPANY_CHUNKS_CACHE = json.load(f)

        for chunk in _COMPANY_CHUNKS_CACHE:
            chunk["_norm_text"] = chunk.get("text", "")
            chunk["source_file"] = chunk.get("file", "company_kb")

        _COMPANY_TOKENIZED_CORPUS = [extract_keywords(c.get("_norm_text", c["text"])) for c in _COMPANY_CHUNKS_CACHE]
        _COMPANY_BM25_MODEL = BM25Okapi(_COMPANY_TOKENIZED_CORPUS)
        return _COMPANY_CHUNKS_CACHE

    # Default: CX-02 namespace
    if _CHUNKS_CACHE is not None and not force_reload:
        return _CHUNKS_CACHE

    chunks_path = BASE_DIR / "data" / "chunks.json"

    if not chunks_path.exists() or force_reload:
        logger.info("retriever: building chunks from KB directory %s", Config.KB_DIR)
        _CHUNKS_CACHE = build_chunks(Config.KB_DIR, chunks_path)
    else:
        with open(chunks_path, "r", encoding="utf-8") as f:
            _CHUNKS_CACHE = json.load(f)

    # Load all product chunks from catalogue KB
    _CHUNKS_CACHE = list(_CHUNKS_CACHE)

    import re as _re
    # Pre-compute embed text and normalize dimension formats for BM25 consistency:
    for chunk in _CHUNKS_CACHE:
        norm_text = _re.sub(r"(\d+)\s*[xX]\s*(\d+)", r"\1x\2", chunk.get("text", ""))
        chunk["_embed_text"] = f"{chunk.get('section', '')} {norm_text}"
        chunk["_norm_text"] = norm_text
        chunk["source_file"] = chunk.get("file", "catalogue_kb")

    # Build BM25 index on normalised text so "4 x 6" and "4x6" are equivalent
    _TOKENIZED_CORPUS = [extract_keywords(c.get("_norm_text", c["text"])) for c in _CHUNKS_CACHE]
    _BM25_MODEL = BM25Okapi(_TOKENIZED_CORPUS)

    global _CATALOG_VOCABULARY
    _CATALOG_VOCABULARY = set()
    for tokens in _TOKENIZED_CORPUS:
        _CATALOG_VOCABULARY.update(tokens)

    logger.info(
        "retriever: indexed %d chunks (%d vocabulary terms; BM25 ready).",
        len(_CHUNKS_CACHE),
        len(_CATALOG_VOCABULARY),
    )
    return _CHUNKS_CACHE


def retrieve(
    query: str,
    top_k: int = 3,
    score_threshold: float = 0.08,
    min_word_coverage: float = 0.30,
    use_dense: bool = False,
    namespace: str = "cx02",
    category: Optional[str] = None,
    model: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Hybrid BM25 + Dense retrieval with positive scope gating and category filtering.
    """
    chunks = load_chunks(namespace=namespace)
    bm25_model = _COMPANY_BM25_MODEL if namespace == "company" else _BM25_MODEL

    if not chunks or bm25_model is None:
        return []

    # Filter chunks by category/model if specified
    q_lower = query.lower()
    is_cad_query = category == "cad_plotter" or any(w in q_lower for w in ["cad", "blueprint", "plotter", "architectural", "t3100", "t5100", "t7700"])
    is_office_query = category == "business_mfp" or any(w in q_lower for w in ["office", "workforce", "c5890", "em-c800", "am-c400", "duplex"])
    is_scanner_query = category == "scanner" or any(w in q_lower for w in ["scanner", "ds-530", "ds-770", "scanning"])

    if is_cad_query and not any(cx in q_lower for cx in ["cx-02", "cx02"]):
        candidate_chunks = [c for c in chunks if "CAD" in c.get("title", "") or "T3100" in c.get("title", "") or "T5100" in c.get("title", "") or "T7700" in c.get("title", "")]
        if candidate_chunks:
            return candidate_chunks[:top_k]
    elif is_office_query and not any(cx in q_lower for cx in ["cx-02", "cx02"]):
        candidate_chunks = [c for c in chunks if "WorkForce" in c.get("title", "") or "WF-C5890" in c.get("title", "") or "EM-C800" in c.get("title", "")]
        if candidate_chunks:
            return candidate_chunks[:top_k]
    elif is_scanner_query and not any(cx in q_lower for cx in ["cx-02", "cx02"]):
        candidate_chunks = [c for c in chunks if "Scanner" in c.get("title", "") or "DS-530" in c.get("title", "") or "DS-770" in c.get("title", "")]
        if candidate_chunks:
            return candidate_chunks[:top_k]

    # Positive scope gating for products namespace
    if namespace == "cx02":
        has_our_product = any(w in q_lower for w in [
            "cx-02", "cx02", "cx 02", "cx-02w", "cx02w", "cx 02w", "cy-02", "cy02", "cy 02", "cz-01", "cz01", "cz 01",
            "citizen", "kepler", "ms46", "ms57", "ms68", "cleaning pen", "cx2", "cx-2",
            "epson", "surecolor", "workforce", "t3100", "t5100", "t7700", "p700", "p900", "p9500", "p8500",
            "f100", "f500", "c5890", "em-c800", "am-c400", "ds-530", "ds-770", "scanner", "plotter", "blueprint", "cad",
            "overcoat", "cups", "strip", "strips", "dual-cut", "dual cut",
            "سيتيزن", "ابسون", "إبسون", "كيبلر", "الأوفركوت", "أوفركوت", "ريبان", "الريبان",
            "سي اكس", "سي واي", "سي زد", "സിറ്റിസൺ", "കെപ്ലർ", "എപ്സൺ",
            "shuf", "bikam", "se3r", "marhaba", "wayn"
        ])
        if not has_our_product:
            q_keywords = extract_keywords(query)
            from app.rag.relevance import SYNONYMS
            catalog_vocab = _CATALOG_VOCABULARY or set()
            for kw in q_keywords:
                if kw in COMMON_INQUIRY_TERMS:
                    continue
                syns = SYNONYMS.get(kw, {kw})
                if not (kw in catalog_vocab or any(s in catalog_vocab for s in syns)):
                    return []

            eff_thresh = max(score_threshold, 0.10)
            eff_cov = min_word_coverage
        else:
            eff_thresh = score_threshold
            eff_cov = min_word_coverage
    else:
        eff_thresh = min(score_threshold, 0.04)
        eff_cov = min(min_word_coverage, 0.15)

    eff_dense = use_dense if namespace == "cx02" else False

    res = hybrid_retrieve(
        query=query,
        chunks=chunks,
        bm25_model=bm25_model,
        top_k=top_k,
        score_threshold=eff_thresh,
        min_word_coverage=eff_cov,
        use_dense=eff_dense,
    )
    if not res and namespace == "cx02":
        comp_res = retrieve(query, top_k=top_k, score_threshold=0.04, min_word_coverage=0.15, use_dense=False, namespace="company")
        if comp_res:
            return comp_res
    return res


def retrieve_company(query: str, top_k: int = 3) -> List[Dict[str, Any]]:
    """Convenience helper to retrieve from company knowledge base namespace."""
    return retrieve(query, top_k=top_k, namespace="company")


def hit_rate_report(test_queries: List[Dict[str, Any]], top_k: int = 3) -> Dict[str, Any]:
    """
    Offline evaluation helper: compute top-1 and top-3 hit rates.
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
