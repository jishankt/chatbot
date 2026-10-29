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
    url = prod.get("url")
    if not url:
        return {
            "status": "unavailable",
            "sku": prod["sku"],
            "name": prod["name"],
            "message": f"An official product page URL for '{prod['name']}' is currently being updated. Our sales team will be pleased to share the official datasheet and specifications directly.",
            "url": None
        }

    return {
        "status": "success",
        "sku": prod["sku"],
        "name": prod["name"],
        "url": url
    }
