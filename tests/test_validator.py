import pytest
from app.agent.validator import validate_output, make_extractive_fallback, extract_numbers_and_claims


def test_validator_accepts_grounded_answer():
    chunks = [{
        "section": "Print Speeds",
        "text": "## Print Speeds\n- 4 x 6 inch: 8.4 seconds in High Speed mode; 9.8 seconds in High Quality mode"
    }]
    question = "How fast is 4x6?"
    candidate = "The Citizen CX-02 prints a 4x6 photo in 8.4 seconds (High Speed) or 9.8 seconds (High Quality)."

    is_valid, reason = validate_output(candidate, chunks, question)
    assert is_valid is True
    assert reason == ""


def test_validator_rejects_hallucinated_price():
    chunks = [{
        "section": "Print Speeds",
        "text": "## Print Speeds\n- 4 x 6 inch: 8.4 seconds in High Speed mode"
    }]
    question = "How much is the printer?"
    # 2999 AED is not in context or question
    candidate = "The Citizen CX-02 is priced at 2,999 AED and prints in 8.4 seconds."

    is_valid, reason = validate_output(candidate, chunks, question)
    assert is_valid is False
    assert "2999" in reason or "Ungrounded" in reason


def test_validator_rejects_hallucinated_warranty_claim():
    chunks = [{
        "section": "Print Speeds",
        "text": "## Print Speeds\n- 4 x 6 inch: 8.4 seconds in High Speed mode"
    }]
    question = "Does it have a warranty?"
    candidate = "Yes, it comes with a 3-year warranty and free delivery across Dubai."

    is_valid, reason = validate_output(candidate, chunks, question)
    assert is_valid is False
    assert "warranty" in reason.lower() or "free delivery" in reason.lower()


def test_validator_rejects_competitor_leakage():
    chunks = [{
        "section": "Overview",
        "text": "## Product Overview\nCitizen CX-02 dye-sub photo printer."
    }]
    candidate = "Unlike the DNP DS620, the Citizen CX-02 is more compact."

    is_valid, reason = validate_output(candidate, chunks, "Tell me about CX-02")
    assert is_valid is False
    assert "competitor" in reason.lower()


def test_make_extractive_fallback():
    chunks = [{
        "section": "Supported Print Sizes",
        "text": "## Supported Print Sizes\n- 4 x 6 inches (102 x 152 mm): 400 prints per roll\n- 5 x 7 inches: 230 prints per roll"
    }]
    fallback = make_extractive_fallback(chunks, "What sizes?")
    assert "Citizen CX-02" in fallback
    assert "4 x 6 inches" in fallback
    assert "00971 4 323 1008" in fallback
