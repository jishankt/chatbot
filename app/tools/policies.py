import json
from typing import Dict, Any, Optional
from app.config import Config

POLICY_NAMES_MAP = {
    "warranty": "warranty",
    "warranties": "warranty",
    "guarantee": "warranty",
    "delivery": "delivery_charges",
    "delivery charge": "delivery_charges",
    "delivery charges": "delivery_charges",
    "delivery fee": "delivery_charges",
    "delivery fees": "delivery_charges",
    "shipping": "delivery_charges",
    "shipping charge": "delivery_charges",
    "shipping charges": "delivery_charges",
    "shipping cost": "delivery_charges",
    "shipping costs": "delivery_charges",
    "delivery_time": "order_processing",
    "delivery time": "order_processing",
    "order_processing": "order_processing",
    "order processing": "order_processing",
    "processing": "order_processing",
    "transit_time": "transit_time",
    "transit time": "transit_time",
    "transit": "transit_time",
    "shipping_time": "transit_time",
    "shipping time": "transit_time",
    "delivery_charges": "delivery_charges",
    "payment": "payment_methods",
    "payment method": "payment_methods",
    "payment methods": "payment_methods",
    "payment options": "payment_methods",
    "how to pay": "payment_methods",
    "cod": "payment_methods",
    "cancellation": "cancellation_policy",
    "cancel": "cancellation_policy",
    "cancellation_policy": "cancellation_policy",
    "return": "return_policy",
    "returns": "return_policy",
    "return_policy": "return_policy",
    "refund": "return_policy",
    "pickup": "pickup",
    "pick up": "pickup",
    "store pickup": "pickup",
    "tracking": "tracking",
    "track": "tracking",
    "shipment tracking": "tracking",
    "installation": "installation",
    "install": "installation",
    "setup": "installation",
    "support": "support_terms",
    "support_terms": "support_terms",
    "maintenance": "support_terms",
    "vat": "vat_treatment",
    "vat_treatment": "vat_treatment",
    "tax": "vat_treatment",
    "outside_gcc": "delivery_outside_gcc",
    "outside_gcc_delivery": "delivery_outside_gcc",
    "delivery_outside_gcc": "delivery_outside_gcc",
    "africa_delivery": "delivery_outside_gcc",
    "import_duty_vat_outside_uae": "import_duty_vat_outside_uae",
    "import_duty": "import_duty_vat_outside_uae",
    "customs": "import_duty_vat_outside_uae",
    "duty": "import_duty_vat_outside_uae",
    "price_changes": "price_changes",
    "price_change": "price_changes",
    "pricing_errors": "price_changes"
}

GCC_COUNTRIES = {"uae", "united arab emirates", "saudi arabia", "ksa", "kuwait", "qatar", "bahrain", "oman"}
NON_GCC_INDICATORS = {"kenya", "nigeria", "africa", "uk", "usa", "europe", "india", "egypt", "outside gcc"}


def get_policy(policy_name: str, destination: Optional[str] = None, country: Optional[str] = None) -> Dict[str, Any]:
    with open(Config.POLICIES_PATH, "r", encoding="utf-8") as f:
        policies = json.load(f)

    clean_name = policy_name.strip().lower()
    dest = destination or country

    # Check for outside-GCC delivery requests
    is_outside_gcc = False
    if dest and dest.strip().lower() not in GCC_COUNTRIES:
        is_outside_gcc = True
    elif any(ind in clean_name for ind in NON_GCC_INDICATORS):
        is_outside_gcc = True

    if is_outside_gcc:
        outside_entry = policies.get("delivery_outside_gcc", {})
        terms_text = outside_entry.get("terms", "We only deliver our products to the UAE, Oman, and all other GCC countries.")
        return {
            "status": "handoff",
            "policy": "delivery_outside_gcc",
            "handoff": True,
            "message": f"{terms_text} Delivery outside the GCC is handled by our sales specialist team for custom export and shipping options.",
            "requires_sales_desk": True
        }

    canonical_key = POLICY_NAMES_MAP.get(clean_name, clean_name)
    val = policies.get(canonical_key)
    company = policies.get("company_contact", {})

    # Force handoff for null policies
    if val is None:
        friendly_title = canonical_key.replace("_", " ").title()
        return {
            "status": "unknown",
            "policy": canonical_key,
            "handoff": True,
            "message": (
                f"Official terms for {friendly_title} require confirmation from Kepler Tech LLC sales desk specialist team. "
                f"Please reach our Dubai team at {company.get('phone', Config.KEPLER_PHONE)} or "
                f"WhatsApp {company.get('whatsapp', Config.KEPLER_WHATSAPP)}."
            )
        }

    # If action is explicitly handoff
    if isinstance(val, dict) and val.get("action") == "handoff":
        msg = val.get("terms", "This inquiry requires confirmation from our sales specialist team.")
        if canonical_key == "delivery_outside_gcc" and "outside the gcc" not in msg.lower():
            msg = f"{msg} Delivery outside the GCC is handled by our sales specialist team for custom export and shipping options."
        return {
            "status": "handoff",
            "policy": canonical_key,
            "handoff": True,
            "message": msg,
            "details": val
        }

    # For filled policies: answer with policy text + disclaimer and offer a handoff
    terms = val.get("terms") if isinstance(val, dict) else str(val)
    source_date = val.get("source_date", "2023-09-19") if isinstance(val, dict) else "2023-09-19"
    formatted_reply = (
        f"{terms}\n\n"
        f"Per our website terms (updated {source_date}); our team will confirm. "
        f"If you would like me to connect you with our sales desk, please let me know."
    )

    return {
        "status": "success",
        "policy": canonical_key,
        "handoff": False,
        "handoff_offered": True,
        "message": formatted_reply,
        "details": val
    }
