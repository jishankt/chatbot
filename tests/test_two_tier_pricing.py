"""
tests/test_two_tier_pricing.py
Unit tests for Step 3: Validated Catalogue Ingestion & Two-Tier Pricing.
"""

import pytest
from app.tools.pricing import get_price, calculate_cost_per_print
from app.tools.links import get_product_link
from app.agent.pipeline import CX02Pipeline


def test_tier1_verified_numeric_pricing():
    # 1. SC-T3100 (Epson CAD) -> 3,880.00 AED
    p_t3100 = get_price("SC-T3100")
    assert p_t3100["status"] == "success"
    assert p_t3100["price"] == 3880.0
    assert "3,880.00 AED" in p_t3100["formatted_price"]
    assert "VAT" in p_t3100["vat_status"]
    assert "confirmation by our sales desk" in p_t3100["confirmation_note"]

    # 2. SC-T5100 (Epson CAD) -> 9,700.00 AED
    p_t5100 = get_price("SC-T5100")
    assert p_t5100["status"] == "success"
    assert p_t5100["price"] == 9700.0

    # 3. SC-P700 (Epson Photo) -> 3,400.00 AED
    p_p700 = get_price("SC-P700")
    assert p_p700["status"] == "success"
    assert p_p700["price"] == 3400.0

    # 4. SC-P900 (Epson Photo) -> 4,880.00 AED
    p_p900 = get_price("SC-P900")
    assert p_p900["status"] == "success"
    assert p_p900["price"] == 4880.0

    # 5. SC-F100 (Epson Sublimation) -> 1,950.00 AED
    p_f100 = get_price("SC-F100")
    assert p_f100["status"] == "success"
    assert p_f100["price"] == 1950.0

    # 6. WF-C5890 (Epson Office) -> 1,656.00 AED
    p_c5890 = get_price("WF-C5890")
    assert p_c5890["status"] == "success"
    assert p_c5890["price"] == 1656.0

    # 7. Citizen Lineup
    assert get_price("CX-02")["price"] == 4385.0
    assert get_price("CY-02")["price"] == 3400.0
    assert get_price("CZ-01")["price"] == 3200.0
    assert get_price("CX-02W")["price"] == 6820.0


def test_tier2_price_on_request_no_numbers():
    # 1. SC-T7700D -> Quote required, price is None
    p_t7700d = get_price("SC-T7700D")
    assert p_t7700d["status"] == "quote_required"
    assert p_t7700d["price"] is None
    assert "official quotation" in p_t7700d["message"]

    # 2. SC-P9500 -> Quote required, price is None
    p_p9500 = get_price("SC-P9500")
    assert p_p9500["status"] == "quote_required"
    assert p_p9500["price"] is None
    assert "official quotation" in p_p9500["message"]

    # 3. EM-C800 -> Quote required, price is None
    p_emc800 = get_price("EM-C800")
    assert p_emc800["status"] == "quote_required"
    assert p_emc800["price"] is None

    # 4. Scanners (DS-530II, DS-770II) -> Quote required, price is None
    p_ds530 = get_price("DS-530II")
    assert p_ds530["status"] == "quote_required"
    assert p_ds530["price"] is None

    p_ds770 = get_price("DS-770II")
    assert p_ds770["status"] == "quote_required"
    assert p_ds770["price"] is None


def test_scanner_consumables_and_cx02w_media():
    # Scanner consumables -> not listed, offer specialist
    res_sc = get_price("scanner roller kit")
    assert res_sc["status"] == "not_listed"
    assert "not listed on our online store" in res_sc["message"]

    # CX2-MS46-2PC print cost calculation has unverified estimate note
    cpp = calculate_cost_per_print("4x6")
    assert cpp["status"] == "success"
    assert cpp["is_estimate"] is True
    assert "unverified estimate" in cpp["estimate_note"]


def test_ds770ii_url_suppressed():
    # DS-770II URL must not duplicate DS-530II
    link_res = get_product_link("DS-770II")
    assert link_res["status"] == "unavailable"
    assert link_res["url"] is None


def test_pipeline_two_tier_pricing_flow():
    pipeline = CX02Pipeline()

    # 1. SC-T3100: must output exact verified price
    r1 = pipeline.process("What is the price of the Epson SC-T3100 plotter?", sender_id="p_user_1")
    assert "3,880.00 AED" in r1["reply"]
    assert "5% UAE VAT" in r1["reply"]

    # 2. SC-T7700D: must output official quotation, no numbers
    r2 = pipeline.process("What is the price of the Epson SC-T7700D?", sender_id="p_user_2")
    assert "official quotation" in r2["reply"]
    assert "AED" not in r2["reply"]

    # 3. Discount negotiation: no invented number, offers handoff
    r3 = pipeline.process("Can I get a 20% discount on 3 units?", sender_id="p_user_3")
    assert "management" in r3["reply"].lower() or "sales" in r3["reply"].lower()
