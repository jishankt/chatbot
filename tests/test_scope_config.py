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

    assert "company_scope" in scope
    assert scope["company_scope"] == "kepler_printers"
    assert "product_detail_active" in scope
    assert "CX-02" in scope["product_detail_active"]
    assert "brands_sold" in scope
    assert "Epson" in scope["brands_sold"]
    assert "Citizen" in scope["brands_sold"]

    assert "blocked_brands" in scope
    assert "dnp" in scope["blocked_brands"]
    assert "epson" not in scope["blocked_brands"]
    assert "fujifilm" in scope["blocked_brands"]

    assert "handoff_only_products" in scope
    assert "cx-02w" in scope["handoff_only_products"]
    assert "cy-02" in scope["handoff_only_products"]

    assert "catalog_categories" in scope
    assert len(scope["catalog_categories"]) >= 5

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

    with open(BASE_DIR / "config" / "scope.yaml", "r", encoding="utf-8") as f:
        scope = yaml.safe_load(f)

    for sku, prod in products.items():
        for field in required_agnostic_fields:
            assert field in prod, f"Product {sku} missing required field '{field}'"
        assert prod["brand"] in scope["brands_sold"]
        assert prod["currency"] == "AED"
        assert prod["purchase_mode"] in ("cart", "enquiry", "quote")
        assert prod["price"] is None or isinstance(prod["price"], float)
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


def test_numbers_and_attributes_grounded():
    import re
    # 1. Test KB chunks against declared raw sources
    chunks_path = BASE_DIR / "data" / "chunks.json"
    with open(chunks_path, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    for c in chunks:
        raw_sources = c.get("raw_sources", [])
        assert raw_sources, f"Chunk {c['chunk_id']} missing declared raw_sources"
        corpus = ""
        for src in raw_sources:
            p = BASE_DIR / src if not Path(src).is_absolute() else Path(src)
            assert p.exists(), f"Raw source {src} not found on disk"
            corpus += p.read_text(encoding="utf-8") + "\n"

        numbers = set(re.findall(r"\b\d+(?:\.\d+)?\b", c["text"]))
        for num in numbers:
            pattern = r"(?<![0-9])" + re.escape(num) + r"(?![0-9])"
            assert re.search(pattern, corpus), (
                f"Number '{num}' in chunk {c['chunk_id']} ({c['file']}) does not appear in its declared raw source(s) {raw_sources}"
            )

    # 2. Test products.json attributes against declared raw_source_file
    catalog = load_catalog()
    for pid, prod in catalog["products"].items():
        for attr_name, attr_data in prod.get("attributes", {}).items():
            assert isinstance(attr_data, dict), f"Attribute {pid}.{attr_name} must be a dict"
            assert "source_url" in attr_data and attr_data["source_url"].startswith("http"), (
                f"Attribute {pid}.{attr_name} must carry a valid source_url"
            )
            src_file = attr_data.get("raw_source_file")
            assert src_file, f"Attribute {pid}.{attr_name} missing declared raw_source_file"
            src_path = BASE_DIR / src_file if not Path(src_file).is_absolute() else Path(src_file)
            assert src_path.exists(), f"Declared raw source {src_file} does not exist on disk"
            corpus = src_path.read_text(encoding="utf-8")

            val_str = str(attr_data.get("value", ""))
            numbers = set(re.findall(r"\b\d+(?:\.\d+)?\b", val_str))
            for num in numbers:
                pattern = r"(?<![0-9])" + re.escape(num) + r"(?![0-9])"
                assert re.search(pattern, corpus), (
                    f"Number '{num}' in attribute {pid}.{attr_name} not found in declared raw source {src_file}"
                )
