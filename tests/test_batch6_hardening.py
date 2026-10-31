"""
tests/test_batch6_hardening.py
Batch 6 hardening test suite for CX-02 Web Chatbot.
Failing tests first: verifies admission control, positive scope gating,
real Ollama capacity handling, Stopped regime fail-fast, and admin unlock auth tracking.
"""

import os
import time
import pytest
from pathlib import Path
from unittest.mock import patch

from app.main import create_app
from app.config import Config


# ============================================================================
# 1. Deterministic intents bypass LLM
# ============================================================================

def test_deterministic_intents_bypass_llm():
    """
    Deterministic inquiries (pricing, policies, stock, quotations, website links)
    MUST bypass both LLM NLU and LLM text generation entirely to save capacity
    and guarantee non-negotiable commercial authority.
    """
    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()

    deterministic_messages = [
        "What is the price of the Citizen CX-02 printer?",
        "What is your warranty policy for Dubai?",
        "Can I get a quotation for 2 boxes of 4x6 media?",
        "What is the website link for Kepler Tech?",
        "Do you have stock of the CX-02 carry bag?"
    ]

    with patch("app.agent.llm.generate_llm_response") as mock_gen, \
         patch("app.cognitive.understander.extract_llm_nlu") as mock_nlu:
        mock_gen.side_effect = AssertionError("LLM generation called for deterministic inquiry!")
        mock_nlu.side_effect = AssertionError("LLM NLU called for deterministic inquiry!")

        for msg in deterministic_messages:
            res = client.post("/chat", json={"message": msg, "sender_id": "test_bypass_sess"})
            assert res.status_code == 200
            data = res.get_json()
            assert "reply" in data and len(data["reply"]) > 0


# ============================================================================
# 2. Concurrency cap & fail-fast queue wait budget
# ============================================================================

def test_concurrency_cap_shared_across_workers():
    """
    Admission control: cap on concurrent generations shared across gunicorn workers
    via DB-backed lease or semaphore. Excess requests waiting longer than budget
    fail fast to deterministic extractive reply with fallback reason 'queue_wait_timeout'.
    """
    from app.agent.admission import acquire_generation_slot, release_generation_slot, get_active_generation_count

    # Should allow up to MAX_CONCURRENT_GENERATIONS
    max_slots = getattr(Config, "MAX_CONCURRENT_GENERATIONS", 2)
    leases = []
    for i in range(max_slots):
        lease_id = acquire_generation_slot(worker_id=f"worker_test_{i}", wait_timeout=0.1)
        assert lease_id is not None, f"Failed to acquire slot {i} under capacity limit {max_slots}"
        leases.append(lease_id)

    # Attempting to acquire beyond capacity should fail fast
    extra_lease = acquire_generation_slot(worker_id="worker_extra", wait_timeout=0.2)
    assert extra_lease is None, "Admission control allowed generation beyond concurrency cap!"

    # Releasing slot restores availability
    release_generation_slot(leases[0])
    restored_lease = acquire_generation_slot(worker_id="worker_restored", wait_timeout=0.2)
    assert restored_lease is not None, "Failed to re-acquire released generation slot!"

    for l in leases[1:] + [restored_lease]:
        release_generation_slot(l)


# ============================================================================
# 3. Widget typing indicator
# ============================================================================

def test_widget_typing_indicator_in_frontend():
    """
    Frontend must include typing indicator elements and JS state handling
    to provide immediate visual responsiveness while admission/generation runs.
    """
    js_content = Path("/opt/basics/app/static/js/app.js").read_text(encoding="utf-8")
    css_content = Path("/opt/basics/app/static/css/index.css").read_text(encoding="utf-8")

    assert "typing-indicator" in js_content, "typing-indicator not referenced in app.js!"
    assert "showTypingIndicator" in js_content or "showTyping" in js_content, "Typing indicator helper missing in app.js!"
    assert "typing-indicator" in css_content, "typing-indicator CSS animation missing in index.css!"


# ============================================================================
# 4. Stopped regime fail-fast (<1.0s, p50 < 2.0s)
# ============================================================================

def test_stopped_regime_fails_under_1s_with_fallback():
    """
    When Ollama is unreachable / connection refused, the system must fail in under 1.0s
    and immediately return the deterministic extractive fallback.
    """
    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()

    import requests
    def mock_conn_refused(*args, **kwargs):
        raise requests.exceptions.ConnectionError("Connection refused on port 11434")

    with patch("requests.post", side_effect=mock_conn_refused):
        t0 = time.perf_counter()
        res = client.post(
            "/chat",
            json={"message": "Can you explain the thermal dye-sub print process?", "sender_id": "test_stopped_sess"}
        )
        elapsed = time.perf_counter() - t0

        assert res.status_code == 200
        assert elapsed < 1.0, f"Stopped regime took {elapsed:.2f}s, expected < 1.0s!"
        body = res.get_json()
        assert "Citizen CX-02" in body["reply"] or "specifications" in body["reply"].lower()


