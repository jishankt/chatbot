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
    "that", "these", "those", "tell", "about", "give", "please", "know",
    # Arabic stopwords
    "ما", "ماذا", "كم", "هل", "من", "في", "على", "إلى", "عن", "مع", "هذا", "هذه", "التي", "الذي", "هو", "هي", "له", "لها", "أين", "كيف", "سعر", "اسعار"
}

SYNONYMS: Dict[str, Set[str]] = {
    "weight": {"weight", "kg", "lbs", "heavy", "light", "lighter", "weigh", "weighs", "dimensions"},
    "وزن": {"weight", "kg", "lbs", "heavy", "light", "lighter", "weigh", "weighs", "dimensions"},
    "size": {"dimensions", "dimension", "width", "depth", "height", "mm", "inches", "footprint", "volume", "compact", "sizes", "capacity"},
    "مقاس": {"dimensions", "dimension", "width", "depth", "height", "mm", "inches", "footprint", "volume", "compact", "sizes", "capacity", "4x6", "5x7", "6x8"},
    "مقاسات": {"dimensions", "dimension", "width", "depth", "height", "mm", "inches", "footprint", "volume", "compact", "sizes", "capacity", "4x6", "5x7", "6x8"},
    "حجم": {"dimensions", "dimension", "width", "depth", "height", "mm", "inches", "footprint", "volume", "compact"},
    "dimensions": {"dimensions", "dimension", "width", "depth", "height", "mm", "inches", "footprint", "volume"},
    "dimension": {"dimensions", "dimension", "width", "depth", "height", "mm", "inches", "footprint", "volume"},
    "أبعاد": {"dimensions", "dimension", "width", "depth", "height", "mm", "inches", "footprint", "volume"},
    "speed": {"speed", "speeds", "seconds", "second", "sec", "fast", "rate", "time", "long", "how long", "take"},
    "سرعة": {"speed", "speeds", "seconds", "second", "sec", "fast", "rate", "time", "long", "take"},
    "fast": {"speed", "speeds", "seconds", "second", "sec", "fast", "time", "long"},
    "photo": {"speed", "speeds", "seconds", "print", "4x6", "5x7", "6x8", "time"},
    "صور": {"photo", "speed", "print", "4x6", "5x7", "6x8"},
    "طباعة": {"photo", "print", "printing", "speed", "sizes"},
    "long": {"speed", "speeds", "seconds", "second", "time", "take"},
    "take": {"speed", "speeds", "seconds", "time", "long"},
    "resolution": {"resolution", "dpi", "dots", "quality", "sharp", "sharpness", "300", "600", "print engine", "engine"},
    "دقة": {"resolution", "dpi", "dots", "quality", "sharp", "sharpness"},
    "dpi": {"resolution", "dpi", "dots", "300x300", "300x600"},
    "reduce": {"reduces", "reduce", "reducing", "energy", "consumption", "sleep", "saving", "save"},
    "reduces": {"reduces", "reduce", "reducing", "energy", "consumption", "sleep", "saving", "save"},
    "sleep": {"sleep", "mode", "energy", "consumption", "dormant", "standby"},
    "energy": {"energy", "saving", "power", "consumption", "sleep", "watt", "watts"},
    "carry": {"bag", "case", "carrying", "padded", "transit", "protective"},
    "protective": {"bag", "case", "carrying", "padded", "transit", "protective", "overcoat"},
    "shankah": {"bag", "case", "carrying", "padded", "transit", "protective"},
    "waraq": {"paper", "media", "roll", "rolls"},
    "ترجيع": {"ribbon", "rewind", "waste", "save"},
    "الشريط": {"ribbon", "rewind", "ink"},
    "الإنهاء": {"finish", "finishes", "matte", "glossy", "luster", "overcoat"},
    "المطفي": {"finish", "finishes", "matte", "glossy", "luster"},
    "اللامع": {"finish", "finishes", "matte", "glossy", "luster"},
    "السكون": {"sleep", "energy", "power", "consumption"},
    "الطاقة": {"power", "consumption", "watt", "watts", "sleep", "energy"},
    "الكهرباء": {"power", "consumption", "watt", "watts", "sleep", "energy"},
    "التغليف": {"overcoat", "coating", "laminate", "protection"},
    "الأوفركوت": {"overcoat", "protection", "coating", "durable", "water"},
    "أوفركوت": {"overcoat", "protection", "coating", "durable", "water"},
    "الماء": {"water", "overcoat", "protection"},
    "ماء": {"water", "overcoat", "protection"},
    "البهتان": {"fade", "fading", "protection", "overcoat"},
    "بهتان": {"fade", "fading", "protection", "overcoat"},
    "الأمام": {"front", "loading"},
    "صورة": {"photo", "speed", "print", "4x6", "5x7", "6x8"},
    "ثانية": {"second", "seconds", "sec", "speed", "fast"},
    "chassis": {"dimensions", "dimension", "width", "depth", "height"},
    "mm": {"dimensions", "dimension", "mm", "size"},
    "tool": {"dimensions", "dimension", "height", "width"},
    "ard": {"dimensions", "dimension", "width"},
    "usb": {"usb", "connectivity", "interface", "port"},
    "connectivity": {"usb", "connectivity", "interface", "port"},
    "interface": {"usb", "connectivity", "interface", "port"},
    "port": {"usb", "connectivity", "interface", "port"},
    "drop-in": {"loading", "drop-in", "front", "paper"},
    "loading": {"loading", "drop-in", "front", "paper"},
    "cassette": {"ribbon", "cassette", "handling"},
    "handling": {"ribbon", "handling", "paper", "loading"},
    "front": {"front", "loading", "drop-in"},
    "cy-02": {"cy-02", "cy02", "cy"},
    "cz-01": {"cz-01", "cz01", "cz"},
    "cx-02w": {"cx-02w", "cx02w", "cx02-w", "wide"},
    "8x10": {"8x10", "format", "media", "size", "cx-02w"},
    "8x12": {"8x12", "format", "media", "size", "cx-02w"},
    "4x4": {"4x4", "format", "media", "size", "cz-01"},
    "consumables": {"media", "consumables", "paper", "ribbon", "supplies", "rolls"},
    "consumbles": {"media", "consumables", "paper", "ribbon", "supplies", "rolls"},
    "refill": {"media", "roll", "rolls", "capacity", "prints", "kiosk", "cy-02"},
    "kiosk": {"kiosk", "kiosks", "retail", "capacity", "cy-02"},
    "mall": {"kiosk", "retail", "cy-02"},
    "framed": {"format", "photo", "prints", "8x10", "8x12", "cx-02w", "wide"},
    "bigger": {"format", "photo", "prints", "8x10", "8x12", "cx-02w", "wide"},
    "big": {"format", "photo", "prints", "8x10", "8x12", "cx-02w", "wide"},
    "media": {"media", "paper", "roll", "rolls", "box", "prints", "print", "sheet", "sheets", "capacity", "yield"},
    "ورق": {"media", "paper", "roll", "rolls", "box", "prints", "print", "sheet", "sheets", "capacity", "yield"},
    "وسائط": {"media", "paper", "roll", "rolls", "box", "prints", "print"},
    "paper": {"media", "paper", "roll", "rolls", "box", "prints", "print"},
    "roll": {"media", "paper", "roll", "rolls", "box", "capacity", "yield"},
    "رول": {"media", "paper", "roll", "rolls", "box", "capacity", "yield"},
    "yield": {"yield", "capacity", "prints", "roll", "rolls", "box", "400", "230", "200", "180", "800", "460"},
    "capacity": {"yield", "capacity", "prints", "roll", "rolls", "box", "400", "230", "200", "180"},
    "سعة": {"yield", "capacity", "prints", "roll", "rolls", "box", "400", "230", "200", "180", "800", "460"},
    "ribbon": {"ribbon", "rewind", "ink", "ribbon-save", "waste", "cassette"},
    "شريط": {"ribbon", "rewind", "ink", "ribbon-save", "waste", "cassette"},
    "ريبان": {"ribbon", "rewind", "ink", "ribbon-save", "waste", "cassette"},
    "حبر": {"ribbon", "rewind", "ink", "dye"},
    "rewind": {"ribbon", "rewind", "ribbon-save", "waste"},
    "توفير": {"ribbon", "rewind", "ribbon-save", "waste", "sleep", "energy"},
    "finish": {"finish", "finishes", "matte", "glossy", "luster", "overcoat", "surface"},
    "إنهاء": {"finish", "finishes", "matte", "glossy", "luster", "overcoat", "surface"},
    "matte": {"finish", "finishes", "matte", "glossy", "luster", "overcoat"},
    "مطفي": {"finish", "finishes", "matte", "glossy", "luster", "overcoat"},
    "glossy": {"finish", "finishes", "matte", "glossy", "luster", "overcoat"},
    "لامع": {"finish", "finishes", "matte", "glossy", "luster", "overcoat"},
    "luster": {"finish", "finishes", "matte", "glossy", "luster", "fine matte"},
    "driver": {"driver", "drivers", "windows", "mac", "macos", "linux", "cups", "os", "software"},
    "تعريف": {"driver", "drivers", "windows", "mac", "macos", "linux", "os"},
    "تعريفات": {"driver", "drivers", "windows", "mac", "macos", "linux", "os"},
    "drivers": {"driver", "drivers", "windows", "mac", "macos", "linux", "cups", "os", "software"},
    "os": {"driver", "drivers", "windows", "mac", "macos", "linux", "cups", "os"},
    "نظام": {"driver", "drivers", "windows", "mac", "macos", "linux", "cups", "os", "operating", "system"},
    "طابعة": {"printer", "photo", "print", "citizen", "cx-02"},
    "windows": {"driver", "drivers", "windows", "os"},
    "ويندوز": {"driver", "drivers", "windows", "os"},
    "mac": {"driver", "drivers", "mac", "macos", "os", "cups"},
    "ماك": {"driver", "drivers", "mac", "macos", "os", "cups"},
    "macos": {"driver", "drivers", "mac", "macos", "os", "cups"},
    "linux": {"driver", "drivers", "linux", "cups", "os"},
    "لينكس": {"driver", "drivers", "linux", "cups", "os"},
    "cups": {"driver", "drivers", "linux", "cups", "os"},
    "power": {"power", "consumption", "watt", "watts", "sleep", "standby", "voltage", "ac", "energy"},
    "طاقة": {"power", "consumption", "watt", "watts", "sleep", "standby", "energy"},
    "كهرباء": {"power", "consumption", "watt", "watts", "sleep", "standby", "energy"},
    "consumption": {"power", "consumption", "watt", "watts", "sleep", "standby", "energy"},
    "wattage": {"power", "consumption", "watt", "watts", "sleep", "standby", "energy"},
    "cleaning": {"cleaning", "pen", "printhead", "head", "streak", "clean", "maintenance"},
    "تنظيف": {"cleaning", "pen", "printhead", "head", "streak", "clean", "maintenance"},
    "pen": {"cleaning", "pen", "printhead", "head", "maintenance"},
    "قلم": {"cleaning", "pen", "printhead", "head", "maintenance"},
    "maintenance": {"cleaning", "pen", "printhead", "head", "maintenance", "service"},
    "صيانة": {"cleaning", "pen", "printhead", "head", "maintenance", "service", "repair"},
    "bag": {"bag", "case", "carrying", "padded", "transit", "protective"},
    "حقيبة": {"bag", "case", "carrying", "padded", "transit", "protective"},
    "شنطة": {"bag", "case", "carrying", "padded", "transit", "protective"},
    "case": {"bag", "case", "carrying", "padded", "transit", "protective"},
    "strip": {"strip", "strips", "dual cut", "cut", "booth", "2x6"},
    "strips": {"strip", "strips", "dual cut", "cut", "booth", "2x6"},
    "photobooth": {"photobooth", "booth", "kiosk", "enclosure", "mirror"},
    "booth": {"photobooth", "booth", "kiosk", "enclosure", "mirror"},
    "كشك": {"photobooth", "booth", "kiosk", "retail"},
    "بوث": {"photobooth", "booth", "kiosk"},
    "warranty": {"warranty", "guarantee", "service", "coverage", "printhead", "years", "2-year"},
    "ضمان": {"warranty", "guarantee", "service", "coverage", "printhead", "years", "2-year"},
    "كفالة": {"warranty", "guarantee", "service", "coverage", "printhead", "years"},
    "guaranteed": {"warranty", "guarantee", "service", "coverage", "printhead", "100000", "years"},
    "accidental": {"damage", "accidental", "spills", "drops", "liquid", "warranty"},
    "drops": {"damage", "accidental", "spills", "drops", "liquid", "warranty"},
    "spills": {"damage", "accidental", "spills", "drops", "liquid", "warranty"},
    "سكون": {"sleep", "energy", "power", "consumption"},
    "استهلاك": {"consumption", "energy", "power", "watt"},
    "ملحقات": {"accessories", "accessory", "pen", "bag"},
    "إكسسوارات": {"accessories", "accessory", "pen", "bag"},
    "قص": {"cut", "strips", "strip", "dual", "2x6"},
    "شرائط": {"strips", "strip", "2x6", "cut"},
    "تسامي": {"sublimation", "dye", "dye-sublimation", "thermal"},
    "تغليف": {"overcoat", "coating", "laminate", "protection"},
    "منفذ": {"usb", "connectivity", "interface", "port"},
    "تحميل": {"loading", "drop-in", "front", "paper"},
    "امام": {"front", "loading"},
    "حماية": {"protective", "protection", "overcoat", "bag"},
    "نقل": {"transit", "carrying", "bag", "case"},
    "حراري": {"thermal", "heat", "dye", "sublimation"},
    # Arabic Showroom, Hours, Delivery, Platform
    "ساعات": {"hours", "working", "operating", "time"},
    "عمل": {"hours", "working", "operating", "business"},
    "معرض": {"showroom", "office", "store", "khalid bin waleed", "dubai"},
    "شارع": {"road", "street", "khalid", "bin", "waleed"},
    "خالد": {"khalid", "bin", "waleed", "showroom", "dubai"},
    "الوليد": {"khalid", "bin", "waleed", "showroom", "dubai"},
    "تجربة": {"demo", "demonstration", "live", "showroom"},
    "الشراء": {"buy", "purchase", "order", "price"},
    "أبوظبي": {"delivery", "shipping", "abu dhabi", "uae"},
    "الشارقة": {"delivery", "shipping", "sharjah", "uae"},
    "التوصيل": {"delivery", "shipping", "courier", "uae"},
    "توصيل": {"delivery", "shipping", "courier", "uae"},
    "الحفلات": {"events", "photobooth", "booth", "kiosk"},
    "الفوتوبوث": {"photobooth", "booth", "kiosk", "dual-cut", "strips"},
    # Malayalam Synonyms
    "ഫോട്ടോ": {"photo", "speed", "print", "4x6", "5x7", "6x8"},
    "പ്രിന്റ്": {"print", "photo", "speed", "seconds", "printing"},
    "പ്രിന്റർ": {"printer", "photo", "print", "citizen", "cx-02"},
    "പ്രിന്ററിന്റെ": {"printer", "photo", "print", "citizen", "cx-02"},
    "സ്പീഡ്": {"speed", "speeds", "seconds", "second", "sec", "fast", "time"},
    "ഭാരം": {"weight", "kg", "lbs", "heavy", "weigh", "weighs", "dimensions"},
    "ഭാരവും": {"weight", "kg", "lbs", "heavy", "weigh", "weighs", "dimensions"},
    "വലിപ്പം": {"dimensions", "dimension", "width", "depth", "height", "mm", "size"},
    "വലിപ്പവും": {"dimensions", "dimension", "width", "depth", "height", "mm", "size"},
    "ഫോട്ടോബൂത്ത്": {"photobooth", "booth", "kiosk", "dual-cut", "strips", "events"},
    "ക്ലീനിംഗ്": {"cleaning", "pen", "printhead", "head", "maintenance"},
    "പ്രിന്റ്ഹെഡ്": {"cleaning", "pen", "printhead", "head", "maintenance"},
    "പെൻ": {"cleaning", "pen", "printhead", "head"},
    "വാറന്റി": {"warranty", "guarantee", "service", "coverage", "2-year"},
    "ലഭ്യമാണോ": {"stock", "available", "citizen", "cx-02", "pen", "cleaning"},
    "ലഭിക്കുമോ": {"warranty", "guarantee", "service", "coverage"},
    "ദുബായിൽ": {"dubai", "uae", "warranty", "showroom"},
    "സമയം": {"speed", "time", "seconds", "second", "fast"}
}


