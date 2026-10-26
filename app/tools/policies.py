import json
from typing import Dict, Any, Optional
from app.config import Config

POLICY_NAMES_MAP = {
    "warranty": "warranty",
    "warranties": "warranty",
    "guarantee": "warranty",
    "delivery": "delivery_charges",
    "delivery_time": "delivery_time",
    "processing": "delivery_time",
    "shipping": "delivery_charges",
    "delivery_charges": "delivery_charges",
    "shipping_cost": "delivery_charges",
    "payment": "payment_methods",
    "payment_methods": "payment_methods",
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
    "africa_delivery": "delivery_outside_gcc"
}

GCC_COUNTRIES = {"uae", "united arab emirates", "saudi arabia", "ksa", "kuwait", "qatar", "bahrain", "oman"}
NON_GCC_INDICATORS = {"kenya", "nigeria", "africa", "uk", "usa", "europe", "india", "egypt", "outside gcc"}


def get_policy(policy_name: str, destination: Optional[str] = None) -> Dict[str, Any]:
    with open(Config.POLICIES_PATH, "r", encoding="utf-8") as f:
        policies = json.load(f)

    clean_name = policy_name.strip().lower()

    # Check for outside-GCC delivery requests
    is_outside_gcc = False
    if destination and destination.strip().lower() not in GCC_COUNTRIES:
        is_outside_gcc = True
    elif any(ind in clean_name for ind in NON_GCC_INDICATORS):
        is_outside_gcc = True

    if is_outside_gcc:
        outside_entry = policies.get("delivery_outside_gcc", {})
        terms_text = outside_entry.get("terms", "Deliveries outside the GCC require custom logistics and must be arranged directly through our sales desk.")
        return {
            "status": "handoff",
            "policy": "delivery_outside_gcc",
            "handoff": True,
            "message": f"{terms_text} Our team will connect with you to review export and shipping options.",
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
                f"Official terms for {friendly_title} require confirmation from Kepler Tech LLC sales desk. "
                f"Please reach our Dubai team at {company.get('phone', '00971 4 323 1008')} or "
                f"WhatsApp {company.get('whatsapp', '+971 50 890 1641')}."
            )
        }

    # If action is explicitly handoff
    if isinstance(val, dict) and val.get("action") == "handoff":
        return {
            "status": "handoff",
            "policy": canonical_key,
            "handoff": True,
            "message": val.get("terms", "This inquiry requires confirmation from our sales desk."),
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
