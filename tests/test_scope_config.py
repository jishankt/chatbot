import json
from pathlib import Path
import yaml
from app.config import Config, BASE_DIR
from app.tools.pricing import load_catalog, load_products_whitelist, get_price


def test_scope_yaml_structure():
    scope_path = BASE_DIR / "config" / "scope.yaml"
    assert scope_path.exists(), "config/scope.yaml must exist"

    with open(scope_path, "r", encoding="utf-8") as f:
        scope = yaml.safe_load(f)

    assert "active_products" in scope
    active_ids = [p["id"] for p in scope["active_products"]]
    assert "CX-02" in active_ids

    assert "whitelisted_accessories" in scope
    acc_ids = [a["id"] for a in scope["whitelisted_accessories"]]
    assert "CX2-MS46-2PC" in acc_ids
    assert "CX-02-BAG" in acc_ids
    assert "CITIZEN-PEN" in acc_ids

    assert "blocked_brands" in scope
    assert "dnp" in scope["blocked_brands"]
    assert "epson" in scope["blocked_brands"]
    assert "fujifilm" in scope["blocked_brands"]

    assert "handoff_only_products" in scope
    assert "cx-02w" in scope["handoff_only_products"]
    assert "cy-02" in scope["handoff_only_products"]

    assert "large_quantity_handoff_threshold" in scope
    assert scope["large_quantity_handoff_threshold"] == 10


def test_products_json_schema_enrichment():
    catalog = load_catalog()
    assert "products" in catalog
    products = catalog["products"]

    required_agnostic_fields = [
        "id", "sku", "site_sku", "model_number", "purchase_mode",
        "brand", "family", "name", "category",
        "price", "currency", "as_of", "in_stock", "active",
        "compatible_with", "unverified_fields", "attributes", "url"
    ]

    for sku, prod in products.items():
        for field in required_agnostic_fields:
            assert field in prod, f"Product {sku} missing required field '{field}'"
        assert prod["brand"] == "Citizen"
        assert prod["currency"] == "AED"
        assert prod["purchase_mode"] in ("cart", "enquiry")
        assert isinstance(prod["price"], float)
        assert isinstance(prod["compatible_with"], list)
        assert isinstance(prod["attributes"], dict)


def test_policies_json_metadata():
    with open(Config.POLICIES_PATH, "r", encoding="utf-8") as f:
        policies = json.load(f)

    # Every filled policy must have source_url, source_date, and confirm_before_use
    for key, val in policies.items():
        if key == "company_contact":
            continue
        if val is not None:
            assert "source_url" in val, f"Policy '{key}' missing source_url"
            assert "source_date" in val, f"Policy '{key}' missing source_date"
            assert "confirm_before_use" in val, f"Policy '{key}' missing confirm_before_use"
            assert val["confirm_before_use"] is True


def test_6x9_media_not_listed_and_handoff():
    from app.agent.pipeline import CX02Pipeline
    pipeline = CX02Pipeline()

    res = pipeline.process("Do you sell 6x9 media")
    assert "not listed, I'll ask the team" in res["reply"] or "not listed on our website" in res["reply"]
    # Verify handoff triggered
    assert any(t.get("tool") == "handoff_to_human" for t in res["tools_called"])


def test_backward_compatibility_with_existing_tools():
    # Verify legacy tool calls still operate seamlessly with migrated schema
    res = get_price("CX-02")
    assert res["status"] == "success"
    assert res["price"] == 4385.0
    assert res["formatted_price"] == "4,385.00 AED"

    res_pen = get_price("CITIZEN-PEN")
    assert res_pen["status"] == "success"
    assert res_pen["price"] == 190.0

    res_media = get_price("CX2-MS46-2PC")
    assert res_media["status"] == "success"
    assert res_media["price"] == 490.0
    assert res_media["estimate_note"] is not None
