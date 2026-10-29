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
    r"(connect|transfer)\s+(me\s+)?(to\s+)?.*(human|person|agent|someone|representative|manager|sales|team|specialist)",
    r"talk\s+to\s+(a\s+)?(human|person|agent|someone|representative|manager|real\s+person)",
    r"speak\s+with\s+(a\s+)?(human|person|agent|someone|representative|manager)",
    r"want\s+to\s+talk\s+to\s+a\s+person",
    r"call\s+me(\s+back)?",
    r"human\s+agent",
    r"real\s+person",
    r"sales\s+team",
    r"customer\s+(service|support|care)",
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
    "shipping time", "delivery", "shipping", "payment method", "payment methods", "payment", "pay", "paypal", "credit card", "cod", "cash on delivery",
    "cancellation policy", "cancellation", "cancel",
    "return policy", "refund policy", "refund", "return", "returns", "damaged", "defective", "defect",
    "pickup", "pick up", "store pickup",
    "installation", "install", "setup", "support terms", "vat treatment", "vat", "tax", "taxes", "inclusive of vat", "include vat", "inclusive vat"
]

DISCOUNT_KEYWORDS = [
    "discount", "discounts", "discount code", "promo", "promo code", "coupon",
    "best price", "cheaper", "negotiate", "bargain", "special offer", "reduction",
    "wholesale", "corporate pricing", "% off", "percent off", "lower price", "better price",
    "20% off", "match competitor", "lowest you can do"
]

QUOTE_KEYWORDS = [
    "quote", "quotation", "formal quote", "proforma", "estimate",
    "quote me", "calculate total", "how much for 2", "how much for 3", "how much for 5",
    "bulk quote", "draft", "create a draft", "draft quote", "draft a quote"
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
    "what accessories", "range", "what else do you sell", "bundle", "consumables"
]

PRICE_KEYWORDS = [
    "price", "how much", "cost", "rate", "aed", "dirham", "dirhams",
    "bikam", "kam el se3r", "kam el s3r", "se3r", "s3r",
    "سعر", "بكم", "تكلفة", "كم سعر"
]

LINK_KEYWORDS = [
    "link", "url", "website", "where to buy", "where can i buy", "purchase link", "order online"
]

SERVICE_ENQUIRY_PATTERNS = [
    r"\brepair\b", r"\brepairing\b", r"\bservice\s+center\b", r"\bfix(ing)?\s+(a\s+)?printer\b",
    r"\bmaintenance\b", r"\bamc\b", r"\bfsma\b", r"\bmaintenance\s+contract\b",
    r"\brental\b", r"\brent(ing)?\b", r"\blease\b", r"\bleasing\b", r"\bhire\b",
    r"\bmanaged\s+print(\s+services?)?\b", r"\bmps\b", r"\bcost\s+per\s+copy\b", r"\bpay\s+per\s+click\b",
    r"\berp\b", r"\berpnext\b", r"\bodoo\b", r"\bsap\b", r"\btally\b", r"\bquickbooks\b",
    r"\badobe\b", r"\bcreative\s+cloud\b", r"\bphotoshop\b", r"\billustrator\b", r"\blightroom\b"
]

BULK_ORDER_PATTERNS = [
    r"\bbulk\b", r"\bwholesale\b", r"\bvolume\s+discount\b", r"\bquantity\s+discount\b",
    r"\bcorporate\s+pricing\b", r"\breseller\b", r"\bdistributor\s+pricing\b",
    r"\btrade\s+inquir(y|ies)\b", r"\bexport\s+order\b",
    r"\b(10|15|20|25|30|40|50|100|5000)\s*(cx[-_]?02\s*)?(units?|printers?|boxes|sets|rolls|cleaning\s+pens|pens)\b"
]

COVERAGE_PATTERNS = [
    r"\b(do\s+you\s+)?(ship|deliver|delivery|shipping)\s+(to|in)\b",
    r"\bcountries\s+we\s+serve\b", r"\bcoverage\b", r"\bdelivery\s+coverage\b",
    r"\bkuwait\b", r"\bsaudi(\s+arabia)?\b", r"\bksa\b", r"\bqatar\b", r"\bbahrain\b", r"\boman\b",
    r"\bal\s+ain\b", r"\bsharjah\b", r"\briyadh\b",
    r"\bafrica\b", r"\bkenya\b", r"\bnigeria\b", r"\bghana\b", r"\btanzania\b", r"\buganda\b",
    r"\brwanda\b", r"\begypt\b"
]

