import re
from typing import Tuple, Dict, Any, List

# Competitor brands and unauthorized printer models
COMPETITOR_BRANDS = [
    "dnp", "rx1", "ds620", "ds820", "ds40", "ds80", "qw410",
    "fujifilm", "fuji", "ask-300", "ask300", "frontier", "de100", "dx100",
    "hiti", "p525l", "p520l", "p720l", "p750l",
    "sinfonia", "cs2", "s3", "color stream",
    "mitsubishi", "cp-d70dw", "cp-d80dw", "cp-d90dw", "cp-m1e",
    "epson", "surelab", "d500", "d1000", "d700", "d800", "l805", "l1800",
    "canon", "selphy", "cp1300", "cp1500", "pro-200", "pro-300", "pro-1000"
]

OTHER_CITIZEN_MODELS = [
    "cx-02w", "cx02w", "cx-02s", "cx02s", "cy-02", "cy02", "cz-01", "cz01",
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
    r"sql\s+injection|select\s+\*\s+from|drop\s+table"
]

# Commercial & Margin Secrets
COMMERCIAL_EXPLOIT_PATTERNS = [
    r"cost\s+price",
    r"wholesale\s+cost",
    r"distributor\s+(margin|cost|pricing)",
    r"how\s+much\s+does\s+kepler\s+buy\s+it\s+for",
    r"your\s+profit\s+margin"
]

# Abuse / Profanity Patterns
ABUSE_PATTERNS = [
    r"\bfuck\b", r"\bshit\b", r"\bbitch\b", r"\basshole\b", r"\bastard\b"
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
                "response": "I am the Citizen CX-02 sales assistant and can only assist with information, pricing, and quotations for the Citizen CX-02 photo printer and its official accessories."
            }

    # 2. Commercial exploit / cost price check
    for pattern in COMMERCIAL_EXPLOIT_PATTERNS:
        if re.search(pattern, clean_text, re.IGNORECASE):
            return False, "commercial_exploit", {
                "reason": "Inquiry regarding internal distributor cost price or profit margin.",
                "response": "Internal cost prices and margins are proprietary to Kepler Tech LLC. For official wholesale and bulk commercial quotes, please consult our corporate sales desk."
            }

    # 3. Abuse / profanity check
    for pattern in ABUSE_PATTERNS:
        if re.search(pattern, clean_text, re.IGNORECASE):
            return False, "abuse", {
                "reason": "Abusive or offensive language detected.",
                "response": "Please keep our conversation professional. How can I assist you with the Citizen CX-02 printer today?"
            }

    # 4. Competitor brand check
    for comp in COMPETITOR_BRANDS:
        if re.search(r"\b" + re.escape(comp) + r"\b", clean_text):
            return False, "competitor", {
                "competitor": comp,
                "reason": f"Inquiry mentions competitor brand or model '{comp}'.",
                "response": "I specialize exclusively in the Citizen CX-02 dye-sublimation photo printer. We do not provide information or comparisons regarding other brands. However, I would be delighted to share the technical strengths, pricing, and capabilities of the Citizen CX-02!"
            }

    # 5. Other Citizen models check
    if "cx-01" in clean_text or "cx01" in clean_text:
        if "smaller" in clean_text or "lighter" in clean_text:
            pass  # Allowed: documented comparative spec in datasheet
        else:
            return False, "other_model", {
                "model": "cx-01",
                "reason": "Inquiry asks about non-CX-02 model 'CX-01'.",
                "response": "This assistant is strictly dedicated to the standard Citizen CX-02 photo printer. For assistance regarding older models, I will connect you directly with our specialized hardware sales team."
            }

    for model in OTHER_CITIZEN_MODELS:
        if model in ("cx-01", "cx01"):
            continue
        if re.search(r"\b" + re.escape(model) + r"\b", clean_text):
            return False, "other_model", {
                "model": model,
                "reason": f"Inquiry asks about non-CX-02 model '{model.upper()}'.",
                "response": "This assistant is strictly dedicated to the standard Citizen CX-02 photo printer. For assistance regarding other models, I will connect you directly with our specialized hardware sales team."
            }

    # 6. Unsupported media sizes (e.g. A4)
    if re.search(r"\ba4\b", clean_text):
        return False, "unsupported_media", {
            "media": "A4",
            "reason": "Citizen CX-02 does not print A4 sheets.",
            "response": "The Citizen CX-02 is a dedicated roll-fed photo printer supporting sizes up to 6x9 inches (4x6, 5x7, 6x8, 2x6 strips), and does not support A4 sheet printing. I can connect you to our sales team for wide-format commercial options."
        }

    return True, "", {}


def check_post_guardrails(reply_text: str) -> Tuple[bool, str]:
    """
    Verifies that the generated reply does not mention competitor brands,
    unauthorized models, or off-limit promises.
    """
    clean_reply = reply_text.lower()

    for comp in COMPETITOR_BRANDS:
        if re.search(r"\b" + re.escape(comp) + r"\b", clean_reply):
            return False, f"Output mentions unauthorized competitor: {comp}"

    for model in OTHER_CITIZEN_MODELS:
        if model in ("cx-01", "cx01"):
            continue
        if re.search(r"\b" + re.escape(model) + r"\b", clean_reply):
            return False, f"Output mentions non-CX-02 model: {model}"

    return True, ""
