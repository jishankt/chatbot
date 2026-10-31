import re
from typing import Any, Optional, Tuple, List, Dict
import yaml
from pathlib import Path
from app.config import Config, BASE_DIR

ARABIC_INDIC_DIGITS = {
    '٠': '0', '١': '1', '٢': '2', '٣': '3', '٤': '4',
    '٥': '5', '٦': '6', '٧': '7', '٨': '8', '٩': '9'
}


def normalize_digits(text: str) -> str:
    """Translates Eastern Arabic-Indic digits to ASCII standard digits."""
    for ar, en in ARABIC_INDIC_DIGITS.items():
        text = text.replace(ar, en)
    return text


def parse_quantity(val_or_text: Any) -> Optional[int]:
    """
    Parses integer quantity from string, float, int, or user query text.
    Handles:
      - Integers / floats: 5 -> 5
      - Comma strings: "5,000" -> 5000
      - Metric suffixes: "1k" -> 1000, "2.5k" -> 2500, "10k" -> 10000
      - Eastern Arabic digits: "٣" -> 3, "١,٠٠٠" -> 1000
      - Text patterns: "quote for 5 units" -> 5
    """
    if val_or_text is None:
        return None

    if isinstance(val_or_text, int):
        return val_or_text

    if isinstance(val_or_text, float):
        return int(val_or_text)

    s = normalize_digits(str(val_or_text).strip().lower())

    # Check for metric suffix like "1k", "2.5k", "10k"
    k_match = re.search(r"\b(\d+(?:\.\d+)?)\s*k\b", s)
    if k_match:
        try:
            return int(float(k_match.group(1)) * 1000)
        except ValueError:
            pass

    # Clean commas in numbers like "5,000"
    s_clean = re.sub(r"(\d+),(\d+)", r"\1\2", s)

    # If the input string is solely an integer
    if s_clean.isdigit():
        return int(s_clean)

    # For full sentence queries, strip out model numbers, dimensions, and specs
    # so they are never misparsed as purchase quantities
    s_stripped = s_clean
    s_stripped = re.sub(r"\bcx[- ]*0?2\b", "", s_stripped)
    s_stripped = re.sub(r"\b\d+\s*(?:x|\*|×)\s*\d+\b", "", s_stripped)  # e.g. 4x6, 5x7, 6x8, 6x9
    s_stripped = re.sub(r"\b\d+\s*(?:dpi|watts?|watt|kg|mm|cm|seconds?|sec|s)\b", "", s_stripped)
    s_stripped = re.sub(r"\+?\d{7,15}\b", "", s_stripped)  # phone numbers
    s_stripped = re.sub(r"(?:aed|dirhams?)\s*\d+(?:\.\d+)?\b", "", s_stripped)  # prices

    # 1. Look for explicit quantity patterns with units
    unit_m = re.search(r"\b(\d+)\s*(?:units?|printers?|boxes?|rolls?|sets?|pieces?|pcs?|items?|pack|cartons?)\b", s_stripped)
    if unit_m:
        return int(unit_m.group(1))

    # 2. Look for quantity after intent verbs
    action_m = re.search(r"(?:quote\s+for|price\s+for|how\s+much\s+for|need|want|order|send|buy|give\s+me|quote\s+me)\s+(\d+)\b", s_stripped)
    if action_m:
        return int(action_m.group(1))

    # 3. Look for "X of them / of it"
    of_them_m = re.search(r"\b(\d+)\s*(?:of\s+them|of\s+it|of\s+these|of\s+those)\b", s_stripped)
    if of_them_m:
        return int(of_them_m.group(1))

    # 4. Look for "for X"
    for_m = re.search(r"\bfor\s+(\d+)\b", s_stripped)
    if for_m:
        return int(for_m.group(1))

    # 5. Look for standalone positive integers (excluding leading zeros like 02)
    standalone = re.findall(r"\b([1-9]\d*)\b", s_stripped)
    if len(standalone) == 1:
        return int(standalone[0])

    return None


