from typing import Dict, Any
from app.tools.pricing import load_catalog, normalize_sku


def get_product_link(sku: str) -> Dict[str, Any]:
    catalog = load_catalog()
    products = catalog.get("products", {})
    norm_sku = normalize_sku(sku)

    if norm_sku not in products:
        return {
            "status": "error",
            "message": f"Cannot find official product URL for unrecognized SKU '{sku}'.",
            "handoff": True
        }

    prod = products[norm_sku]
    return {
        "status": "success",
        "sku": prod["sku"],
        "name": prod["name"],
        "url": prod["url"]
    }
