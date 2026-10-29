"""
app/cognitive/normalizer.py
Model/SKU normalizer, alias table, phantom-model detector, and disambiguation.

Key Functions:
- normalize_brand: Maps typos/aliases ('citizon', 'epsonn') to canonical brand names.
- normalize_model_or_sku: Maps common abbreviations ('f100', 'emc800', 'cx02', 'c13t49n400') to canonical models.
- detect_phantom_model: Catches non-existent models ('CX-02S', 'SC-P9999', 'WF-C55890') and suggests real equivalents without silent substitution.
- detect_ambiguous_model: Detects ambiguous references (e.g. 'P8500') and triggers 1-question disambiguation.
"""

import re
from typing import Optional, Dict, Any, Tuple, List

# Canonical Brand Aliases
BRAND_ALIASES: Dict[str, str] = {
    "citizen": "Citizen",
    "citizon": "Citizen",
    "citzen": "Citizen",
    "citizn": "Citizen",
    "سيتيزن": "Citizen",
    "سيتيزين": "Citizen",
    "സിറ്റിസൺ": "Citizen",
    "epson": "Epson",
    "epsonn": "Epson",
    "eposn": "Epson",
    "ebson": "Epson",
    "ابسون": "Epson",
    "إبسون": "Epson",
    "എപ്സൺ": "Epson",
}

