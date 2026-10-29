import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
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
    (r"\bcitzen\b|\bcittizen\b|\bcitizn\b|\bsitizen\b|\bcitixen\b|\bcitizne\b", "citizen"),
    (r"\bcx02\b|\bcx2\b|\bcx-2\b|\bcx 2\b|\bcx 02\b", "cx-02"),
    (r"\bprentir\b|\bprintr\b|\bprinte\b|\bprintar\b|\bpringer\b|\bpriner\b", "printer"),
    (r"\bpritn\b|\bprnt\b", "print"),
    (r"\bcatridge\b|\bcartidge\b|\bcartrige\b", "cartridge"),
    (r"\brebon\b|\bribon\b|\bribin\b", "ribbon"),
    (r"\bwarenty\b|\bwaranty\b|\bguarnty\b|\bguranty\b", "warranty"),
    (r"\bdelvery\b|\bdilvery\b|\bdelivry\b|\bdelivary\b", "delivery"),
    (r"\bshippin\b|\bshiping\b", "shipping"),
    (r"\bdiscunt\b|\bdiscout\b|\bdescount\b", "discount"),
    (r"\bcompnay\b|\bcompny\b|\bcompaney\b|\bcopmany\b|\bcompant\b", "company"),
    (r"\bresolushun\b|\bresolutin\b|\bresulution\b|\bresolutionn\b", "resolution"),
    (r"\bspead\b|\bspeedd\b", "speed"),
    (r"\bpric\b|\bprise\b|\bpirce\b", "price"),
    (r"\byrld\b|\byeild\b", "yield"),
    (r"\bwgt\b|\bwieght\b", "weight")
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
    "draft", "create a draft", "make a draft", "draft quote", "draft a quote", "draft it",
    "quote it", "send quote", "prepare quote",
    # Arabic anaphoric indicators
    "كم سعرها", "كم سعره", "هل متوفر", "هل متوفرة", "بكم هذي", "بكم هذا",
    "ابغى منها", "احتاج منها", "اعطني سعرها", "كم تكلف", "كم تكلفة", "عرض سعر"
]


from app.cognitive.normalizer import (
    normalize_brand,
    normalize_model_or_sku,
    detect_phantom_model,
    detect_ambiguous_model,
)


@dataclass
class ReadContext:
    raw_text: str
    normalized_text: str
    language: str  # "en", "ar", "manglish", "ml"
    detected_sku: Optional[str] = None
    resolved_sku: Optional[str] = None
    resolved_model: Optional[str] = None
    resolved_models: List[str] = field(default_factory=list)
    resolved_qty: Optional[int] = None
    is_anaphora: bool = False
    reference_type: Optional[str] = None  # "single", "plural", "first", "second", "consumables", "why", "alternative", "quote"
    is_correction: bool = False
    correction_slot: Optional[str] = None
    correction_val: Optional[Any] = None
    interpreted_context: Optional[str] = None
    sku_source: Optional[str] = None  # "explicit", "state", "default"
    phantom_model: Optional[Dict[str, Any]] = None
    disambiguation: Optional[Dict[str, Any]] = None
    detected_brand: Optional[str] = None
    detected_category: Optional[str] = None
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

    # 2. Strip Unicode category 'Cf' (Format characters: zero-width spaces \u200B, joiners \u200C/\u200D, BOM \uFEFF, bidi marks)
    norm = "".join(c for c in norm if unicodedata.category(c) != "Cf")

    # 3. Escape angle brackets to prevent HTML/XML/injection bypass
    norm = norm.replace("<", "&lt;").replace(">", "&gt;")

    # 4. Translate Eastern Arabic-Indic digits to ASCII (٠-٩ -> 0-9)
    norm = normalize_digits(norm)

    # 5. Standardize quotes, dashes, multiplication signs
    norm = norm.replace('“', '"').replace('”', '"').replace('’', "'").replace('‘', "'")
    norm = norm.replace('–', '-').replace('—', '-').replace('×', 'x').replace('*', 'x')

    # 6. Arabic character normalization if text contains Arabic block
    if any('\u0600' <= char <= '\u06FF' for char in norm):
        norm = normalize_arabic(norm)

    # 7. Collapse excessive whitespace
    norm = re.sub(r'\s+', ' ', norm).strip()

    # 8. Apply domain typo corrections (case-insensitive)
    for pattern, replacement in TYPO_MAPPINGS:
        norm = re.sub(pattern, replacement, norm, flags=re.IGNORECASE)

    return norm


