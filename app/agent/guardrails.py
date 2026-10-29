import re
from typing import Tuple, Dict, Any, List

# Competitor brands (Only brands Kepler Tech LLC does NOT carry)
# Note: Epson and Citizen are authorized Kepler partner brands and are REMOVED.
COMPETITOR_BRANDS = [
    "dnp", "rx1", "ds620", "ds820", "ds40", "ds80", "qw410",
    "fujifilm", "fuji", "ask-300", "ask300", "frontier", "de100", "dx100",
    "hiti", "p525l", "p520l", "p720l", "p750l",
    "sinfonia", "cs2", "s3", "color stream",
    "mitsubishi", "cp-d70dw", "cp-d80dw", "cp-d90dw", "cp-m1e",
    "canon", "selphy", "cp1300", "cp1500", "pro-200", "pro-300", "pro-1000", "كانون",
    "kodak", "noritsu", "shinko", "كوداك", "فوجي", "ميتسوبيشي", "دي ان بي",
    "ecotank", "l805", "l1800", "കാനൺ", "സെൽഫി",
    "polaroid", "hp", "brother", "sony", "sprocket"
]

# Other Citizen models carried by Kepler Tech LLC (commercial details pending in chat)
OTHER_CITIZEN_MODELS = [
    "cx-02w", "cx02w", "cx 02w", "cx-02s", "cx02s", "cy-02", "cy02", "cy 02", "cz-01", "cz01", "cz 01",
    "op900ii", "op900", "cw-01", "cw01", "cx-01", "cx01"
]

# Injection & Security Patterns
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)?\s*(instructions|prompts|directives|rules|constraints|system\s+message)",
    r"disregard\s+(all\s+)?(previous|prior|above)?\s*(instructions|prompts|directives|rules|constraints|safety)",
    r"forget\s+(your\s+)?(cx-02\s+)?instructions",
    r"(reveal|tell\s+me|print|show)\s+(your\s+)?(system\s+)?(prompt|instructions|secret)",
    r"what\s+was\s+the\s+exact\s+text\s+given\s+to\s+you",
    r"system\s+prompt(\s+leak)?",
    r"system\s+override",
    r"bypass\s+guardrails",
    r"you\s+are\s+now\s+(an?|a\s+new)",
    r"jailbreak",
    r"dan\s+mode",
    r"act\s+as\s+(an?\s+unrestricted|someone\s+else|a\s+linux|a\s+competitor)",
    r"developer\s+mode",
    r"what\s+are\s+your\s+(initial|system)\s+instructions",
    r"repeat\s+(everything\s+above|the\s+words\s+above)",
    r"(admin\s+)?credentials|secret\s+password|internal\s+configuration\s+and\s+secrets",
    r"roleplay(ing)?|pretend\s+you",
    r"write\s+a\s+python\s+script\s+to\s+scrape",
    r"open\s+source\s+assistant",
    r"(output|show|print)\s+.*(verbatim|instructions|prompt)",
    # Malayalam injection patterns
    r"നിർദ്ദേശങ്ങൾ\s+(അവഗണിക്കുക|മറക്കുക|മാറ്റുക)",
    r"നിങ്ങളുടെ\s+(മുൻ\s+)?നിർദ്ദേശങ്ങൾ",
    r"പുതിയ\s+സിസ്റ്റം",
    r"സിസ്റ്റം\s+(പ്രോംപ്റ്റ്|നിർദ്ദേശങ്ങൾ)"
]

# Privacy / Personal Data Access Patterns
PRIVACY_PATTERNS = [
    r"(phone\s+number|contact\s+details|email)\s+of\s+(my\s+)?(last\s+)?order",
    r"(show|list|dump)\s+(me\s+)?(all\s+)?customer\s+(names|data|database|details|records)",
    r"personal\s+(data|information)\s+of\s+customer"
]