# Canonical Model / SKU Aliases
# Format: lowercase normalized key -> (canonical_sku_or_model, brand, category)
MODEL_ALIASES: Dict[str, Tuple[str, str, str]] = {
    # Citizen Photo Printers
    "cx-02": ("CX-02", "Citizen", "photo"),
    "cx02": ("CX-02", "Citizen", "photo"),
    "cx 02": ("CX-02", "Citizen", "photo"),
    "cx-02w": ("CX-02W", "Citizen", "photo"),
    "cx02w": ("CX-02W", "Citizen", "photo"),
    "cx 02w": ("CX-02W", "Citizen", "photo"),
    "cx-02 wide": ("CX-02W", "Citizen", "photo"),
    "cx02 wide": ("CX-02W", "Citizen", "photo"),
    "cy-02": ("CY-02", "Citizen", "photo"),
    "cy02": ("CY-02", "Citizen", "photo"),
    "cy 02": ("CY-02", "Citizen", "photo"),
    "cz-01": ("CZ-01", "Citizen", "photo"),
    "cz01": ("CZ-01", "Citizen", "photo"),
    "cz 01": ("CZ-01", "Citizen", "photo"),
    
    # Citizen Official Media Sets & Accessories
    "cx2-ms46-2pc": ("CX2-MS46-2PC", "Citizen", "media"),
    "cx2-ms46": ("CX2-MS46-2PC", "Citizen", "media"),
    "ms46": ("CX2-MS46-2PC", "Citizen", "media"),
    "cx2-ms57-2pc": ("CX2-MS57-2PC", "Citizen", "media"),
    "cx2-ms57": ("CX2-MS57-2PC", "Citizen", "media"),
    "ms57": ("CX2-MS57-2PC", "Citizen", "media"),
    "cx2-ms68-2pc": ("CX2-MS68-2PC", "Citizen", "media"),
    "cx2-ms68": ("CX2-MS68-2PC", "Citizen", "media"),
    "ms68": ("CX2-MS68-2PC", "Citizen", "media"),
    "cx2w 812": ("CX2W 812", "Citizen", "media"),
    "cx2w812": ("CX2W 812", "Citizen", "media"),
    "cx-02-bag": ("CX-02-BAG", "Citizen", "accessory"),
    "cx02-bag": ("CX-02-BAG", "Citizen", "accessory"),
    "cx02 bag": ("CX-02-BAG", "Citizen", "accessory"),
    "carry bag": ("CX-02-BAG", "Citizen", "accessory"),
    "citizen-pen": ("CITIZEN-PEN", "Citizen", "accessory"),
    "cleaning pen": ("CITIZEN-PEN", "Citizen", "accessory"),
    "printhead pen": ("CITIZEN-PEN", "Citizen", "accessory"),
    "cy-ms46": ("CY-MS46", "Citizen", "media"),
    "cyms46": ("CY-MS46", "Citizen", "media"),
    "cy-ms57": ("CY-MS57", "Citizen", "media"),
    "cyms57": ("CY-MS57", "Citizen", "media"),
    "cy-ms68": ("CY-MS68", "Citizen", "media"),
    "cyms68": ("CY-MS68", "Citizen", "media"),
    "cz-ms46": ("CZ-MS46", "Citizen", "media"),
    "czms46": ("CZ-MS46", "Citizen", "media"),

    # Epson CAD / Technical Plotters (SureColor T-Series)
    "sc-t3100": ("SC-T3100", "Epson", "cad_plotter"),
    "sct3100": ("SC-T3100", "Epson", "cad_plotter"),
    "t3100": ("SC-T3100", "Epson", "cad_plotter"),
    "t3100n": ("SC-T3100", "Epson", "cad_plotter"),
    "sc-t3100x": ("SC-T3100X", "Epson", "cad_plotter"),
    "sct3100x": ("SC-T3100X", "Epson", "cad_plotter"),
    "t3100x": ("SC-T3100X", "Epson", "cad_plotter"),
    "sc-t5100": ("SC-T5100", "Epson", "cad_plotter"),
    "sct5100": ("SC-T5100", "Epson", "cad_plotter"),
    "t5100": ("SC-T5100", "Epson", "cad_plotter"),
    "t5100n": ("SC-T5100", "Epson", "cad_plotter"),
    "sc-t7700d": ("SC-T7700D", "Epson", "cad_plotter"),
    "sct7700d": ("SC-T7700D", "Epson", "cad_plotter"),
    "t7700d": ("SC-T7700D", "Epson", "cad_plotter"),
    "sc-t7700": ("SC-T7700D", "Epson", "cad_plotter"),
    "t7700": ("SC-T7700D", "Epson", "cad_plotter"),

    # Epson Photo / Fine Art (SureColor P-Series)
    "sc-p700": ("SC-P700", "Epson", "photo"),
    "scp700": ("SC-P700", "Epson", "photo"),
    "p700": ("SC-P700", "Epson", "photo"),
    "sc-p900": ("SC-P900", "Epson", "photo"),
    "scp900": ("SC-P900", "Epson", "photo"),
    "p900": ("SC-P900", "Epson", "photo"),
    "sc-p9500": ("SC-P9500", "Epson", "photo"),
    "scp9500": ("SC-P9500", "Epson", "photo"),
    "p9500": ("SC-P9500", "Epson", "photo"),
    "sc-p8500d": ("SC-P8500D", "Epson", "photo"),
    "scp8500d": ("SC-P8500D", "Epson", "photo"),
    "p8500d": ("SC-P8500D", "Epson", "photo"),
    "sc-p8500dm": ("SC-P8500DM", "Epson", "photo"),
    "scp8500dm": ("SC-P8500DM", "Epson", "photo"),
    "p8500dm": ("SC-P8500DM", "Epson", "photo"),

    # Epson Dye Sublimation (SureColor F-Series)
    "sc-f100": ("SC-F100", "Epson", "sublimation"),
    "scf100": ("SC-F100", "Epson", "sublimation"),
    "f100": ("SC-F100", "Epson", "sublimation"),
    "sc-f500": ("SC-F500", "Epson", "sublimation"),
    "scf500": ("SC-F500", "Epson", "sublimation"),
    "f500": ("SC-F500", "Epson", "sublimation"),

    # Epson Business & Office MFP / WorkForce
    "wf-c5890": ("WF-C5890", "Epson", "business_mfp"),
    "wfc5890": ("WF-C5890", "Epson", "business_mfp"),
    "c5890": ("WF-C5890", "Epson", "business_mfp"),
    "wf-c5890-dwf": ("WF-C5890", "Epson", "business_mfp"),
    "em-c800": ("EM-C800", "Epson", "business_mfp"),
    "emc800": ("EM-C800", "Epson", "business_mfp"),
    "c800": ("EM-C800", "Epson", "business_mfp"),
    "am-c400": ("AM-C4000", "Epson", "business_mfp"),
    "amc400": ("AM-C4000", "Epson", "business_mfp"),
    "am-c4000": ("AM-C4000", "Epson", "business_mfp"),
    "amc4000": ("AM-C4000", "Epson", "business_mfp"),
    "c4000": ("AM-C4000", "Epson", "business_mfp"),
    "am-c550": ("AM-C5000", "Epson", "business_mfp"),
    "amc550": ("AM-C5000", "Epson", "business_mfp"),
    "am-c5000": ("AM-C5000", "Epson", "business_mfp"),
    "amc5000": ("AM-C5000", "Epson", "business_mfp"),
    "c5000": ("AM-C5000", "Epson", "business_mfp"),
    "am-c6000": ("AM-C6000", "Epson", "business_mfp"),
    "amc6000": ("AM-C6000", "Epson", "business_mfp"),
    "c6000": ("AM-C6000", "Epson", "business_mfp"),

    # Epson Document Scanners
    "ds-530ii": ("DS-530II", "Epson", "scanner"),
    "ds530ii": ("DS-530II", "Epson", "scanner"),
    "ds-530": ("DS-530II", "Epson", "scanner"),
    "ds530": ("DS-530II", "Epson", "scanner"),
    "ds-770ii": ("DS-770II", "Epson", "scanner"),
    "ds770ii": ("DS-770II", "Epson", "scanner"),
    "ds-770": ("DS-770II", "Epson", "scanner"),
    "ds770": ("DS-770II", "Epson", "scanner"),

    # Selected Verified Consumables
    "c13t49n400": ("C13T49N400", "Epson", "ink"),
    "t49n400": ("C13T49N400", "Epson", "ink"),
    "t49n4": ("C13T49N400", "Epson", "ink"),
    "c13t49n100": ("C13T49N100", "Epson", "ink"),
    "t49n100": ("C13T49N100", "Epson", "ink"),
    "c13t49n200": ("C13T49N200", "Epson", "ink"),
    "t49n200": ("C13T49N200", "Epson", "ink"),
    "c13t49n300": ("C13T49N300", "Epson", "ink"),
    "t49n300": ("C13T49N300", "Epson", "ink"),
}

