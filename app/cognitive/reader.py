import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from app.utils.quantity import parse_quantity, normalize_digits


# Arabic character normalization mapping
ARABIC_CHAR_MAP = {
    'أ': 'ا', 'إ': 'ا', 'آ': 'ا', 'ٱ': 'ا',
    'ة': 'ه',
    'ى': 'ي',
    'ؤ': 'و', 'ئ': 'ي'
}

# Arabic diacritics regex (harakat + tatweel)
ARABIC_DIACRITICS_REGEX = re.compile(r'[\u064B-\u065F\u0670\u0640]')

# Arabizi / Gulf Manglish keywords
MANGLISH_PATTERNS = [
    r"\bbikam\b", r"\bkam\s+el\b", r"\bse3r\b", r"\bs3r\b", r"\bmarhaba\b",
    r"\bshukran\b", r"\binshallah\b", r"\binsha\s*allah\b", r"\baywa\b",
    r"\bkhalas\b", r"\bhabibi\b", r"\bsalam\b", r"\bsalam\s*alaykum\b",
    r"\bfeen\b", r"\bwein\b", r"\bwayn\b", r"\blazem\b", r"\bwallah\b",
    r"\bmashallah\b", r"\bya\s+akhi\b", r"\bsho\s+el\b", r"\bshu\s+el\b"
]

# Common typos for domain vocabulary
TYPO_MAPPINGS = [
    (r"\bcitzen\b|\bcittizen\b|\bcitizn\b|\bsitizen\b", "citizen"),
    (r"\bcx02\b|\bcx2\b|\bcx-2\b|\bcx 2\b", "cx-02"),
    (r"\bprentir\b|\bprintr\b|\bprinte\b|\bprintar\b", "printer"),
    (r"\bcatridge\b|\bcartidge\b|\bcartrige\b", "cartridge"),
    (r"\brebon\b|\bribon\b|\bribin\b", "ribbon"),
    (r"\bwarenty\b|\bwaranty\b|\bguarnty\b|\bguranty\b", "warranty"),
    (r"\bdelvery\b|\bdilvery\b|\bdelivry\b|\bdelivary\b", "delivery"),
    (r"\bshippin\b|\bshiping\b", "shipping"),
    (r"\bdiscunt\b|\bdiscout\b|\bdescount\b", "discount")
]

UNSUPPORTED_ITEMS = [
    "tripod", "cable", "adapter", "battery", "scanner", "stand", "bluetooth", "wireless", "xyz"
]

ANAPHORA_INDICATORS = [
    "it", "this", "that", "them", "these", "those",
    "the unit", "the machine", "the printer", "the media",
    "the 4x6", "the 5x7", "the 6x8", "the bag", "the pen",
    "how much for", "quote for", "price for", "what about",
    "cost for", "is that in stock", "are they in stock",
    "is it available", "how much is it", "for it", "for them",
    # Arabic anaphoric indicators
    "كم سعرها", "كم سعره", "هل متوفر", "هل متوفرة", "بكم هذي", "بكم هذا",
    "ابغى منها", "احتاج منها", "اعطني سعرها", "كم تكلف", "كم تكلفة"
]


@dataclass
class ReadContext:
    raw_text: str
    normalized_text: str
    language: str  # "en", "ar", "manglish"
    detected_sku: Optional[str] = None
    resolved_sku: Optional[str] = None
    resolved_qty: Optional[int] = None
    is_anaphora: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


def normalize_arabic(text: str) -> str:
    """Standardizes Arabic characters and strips diacritics and tatweel."""
    # Strip tatweel and tashkeel
    t = ARABIC_DIACRITICS_REGEX.sub('', text)
    # Normalize characters
    for src, dst in ARABIC_CHAR_MAP.items():
        t = t.replace(src, dst)
    return t


def normalize_text(text: str) -> str:
    """Comprehensive unicode, whitespace, and digit normalization."""
    if not text:
        return ""

    # 1. NFKC unicode normalization
    norm = unicodedata.normalize("NFKC", text)

    # 2. Translate Eastern Arabic-Indic digits to ASCII (٠-٩ -> 0-9)
    norm = normalize_digits(norm)

    # 3. Strip zero-width & non-printable characters
    norm = re.sub(r'[\u200B-\u200D\uFEFF\u200E\u200F]', '', norm)

    # 4. Standardize quotes, dashes, multiplication signs
    norm = norm.replace('“', '"').replace('”', '"').replace('’', "'").replace('‘', "'")
    norm = norm.replace('–', '-').replace('—', '-').replace('×', 'x').replace('*', 'x')

    # 5. Arabic character normalization if text contains Arabic block
    if any('\u0600' <= char <= '\u06FF' for char in norm):
        norm = normalize_arabic(norm)

    # 6. Collapse excessive whitespace
    norm = re.sub(r'\s+', ' ', norm).strip()

    # 7. Apply domain typo corrections (case-insensitive)
    for pattern, replacement in TYPO_MAPPINGS:
        norm = re.sub(pattern, replacement, norm, flags=re.IGNORECASE)

    return norm