CATEGORY_BROWSE_PATTERNS = [
    r"\bepson(\s+printers?)?\b", r"\boffice\s+printers?\b", r"\bbusiness\s+printers?\b",
    r"\blarge\s+format\b", r"\bplotters?\b", r"\bcad\b", r"\bworkforce\b", r"\bsurecolor\b",
    r"\bscanners?\b", r"\binkjet\s+media\b", r"\bfine\s+art(\s+paper)?\b", r"\bcanvas\b",
    r"\bsublimation\s+paper\b", r"\binnova\b", r"\bolmec\b", r"\bkorejet\b",
    r"\bcx[-_]?02w\b", r"\bcy[-_]?02\b", r"\bcz[-_]?01\b", r"\bop900\b", r"\bcw[-_]?01\b",
    r"\baircastpro\b", r"\bsc[-_]?p900\b", r"\bsc[-_]?p700\b", r"\ba3\s+printers?\b",
    r"\bwhat\s+(printers|brands|products)\s+(do\s+you\s+)?(sell|have|carry|stock)\b",
    r"\bproduct\s+categories\b"
]

COMPANY_INFO_PATTERNS = [
    r"\bcompany\s+name\b", r"\bwho\s+is\s+kepler\b", r"\bwhat\s+is\s+kepler\b",
    r"\babout\s+kepler\b", r"\babout\s+(your\s+)?company\b", r"\bwho\s+are\s+you\b",
    r"\bwhere\s+are\s+you\s+located\b", r"\boffice\s+location\b", r"\bshowroom\s+address\b",
    r"\bhead\s+office\b", r"\bdubai\s+silicon\s+oasis\b", r"\bdso\b",
    r"\bcontact\s+(info|information|details|number)\b", r"\bphone\s+number\b",
    r"\bemail(\s+address)?\b", r"\bopening\s+hours\b", r"\bworking\s+hours\b", r"\btimings\b",
    r"\bwhy\s+printers\s+are\s+used\b", r"\bbrands\b", r"\bwhich\s+brands\b", r"\bwhat\s+brands\b",
    r"\bauthorized\b", r"\bauthorised\b", r"\bepson\s+dealer\b", r"\bindustries\b",
    r"\breviews\b", r"\bgoogle\s+reviews\b", r"\bhow\s+long\s+(have\s+you\s+been\s+)?in\s+business\b",
    r"\bsince\s+when\b", r"\breal\s+company\b", r"\boriginal\s+products\b",
    r"\bvisit\s+(your\s+)?(shop|office|showroom|store)\b", r"\bbranch\s+in\s+abu\s+dhabi\b",
    r"\babu\s+dhabi\s+branch\b", r"\bindividuals\s+or\s+(only\s+)?companies\b",
    r"\btraining\s+on\s+the\s+printer\b", r"\bwho\s+built\s+this\b", r"\bwho\s+build\s+this\b"
]

OBJECTION_PATTERNS = [
    r"\btoo\s+expensive\b", r"\bworth\s+the\s+money\b", r"\bwhy\s+buy\s+from\s+you\b",
    r"\bwhy\s+kepler\b", r"\bamazon\b", r"\bwhy\s+is\s+the\s+cleaning\s+pen\b",
    r"\bwhy\s+(not\s+)?(an\s+)?inkjet\b", r"\bdye[- ]?sub\s+(better\s+than|vs)\s+inkjet\b",
    r"\bwhy\s+not\s+just\s+buy\s+an\s+inkjet\b", r"\bbetter\s+than\s+dnp\b",
    r"\banother\s+shop\s+quoted\b", r"\bmatch\s+(it|the\s+price)\b", r"\blowest\s+you\s+can\s+do\b",
    r"\bmy\s+friend\s+bought\b", r"\bepson\s+or\s+citizen\s+for\s+photos\b",
    r"\bwhat('?s|\s+is)\s+your\s+best\s+printer\b", r"\bwhat\s+do\s+professionals\s+use\b",
    r"\bcheaper\s+alternative\b", r"\bused\s+or\s+refurbished\b"
]

