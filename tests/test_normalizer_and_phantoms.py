"""
tests/test_normalizer_and_phantoms.py
Unit tests for Step 2:
1. Brand, Model & SKU Alias Normalization
2. Phantom Model Detection & Rejection (No Silent Substitution)
3. Ambiguous Model Disambiguation (P8500 -> P8500D vs P8500DM)
4. End-to-end Pipeline Verification
"""

import pytest
from app.cognitive.normalizer import (
    normalize_brand,
    normalize_model_or_sku,
    detect_phantom_model,
    detect_ambiguous_model,
)
from app.cognitive.reader import read_message
from app.agent.pipeline import CX02Pipeline


def test_brand_aliases():
    assert normalize_brand("citizon photo printer") == "Citizen"
    assert normalize_brand("citzen printers in UAE") == "Citizen"
    assert normalize_brand("سيتيزن للطباعة") == "Citizen"
    assert normalize_brand("epsonn plotter") == "Epson"
    assert normalize_brand("ابسون a1") == "Epson"
    assert normalize_brand("HP laserjet") is None


def test_model_and_sku_aliases():
    # Citizen models
    assert normalize_model_or_sku("price of cx02")[0] == "CX-02"
    assert normalize_model_or_sku("do you have cx02w in stock?")[0] == "CX-02W"
    assert normalize_model_or_sku("tell me about cy02")[0] == "CY-02"
    assert normalize_model_or_sku("cz01 lightweight")[0] == "CZ-01"

    # Epson CAD / Technical
    assert normalize_model_or_sku("epson t3100")[0] == "SC-T3100"
    assert normalize_model_or_sku("sct5100 specs")[0] == "SC-T5100"
    assert normalize_model_or_sku("sc-t7700d dual roll")[0] == "SC-T7700D"

    # Epson Photo / Fine Art
    assert normalize_model_or_sku("sc-p700 a3 photo")[0] == "SC-P700"
    assert normalize_model_or_sku("p900 17 inch")[0] == "SC-P900"
    assert normalize_model_or_sku("scp9500 44 inch")[0] == "SC-P9500"

    # Epson Sublimation & Business MFP
    assert normalize_model_or_sku("f100 sublimation")[0] == "SC-F100"
    assert normalize_model_or_sku("emc800 workforce")[0] == "EM-C800"
    assert normalize_model_or_sku("wfc5890 dwf")[0] == "WF-C5890"
    assert normalize_model_or_sku("am-c400 enterprise")[0] == "AM-C4000"

    # Consumables
    assert normalize_model_or_sku("c13t49n400 yellow ink")[0] == "C13T49N400"
    assert normalize_model_or_sku("cx2w 812 media roll")[0] == "CX2W 812"


def test_phantom_model_detection():
    # CX-02S -> must not silently become CX-02!
    p_cx02s = detect_phantom_model("Do you have the Citizen CX-02S in stock?")
    assert p_cx02s is not None
    assert "Citizen CX-02S" in p_cx02s["raw_name"]
    assert "CX-02" in p_cx02s["suggested_models"]
    assert "CX-02W" in p_cx02s["suggested_models"]

    # SC-P9999 -> must reject
    p_p9999 = detect_phantom_model("How much for Epson SC-P9999?")
    assert p_p9999 is not None
    assert "SC-P9500" in p_p9999["suggested_models"]

    # WF-C55890 -> must reject
    p_wfc55890 = detect_phantom_model("Quote for WF-C55890 please")
    assert p_wfc55890 is not None
    assert "WF-C5890" in p_wfc55890["suggested_models"]

    # CX-01 -> must reject
    p_cx01 = detect_phantom_model("Tell me about Citizen CX-01")
    assert p_cx01 is not None
    assert "CZ-01" in p_cx01["suggested_models"]


def test_ambiguous_model_disambiguation():
    # P8500 requires disambiguation between SC-P8500D and SC-P8500DM
    amb = detect_ambiguous_model("What is the price of Epson P8500?")
    assert amb is not None
    assert "SC-P8500D" in amb["options"]
    assert "SC-P8500DM" in amb["options"]

    # Explicit SC-P8500D should NOT be flagged as ambiguous
    assert detect_ambiguous_model("What is the price of SC-P8500D?") is None


def test_pipeline_phantom_and_disambiguation_flow():
    pipeline = CX02Pipeline()

    # 1. User asks for phantom CX-02S
    res_phantom = pipeline.process("Can I get a quotation for the Citizen CX-02S?", sender_id="phantom_user_1")
    assert "CX-02S" in res_phantom["reply"]
    assert "does not exist" in res_phantom["reply"]
    assert "CX-02" in res_phantom["reply"]
    assert "CX-02W" in res_phantom["reply"]
    assert res_phantom["intent"] == "out_of_scope"

    # 2. User asks for ambiguous P8500
    res_amb = pipeline.process("Tell me about the Epson P8500 printer", sender_id="amb_user_1")
    assert "SC-P8500D" in res_amb["reply"]
    assert "SC-P8500DM" in res_amb["reply"]
    assert "dual-roll" in res_amb["reply"]
    assert res_amb["intent"] == "clarification"
