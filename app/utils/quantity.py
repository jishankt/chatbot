import re
from typing import Any, Optional, Tuple
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
