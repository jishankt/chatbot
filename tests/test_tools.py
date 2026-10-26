import pytest
from app.config import Config
from app.tools.pricing import get_price, check_stock, list_products, calculate_cost_per_print
from app.tools.links import get_product_link
from app.tools.quote import create_quote
from app.tools.policies import get_policy
from app.tools.handoff import handoff_to_human, create_lead
from app.tools.dispatcher import execute_tool


def test_get_price_whitelisted():
    res = get_price("CX-02")
    assert res["status"] == "success"
    assert res["price"] == 4385.0
    assert "4,385.00 AED" in res["formatted_price"]
    assert res["in_stock"] is True

    # Bag
    res_bag = get_price("CX-02-BAG")
    assert res_bag["status"] == "success"
    assert res_bag["price"] == 325.0

    # Pen (190 AED with to_confirm_note)
    res_pen = get_price("CITIZEN-PEN")
    assert res_pen["status"] == "success"
    assert res_pen["price"] == 190.0
    assert res_pen["to_confirm_note"] is not None

    # Media sets (estimates vs verified)
    res_ms46 = get_price("CX2-MS46-2PC")
    assert res_ms46["price"] == 490.0
    assert "estimate" in res_ms46["estimate_note"].lower()

    res_ms57 = get_price("CX2-MS57-2PC")
    assert res_ms57["price"] == 500.0
    assert res_ms57["estimate_note"] is None


def test_get_price_unknown_or_unsupported():
    res_unknown = get_price("UNKNOWN-SKU-999")
    assert res_unknown["status"] == "error"
    assert res_unknown["handoff"] is True

    # 6x9 media set
    res_6x9 = get_price("6x9 media")
    assert res_6x9["status"] == "unsupported"
    assert res_6x9["handoff"] is True


def test_stale_price_note(monkeypatch):
    monkeypatch.setattr(Config, "PRICE_MAX_AGE_DAYS", 0)
    res = get_price("CX-02")
    assert res["stale_note"] is not None
    assert "Please confirm current rates" in res["stale_note"]


def test_calculate_cost_per_print():
    res_46 = calculate_cost_per_print("4x6", volume=800)
    assert res_46["status"] == "success"
    # 490 / 800 = 0.6125 AED
    assert abs(res_46["cost_per_print"] - 0.6125) < 0.001
    assert res_46["is_estimate"] is True
    assert res_46["total_cost"] == 490.0

    res_57 = calculate_cost_per_print("5x7", volume=460)
    assert res_57["is_estimate"] is False
    assert abs(res_57["cost_per_print"] - (500.0 / 460)) < 0.001

    res_69 = calculate_cost_per_print("6x9")
    assert res_69["status"] == "unsupported"
    assert res_69["handoff"] is True


def test_quote_quantity_limits_and_arithmetic():
    # 1. Negative or 0 qty rejected
    res_zero = create_quote([{"sku": "CX-02", "qty": 0}])
    assert res_zero["status"] == "error"

    # 2. Exceeding 1000 qty rejected
    res_excess = create_quote([{"sku": "CX-02", "qty": 1001}])
    assert res_excess["status"] == "error"

    # 3. Valid quote calculation (VAT disabled by default)
    res_valid = create_quote([
        {"sku": "CX-02", "qty": 2},
        {"sku": "CX2-MS46-2PC", "qty": 3}
    ], customer_name="Tech Studio Dubai")

    assert res_valid["status"] == "success"
    expected_subtotal = round((4385.0 * 2) + (490.0 * 3), 2)  # 8770 + 1470 = 10240
    assert res_valid["subtotal"] == expected_subtotal
    assert res_valid["total"] == expected_subtotal
    assert res_valid["vat_amount"] is None
    assert "Consult sales desk" in res_valid["text_summary"]


def test_quote_with_vat_configured(monkeypatch):
    monkeypatch.setattr(Config, "VAT_RATE", 0.05)
    monkeypatch.setattr(Config, "PRICES_INCLUDE_VAT", False)

    res = create_quote([{"sku": "CX-02", "qty": 1}])
    assert res["status"] == "success"
    assert res["subtotal"] == 4385.0
    expected_vat = round(4385.0 * 0.05, 2)  # 219.25
    assert res["vat_amount"] == expected_vat
    assert res["total"] == 4385.0 + expected_vat
    assert "VAT (5%): 219.25 AED" in res["text_summary"]


def test_get_policy_filled_policy_with_disclaimer():
    # Filled policies must answer with policy text and website terms disclaimer
    for p in ["payment_methods", "delivery_charges", "delivery_time", "return_policy", "cancellation", "pickup"]:
        res = get_policy(p)
        assert res["status"] == "success"
        assert res["handoff"] is False
        assert res["handoff_offered"] is True
        assert "per our website terms (updated" in res["message"].lower()


def test_get_policy_null_policies_handoff():
    # Null policies must force a handoff
    for p in ["warranty", "vat_treatment", "installation", "support_terms"]:
        res = get_policy(p)
        assert res["status"] == "unknown"
        assert res["handoff"] is True
        assert "require confirmation from Kepler Tech LLC sales desk" in res["message"]


def test_get_policy_outside_gcc_delivery_handoff():
    # Inquiries specifying delivery outside GCC must force a handoff
    res_kenya = get_policy("delivery", destination="Kenya")
    assert res_kenya["status"] == "handoff"
    assert res_kenya["handoff"] is True
    assert "outside the gcc" in res_kenya["message"].lower()

    res_kw = get_policy("delivery_outside_gcc")
    assert res_kw["status"] == "handoff"
    assert res_kw["handoff"] is True
    assert "outside the gcc" in res_kw["message"].lower()


def test_safe_dispatcher():
    # Valid call
    ok_res = execute_tool("get_price", {"sku": "CX-02"})
    assert ok_res["status"] == "success"
    assert ok_res["result"]["price"] == 4385.0

    # Unknown tool
    err_res = execute_tool("invalid_tool", {})
    assert err_res["status"] == "error"
    assert err_res["handoff"] is True

    # Missing required argument
    missing_res = execute_tool("get_price", {})
    assert missing_res["status"] == "error"
    assert "Missing required parameter" in missing_res["message"]
