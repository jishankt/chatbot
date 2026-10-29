#!/usr/bin/env python3
"""
scripts/ingest_master_products.py
Ingests validated master catalogue rows from /opt/salesai/data/sheets/master_complete_products.csv
into data/products.json with Two-Tier Pricing rules:
  Tier 1: Fixed verified numeric price + 5% UAE VAT note + sales desk confirmation.
  Tier 2: Price on Request / quotation required (no numbers or estimates produced).
"""

import csv
import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
MASTER_CSV = Path("/opt/salesai/data/sheets/master_complete_products.csv")
PRODUCTS_JSON = BASE_DIR / "data" / "products.json"

# Canonical SKU mapping for hardware printers
CANONICAL_PRINTER_SKUS = {
    "citizen-cx-02": "CX-02",
    "citizen-cx-02w": "CX-02W",
    "citizen-cy-02": "CY-02",
    "citizen-cz-01": "CZ-01",
    "epson-sc-t3100": "SC-T3100",
    "epson-sc-t5100": "SC-T5100",
    "epson-sc-t7700d": "SC-T7700D",
    "epson-sc-p700": "SC-P700",
    "epson-sc-p900": "SC-P900",
    "epson-sc-p900-roll": "SC-P900-ROLL",
    "epson-sc-p9500": "SC-P9500",
    "epson-sc-p8500d": "SC-P8500D",
    "epson-sc-p8500dm": "SC-P8500DM",
    "epson-sc-f100": "SC-F100",
    "epson-sc-f500": "SC-F500",
    "epson-wf-c5890-dwf": "WF-C5890",
    "epson-em-c800": "EM-C800",
    "epson-am-c400": "AM-C4000",
    "epson-am-c550": "AM-C5000",
    "epson-am-c4000": "AM-C4000-ENT",
    "epson-am-c5000": "AM-C5000-ENT",
    "epson-am-c6000": "AM-C6000-ENT",
    "epson-wf-c878r-dwf": "WF-C878R",
    "epson-wf-c879r-dwf": "WF-C879R",
    "epson-workforce-ds-530ii": "DS-530II",
    "epson-workforce-ds-770ii": "DS-770II",
}


def parse_price(val: str):
    if not val:
        return None, "price_on_request"
    clean = val.strip().lower()
    if clean in ("price on request", "por", "quote", "n/a", "none"):
        return None, "price_on_request"
    try:
        num = float(clean.replace(",", ""))
        return num, "fixed_verified"
    except ValueError:
        return None, "price_on_request"


def run_ingest():
    with open(PRODUCTS_JSON, "r", encoding="utf-8") as f:
        existing_data = json.load(f)

    products = existing_data.get("products", {})

    with open(MASTER_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        master_rows = list(reader)

    print(f"Total rows in master CSV: {len(master_rows)}")

    ingested_count = 0
    for r in master_rows:
        item_type = r.get("item_type", "").strip()
        raw_sku = r.get("id_or_sku", "").strip()
        name = r.get("name", "").strip()
        brand = r.get("brand", "").strip()
        category = r.get("category", "").strip()
        raw_price = r.get("price_aed", "").strip()
        product_url = r.get("product_url", "").strip()
        specs = r.get("key_specifications", "").strip()
        consumables_summary = r.get("consumables_or_media_summary", "").strip()
        desc = r.get("description", "").strip()

        if not raw_sku:
            continue

        canonical_sku = CANONICAL_PRINTER_SKUS.get(raw_sku, raw_sku.upper())
        numeric_price, price_tier = parse_price(raw_price)

        # DS-770II duplicate URL suppression:
        # DS-770II currently duplicates DS-530II URL in the sheet. Suppress until verified dedicated URL provided.
        if canonical_sku == "DS-770II":
            product_url = None

        existing_entry = products.get(canonical_sku, {})

        # Build product structure
        entry = {
            "id": canonical_sku,
            "sku": canonical_sku,
            "site_sku": raw_sku,
            "model_number": canonical_sku,
            "brand": brand or existing_entry.get("brand", "Unknown"),
            "family": canonical_sku.split("-")[0] if "-" in canonical_sku else canonical_sku,
            "name": name or existing_entry.get("name", canonical_sku),
            "category": "printer" if item_type == "Hardware Printer" else category or existing_entry.get("category", "hardware"),
            "purchase_mode": "cart" if price_tier == "fixed_verified" else "quote",
            "price_tier": price_tier,
            "price": numeric_price,
            "currency": "AED",
            "as_of": "2026-10-26",
            "in_stock": True,
            "active": True,
            "vat_status": "Subject to 5% UAE VAT",
            "price_confirmation_note": "Price subject to confirmation by our sales desk.",
            "url": product_url or existing_entry.get("url"),
            "description": desc or existing_entry.get("description", name),
            "key_specifications": specs,
            "consumables_or_media_summary": consumables_summary,
            "compatible_with": existing_entry.get("compatible_with", []),
            "unverified_fields": existing_entry.get("unverified_fields", []),
            "attributes": existing_entry.get("attributes", {})
        }

        # Keep existing verified attributes for CX-02 and accessories
        if canonical_sku == "CX-02":
            entry["compatible_with"] = ["CX2-MS46-2PC", "CX2-MS57-2PC", "CX2-MS68-2PC", "CX-02-BAG", "CITIZEN-PEN"]
            entry["price"] = 4385.0
            entry["old_price"] = 4900.0
            entry["price_tier"] = "fixed_verified"
        elif canonical_sku == "CY-02":
            entry["price"] = 3400.0
            entry["price_tier"] = "fixed_verified"
            entry["compatible_with"] = ["CY-MS46", "CY-MS57", "CY-MS68"]
            entry["url"] = "https://www.keplertechllc.com/product/citizen-cy-02-photo-printer/"
        elif canonical_sku == "CZ-01":
            entry["price"] = 3200.0
            entry["price_tier"] = "fixed_verified"
            entry["compatible_with"] = ["CZ-MS46"]
            entry["url"] = "https://www.keplertechllc.com/product/citizen-cz-01-photo-printer/"
        elif canonical_sku == "CX-02W":
            entry["price"] = 6820.0
            entry["price_tier"] = "fixed_verified"
            # Only CX2W 812 media in official data
            entry["compatible_with"] = ["CX2W 812"]
            entry["url"] = "https://www.keplertechllc.com/product/citizen-cx-02w-photo-printer/"

        # Ensure unverified prints disclaimers are set on CX2-MS46 and CX2-MS68
        if canonical_sku == "CX2-MS46-2PC":
            entry["prints_per_set"] = 800
            entry["prints_verified"] = False
            entry["estimate_note"] = "approx. / unverified estimate (based on 2 rolls x ~400 prints)"
            entry["unverified_fields"] = ["prints_per_set"]
        elif canonical_sku == "CX2-MS68-2PC":
            entry["prints_per_set"] = 400
            entry["prints_verified"] = False
            entry["estimate_note"] = "approx. / unverified estimate (based on 2 rolls x ~200 prints)"
            entry["unverified_fields"] = ["prints_per_set"]

        products[canonical_sku] = entry
        ingested_count += 1

    existing_data["products"] = products
    existing_data["as_of"] = "2026-10-26"

    with open(PRODUCTS_JSON, "w", encoding="utf-8") as f:
        json.dump(existing_data, f, indent=2, ensure_ascii=False)

    print(f"Successfully ingested {ingested_count} products into {PRODUCTS_JSON}")
    print(f"Total products in catalog: {len(products)}")


if __name__ == "__main__":
    run_ingest()
