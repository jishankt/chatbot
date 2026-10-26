import json
from datetime import datetime, date
from typing import Dict, Any, Optional
from app.config import Config

SKU_ALIASES = {
    "cx02": "CX-02",
    "cx-02": "CX-02",
    "printer": "CX-02",
    "citizen cx-02": "CX-02",
    "cx02-bag": "CX-02-BAG",
    "cx-02-bag": "CX-02-BAG",
    "citizen cx-02 bag": "CX-02-BAG",
    "bag": "CX-02-BAG",
    "case": "CX-02-BAG",
    "citizen pen": "CITIZEN-PEN",
    "citizen-pen": "CITIZEN-PEN",
    "pen": "CITIZEN-PEN",
    "cleaning pen": "CITIZEN-PEN",
    "ms46": "CX2-MS46-2PC",
    "cx2-ms46-2pc": "CX2-MS46-2PC",
    "4x6": "CX2-MS46-2PC",
    "4x6 media": "CX2-MS46-2PC",
    "ms57": "CX2-MS57-2PC",
    "cx2-ms57-2pc": "CX2-MS57-2PC",
    "5x7": "CX2-MS57-2PC",
    "5x7 media": "CX2-MS57-2PC",
    "ms68": "CX2-MS68-2PC",
    "cx2-ms68-2pc": "CX2-MS68-2PC",
    "6x8": "CX2-MS68-2PC",
    "6x8 media": "CX2-MS68-2PC"
}


def load_catalog() -> Dict[str, Any]:
    with open(Config.PRODUCTS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_products_whitelist() -> Dict[str, Any]:
    return load_catalog().get("products", {})


def normalize_sku(sku_input: str) -> str:
    cleaned = sku_input.strip().lower()
    return SKU_ALIASES.get(cleaned, sku_input.strip())


def is_price_stale(as_of_str: str, max_age_days: Optional[int] = None) -> bool:
    limit = Config.PRICE_MAX_AGE_DAYS if max_age_days is None else max_age_days
    try:
        as_of_dt = datetime.strptime(as_of_str, "%Y-%m-%d").date()
        today = date.today()
        days_diff = (today - as_of_dt).days
        if limit <= 0:
            return True
        return days_diff > limit
    except Exception:
        return False


def get_price(sku: str) -> Dict[str, Any]:
    catalog = load_catalog()
    products = catalog.get("products", {})
    as_of = catalog.get("as_of", "")
    norm_sku = normalize_sku(sku)

    if norm_sku not in products:
        # Check if 6x9 media
        if "6x9" in sku.lower():
            return {
                "status": "unsupported",
                "message": "6x9 media is not listed on our website. I'll ask the team to check availability.",
                "handoff": True
            }
        return {
            "status": "error",
            "message": f"SKU '{sku}' is not recognized in the official Citizen CX-02 catalog. We only provide pricing for the CX-02 printer and its official accessories.",
            "handoff": True
        }

    prod = products[norm_sku]
    price = prod["price"]
    old_price = prod.get("old_price")

    stale = is_price_stale(as_of)
    stale_note = f"Prices shown are as of {as_of}. Please confirm current rates with our sales team." if stale else None

    return {
        "status": "success",
        "sku": prod["sku"],
        "name": prod["name"],
        "price": price,
        "old_price": old_price,
        "formatted_price": f"{price:,.2f} AED",
        "formatted_old_price": f"{old_price:,.2f} AED" if old_price else None,
        "in_stock": prod.get("in_stock", True),
        "as_of": as_of,
        "stale_note": stale_note,
        "estimate_note": prod.get("estimate_note"),
        "to_confirm_note": prod.get("to_confirm_note"),
        "url": prod.get("url")
    }


def check_stock(sku: str) -> Dict[str, Any]:
    catalog = load_catalog()
    products = catalog.get("products", {})
    norm_sku = normalize_sku(sku)

    if norm_sku not in products:
        return {
            "status": "error",
            "message": f"SKU '{sku}' is not found in the official CX-02 catalog.",
            "handoff": True
        }

    prod = products[norm_sku]
    in_stock = prod.get("in_stock", True)
    return {
        "status": "success",
        "sku": prod["sku"],
        "name": prod["name"],
        "in_stock": in_stock,
        "stock_status": "In Stock (Dubai Warehouse)" if in_stock else "Available on Pre-order"
    }


def list_products() -> Dict[str, Any]:
    catalog = load_catalog()
    products = catalog.get("products", {})
    as_of = catalog.get("as_of", "")
    stale = is_price_stale(as_of)

    items = []
    for p in products.values():
        items.append({
            "sku": p["sku"],
            "name": p["name"],
            "category": p.get("category"),
            "price": p["price"],
            "formatted_price": f"{p['price']:,.2f} AED",
            "in_stock": p.get("in_stock", True),
            "url": p.get("url")
        })

    return {
        "status": "success",
        "as_of": as_of,
        "stale_note": f"Prices shown are as of {as_of}. Please confirm current rates with our sales team." if stale else None,
        "currency": catalog.get("currency", "AED"),
        "products": items
    }


def calculate_cost_per_print(size: str = "4x6", volume: int = 1) -> Dict[str, Any]:
    catalog = load_catalog()
    clean_size = size.lower().replace("\"", "").replace(" ", "")

    if "4x6" in clean_size or "102x152" in clean_size:
        sku = "CX2-MS46-2PC"
        prod = catalog["products"][sku]
        cost_per_print = prod["price"] / prod["prints_per_set"]
        is_estimate = not prod["prints_verified"]
        prints_per_box = prod["prints_per_set"]
    elif "5x7" in clean_size or "127x178" in clean_size:
        sku = "CX2-MS57-2PC"
        prod = catalog["products"][sku]
        cost_per_print = prod["price"] / prod["prints_per_set"]
        is_estimate = not prod["prints_verified"]
        prints_per_box = prod["prints_per_set"]
    elif "6x8" in clean_size or "152x203" in clean_size:
        sku = "CX2-MS68-2PC"
        prod = catalog["products"][sku]
        cost_per_print = prod["price"] / prod["prints_per_set"]
        is_estimate = not prod["prints_verified"]
        prints_per_box = prod["prints_per_set"]
    elif "6x9" in clean_size:
        return {
            "status": "unsupported",
            "message": "6x9 media is not listed on our website. I'll ask the team to check availability.",
            "handoff": True
        }
    else:
        # Default to 4x6
        sku = "CX2-MS46-2PC"
        prod = catalog["products"][sku]
        cost_per_print = prod["price"] / prod["prints_per_set"]
        is_estimate = not prod["prints_verified"]
        prints_per_box = prod["prints_per_set"]

    vol = max(1, volume)
    total_cost = cost_per_print * vol

    estimate_text = "(Estimated: based on 2 rolls / unverified box yield)" if is_estimate else "(Verified yield)"

    return {
        "status": "success",
        "size": size,
        "media_sku": sku,
        "media_name": prod["name"],
        "media_box_price": prod["price"],
        "prints_per_box": prints_per_box,
        "cost_per_print": round(cost_per_print, 4),
        "formatted_cost_per_print": f"{cost_per_print:.3f} AED",
        "is_estimate": is_estimate,
        "estimate_note": estimate_text,
        "volume": vol,
        "total_cost": round(total_cost, 2),
        "formatted_total_cost": f"{total_cost:,.2f} AED"
    }
