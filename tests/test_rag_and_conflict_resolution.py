"""
tests/test_rag_and_conflict_resolution.py
Unit tests verifying RAG accuracy, conflict resolution, ambiguous recommendation clarification,
and out-of-scope refusals for the 4 Citizen photo printers and consumables.
"""

import pytest
from app.agent.pipeline import CX02Pipeline
from app.rag.retriever import retrieve


def test_rag_retrieval_accuracy():
    # 1. Anti-curl query retrieves CZ-01 specs
    r_curl = retrieve("Which printer has anti-curl mechanism?")
    assert len(r_curl) > 0
    assert any("CZ-01" in c["section"] or "Conflict" in c["section"] or "Lineup" in c["section"] for c in r_curl)
    assert any("anti-curl" in c["text"].lower() for c in r_curl)

    # 2. Large format 8x10 query retrieves CX-02W specs
    r_810 = retrieve("Which printer can print 8x10 studio portraits?")
    assert len(r_810) > 0
    assert any("CX-02W" in c["section"] or "Conflict" in c["section"] or "Lineup" in c["section"] for c in r_810)
    assert any("8x10" in c["text"].lower() for c in r_810)

    # 3. High capacity 700 prints query retrieves CY-02 specs
    r_700 = retrieve("What is the roll capacity of the Citizen CY-02?")
    assert len(r_700) > 0
    assert any("CY-02" in c["section"] for c in r_700)
    assert any("700 prints" in c["text"].lower() for c in r_700)

    # 4. Thermal printhead cleaning pen maintenance
    r_pen = retrieve("How to clean the thermal printhead with the cleaning pen?")
    assert len(r_pen) > 0
    assert any("Cleaning Pen" in c["text"] or "CITIZEN-PEN" in c["text"] for c in r_pen)


def test_conflict_resolution_large_format_vs_high_capacity():
    pipeline = CX02Pipeline()
    res = pipeline.process(
        "I need a printer for 8x10 prints and 700 prints per roll capacity",
        sender_id="test_conf_810_700"
    )
    # Must explain trade-off between CX-02W (8x10) and CY-02 (700 prints/roll)
    assert "CX-02W" in res["reply"]
    assert "CY-02" in res["reply"]
    assert "8×10" in res["reply"] or "8x10" in res["reply"]
    assert "700" in res["reply"]
    # Must return cards for both compared models
    skus = [c["sku"] for c in res["cards"]]
    assert "CX-02W" in skus
    assert "CY-02" in skus


def test_conflict_resolution_ultralight_vs_large_format():
    pipeline = CX02Pipeline()
    res = pipeline.process(
        "Can I get a 5.8kg ultra lightweight printer that prints 8x10?",
        sender_id="test_conf_light_810"
    )
    # Must explain trade-off between CZ-01 (5.8 kg) and CX-02W (8x10)
    assert "CZ-01" in res["reply"]
    assert "CX-02W" in res["reply"]
    assert "5.8 kg" in res["reply"]
    skus = [c["sku"] for c in res["cards"]]
    assert "CZ-01" in skus
    assert "CX-02W" in skus


def test_ambiguous_recommendation_clarifying_question():
    pipeline = CX02Pipeline()
    res = pipeline.process(
        "Which printer should I buy for my business?",
        sender_id="test_ambiguous_rec"
    )
    # Must ask clarifying questions for formats and key priorities
    assert "Print Formats" in res["reply"]
    assert "CZ-01" in res["reply"]
    assert "CY-02" in res["reply"]
    assert len(res["cards"]) == 4


def test_out_of_scope_other_products_refusal():
    pipeline = CX02Pipeline()
    res = pipeline.process(
        "Do you sell 3D printers or laptops?",
        sender_id="test_other_prod"
    )
    assert "Currently, we do not provide that product" in res["reply"]
    assert "Citizen" in res["reply"]
    assert len(res["cards"]) == 0