TROUBLESHOOTING_PATTERNS = [
    r"\bwhite\s+lines\b", r"\bstreaks?\b", r"\b(strange|weird|loud)\s+noise\b",
    r"\bpaper\s+(keeps\s+)?jam(ming)?\b", r"\bwon'?t\s+turn\s+on\b", r"\bnot\s+turning\s+on\b",
    r"\bdownload\s+(the\s+)?driver\b", r"\bwhere\s+do\s+i\s+download\s+the\s+driver\b",
    r"\binstall\s+(the\s+)?ribbon\b", r"\bhow\s+do\s+i\s+install\s+the\s+ribbon\b",
    r"\bif\s+i\s+drop\s+it\b", r"\bdropped\b", r"\bcan\s+you\s+fix\s+my\s+epson\b",
    r"\barrives\s+broken\b", r"\bpaid\s+but\s+nothing\s+arrived\b", r"\bchanged\s+my\s+mind\b"
]

INDIRECT_NEED_PATTERNS = [
    r"\bphoto\s*booth\s+business\b", r"\bstarting\s+a\s+photo\s*booth\b",
    r"\binstant\s+prints?\s+at\s+weddings\b", r"\bprint\s+about\s+\d+\s+photos\b",
    r"\bportable\s+for\s+events\b", r"\bwhat\s+do\s+i\s+need\s+to\s+start\b",
    r"\bwhat\s+else\s+do\s+i\s+need\b", r"\bpassport\s+photos?\b", r"\bbig\s+posters?\b",
    r"\bboth\s+documents\s+and\s+photos\b", r"\bprinter\s+died\b", r"\bneed\s+to\s+buy\s+ink\b",
    r"\bprint\s+from\s+(my\s+)?phone\b", r"\bfit\s+in\s+(my\s+)?car\b",
    r"\bhow\s+long\s+does\s+one\s+roll\s+last\b", r"\bruns?\s+a\s+small\s+studio\b"
]

BUDGET_PATTERNS = [
    r"\bbudget\s+is\s+\d+", r"\banything\s+cheaper\b", r"\btotal\s+for\s+everything\b",
    r"\bwhat\s+will\s+\d+\s+photos\s+cost\b", r"\bcheapest\s+way\s+to\s+start\b",
    r"\binstallments?\b", r"\bprice\s+in\s+dollars?\b", r"\bold\s+price\s+still\s+available\b",
    r"\bpay\s+in\s+installments\b", r"\bpay\s+half\s+now\b"
]

DISCOVERY_PATTERNS = [
    r"^\?+$", r"^i\s+need\s+help[\s.!]*$", r"^printer[\s.!]*$",
    r"^recommend(\s+something)?[\s.!]*$", r"^what\s+do\s+you\s+have[\s.?]*$",
    r"^📸\s*🖨️\s*\??$", r"^the\s+black\s+one[\s.?]*$", r"^that\s+one[\s.?]*$"
]

META_PATTERNS = [
    r"\bare\s+you\s+a\s+robot\b", r"\bare\s+you\s+ai\b",
    r"\bwho\s+built\s+this\b", r"\bwho\s+build\s+this\b",
    r"\bwhat\s+i\s+asked\s+u\s+did\s+not\s+understand\b",
    r"\byou\s+don'?t\s+understand\b"
]

CLOSURE_PATTERNS = [
    r"^ok[\s.!]*$", r"^no\s+thanks[\s.!]*$", r"^thank\s+you\s+so\s+much[\s.!]*$",
    r"^you'?ve\s+been\s+so\s+helpful[\s.!]*$", r"^👍+$"
]

UNANSWERABLE_PATTERNS = [
    r"\bhow\s+loud\s+is\s+the\s+cx[-_]?02\b",
    r"\bcanon\s+software\b",
    r"\bresale\s+value\b",
    r"\bmatch\s+a\s+competitor'?s?\s+price\b",
    r"\bwhat\s+power\s+supply\s+does\s+it\s+need\b"
]