def detect_language(text: str) -> str:
    """
    Detects language of message:
      - 'ar' for Arabic script
      - 'ml' for Malayalam script
      - 'manglish' for Arabizi / Gulf colloquial English-Arabic slang
      - 'en' for English (default)
    """
    if not text:
        return "en"

    total_alpha = [c for c in text if c.isalpha()]
    if not total_alpha:
        return "en"

    # Check for Malayalam script characters (\u0D00 - \u0D7F)
    ml_chars = [c for c in text if '\u0D00' <= c <= '\u0D7F']
    if len(ml_chars) / len(total_alpha) > 0.25:
        return "ml"

    # Check for Arabic script characters (\u0600 - \u06FF)
    arabic_chars = [c for c in text if '\u0600' <= c <= '\u06FF']
    if len(arabic_chars) / len(total_alpha) > 0.25:
        return "ar"

    lower = text.lower()
    for pattern in MANGLISH_PATTERNS:
        if re.search(pattern, lower):
            return "manglish"

    return "en"


def extract_sku_direct(text: str) -> Optional[str]:
    """Extracts explicit product SKU or alias from the text without context."""
    raw_lower = text.lower()

    # 1. Normalizer alias table match
    canonical, _, _ = normalize_model_or_sku(text)
    if canonical:
        return canonical

    # 2. Unsupported items check
    if any(u in raw_lower for u in UNSUPPORTED_ITEMS):
        return None

    # 3. Check for specific CX numbers (like CX-04 etc)
    cx_m = re.search(r"\bcx[-_]?(0?[0-9]+)\b", raw_lower)
    if cx_m:
        num = int(cx_m.group(1))
        return f"CX-{num:02d}"

    # 4. Accessories
    if any(b in raw_lower for b in ["bag", "case", "شنطة", "شنطه", "حقيبة", "حقيبه", "ബാഗ്"]):
        return "CX-02-BAG"
    if any(p in raw_lower for p in ["cleaning pen", "تنظيف", "قلم", "ക്ലീനിംഗ്"]):
        return "CITIZEN-PEN"

    # 5. Explicit media formats if mentioned alongside media/paper/rolls
    if any(m in raw_lower for m in ["media", "paper", "roll", "rolls", "box"]):
        if any(s in raw_lower for s in ["4x6", "4*6", "10x15", "٤×٦", "ms46"]):
            return "CX2-MS46-2PC"
        if any(s in raw_lower for s in ["5x7", "5*7", "127x178", "٥×٧", "ms57"]):
            return "CX2-MS57-2PC"
        if any(s in raw_lower for s in ["6x8", "6*8", "152x203", "٦×٨", "ms68"]):
            return "CX2-MS68-2PC"

    # 6. Never default generic 'printer', 'photo printer', or 'media' to CX-02 (Rule 5)
    return None


def parse_self_correction(text: str) -> Tuple[bool, Optional[str], Optional[Any]]:
    """
    Parses conversational corrections like:
      - 'actually A1' / 'sorry A1 not A0' / 'sorry meant 5x7'
      - 'sorry it's 200' / 'actually 500 prints per day'
      - 'no, photo printer' / 'actually cad plotter'
    """
    lower = text.lower()
    
    # 1. Paper size correction
    size_match = re.search(r"\b(sorry|actually|no|correction|meant)\b.*?\b(a[0-4]|24[\"\s]|36[\"\s]|44[\"\s]|4x6|5x7|6x8|8x10|8x12)\b", lower)
    if size_match:
        raw_sz = size_match.group(2).replace("\"", "").strip()
        size = raw_sz.upper() if raw_sz.lower().startswith("a") else raw_sz.lower()
        return True, "paper_size", size

    # 2. Volume correction
    vol_match = re.search(r"\b(sorry|actually|no|correction|meant)\b.*?\b(\d{1,6})\b.*?(page|print|day|month)?", lower)
    if vol_match:
        num = vol_match.group(2)
        unit = "month" if "month" in lower else "day"
        return True, "volume", f"{num} prints/{unit}"

    # 3. Category / brand correction
    if any(p in lower for p in ["photo printer", "photobooth", "photo booth"]):
        if any(c in lower for c in ["no", "actually", "not cad", "not office", "sorry"]):
            return True, "category", "photo"
    if any(p in lower for p in ["cad", "technical", "plotter", "architectural", "blueprint"]):
        if any(c in lower for c in ["no", "actually", "not photo", "sorry"]):
            return True, "category", "cad_plotter"
    if any(p in lower for p in ["office", "enterprise", "business printer", "workforce"]):
        if any(c in lower for c in ["no", "actually", "not photo", "sorry"]):
            return True, "category", "business_mfp"
    if any(p in lower for p in ["sublimation", "mug", "t shirt", "t-shirt"]):
        if any(c in lower for c in ["no", "actually", "sorry"]):
            return True, "category", "sublimation"

    return False, None, None


