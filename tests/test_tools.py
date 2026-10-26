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
    assert "validation error" in missing_res["message"].lower() or "missing" in missing_res["message"].lower()


def test_unknown_sku_refusal_no_default_cx02():
    from app.agent.pipeline import CX02Pipeline
    pipeline = CX02Pipeline()

    # Asking for unsupported accessory or unknown SKU must not quote 4,385 AED printer
    res_adapter = pipeline.process("What is the price of the wireless adapter?")
    assert "4,385" not in res_adapter["reply"]
    assert any(t.get("tool") == "handoff_to_human" for t in res_adapter["tools_called"])
    assert "could not identify the specific product" in res_adapter["reply"].lower()

    res_tripod = pipeline.process("How much does the tripod cost?")
    assert "4,385" not in res_tripod["reply"]
    assert any(t.get("tool") == "handoff_to_human" for t in res_tripod["tools_called"])


def test_quantity_parsing_arabic_and_k_suffix():
    from app.utils.quantity import parse_quantity
    assert parse_quantity("5,000") == 5000
    assert parse_quantity("1k") == 1000
    assert parse_quantity("2.5k") == 2500
    assert parse_quantity("٣") == 3
    assert parse_quantity("quote for 10 units") == 10

    # Quotation with quantity >= 10 printers must trigger large-quantity handoff
    res_bulk = create_quote([{"sku": "CX-02", "qty": "10"}])
    assert res_bulk["status"] == "error"
    assert res_bulk["handoff"] is True
    assert res_bulk.get("large_quantity") is True
    assert "commercial tier pricing" in res_bulk["message"].lower()


def test_outbound_whatsapp_sender():
    from app.whatsapp.client import send_whatsapp_message
    res = send_whatsapp_message(to="+971508901641", text="Hello from Kepler Tech")
    assert res["status"] in ("sent", "mock_sent")
    assert "***" in res["to"]  # Phone number masked in logs / responses


import uuid

def test_quote_idempotency():
    sender = f"test_quote_idemp_{uuid.uuid4().hex[:8]}"
    items = [{"sku": "CX2-MS46-2PC", "qty": 2}]

    # Call 1: Creates fresh quote
    q1 = create_quote(items=items, sender_id=sender)
    assert q1["status"] == "success"
    assert "quote_id" in q1
    assert q1.get("idempotent") is None

    # Call 2: Identical items and sender returns the existing quote
    q2 = create_quote(items=items, sender_id=sender)
    assert q2["status"] == "success"
    assert q2["quote_id"] == q1["quote_id"]
    assert q2.get("idempotent") is True


def test_handoff_and_lead_idempotency():
    from app.tools.handoff import handoff_to_human, create_lead
    sender = f"test_handoff_idemp_{uuid.uuid4().hex[:8]}"

    # Handoff idempotency
    h1 = handoff_to_human(reason="Commercial discount request", sender_id=sender)
    assert h1["status"] == "handoff_initiated"
    assert h1.get("idempotent") is None

    h2 = handoff_to_human(reason="Commercial discount request", sender_id=sender)
    assert h2["status"] == "handoff_initiated"
    assert h2.get("idempotent") is True

    # Lead capture idempotency
    l1 = create_lead(name="Sarah", phone="+971501112233", sender_id=sender)
    assert l1["status"] == "success"
    assert l1.get("idempotent") is None

    l2 = create_lead(name="Sarah", phone="+971501112233", sender_id=sender)
    assert l2["status"] == "success"
    assert l2["lead_id"] == l1["lead_id"]
    assert l2.get("idempotent") is True


def test_dispatcher_pydantic_validation_bounds():
    # Invalid quantity > 1000 in create_quote
    res_overflow = execute_tool("create_quote", {
        "items": [{"sku": "CX-02", "qty": 5000}]
    })
    assert res_overflow["status"] == "error"
    assert "validation error" in res_overflow["message"].lower()

    # Invalid empty items in create_quote
    res_empty = execute_tool("create_quote", {"items": []})
    assert res_empty["status"] == "error"
    assert "validation error" in res_empty["message"].lower()

