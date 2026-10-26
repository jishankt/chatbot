import pytest
from app.cognitive.reader import (
    normalize_text,
    detect_language,
    extract_sku_direct,
    resolve_anaphora_sku,
    read_message
)
from app.agent.pipeline import CX02Pipeline


def test_normalize_text_unicode_and_digits():
    # NFKC ligature normalization & eastern arabic digits
    raw = "What is the price of ٥ boxes of ٤×٦ media?"
    norm = normalize_text(raw)
    assert "5 boxes of 4x6 media" in norm
    assert "٥" not in norm


def test_normalize_text_zero_width_and_whitespace():
    # Zero width space and excessive spaces
    raw = "Citizen\u200B \uFEFFCX-02    photo   printer"
    norm = normalize_text(raw)
    assert norm == "Citizen CX-02 photo printer"


def test_normalize_text_typos():
    raw = "citzen prentir cx02 warenty and delvery discunt"
    norm = normalize_text(raw)
    assert "citizen" in norm
    assert "printer" in norm
    assert "cx-02" in norm
    assert "warranty" in norm
    assert "delivery" in norm
    assert "discount" in norm


def test_detect_language():
    assert detect_language("What is the cost of the CX-02 printer?") == "en"
    assert detect_language("كم سعر طابعة الصور سيتيزن في دبي؟") == "ar"
    assert detect_language("bikam el printer ya habibi") == "manglish"
    assert detect_language("kam el se3r el cx02 inshallah") == "manglish"
    assert detect_language("marhaba, how much is the printer?") == "manglish"


def test_extract_sku_direct_english():
    assert extract_sku_direct("Citizen CX-02 printer") == "CX-02"
    assert extract_sku_direct("4x6 media set") == "CX2-MS46-2PC"
    assert extract_sku_direct("5x7 media") == "CX2-MS57-2PC"
    assert extract_sku_direct("6x8 consumable paper") == "CX2-MS68-2PC"
    assert extract_sku_direct("protective carry bag") == "CX-02-BAG"
    assert extract_sku_direct("thermal printhead cleaning pen") == "CITIZEN-PEN"
    assert extract_sku_direct("6x9 media") == "6x9"


def test_extract_sku_direct_arabic():
    assert extract_sku_direct("كم سعر الطابعة") == "CX-02"
    assert extract_sku_direct("شنطة الطابعة CX-02") == "CX-02-BAG"
    assert extract_sku_direct("قلم تنظيف رأس الطباعة") == "CITIZEN-PEN"
    assert extract_sku_direct("ورق 4x6") == "CX2-MS46-2PC"
    assert extract_sku_direct("ورق 5x7") == "CX2-MS57-2PC"


def test_extract_sku_unsupported_items():
    # Should never map unsupported items to CX-02
    assert extract_sku_direct("tripod stand for the camera") is None
    assert extract_sku_direct("wireless bluetooth adapter") is None
    assert extract_sku_direct("replacement battery pack") is None
    assert extract_sku_direct("scanner flatbed") is None


def test_anaphora_resolution_multi_turn():
    history = [
        {"role": "user", "content": "Do you sell 5x7 media for the printer?"},
        {"role": "assistant", "content": "Yes, we stock the CX2-MS57-2PC 5x7 media set."}
    ]

    # Reference with pronoun "them" and quantity 3
    sku_resolved = resolve_anaphora_sku("how much for 3 of them?", history)
    assert sku_resolved == "CX2-MS57-2PC"

    # Reference with "is it in stock"
    bag_history = [
        {"role": "user", "content": "Tell me about the protective carry bag."},
        {"role": "assistant", "content": "The Citizen CX-02 Protective carry bag is available."}
    ]
    sku_bag = resolve_anaphora_sku("is it in stock right now?", bag_history)
    assert sku_bag == "CX-02-BAG"


def test_read_message_comprehensive():
    history = [
        {"role": "user", "content": "I am interested in 5x7 media sets."},
        {"role": "assistant", "content": "The 5x7 media set (CX2-MS57-2PC) provides 460 prints."}
    ]

    ctx = read_message("how much for 3 of them?", history=history)
    assert ctx.resolved_sku == "CX2-MS57-2PC"
    assert ctx.resolved_qty == 3
    assert ctx.is_anaphora is True
    assert ctx.language == "en"


def test_pipeline_multi_turn_anaphora_quote():
    pipeline = CX02Pipeline()
    sender = "test_turn_anaphora_user"

    # Turn 1: Inquire about 5x7 media
    resp1 = pipeline.process(
        "Do you have 5x7 media sets available?",
        sender_id=sender,
        channel="web"
    )
    assert resp1["resolved_sku"] == "CX2-MS57-2PC"

    # Turn 2: Ask for a quote using anaphoric reference
    resp2 = pipeline.process(
        "Can you send a quote for 4 of them?",
        sender_id=sender,
        channel="web"
    )
    assert resp2["is_anaphora"] is True
    assert resp2["resolved_sku"] == "CX2-MS57-2PC"
    assert "Quotation" in resp2["reply"]
    assert "CX2-MS57-2PC" in resp2["reply"]
    assert "4x Citizen" in resp2["reply"]