# Known Phantom Models and their structured rejections
PHANTOM_MODELS: Dict[str, Dict[str, Any]] = {
    "cx-02s": {
        "pattern": r"\bcx[-_\s]?0?2\s*s\b",
        "raw_name": "Citizen CX-02S",
        "explanation": "The model **Citizen CX-02S** does not exist in the official Citizen lineup.",
        "suggested_models": ["CX-02", "CX-02W"],
        "reply": (
            "The model **Citizen CX-02S** does not exist in the Citizen lineup. "
            "Citizen manufactures the **Citizen CX-02** (standard 6-inch dye-sublimation photo printer) "
            "and the **Citizen CX-02W** (8-inch wide-format dye-sublimation photo printer).\n\n"
            "Would you like details on the standard **CX-02** (4x6, 5x7, 6x8) or the wide-format **CX-02W** (8x10, 8x12)?"
        )
    },
    "sc-p9999": {
        "pattern": r"\b(sc[-_\s]?)?p[-_\s]?9999\b",
        "raw_name": "Epson SC-P9999",
        "explanation": "The model **Epson SC-P9999** does not exist in the Epson lineup.",
        "suggested_models": ["SC-P9500", "SC-P900"],
        "reply": (
            "The model **Epson SC-P9999** does not exist. In Epson's 44-inch professional photo printer lineup, "
            "we supply the **Epson SureColor SC-P9500** (12-colour fine art & proofing system) "
            "and the 17-inch **Epson SureColor SC-P900**.\n\n"
            "Would you like specifications or pricing for the 44-inch **SC-P9500** or the 17-inch **SC-P900**?"
        )
    },
    "wf-c55890": {
        "pattern": r"\b(wf[-_\s]?)?c[-_\s]?55890\b|\b(wf[-_\s]?)?c[-_\s]?58900\b",
        "raw_name": "Epson WF-C55890",
        "suggested_models": ["WF-C5890"],
        "reply": (
            "The model **Epson WF-C55890** does not exist. You are likely referring to the "
            "**Epson WorkForce Pro WF-C5890 DWF** (A4 colour business multifunction printer with Replaceable Ink Pack System).\n\n"
            "Would you like specifications and pricing for the **WF-C5890**?"
        )
    },
    "cx-01": {
        "pattern": r"\bcx[-_\s]?0?1\b",
        "raw_name": "Citizen CX-01",
        "suggested_models": ["CZ-01", "CX-02"],
        "reply": (
            "The model **Citizen CX-01** does not exist. Citizen's compact, ultra-lightweight (5.8 kg) "
            "photo printer is the **Citizen CZ-01**, and the standard 6-inch flagship is the **Citizen CX-02**.\n\n"
            "Would you like details on the ultra-portable **CZ-01** (4x6) or the flagship **CX-02** (up to 6x8)?"
        )
    },
    "cx-03": {
        "pattern": r"\bcx[-_\s]?0?3\b",
        "raw_name": "Citizen CX-03",
        "suggested_models": ["CX-02", "CX-02W", "CY-02"],
        "reply": (
            "The model **Citizen CX-03** does not exist. In the Citizen photo printer series, "
            "we offer the **CX-02** (compact 6-inch), **CX-02W** (8-inch wide), and **CY-02** (high-capacity 700 prints/roll).\n\n"
            "Which format or capacity fits your workflow?"
        )
    },
    "sc-t31000": {
        "pattern": r"\b(sc[-_\s]?)?t[-_\s]?31000\b",
        "raw_name": "SC-T31000",
        "suggested_models": ["SC-T3100"],
        "reply": (
            "The model **SC-T31000** does not exist. You may be referring to the "
            "**Epson SureColor SC-T3100** (24-inch entry-level wireless technical CAD plotter).\n\n"
            "Would you like details and pricing on the **SC-T3100**?"
        )
    }
}