def resolve_anaphora_sku(current_text: str, history: List[Dict[str, str]], sales_state: Optional[Any] = None) -> Optional[str]:
    """
    Resolves product references from conversation history or structured sales_state
    when anaphoric pronouns or elliptical phrasing is used.
    """
    lower = current_text.lower()
    is_anaphoric = any(indicator in lower for indicator in ANAPHORA_INDICATORS)

    parsed_qty = parse_quantity(current_text)
    if parsed_qty and not extract_sku_direct(current_text):
        is_anaphoric = True

    if not is_anaphoric:
        return None

    # Check structured sales state first
    if sales_state:
        if sales_state.current_model:
            return sales_state.current_model
        if sales_state.target_sku:
            return sales_state.target_sku

    # Search history backwards for the most recently referenced SKU or model (user or assistant)
    for turn in reversed(history):
        content = turn.get("content", "")
        c_low = content.lower()
        if "cy-02" in c_low or "cy02" in c_low or "cy 02" in c_low:
            return "CY-02"
        if "cz-01" in c_low or "cz01" in c_low or "cz 01" in c_low:
            return "CZ-01"
        if "cx-02w" in c_low or "cx02w" in c_low or "cx 02w" in c_low:
            return "CX-02W"
        if "cx-02" in c_low or "cx02" in c_low or "cx 02" in c_low:
            return "CX-02"
        sku = extract_sku_direct(content)
        if sku:
            return sku

    return None


