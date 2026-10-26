import re
from typing import Set, Dict, List

STOPWORDS = {
    "a", "an", "the", "in", "on", "at", "to", "for", "of", "with", "by", "from",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "can", "could", "will", "would", "shall", "should",
    "what", "which", "who", "when", "where", "why", "how", "all", "any",
    "both", "each", "few", "more", "most", "other", "some", "such", "no", "nor",
    "not", "only", "own", "same", "so", "than", "too", "very", "i", "me", "my",
    "you", "your", "we", "our", "it", "its", "they", "them", "their", "this",
    "that", "these", "those", "tell", "about", "give", "please", "know"
}

SYNONYMS: Dict[str, Set[str]] = {
    "weight": {"weight", "kg", "lbs", "heavy", "light", "lighter", "weigh", "weighs", "dimensions"},
    "size": {"dimensions", "dimension", "width", "depth", "height", "mm", "inches", "footprint", "volume", "compact", "sizes", "capacity"},
    "dimensions": {"dimensions", "dimension", "width", "depth", "height", "mm", "inches", "footprint", "volume"},
    "dimension": {"dimensions", "dimension", "width", "depth", "height", "mm", "inches", "footprint", "volume"},
    "speed": {"speed", "speeds", "seconds", "second", "sec", "fast", "rate", "time", "long", "how long", "take"},
    "fast": {"speed", "speeds", "seconds", "second", "sec", "fast", "time", "long"},
    "photo": {"speed", "speeds", "seconds", "print", "4x6", "5x7", "6x8", "time"},
    "long": {"speed", "speeds", "seconds", "second", "time", "take"},
    "take": {"speed", "speeds", "seconds", "time", "long"},
    "resolution": {"resolution", "dpi", "dots", "quality", "sharp", "sharpness"},
    "dpi": {"resolution", "dpi", "dots", "300x300", "300x600"},
    "media": {"media", "paper", "roll", "rolls", "box", "prints", "print", "sheet", "sheets", "capacity", "yield"},
    "paper": {"media", "paper", "roll", "rolls", "box", "prints", "print"},
    "roll": {"media", "paper", "roll", "rolls", "box", "capacity", "yield"},
    "yield": {"yield", "capacity", "prints", "roll", "rolls", "box", "400", "230", "200", "180", "800", "460"},
    "capacity": {"yield", "capacity", "prints", "roll", "rolls", "box", "400", "230", "200", "180"},
    "ribbon": {"ribbon", "rewind", "ink", "ribbon-save", "waste", "cassette"},
    "rewind": {"ribbon", "rewind", "ribbon-save", "waste"},
    "finish": {"finish", "finishes", "matte", "glossy", "luster", "overcoat", "surface"},
    "matte": {"finish", "finishes", "matte", "glossy", "luster", "overcoat"},
    "glossy": {"finish", "finishes", "matte", "glossy", "luster", "overcoat"},
    "luster": {"finish", "finishes", "matte", "glossy", "luster", "fine matte"},
    "driver": {"driver", "drivers", "windows", "mac", "macos", "linux", "cups", "os", "software"},
    "drivers": {"driver", "drivers", "windows", "mac", "macos", "linux", "cups", "os", "software"},
    "os": {"driver", "drivers", "windows", "mac", "macos", "linux", "cups", "os"},
    "windows": {"driver", "drivers", "windows", "os"},
    "mac": {"driver", "drivers", "mac", "macos", "os", "cups"},
    "macos": {"driver", "drivers", "mac", "macos", "os", "cups"},
    "linux": {"driver", "drivers", "linux", "cups", "os"},
    "cups": {"driver", "drivers", "linux", "cups", "os"},
    "power": {"power", "consumption", "watt", "watts", "sleep", "standby", "voltage", "ac", "energy"},
    "consumption": {"power", "consumption", "watt", "watts", "sleep", "standby", "energy"},
    "wattage": {"power", "consumption", "watt", "watts", "sleep", "standby", "energy"},
    "cleaning": {"cleaning", "pen", "printhead", "head", "streak", "clean", "maintenance"},
    "pen": {"cleaning", "pen", "printhead", "head", "maintenance"},
    "maintenance": {"cleaning", "pen", "printhead", "head", "maintenance", "service"},
    "bag": {"bag", "case", "carrying", "padded", "transit", "protective"},
    "case": {"bag", "case", "carrying", "padded", "transit", "protective"},
    "strip": {"strip", "strips", "dual cut", "cut", "booth", "2x6"},
    "strips": {"strip", "strips", "dual cut", "cut", "booth", "2x6"},
    "photobooth": {"photobooth", "booth", "kiosk", "enclosure", "mirror"},
    "booth": {"photobooth", "booth", "kiosk", "enclosure", "mirror"},
    "warranty": {"warranty", "guarantee", "service", "coverage", "printhead", "years", "2-year"},
    "guaranteed": {"warranty", "guarantee", "service", "coverage", "printhead", "100000", "years"},
    "accidental": {"damage", "accidental", "spills", "drops", "liquid", "warranty"},
    "drops": {"damage", "accidental", "spills", "drops", "liquid", "warranty"},
    "spills": {"damage", "accidental", "spills", "drops", "liquid", "warranty"}
}


def extract_keywords(text: str) -> List[str]:
    # First extract dimension tokens like 4x6, 5x7, 6x8, 300x600 as atomic units
    norm = text.lower()
    dim_tokens = re.findall(r"\d+x\d+", norm)
    # Remove dimension substrings to avoid double-counting
    norm_no_dims = re.sub(r"\d+x\d+", " ", norm)
    # Standard alphanumeric tokens (keep 2+ char; also keep 2-digit+ pure numbers)
    raw_tokens = re.findall(r"[a-z0-9]+", norm_no_dims)
    filtered = [
        t for t in raw_tokens
        if t not in STOPWORDS and (len(t) > 1 or t.isdigit())
    ]
    return dim_tokens + filtered


def calculate_word_coverage(query: str, chunk_text: str) -> float:
    query_words = extract_keywords(query)
    if not query_words:
        return 1.0

    chunk_words = set(re.findall(r"[a-z0-9]+", chunk_text.lower()))

    matched_count = 0
    for q_word in query_words:
        if q_word in chunk_words:
            matched_count += 1
            continue

        syns = SYNONYMS.get(q_word, set())
        if any(s in chunk_words for s in syns):
            matched_count += 1
            continue

        if any(q_word in cw or cw in q_word for cw in chunk_words if len(cw) > 3):
            matched_count += 1
            continue

    return matched_count / len(query_words)


def passes_relevance_gate(query: str, chunk_text: str, score: float, score_threshold: float = 0.05, min_coverage: float = 0.25) -> bool:
    if score < score_threshold:
        return False

    coverage = calculate_word_coverage(query, chunk_text)
    return coverage >= min_coverage