def classify_intent(message: str) -> Dict[str, Any]:
    """
    Classifies user message according to hierarchy:
    1. guardrails
    2. small_talk / meta_chat / polite_closure
    3. human_demo_reserve
    4. out_of_scope
    5. datasheet
    6. policies
    7. discount_negotiation
    8. quote / category_browse / service_enquiry / bulk_order
    9. stock / handoff
    10. media_yield_cost
    11. bundle_catalog
    12. price
    13. link
    14. rag / company_info / troubleshooting / sales_objection / product_consultation / budget_cost / discovery / coverage
    """
    clean_msg = message.strip().lower()

    # Priority 1: Guardrails (Injections, Cost Price, Abuse, Competitors, A4)
    is_safe, fail_type, details = check_pre_guardrails(clean_msg)
    if not is_safe:
        return {
            "intent": "guardrails",
            "priority": 1,
            "failure_type": fail_type,
            "reason": details.get("reason", "Guardrail breach"),
            "fixed_response": details.get("response")
        }

    # Priority 2: Meta Chat / Polite Closure / Small Talk
    for pat in META_PATTERNS:
        if re.search(pat, clean_msg):
            return {
                "intent": "meta_chat",
                "priority": 2,
                "reason": f"Meta conversational inquiry: '{pat}'"
            }

    for pat in CLOSURE_PATTERNS:
        if re.search(pat, clean_msg):
            return {
                "intent": "polite_closure",
                "priority": 2,
                "reason": "Polite conversational closure"
            }

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

    # Priority 4: Out of Scope
    unrelated_topics = [
        "television", "tv", "toyota", "nissan", "flight", "weather",
        "football", "crypto", "bitcoin", "restaurant", "burger", "pizza",
        "pasta", "joke", "capital of", "recipe", r"2\s*\+\s*2", "poem", "cricket"
    ]
    for topic in unrelated_topics:
        if re.search(r"\b" + topic + r"\b" if not topic.startswith(r"\b") else topic, clean_msg):
            return {
                "intent": "out_of_scope",
                "priority": 4,
                "reason": f"Inquiry about unrelated topic: '{topic}'",
                "fixed_response": f"Kepler Tech specializes in commercial printing hardware, media, and print solutions. I cannot assist with inquiries regarding {topic}."
            }

    # Safe handling of 'car' (only out of scope if NOT asking about fitting in car or transport)
    if re.search(r"\bcar\b", clean_msg) and not re.search(r"\b(fit\s+in|trunk|portable|carry|transport|load)\b", clean_msg):
        return {
            "intent": "out_of_scope",
            "priority": 4,
            "reason": "Inquiry about automotive car vehicles",
            "fixed_response": "Kepler Tech specializes in commercial printing hardware, media, and print solutions. I cannot assist with automotive vehicle inquiries."
        }

    # Priority 5: Datasheet Specs
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

    # Priority 7: Discount Negotiation
    for kw in DISCOUNT_KEYWORDS:
        if re.search(r"\b" + re.escape(kw) + r"\b", clean_msg):
            return {
                "intent": "discount_negotiation",
                "priority": 7,
                "reason": f"Discount / pricing negotiation request: '{kw}'"
            }

    # Priority 8: Quote / Category Browse / Service Enquiry / Bulk Order
    for kw in QUOTE_KEYWORDS:
        if kw in clean_msg:
            return {
                "intent": "quote",
                "priority": 8,
                "reason": f"Formal quotation request: '{kw}'"
            }

    if "6x9" not in clean_msg:
        if any(m in clean_msg for m in ["cx-02w", "cx02w", "cx 02w", "cy-02", "cy02", "cy 02", "cz-01", "cz01", "cz 01", "aircastpro", "sc-p900", "p900"]):
            return {
                "intent": "category_browse",
                "priority": 8,
                "reason": "Customer browsing partner catalog line or other Citizen model"
            }
        if any(req in clean_msg for req in [
            "mall kiosk", "refill all the time", "refill all time", "busy kiosk", "without refilling",
            "big framed prints", "bigger than normal", "large framed prints", "framed prints",
            "weddings and need small", "small prints fast"
        ]):
            return {
                "intent": "category_browse",
                "priority": 8,
                "reason": "Customer seeking printer recommendation for specific workflow requirement"
            }
        has_price_kw = any(re.search(r"\b" + re.escape(p) + r"\b", clean_msg) for p in PRICE_KEYWORDS)
        if not has_price_kw:
            for pat in CATEGORY_BROWSE_PATTERNS:
                if re.search(pat, clean_msg):
                    return {
                        "intent": "category_browse",
                        "priority": 8,
                        "reason": f"Customer browsing catalog brand/category: '{pat}'"
                    }

    for pat in SERVICE_ENQUIRY_PATTERNS:
        if re.search(pat, clean_msg):
            return {
                "intent": "service_enquiry",
                "priority": 8,
                "service_pattern": pat,
                "reason": f"Customer inquired about service: '{pat}'"
            }

    for pat in BULK_ORDER_PATTERNS:
        if re.search(pat, clean_msg):
            return {
                "intent": "bulk_order",
                "priority": 8,
                "reason": f"Customer inquired about commercial bulk/wholesale order: '{pat}'"
            }

    # Priority 9: Stock Availability / Restocking Handoff
    if any(rt in clean_msg for rt in ["next week", "when will you have", "restock", "restocking"]):
        return {
            "intent": "handoff",
            "priority": 9,
            "reason": "Restocking schedule inquiry -> handoff"
        }

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
    if any(w in clean_msg for w in ["and", "what about", "how about"]) and any(s in clean_msg for s in ["4x6", "5x7", "6x8", "bag", "pen", "cx-02", "cx02"]):
        return {
            "intent": "price",
            "priority": 12,
            "reason": "Elliptical price follow-up inquiry"
        }

    for kw in PRICE_KEYWORDS:
        if re.search(r"\b" + re.escape(kw) + r"\b", clean_msg):
            return {
                "intent": "price",
                "priority": 12,
                "reason": f"Product price inquiry: '{kw}'"
            }

    # Priority 13: Link / Where to buy
    for kw in LINK_KEYWORDS:
        if re.search(r"\b" + re.escape(kw) + r"\b", clean_msg):
            return {
                "intent": "link",
                "priority": 13,
                "reason": f"Purchase link or website URL inquiry: '{kw}'"
            }

    # Priority 14: Knowledge Base / Context / RAG Fallback
    for pat in UNANSWERABLE_PATTERNS:
        if re.search(pat, clean_msg):
            return {
                "intent": "unanswerable_boundary",
                "priority": 14,
                "reason": f"Unanswerable or unverified specification inquiry: '{pat}'"
            }

    for pat in TROUBLESHOOTING_PATTERNS:
        if re.search(pat, clean_msg):
            return {
                "intent": "troubleshooting",
                "priority": 14,
                "reason": f"Troubleshooting inquiry: '{pat}'"
            }

    for pat in OBJECTION_PATTERNS:
        if re.search(pat, clean_msg):
            return {
                "intent": "sales_objection",
                "priority": 14,
                "reason": f"Sales objection inquiry: '{pat}'"
            }

    for pat in INDIRECT_NEED_PATTERNS:
        if re.search(pat, clean_msg):
            return {
                "intent": "product_consultation",
                "priority": 14,
                "reason": f"Product consultation inquiry: '{pat}'"
            }

    for pat in BUDGET_PATTERNS:
        if re.search(pat, clean_msg):
            return {
                "intent": "budget_cost",
                "priority": 14,
                "reason": f"Budget / cost consultation: '{pat}'"
            }

    for pat in DISCOVERY_PATTERNS:
        if re.search(pat, clean_msg):
            return {
                "intent": "conversational_discovery",
                "priority": 14,
                "reason": f"Vague conversational inquiry: '{pat}'"
            }

    for pat in COVERAGE_PATTERNS:
        if re.search(pat, clean_msg):
            return {
                "intent": "coverage",
                "priority": 14,
                "reason": f"Customer inquired about geographic shipping coverage: '{pat}'"
            }

    for pat in COMPANY_INFO_PATTERNS:
        if re.search(pat, clean_msg):
            return {
                "intent": "company_info",
                "priority": 14,
                "reason": f"Customer asked for company info: '{pat}'"
            }

    # Default RAG (CX-02 Knowledge)
    return {
        "intent": "rag",
        "priority": 14,
        "reason": "General CX-02 conversational technical query"
    }