def extract_keywords(text: str) -> List[str]:
    # Normalize dimension separators (e.g., 4×6 -> 4x6) and special dashes
    norm = text.lower().replace("×", "x").replace("✕", "x").replace("✖", "x").replace("–", "-").replace("—", "-")
    # First extract dimension tokens like 4x6, 5x7, 6x8, 300x600 as atomic units
    dim_tokens = re.findall(r"\d+x\d+", norm)
    # Remove dimension substrings to avoid double-counting
    norm_no_dims = re.sub(r"\d+x\d+", " ", norm)
    # Standard tokens: Unicode-safe non-whitespace token extraction (preserves Malayalam & Arabic combining marks)
    raw_tokens = re.findall(r'[^\s.,?!:;()\"\'/\\\u061F\-]+', norm_no_dims)
    filtered = [
        t for t in raw_tokens
        if t not in STOPWORDS and (len(t) > 1 or t.isdigit())
    ]
    seen = set()
    res = []
    for t in dim_tokens + filtered:
        if t not in seen:
            seen.add(t)
            res.append(t)
        if t.startswith("ال") and len(t) > 3:
            stemmed = t[2:]
            if stemmed not in seen:
                seen.add(stemmed)
                res.append(stemmed)
        if (t.startswith("و") or t.startswith("ل")) and len(t) > 3:
            stemmed = t[1:]
            if stemmed not in seen:
                seen.add(stemmed)
                res.append(stemmed)
            if stemmed.startswith("ال") and len(stemmed) > 3:
                s2 = stemmed[2:]
                if s2 not in seen:
                    seen.add(s2)
                    res.append(s2)
    return res


def calculate_word_coverage(query: str, chunk_text: str) -> float:
    query_words = extract_keywords(query)
    if not query_words:
        return 1.0

    chunk_words = set(re.findall(r'[^\s.,?!:;()\"\'/\\-]+', chunk_text.lower()))

    matched_count = 0
    for q_word in query_words:
        if q_word in chunk_words:
            matched_count += 1
            continue

        syns = SYNONYMS.get(q_word, set())
        if not syns and q_word.startswith("ال") and len(q_word) > 3:
            syns = SYNONYMS.get(q_word[2:], set())

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
