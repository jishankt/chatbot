"""
tests/test_category_retrieval_and_out_of_catalogue.py
Unit tests for Step 4: Category- and Brand-Filtered Retrieval and Out-of-Catalogue refusals.
"""

import pytest
from app.rag.retriever import retrieve
from app.agent.pipeline import CX02Pipeline
from app.agent.guardrails import check_pre_guardrails


def test_category_filtered_retrieval():
    # 1. CAD / Blueprint query -> must retrieve CAD chunk, not CX-02
    cad_chunks = retrieve("I need a printer for CAD blueprints and architectural drawings")
    assert len(cad_chunks) > 0
    assert any("CAD" in c["title"] or "T3100" in c["title"] for c in cad_chunks)
    assert not any("Dye-Sublimation Technology" in c["title"] for c in cad_chunks)

    # 2. Office MFP / Duplex query -> must retrieve WorkForce chunk, not CX-02
    office_chunks = retrieve("Looking for a high speed office printer with automatic duplex scanning")
    assert len(office_chunks) > 0
    assert any("WorkForce" in c["title"] for c in office_chunks)

    # 3. Document scanner query -> must retrieve scanner chunk
    scanner_chunks = retrieve("We need a sheetfed duplex document scanner for records")
    assert len(scanner_chunks) > 0
    assert any("Scanner" in c["title"] for c in scanner_chunks)


def test_out_of_catalogue_polite_refusal_no_cx02_pitch():
    pipeline = CX02Pipeline()

    # 1. 3D printer inquiry -> polite refusal, no CX-02 pitch
    r_3d = pipeline.process("Do you sell 3D printers?", sender_id="user_3d")
    assert "not part of the Kepler Tech commercial catalogue" in r_3d["reply"] or "not available" in r_3d["reply"]
    assert "8.4" not in r_3d["reply"]
    assert "ribbon rewind" not in r_3d["reply"].lower()

    # 2. Thermal POS receipt printer inquiry -> polite refusal, no CX-02 pitch
    r_pos = pipeline.process("I need a thermal POS receipt printer for my restaurant", sender_id="user_pos")
    assert "not part of the Kepler Tech commercial catalogue" in r_pos["reply"] or "not available" in r_pos["reply"]
    assert "8.4" not in r_pos["reply"]

    # 3. Laptop inquiry -> polite refusal
    r_laptop = pipeline.process("Do you sell gaming laptops or MacBooks?", sender_id="user_laptop")
    assert "not part of the Kepler Tech commercial catalogue" in r_laptop["reply"] or "not available" in r_laptop["reply"]

    # 4. Competitor brand inquiry (DNP) -> polite refusal listing authorized Citizen & Epson
    r_dnp = pipeline.process("Do you have DNP DS620 printers or media?", sender_id="user_dnp")
    assert "not available in our catalog" in r_dnp["reply"] or "authorized" in r_dnp["reply"]
    assert "Citizen" in r_dnp["reply"]
    assert "Epson" in r_dnp["reply"]
