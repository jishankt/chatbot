import re
from typing import Dict, Any
from app.agent.guardrails import check_pre_guardrails

# Keyword definitions for priority matching
GREETING_PATTERNS = [
    r"\b(hi|hello|hey|good\s+morning|good\s+afternoon|good\s+evening|howdy|salam)\b",
    r"\b(thanks|thank\s+you|shukran|bye|goodbye|see\s+you)\b",
    r"\bhow\s+are\s+you\b"
]

HUMAN_DEMO_RESERVE_PATTERNS = [
    r"talk\s+to\s+(a\s+)?(human|person|agent|someone|representative|manager)",
    r"speak\s+with\s+(a\s+)?(human|person|agent|someone)",
    r"human\s+agent",
    r"customer\s+(service|support|care)",
    r"call\s+me",
    r"book\s+(a\s+)?demo",
    r"see\s+(a\s+)?demo",
    r"showroom\s+visit",
    r"visit\s+(your\s+)?showroom",
    r"reserve\s+(a\s+)?(unit|printer)"
]

DATASHEET_KEYWORDS = [
    "spec", "specification", "specifications", "dpi", "resolution", "weight",
    "dimension", "dimensions", "size", "speed", "fast", "seconds", "ribbon rewind",
    "rewind", "power", "watt", "watts", "sleep mode", "standby", "usb",
    "driver", "drivers", "windows", "mac", "macos", "linux", "cups", "overcoat",
    "glossy", "matte", "luster", "print size", "print sizes"
]

POLICY_KEYWORDS = [
    "warranty", "guarantee", "warranty policy", "delivery charge", "delivery charges", "shipping cost", "delivery time",
    "shipping time", "payment method", "payment methods", "cod", "cash on delivery",
    "return policy", "refund policy", "refund", "installation", "install",
    "setup", "support terms", "vat treatment"
]

DISCOUNT_KEYWORDS = [
    "discount", "discounts", "discount code", "promo", "promo code", "coupon",
    "best price", "cheaper", "negotiate", "bargain", "special offer", "reduction"
]

QUOTE_KEYWORDS = [
    "quote", "quotation", "formal quote", "proforma", "estimate",
    "quote me", "calculate total", "how much for 2", "how much for 3", "how much for 5"
]

STOCK_KEYWORDS = [
    "in stock", "stock", "available", "availability", "ready stock", "lead time"
]

MEDIA_YIELD_KEYWORDS = [
    "cost per print", "running cost", "print cost", "prints per roll",
    "prints per box", "yield", "capacity per roll", "how many prints"
]

BUNDLE_CATALOG_KEYWORDS = [
    "catalog", "catalogue", "all products", "list products", "accessories",
    "what accessories", "range", "what else do you sell", "bundle"
]

PRICE_KEYWORDS = [
    "price", "how much", "cost", "rate", "aed", "dirham", "dirhams",
    "bikam", "kam el se3r", "kam el s3r", "se3r", "s3r",
    "سعر", "بكم", "تكلفة", "كم سعر"
]

LINK_KEYWORDS = [
    "link", "url", "website", "where to buy", "where can i buy", "purchase link", "order online"
]