def get_large_quantity_threshold() -> int:
    """Loads large_quantity_handoff_threshold from config/scope.yaml (default: 10)."""
    scope_path = BASE_DIR / "config" / "scope.yaml"
    if scope_path.exists():
        try:
            with open(scope_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                return int(data.get("large_quantity_handoff_threshold", 10))
        except Exception:
            pass
    return 10


def parse_multi_item_quantities(text: str) -> Optional[List[Dict[str, Any]]]:
    """
    Parses multiple items and their respective quantities from text, e.g.:
      "Quote me 2 CX-02 printers and 4 boxes of 4x6 media"
      "1 printer and 2 bags"
    Returns a list of dicts: [{"sku": "<SKU>", "qty": int}, ...] or None if not multi-item.
    """
    norm = normalize_digits(text.lower())
    norm = norm.replace("×", "x").replace("*", "x")

    items = []

    # 1. Printer quantity
    printer_patterns = [
        r"\b(\d+)\s*(?:x\s*)?(?:citizen\s*)?(?:cx[- ]*0?2\s*)?(?:photo\s*)?printers?\b",
        r"\b(\d+)\s*(?:x\s*)?(?:units?|machines?)\b",
        r"(?:quote\s+me|need|want|buy|order)\s+(\d+)\s*(?:citizen\s*)?(?:cx[- ]*0?2|printer)",
        r"(?:cx[- ]*0?2|citizen\s*printer)\s*x?\s*(\d+)\b"
    ]
    printer_qty = None
    for pat in printer_patterns:
        m = re.search(pat, norm)
        if m:
            val = int(m.group(1))
            if val != 2 or ("cx" not in m.group(0) or re.search(r"\b2\s+(?:cx|printer)", norm)):
                printer_qty = val
                break

    if printer_qty is None and any(p in norm for p in ["cx-02", "cx02", "printer", "unit"]) and ("quote" in norm or "quotation" in norm):
        printer_qty = 1

    # 2. Media sets
    media_defs = [
        ("CX2-MS46-2PC", [r"\b(\d+)\s*(?:boxes?|rolls?|sets?|packs?|cartons?|x)?\s*(?:of\s+)?(?:4x6|10x15|ms46)\b", r"\b(?:4x6|10x15|ms46)[^\d]*(\d+)\s*(?:boxes?|rolls?|sets?)?\b"]),
        ("CX2-MS57-2PC", [r"\b(\d+)\s*(?:boxes?|rolls?|sets?|packs?|cartons?|x)?\s*(?:of\s+)?(?:5x7|127x178|ms57)\b", r"\b(?:5x7|127x178|ms57)[^\d]*(\d+)\s*(?:boxes?|rolls?|sets?)?\b"]),
        ("CX2-MS68-2PC", [r"\b(\d+)\s*(?:boxes?|rolls?|sets?|packs?|cartons?|x)?\s*(?:of\s+)?(?:6x8|152x203|ms68)\b", r"\b(?:6x8|152x203|ms68)[^\d]*(\d+)\s*(?:boxes?|rolls?|sets?)?\b"]),
    ]

    found_media = False
    for sku, patterns in media_defs:
        for pat in patterns:
            m = re.search(pat, norm)
            if m:
                qty = int(m.group(1))
                items.append({"sku": sku, "qty": qty})
                found_media = True
                break

    if not found_media and any(m in norm for m in ["media", "paper", "rolls", "consumables"]):
        m_generic = re.search(r"\b(\d+)\s*(?:boxes?|rolls?|sets?|packs?|cartons?|x)?\s*(?:of\s+)?(?:media|paper|rolls|consumables)\b", norm)
        if m_generic:
            items.append({"sku": "CX2-MS46-2PC", "qty": int(m_generic.group(1))})
            found_media = True

    # 3. Accessories: Carry Bag and Cleaning Pen
    bag_m = re.search(r"\b(\d+)\s*(?:x\s*)?(?:carry\s*)?bags?\b", norm)
    if bag_m:
        items.append({"sku": "CX-02-BAG", "qty": int(bag_m.group(1))})
    elif "bag" in norm and any(m in norm for m in ["and", "with", "+"]):
        items.append({"sku": "CX-02-BAG", "qty": 1})

    pen_m = re.search(r"\b(\d+)\s*(?:x\s*)?(?:cleaning\s*)?pens?\b", norm)
    if pen_m:
        items.append({"sku": "CITIZEN-PEN", "qty": int(pen_m.group(1))})
    elif "pen" in norm and any(m in norm for m in ["and", "with", "+"]):
        items.append({"sku": "CITIZEN-PEN", "qty": 1})

    if printer_qty is not None and (found_media or len(items) > 0 or ("printer" in norm and any(m in norm for m in ["media", "paper", "bag", "pen"]))):
        items.insert(0, {"sku": "CX-02", "qty": printer_qty})

    return items if len(items) >= 2 else None