# Ambiguous Models Requiring Exactly One Clarifying Question
AMBIGUOUS_MODELS: Dict[str, Dict[str, Any]] = {
    "p8500": {
        "pattern": r"\b(sc[-_\s]?)?p[-_\s]?8500\b(?!\s*d\b|\s*dm\b)",
        "question": (
            "Are you inquiring about the **Epson SureColor SC-P8500D** (dual-roll 44-inch production photo printer) "
            "or the **Epson SureColor SC-P8500DM** (which includes an integrated 36-inch dual-light CIS scanner)?"
        ),
        "options": ["SC-P8500D", "SC-P8500DM"]
    }
}


def normalize_brand(text: str) -> Optional[str]:
    """Resolves typos and aliases of brands to canonical name."""
    lower = text.lower()
    for alias, canonical in BRAND_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", lower):
            return canonical
    return None


def detect_phantom_model(text: str) -> Optional[Dict[str, Any]]:
    """
    Detects known phantom / fictitious model numbers.
    Never silently substitutes; returns explicit refusal + closest real options.
    """
    lower = text.lower()
    for phantom_id, data in PHANTOM_MODELS.items():
        if re.search(data["pattern"], lower):
            return data
    return None


def detect_ambiguous_model(text: str) -> Optional[Dict[str, Any]]:
    """
    Detects ambiguous models that require exactly one clarifying question.
    Example: 'P8500' -> SC-P8500D vs SC-P8500DM.
    """
    lower = text.lower()
    for amb_id, data in AMBIGUOUS_MODELS.items():
        if re.search(data["pattern"], lower):
            return data
    return None


def normalize_model_or_sku(text: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Normalizes product model or SKU from text.
    Returns: (canonical_model, brand, category) or (None, None, None).
    """
    lower = text.lower()

    # 1. Exact alias match or regex boundary
    for alias, (canonical, brand, category) in sorted(MODEL_ALIASES.items(), key=lambda x: -len(x[0])):
        pattern = rf"(^|[^\w\d]){re.escape(alias)}([^\w\d]|$)"
        if re.search(pattern, lower):
            return canonical, brand, category

    return None, None, None