def read_message(raw_text: str, history: Optional[List[Dict[str, str]]] = None, sales_state: Optional[Any] = None) -> ReadContext:
    """
    Entry point for Cognitive Step 1: READ.
    Normalizes text, detects language, interprets bare numbers / chips, resolves anaphora & self-corrections.
    """
    normalized = normalize_text(raw_text)
    language = detect_language(normalized)
    qty = parse_quantity(normalized)

    # 0. Check phantom models and ambiguous models
    phantom = detect_phantom_model(normalized)
    ambiguous = detect_ambiguous_model(normalized)
    det_brand = normalize_brand(normalized)
    canonical_model, model_brand, model_cat = normalize_model_or_sku(normalized)

    direct_sku = canonical_model if canonical_model else extract_sku_direct(normalized)
    if canonical_model and model_brand:
        det_brand = det_brand or model_brand

    # 1. Check self-correction
    is_corr, corr_slot, corr_val = parse_self_correction(normalized)

    # 2. Check chip & bare-number inheritance from last bot question
    interpreted_ctx = None
    if sales_state and sales_state.last_bot_question:
        norm_clean = normalized.strip().lower()
        if sales_state.last_bot_question == "volume":
            # If user replied with just a number like "100" or "60,000"
            m = re.match(r"^(\d+[\d,]*)\s*(prints?|pages?)?(\s*(per|\/)\s*(day|month))?$", norm_clean)
            if m:
                num = m.group(1).replace(",", "")
                unit = m.group(5) if m.group(5) else "day"
                interpreted_ctx = f"volume: {num} prints per {unit}"
        elif sales_state.last_bot_question == "paper_size":
            if norm_clean in ["a1", "a0", "a2", "a3", "a4", "4x6", "5x7", "6x8", "8x10", "8x12", "24", "36", "44"]:
                interpreted_ctx = f"paper_size: {norm_clean.upper()}"
        elif sales_state.last_bot_question == "function":
            if any(f in norm_clean for f in ["print only", "mfp", "scan", "scanner", "copy"]):
                interpreted_ctx = f"function: {norm_clean}"

    # 3. Anaphora & multi-turn reference resolution
    resolved_sku = direct_sku
    resolved_model = None
    resolved_models = []
    reference_type = None
    is_anaphora = False
    sku_source = "explicit" if direct_sku else None

    norm_low = normalized.lower()

    # Determine current context model from state or recent history
    curr_ctx_model = sales_state.current_model if sales_state else None
    if not curr_ctx_model and history:
        for turn in reversed(history):
            c_low = turn.get("content", "").lower()
            if "cy-02" in c_low or "cy02" in c_low or "cy 02" in c_low:
                curr_ctx_model = "CY-02"
                break
            elif "cz-01" in c_low or "cz01" in c_low or "cz 01" in c_low:
                curr_ctx_model = "CZ-01"
                break
            elif "cx-02w" in c_low or "cx02w" in c_low or "cx 02w" in c_low:
                curr_ctx_model = "CX-02W"
                break
            elif "cx-02" in c_low or "cx02" in c_low or "cx 02" in c_low:
                curr_ctx_model = "CX-02"
                break

    if sales_state:
        # Check specific reference indicators
        if any(w in norm_low for w in ["first one", "the first", "first printer", "first model"]):
            if sales_state.compared_models:
                resolved_model = sales_state.compared_models[0]
                resolved_sku = resolved_model
                is_anaphora = True
                reference_type = "first"
                sku_source = "state"
        elif any(w in norm_low for w in ["second one", "the second", "second printer", "second model"]):
            if len(sales_state.compared_models) > 1:
                resolved_model = sales_state.compared_models[1]
                resolved_sku = resolved_model
                is_anaphora = True
                reference_type = "second"
                sku_source = "state"
        elif any(w in norm_low for w in ["both", "compare them", "which is better", "which one"]):
            if sales_state.compared_models:
                resolved_models = list(sales_state.compared_models)
                is_anaphora = True
                reference_type = "plural"
                sku_source = "state"

    if curr_ctx_model:
        if any(w in norm_low for w in ["its media", "its paper", "its ink", "media for this", "ink for this", "paper for this", "consumables for this"]):
            resolved_model = curr_ctx_model
            is_anaphora = True
            reference_type = "consumables"
            sku_source = "state"
        elif any(w in norm_low for w in ["why this", "why this printer", "why that", "why did you recommend"]):
            resolved_model = curr_ctx_model
            is_anaphora = True
            reference_type = "why"
            sku_source = "state"
        elif any(w in norm_low for w in ["another one", "other option", "different model", "alternative"]):
            reference_type = "alternative"
            is_anaphora = True
            sku_source = "state"
        elif any(w in norm_low for w in ["order this", "buy this", "quote this", "send quote for this"]):
            resolved_model = curr_ctx_model
            resolved_sku = curr_ctx_model
            is_anaphora = True
            reference_type = "quote"
            sku_source = "state"
        elif any(w in norm_low for w in ["how much is it", "is it in stock", "tell me about it", "price for it", "more details on it", "specifications for it"]):
            resolved_model = curr_ctx_model
            resolved_sku = curr_ctx_model
            is_anaphora = True
            reference_type = "single"
            sku_source = "state"


    if not resolved_sku and (history or sales_state):
        context_sku = resolve_anaphora_sku(normalized, history or [], sales_state)
        if context_sku:
            resolved_sku = context_sku
            resolved_model = context_sku
            is_anaphora = True
            reference_type = reference_type or "single"
            sku_source = "state"

    # NOTE: Never default unknown or ambiguous queries to CX-02 (Rule 5).
    # If the user asks general questions without a product, resolved_sku remains None.

    return ReadContext(
        raw_text=raw_text,
        normalized_text=normalized,
        language=language,
        detected_sku=direct_sku,
        resolved_sku=resolved_sku,
        resolved_model=resolved_model,
        resolved_models=resolved_models,
        resolved_qty=qty,
        is_anaphora=is_anaphora,
        reference_type=reference_type,
        is_correction=is_corr,
        correction_slot=corr_slot,
        correction_val=corr_val,
        interpreted_context=interpreted_ctx,
        sku_source=sku_source,
        phantom_model=phantom,
        disambiguation=ambiguous,
        detected_brand=det_brand,
        detected_category=model_cat,
        metadata={
            "char_count": len(raw_text),
            "normalized_char_count": len(normalized)
        }
    )

