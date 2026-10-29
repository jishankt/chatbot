import json
from datetime import datetime, date
from typing import Dict, Any, Optional
from app.config import Config
from app.cognitive.normalizer import normalize_model_or_sku

SKU_ALIASES = {
    "cx02": "CX-02",
    "cx-02": "CX-02",
    "citizen cx-02": "CX-02",
    "cx02-bag": "CX-02-BAG",
    "cx-02-bag": "CX-02-BAG",
    "citizen cx-02 bag": "CX-02-BAG",
    "citizen pen": "CITIZEN-PEN",
    "citizen-pen": "CITIZEN-PEN",
    "cleaning pen": "CITIZEN-PEN",
    "ms46": "CX2-MS46-2PC",
    "cx2-ms46-2pc": "CX2-MS46-2PC",
    "4x6": "CX2-MS46-2PC",
    "ms57": "CX2-MS57-2PC",
    "cx2-ms57-2pc": "CX2-MS57-2PC",
    "5x7": "CX2-MS57-2PC",
    "ms68": "CX2-MS68-2PC",
    "cx2-ms68-2pc": "CX2-MS68-2PC",
    "6x8": "CX2-MS68-2PC",
}


def load_catalog() -> Dict[str, Any]:
    with open(Config.PRODUCTS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_products_whitelist() -> Dict[str, Any]:
    return load_catalog().get("products", {})


def normalize_sku(sku_input: str) -> str:
    cleaned = sku_input.strip()
    norm, _, _ = normalize_model_or_sku(cleaned)
    if norm:
        return norm
    return SKU_ALIASES.get(cleaned.lower(), cleaned)


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
    """
    Two-Tier Pricing Lookup:
      Tier 1 (Verified numeric price): returns exact AED price, VAT note, and sales desk confirmation note.
      Tier 2 (Price on Request / empty price): returns quotation required message, no numbers or estimates.
    """
    catalog = load_catalog()
    products = catalog.get("products", {})
    as_of = catalog.get("as_of", "")
    norm_sku = normalize_sku(sku)

    # 1. Scanner consumables check
    if any(w in sku.lower() for w in ["scanner roller", "pickup roller", "separation pad", "roller kit", "scanner consumable"]):
        return {
            "status": "not_listed",
            "message": (
                "Consumables for document scanners (such as pickup rollers and separation pads) are not listed on our online store. "
                "Our Kepler Tech service desk can check stock and supply genuine parts upon request."
            ),
            "handoff": True
        }

    # 2. 6x9 media check
    if "6x9" in sku.lower():
        return {
            "status": "unsupported",
            "message": "6x9 media is not listed on our website. I'll ask our team to check availability and options for you.",
            "handoff": True
        }

    if norm_sku not in products:
        return {
            "status": "error",
            "message": f"SKU or model '{sku}' is not recognized in our official catalogue. We supply official Citizen photo printers, Epson commercial plotters, and official media/inks.",
            "handoff": True
        }

    prod = products[norm_sku]
    price = prod.get("price")
    old_price = prod.get("old_price")
    price_tier = prod.get("price_tier", "fixed_verified" if price is not None else "price_on_request")

    stale = is_price_stale(as_of)
    stale_note = f"Prices shown are as of {as_of}. Please confirm current rates with our sales team." if stale else None

    # Tier 2: Price on Request / No verified numeric price
    if price is None or price_tier == "price_on_request":
        return {
            "status": "quote_required",
            "sku": prod["sku"],
            "name": prod["name"],
            "price": None,
            "price_tier": "price_on_request",
            "message": (
                f"Pricing for the **{prod['name']}** is available through an official quotation. "
                "Would you like our sales team to prepare an official quote for you?"
            ),
            "in_stock": prod.get("in_stock", True),
            "url": prod.get("url"),
            "handoff": False
        }

    # Tier 1: Fixed Verified Price
    return {
        "status": "success",
        "sku": prod["sku"],
        "name": prod["name"],
        "price": price,
        "old_price": old_price,
        "formatted_price": f"{price:,.2f} AED",
        "formatted_old_price": f"{old_price:,.2f} AED" if old_price else None,
        "price_tier": "fixed_verified",
        "vat_status": "Subject to 5% UAE VAT",
        "confirmation_note": "Price subject to confirmation by our sales desk.",
        "in_stock": prod.get("in_stock", True),
        "as_of": as_of,
        "stale_note": stale_note,
        "estimate_note": prod.get("estimate_note"),
        "url": prod.get("url")
    }


def check_stock(sku: str) -> Dict[str, Any]:
    catalog = load_catalog()
    products = catalog.get("products", {})
    norm_sku = normalize_sku(sku)

    if norm_sku not in products:
        return {
            "status": "error",
            "message": f"SKU '{sku}' is not found in our official catalogue.",
            "handoff": True
        }

    prod = products[norm_sku]
    in_stock = prod.get("in_stock", True)
    return {
        "status": "success",
        "sku": prod["sku"],
        "name": prod["name"],
        "in_stock": in_stock,
        "stock_status": "In Stock and available (Dubai Warehouse)" if in_stock else "Available on Pre-order"
    }


def list_products() -> Dict[str, Any]:
    catalog = load_catalog()
    products = catalog.get("products", {})
    as_of = catalog.get("as_of", "")
    stale = is_price_stale(as_of)

    items = []
    for p in products.values():
        if p.get("price") is not None:
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
    """
    Calculates cost per print only when media price and yield are verified or available.
    If yield is estimated, flags as 'approx. / unverified estimate'.
    """
    catalog = load_catalog()
    clean_size = size.lower().replace("\"", "").replace(" ", "")

    if "4x6" in clean_size or "102x152" in clean_size:
        sku = "CX2-MS46-2PC"
        prod = catalog["products"].get(sku)
    elif "5x7" in clean_size or "127x178" in clean_size:
        sku = "CX2-MS57-2PC"
        prod = catalog["products"].get(sku)
    elif "6x8" in clean_size or "152x203" in clean_size:
        sku = "CX2-MS68-2PC"
        prod = catalog["products"].get(sku)
    elif "6x9" in clean_size:
        return {
            "status": "unsupported",
            "message": "6x9 media is not listed on our website. I'll ask the team to check availability.",
            "handoff": True
        }
    else:
        # If size is unknown or running cost cannot be calculated
        return {
            "status": "input_missing",
            "message": f"Print running cost calculation requires both verified media price and roll yield for '{size}'. Our sales desk will be pleased to calculate an official running cost estimate for your workload.",
            "handoff": True
        }

    if not prod or not prod.get("price") or not prod.get("prints_per_set"):
        return {
            "status": "input_missing",
            "message": f"Yield or media box price is not verified for '{size}'. Our sales team can prepare an official running cost quotation.",
            "handoff": True
        }

    cost_per_print = prod["price"] / prod["prints_per_set"]
    is_estimate = not prod.get("prints_verified", True)
    prints_per_box = prod["prints_per_set"]

    vol = max(1, volume)
    total_cost = cost_per_print * vol

    estimate_text = "(approx. / unverified estimate based on 2 rolls)" if is_estimate else "(Verified yield)"

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