# Off-Scope Non-Catalog Products (laser, consumer gadgets, 3D printers, thermal POS)
OFFSCOPE_PATTERNS = [
    r"3d\s+printers?",
    r"thermal\s+pos(\s+printers?)?",
    r"pos\s+receipt\s+printers?",
    r"receipt\s+printers?",
    r"laser(\s+printer)?s?",
    r"inks?\s+for\s+inkjet\s+printers?",
    r"paper\s+shredders?", r"shredders?",
    r"laptops?", r"cameras?", r"smartphones?", r"coffee(\s+machines?)?"
]

# Commercial & Margin Secrets
COMMERCIAL_EXPLOIT_PATTERNS = [
    r"cost\s+price",
    r"wholesale\s+cost",
    r"distributor\s+(margin|cost|pricing)",
    r"how\s+much\s+does\s+kepler\s+buy\s+it\s+for",
    r"your\s+profit\s+margin"
]

# Abuse, Legal Threats & Blackmail Patterns
ABUSE_AND_THREAT_PATTERNS = [
    r"\bfuck\b", r"\bshit\b", r"\bbitch\b", r"\basshole\b", r"\bastard\b",
    r"sue\s+you", r"reporting\s+you", r"this\s+is\s+a\s+scam", r"leave\s+a\s+1\s+star",
    r"call\s+the\s+authorities", r"call\s+the\s+police", r"you\s+are\s+useless"
]