def detect_language(text: str) -> str:
    """
    Detects language of message:
      - 'ar' for Arabic script
      - 'manglish' for Arabizi / Gulf colloquial English-Arabic slang
      - 'en' for English (default)
    """
    if not text:
        return "en"

    # Check for Arabic script characters
    arabic_chars = [c for c in text if '\u0600' <= c <= '\u06FF']
    total_alpha = [c for c in text if c.isalpha()]

    if total_alpha and len(arabic_chars) / len(total_alpha) > 0.3:
        return "ar"

    lower = text.lower()
    for pattern in MANGLISH_PATTERNS:
        if re.search(pattern, lower):
            return "manglish"

    return "en"


def extract_sku_direct(text: str) -> Optional[str]:
    """Extracts explicit product SKU or alias from the text without context."""
    raw_lower = text.lower()
    t = raw_lower.replace(" ", "").replace("-", "").replace(".", "").replace("\"", "").replace("x", "")

    # Unsupported items check first
    if any(u in raw_lower for u in UNSUPPORTED_ITEMS):
        return None

    # Official Accessories
    if any(b in raw_lower for b in ["bag", "case", "شنطة", "شنطه", "حقيبة", "حقيبه"]):
        return "CX-02-BAG"
    if any(p in raw_lower for p in ["pen", "cleaning", "تنظيف", "قلم"]):
        return "CITIZEN-PEN"

    # 6x9 media (unsupported / not listed)
    if "6x9" in raw_lower or "6*9" in raw_lower or "٦×٩" in raw_lower:
        return "6x9"

    # Media sizes
    if "ms46" in raw_lower or "4x6" in raw_lower or "4*6" in raw_lower or "10x15" in raw_lower or "٤×٦" in raw_lower or "٤*٦" in raw_lower:
        return "CX2-MS46-2PC"
    if "ms57" in raw_lower or "5x7" in raw_lower or "5*7" in raw_lower or "127x178" in raw_lower or "٥×٧" in raw_lower or "٥*٧" in raw_lower:
        return "CX2-MS57-2PC"
    if "ms68" in raw_lower or "6x8" in raw_lower or "6*8" in raw_lower or "152x203" in raw_lower or "٦×٨" in raw_lower or "٦*٨" in raw_lower:
        return "CX2-MS68-2PC"

    # Generic media
    if any(m in raw_lower for m in ["media", "paper", "consumable", "rolls", "ورق", "رول", "وسائط"]):
        return "CX2-MS46-2PC"

    # Printer
    if any(p in raw_lower for p in ["cx-02", "cx02", "printer", "machine", "photo printer", "طابعة", "طابعه"]):
        return "CX-02"

    return None


def resolve_anaphora_sku(current_text: str, history: List[Dict[str, str]]) -> Optional[str]:
    """
    Resolves product references from conversation history when anaphoric pronouns
    or elliptical phrasing is used (e.g. 'the 5x7', 'how much for 3 of them', 'is it in stock').
    """
    if not history:
        return None

    # Check if current message is anaphoric
    lower = current_text.lower()
    is_anaphoric = any(indicator in lower for indicator in ANAPHORA_INDICATORS)

    # Also consider anaphoric if quantity is asked without product name (e.g., "quote for 3", "I need 5")
    parsed_qty = parse_quantity(current_text)
    if parsed_qty and not extract_sku_direct(current_text):
        is_anaphoric = True

    if not is_anaphoric:
        return None

    # Search history backwards for the most recently referenced SKU
    for turn in reversed(history):
        content = turn.get("content", "")
        sku = extract_sku_direct(content)
        if sku:
            return sku

    return None


def read_message(raw_text: str, history: Optional[List[Dict[str, str]]] = None) -> ReadContext:
    """
    Entry point for Cognitive Step 1: READ.
    Normalizes text, detects language, extracts quantities, and resolves anaphora.
    """
    normalized = normalize_text(raw_text)
    language = detect_language(normalized)
    direct_sku = extract_sku_direct(normalized)
    qty = parse_quantity(normalized)

    resolved_sku = direct_sku
    is_anaphora = False

    if not resolved_sku and history:
        context_sku = resolve_anaphora_sku(normalized, history)
        if context_sku:
            resolved_sku = context_sku
            is_anaphora = True

    # Check if text contains unsupported items; never default to CX-02 if unsupported items present
    has_unsupported = any(u in normalized.lower() for u in UNSUPPORTED_ITEMS)

    # If still no SKU and it's a general pricing / buying inquiry about printer (and not unsupported)
    if not resolved_sku and not has_unsupported:
        if any(w in normalized.lower() for w in ["price", "cost", "how much", "quote", "printer", "طابعة", "طابعه", "bikam", "se3r"]):
            resolved_sku = "CX-02"

    return ReadContext(
        raw_text=raw_text,
        normalized_text=normalized,
        language=language,
        detected_sku=direct_sku,
        resolved_sku=resolved_sku,
        resolved_qty=qty,
        is_anaphora=is_anaphora,
        metadata={
            "char_count": len(raw_text),
            "normalized_char_count": len(normalized)
        }
    )