# ============================================================================
# 5. Positive scope gating (no competitor brand blocklist)
# ============================================================================

def test_positive_scope_gating_rejects_invented_and_unrelated_queries():
    """
    Replace competitor brand blocklist with positive scope gating:
    Queries must mention our product / domain or exceed relevance threshold on catalog.
    Invented brands, unrelated products, and 40 fresh unseen questions must be rejected.
    """
    from app.rag.retriever import retrieve

    # 1. Invented brands
    invented_brands = [
        "What is the price of a Xylophonic PX-9 photo printer?",
        "Can I buy AeroPrint 4000 paper rolls?",
        "Quote for Zorblax D7 sublimation unit",
        "Do you sell QuantumJet 900 minilabs?"
    ]

    # 2. Unrelated products
    unrelated_products = [
        "Do you have Italian espresso beans in stock?",
        "I need running shoes size 43",
        "How much is a petrol chainsaw?",
        "Quote for high performance car tires",
        "Where can I buy gaming laptops in Dubai?"
    ]

    # 3. 40 fresh unseen queries (distinct from Batch 5)
    unseen_queries = [
        "What is the cost of Pentax photo scanners?",
        "Do you supply Lexmark laser toner cartridges?",
        "Can you quote Ricoh multifunction copiers?",
        "Price check on Kyocera taskalfa printers",
        "Looking for Toshiba thermal barcode ribbons",
        "How much for Zebra ZT410 industrial printer?",
        "Do you distribute Brady label makers in UAE?",
        "We need Casio compact thermal receipt paper",
        "Is Olympus digital camcorder available?",
        "Price for Panasonic broadcast studio cameras",
        "Can you ship Nikon DSLR camera lenses?",
        "Looking for Leica digital rangefinder bodies",
        "Do you sell Hasselblad medium format sensors?",
        "Quote for Godox studio strobe flash lights",
        "Do you stock Profoto softboxes and diffusers?",
        "What is the warranty on Elinchrom flash heads?",
        "Price check on Manfrotto carbon fiber tripods",
        "Looking for Gitzo heavy duty video monopods",
        "Can I buy DJI Ronin camera gimbals from you?",
        "Do you carry Zhiyun crane camera stabilizers?",
        "What is the lead time for Blackmagic cinema cameras?",
        "Can you quote RED digital cinema accessories?",
        "Price for Sony FX3 full frame cinema line",
        "Do you sell Arri Alexa lighting equipment?",
        "Looking for Sennheiser wireless lavalier microphones",
        "Price check on Rode wireless GO transmitters",
        "Can you ship Shure SM7B dynamic microphones?",
        "Do you stock Zoom H6 handy audio recorders?",
        "How much for Tascam multi track digital mixers?",
        "Quote for Yamaha professional studio monitors",
        "Where can I buy Genelec active sound monitors?",
        "Price check on Focusrite Scarlett audio interfaces",
        "Do you supply Roland vinyl cutting plotters?",
        "What is the price of Graphtec cutting plotters?",
        "Can you quote Mimaki textile sublimation plotters?",
        "Looking for Mutoh eco-solvent sign printers",
        "Do you sell Summa flatbed digital cutters?",
        "How much for GCC vinyl desktop cutters?",
        "Is Silhouette Cameo craft cutter in stock?",
        "Can you provide Cricut maker replacement blades?"
    ]

    all_test_queries = invented_brands + unrelated_products + unseen_queries
    assert len(all_test_queries) == 49

    for q in all_test_queries:
        res = retrieve(q, top_k=2, use_dense=False)
        assert len(res) == 0, f"False match on off-scope query '{q}': {[r['section'] for r in res]}"


# ============================================================================
# 6. Admin unlock auth & failure counting
# ============================================================================

def test_admin_unlock_auth_and_failure_counting():
    """
    POST /admin/unlock must require valid ADMIN_API_KEY.
    Failed unlock attempts must be recorded in admin_auth_failures table.
    """
    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()

    # Unauthorized unlock attempt
    res = client.post(
        "/admin/unlock",
        json={"ip": "192.168.1.50"},
        headers={"X-Admin-Key": "wrong_key"}
    )
    assert res.status_code == 401

    # Verify that failed unlock attempt was recorded
    from app.storage.db import get_db_connection
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM admin_auth_failures WHERE endpoint LIKE '%unlock%'")
    count = cur.fetchone()[0]
    conn.close()
    assert count >= 1, "Failed unlock attempt was not tracked in admin_auth_failures!"