def check_pre_guardrails(user_text: str) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Evaluates input before processing.
    Returns: (is_safe: bool, failure_type: str, details: dict)
    """
    clean_text = user_text.lower()

    # 1. Prompt injection check
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, clean_text, re.IGNORECASE):
            return False, "prompt_injection", {
                "reason": "Suspected prompt injection or system override attempt.",
                "response": "I am the Kepler Tech sales assistant and can assist with information, pricing, and quotations for our commercial printers, official accessories, and printing services."
            }

    # 2. Commercial exploit / cost price check
    for pattern in COMMERCIAL_EXPLOIT_PATTERNS:
        if re.search(pattern, clean_text, re.IGNORECASE):
            return False, "commercial_exploit", {
                "reason": "Inquiry regarding internal distributor cost price or profit margin.",
                "response": "Internal cost prices and margins are proprietary to Kepler Tech LLC. For official wholesale and bulk commercial quotes, please consult our corporate sales desk."
            }

    # 3. Abuse, threat & frustration check
    for pattern in ABUSE_AND_THREAT_PATTERNS:
        if re.search(pattern, clean_text, re.IGNORECASE):
            return False, "abuse", {
                "reason": "Abusive, threatening, or frustrated language detected.",
                "response": "I understand your concern. I am connecting you directly with our specialized sales and customer care team at Kepler Tech LLC (Dubai) for immediate assistance."
            }

    # 4. Privacy & personal customer data check
    for pattern in PRIVACY_PATTERNS:
        if re.search(pattern, clean_text, re.IGNORECASE):
            return False, "privacy_violation", {
                "reason": "Request for private customer data or order contact numbers.",
                "response": "For customer privacy and data protection compliance, order records and customer contact details cannot be disclosed through this chat. Please contact Kepler Tech LLC directly at our Dubai office."
            }

    # 5. Off-scope non-catalog products check
    for pat in OFFSCOPE_PATTERNS:
        if re.search(r"\b" + pat + r"\b", clean_text):
            return False, "out_of_scope", {
                "reason": f"Inquiry about off-scope product '{pat}'.",
                "response": (
                    "That product is not part of the Kepler Tech commercial catalogue. "
                    "Kepler Tech specializes in commercial photo printers (Citizen dye-sublimation), "
                    "large-format CAD & fine art plotters (Epson SureColor), high-speed business MFPs (Epson WorkForce), "
                    "and professional document scanners. Would you like to explore any of our commercial printing solutions?"
                )
            }

    # 6. Comparative model check (e.g. 'Why is Citizen CX-02 better than ...', 'CX-02 vs ...')
    if any(comp_word in clean_text for comp_word in ["better than", "worse than", "compare to", "vs ", "vs."]):
        if any(cx in clean_text for cx in ["cx-02", "cx02"]):
            return False, "competitor", {
                "reason": "Model comparison requested.",
                "response": (
                    "While we do not provide comparative commentary on other brands, the **Citizen CX-02** "
                    "is a compact dye-sublimation photo printer engineered for lab-quality event prints with rapid 8.4-second 4x6\" speeds, "
                    "durable overcoat protection, and ribbon-rewind waste reduction. For detailed technical comparisons or sample prints, "
                    "our specialists will be pleased to assist."
                )
            }

    # 7. Competitor brand check (brands Kepler does NOT carry)
    for comp in COMPETITOR_BRANDS:
        if re.search(r"\b" + re.escape(comp) + r"\b", clean_text):
            return False, "competitor", {
                "competitor": comp,
                "reason": f"Inquiry mentions competitor brand or model '{comp}'.",
                "response": (
                    "That product line is not available in our catalog. Kepler Tech is an authorized UAE distributor for **Citizen** and **Epson** commercial printing systems:\n"
                    "• **Photo Booth & Events**: Citizen CX-02, CY-02, CZ-01\n"
                    "• **CAD, Technical & Fine Art**: Epson SureColor T-Series & P-Series\n"
                    "• **Office & Enterprise MFP**: Epson WorkForce Pro & Enterprise\n\n"
                    "Would you like details on an authorized solution, or assistance from a sales specialist?"
                )
            }

    # 7. Unsupported media sizes on CX-02 (e.g. A4)
    if re.search(r"\ba4\b", clean_text) and any(w in clean_text for w in ["cx-02", "cx02", "this printer"]):
        return False, "unsupported_media", {
            "media": "A4",
            "reason": "Citizen CX-02 does not print A4 sheets.",
            "response": "The Citizen CX-02 is a dedicated roll-fed photo printer supporting sizes up to 6x9 inches (4x6, 5x7, 6x8, 2x6 strips). For A4 sheet printing or wide-format options, Kepler Tech provides Epson office and large-format solutions: https://www.keplertechllc.com/product-category/printers/business-printer/. Our sales team can assist with sizing your setup."
        }

    return True, "", {}


def _build_prompt_shingles(n: int = 8) -> set:
    try:
        from app.agent.prompts import SYSTEM_PROMPT
    except ImportError:
        SYSTEM_PROMPT = ""
    texts = [
        SYSTEM_PROMPT,
        "You are the commercial sales specialist for Kepler Tech LLC Dubai focusing on Citizen photo printers.",
        "You are the official sales assistant for Kepler Tech LLC Dubai.",
        "CRITICAL OPERATIONAL RULES: COMMERCIAL AUTHORITY ZERO INVENTED PRICES FACTUAL GROUNDEDNESS",
        "NEVER produce prices, stock, delivery, warranty, VAT, discounts, totals, links, or policy statements."
    ]
    shingles = set()
    for text in texts:
        words = re.findall(r"\b\w+\b", text.lower())
        for i in range(len(words) - n + 1):
            shingles.add(tuple(words[i:i + n]))
    return shingles


PROMPT_SHINGLES_8 = _build_prompt_shingles(8)


def check_post_guardrails(reply_text: str) -> Tuple[bool, str]:
    """
    Verifies that the generated reply does not mention competitor brands,
    contain forbidden phrases, or leak system prompt instructions (8-word sequence).
    """
    clean_reply = reply_text.lower()

    for comp in COMPETITOR_BRANDS:
        if re.search(r"\b" + re.escape(comp) + r"\b", clean_reply):
            return False, f"Output mentions unauthorized competitor: {comp}"

    # Forbidden strings enforcement
    forbidden_phrases = ["we do not sell", "we do not supply", "specialize exclusively", "excl. vat"]
    for fp in forbidden_phrases:
        if fp in clean_reply:
            return False, f"Output contains forbidden phrase: '{fp}'"

    # 8-word prompt leak detection
    reply_words = re.findall(r"\b\w+\b", clean_reply)
    for i in range(len(reply_words) - 8 + 1):
        shingle = tuple(reply_words[i:i + 8])
        if shingle in PROMPT_SHINGLES_8:
            return False, f"Prompt leak detected: 8-word verbatim sequence from system instructions ({' '.join(shingle)})"

    return True, ""