def classify_intent(message: str) -> Dict[str, Any]:
    """
    Classifies user message according to the strict 14-level priority hierarchy:
    1. guardrails
    2. small_talk
    3. human_demo_reserve
    4. out_of_scope
    5. datasheet
    6. policies
    7. discount_negotiation
    8. quote
    9. stock
    10. media_yield_cost
    11. bundle_catalog
    12. price
    13. link
    14. rag
    """
    clean_msg = message.strip().lower()

    # Priority 1: Guardrails (Injections, Cost Price, Abuse, Competitors, Other Models, A4)
    is_safe, fail_type, details = check_pre_guardrails(clean_msg)
    if not is_safe:
        return {
            "intent": "guardrails",
            "priority": 1,
            "failure_type": fail_type,
            "reason": details.get("reason", "Guardrail breach"),
            "fixed_response": details.get("response")
        }

    # Priority 2: Small Talk
    for pattern in GREETING_PATTERNS:
        if re.search(pattern, clean_msg):
            words = clean_msg.split()
            if len(words) <= 4:
                return {
                    "intent": "small_talk",
                    "priority": 2,
                    "reason": "Customer greeting or polite closing"
                }

    # Priority 3: Human / Demo / Reserve
    for pattern in HUMAN_DEMO_RESERVE_PATTERNS:
        if re.search(pattern, clean_msg):
            return {
                "intent": "human_demo_reserve",
                "priority": 3,
                "reason": f"Customer requested human agent, showroom demo, or reservation: '{pattern}'"
            }

    # Priority 4: Out of Scope (General off-topic checks)
    unrelated_topics = [
        "television", "tv", "car", "toyota", "nissan", "flight", "weather",
        "football", "crypto", "bitcoin", "restaurant", "burger", "pizza"
    ]
    for topic in unrelated_topics:
        if re.search(r"\b" + re.escape(topic) + r"\b", clean_msg):
            return {
                "intent": "out_of_scope",
                "priority": 4,
                "reason": f"Inquiry about unrelated topic: '{topic}'",
                "fixed_response": f"I specialize exclusively in the Citizen CX-02 dye-sublimation photo printer for Kepler Tech LLC. I cannot assist with inquiries regarding {topic}."
            }

    # Check for price term with catalog product (e.g. 'Rate for Citizen Pen maintenance tool')
    has_product_word = any(prod in clean_msg for prod in ["pen", "bag", "cx-02", "cx02", "printer", "paper", "media", "set", "box"])
    has_price_word = any(re.search(r"\b" + re.escape(p) + r"\b", clean_msg) for p in PRICE_KEYWORDS)
    if has_product_word and has_price_word and not any(d in clean_msg for d in DISCOUNT_KEYWORDS) and not any(q in clean_msg for q in QUOTE_KEYWORDS):
        return {
            "intent": "price",
            "priority": 12,
            "reason": "Product price inquiry"
        }

    # Priority 5: Datasheet Specs (including official datasheet warranty specs)
    for kw in DATASHEET_KEYWORDS:
        if re.search(r"\b" + re.escape(kw) + r"\b", clean_msg):
            return {
                "intent": "datasheet",
                "priority": 5,
                "reason": f"Datasheet inquiry matched: '{kw}'"
            }

    # Priority 6: Policies (Delivery charges, payment methods, returns, warranty policy)
    for kw in POLICY_KEYWORDS:
        if re.search(r"\b" + re.escape(kw) + r"\b", clean_msg):
            return {
                "intent": "policies",
                "priority": 6,
                "policy_name": kw,
                "reason": f"Policy inquiry matched: '{kw}'"
            }

    # If general warranty inquiry without "policy"
    if "warranty" in clean_msg or "guarantee" in clean_msg:
        return {
            "intent": "policies",
            "priority": 6,
            "policy_name": "warranty",
            "reason": "Warranty policy inquiry"
        }

    # Priority 7: Discount / Negotiation -> Immediate Handoff
    for kw in DISCOUNT_KEYWORDS:
        if re.search(r"\b" + re.escape(kw) + r"\b", clean_msg):
            return {
                "intent": "discount_negotiation",
                "priority": 7,
                "reason": f"Discount / pricing negotiation request: '{kw}'"
            }

    # Priority 8: Quote Request
    for kw in QUOTE_KEYWORDS:
        if kw in clean_msg:
            return {
                "intent": "quote",
                "priority": 8,
                "reason": f"Formal quotation request: '{kw}'"
            }

    # Priority 9: Stock Availability
    for kw in STOCK_KEYWORDS:
        if kw in clean_msg:
            return {
                "intent": "stock",
                "priority": 9,
                "reason": f"Stock availability inquiry: '{kw}'"
            }

    # Priority 10: Media Yield / Running Cost
    for kw in MEDIA_YIELD_KEYWORDS:
        if kw in clean_msg:
            return {
                "intent": "media_yield_cost",
                "priority": 10,
                "reason": f"Media yield or cost per print inquiry: '{kw}'"
            }

    # Priority 11: Bundle / Catalog
    for kw in BUNDLE_CATALOG_KEYWORDS:
        if kw in clean_msg:
            return {
                "intent": "bundle_catalog",
                "priority": 11,
                "reason": f"Catalog or accessory list inquiry: '{kw}'"
            }

    # Priority 12: Price Inquiry
    for kw in PRICE_KEYWORDS:
        if re.search(r"\b" + re.escape(kw) + r"\b", clean_msg):
            return {
                "intent": "price",
                "priority": 12,
                "reason": f"Product price inquiry: '{kw}'"
            }

    # Priority 13: Link / Where to buy
    for kw in LINK_KEYWORDS:
        if kw in clean_msg:
            return {
                "intent": "link",
                "priority": 13,
                "reason": f"Purchase link or website URL inquiry: '{kw}'"
            }

    # Priority 14: Default RAG (CX-02 Knowledge)
    return {
        "intent": "rag",
        "priority": 14,
        "reason": "General CX-02 conversational technical query"
    }
