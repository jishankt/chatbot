import json
import pytest
from pathlib import Path
from app.rag.retriever import retrieve_company
from app.agent.validator import validate_output
from app.agent.pipeline import CX02Pipeline
from app.tools.policies import get_policy


def test_company_chunks_contain_required_metadata():
    """Verify that every company chunk declares raw source file, site, and source date."""
    company_chunks_path = Path("data/company_chunks.json")
    assert company_chunks_path.exists(), "data/company_chunks.json must exist"

    with open(company_chunks_path, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    assert len(chunks) >= 10, f"Expected at least 10 company chunks, found {len(chunks)}"

    for chunk in chunks:
        assert "file" in chunk or "source_file" in chunk
        assert "site" in chunk, f"Chunk {chunk.get('id')} missing site metadata"
        assert "corporate" in chunk["site"] or "store" in chunk["site"], f"Unexpected site {chunk['site']}"
        assert "source_date" in chunk, f"Chunk {chunk.get('id')} missing source_date"
        assert "raw_sources" in chunk and len(chunk["raw_sources"]) > 0, f"Chunk {chunk.get('id')} missing raw_sources"


def test_company_retrieval_grounding_coverage():
    """Test retrieval for company services, coverage, and contacts."""
    # 1. Services: repair
    repair_chunks = retrieve_company("printer repair maintenance services", top_k=2)
    assert len(repair_chunks) > 0
    assert any("repair" in c["text"].lower() or "services" in c["section"].lower() for c in repair_chunks)

    # 2. Coverage: Kuwait / GCC
    cov_chunks = retrieve_company("shipping to Kuwait GCC delivery", top_k=2)
    assert len(cov_chunks) > 0
    assert any("kuwait" in c["text"].lower() or "gcc" in c["text"].lower() or "delivery" in c["text"].lower() for c in cov_chunks)

    # 3. Contacts / Head office
    contact_chunks = retrieve_company("head office silicon oasis contact phone", top_k=2)
    assert len(contact_chunks) > 0
    assert any("silicon oasis" in c["text"].lower() or "contact" in c["section"].lower() for c in contact_chunks)


def test_company_policies_grounding():
    """Test that free shipping threshold (400 AED) and contact numbers are grounded in policies.json."""
    with open("data/policies.json", "r", encoding="utf-8") as f:
        policies = json.load(f)

    # Free shipping threshold
    assert policies["free_shipping"]["threshold_aed"] == 400.0
    assert policies["delivery_charges"]["free_shipping_threshold_aed"] == 400.0

    # Contact numbers
    contact = policies.get("company_contact", {})
    assert contact.get("whatsapp") == "+971 50 890 1641"
    assert contact.get("tracking_phone") == "+971 521 21 4898"
    assert contact.get("second_phone") == "00971 55 835 8586"
    assert contact.get("email") == "info@keplertech.ae"

    # Per-country delivery transit times
    transit = policies.get("country_delivery_times", {})
    assert "kuwait" in transit
    assert "saudi_arabia" in transit
    assert "uae" in transit


def test_company_validator_rejects_hallucinations():
    """Validator rejects ungrounded numbers or false claims for company facts."""
    context_chunks = [{
        "section": "Delivery & Shipping Coverage",
        "text": "UAE Standard Delivery: 1–3 business days. Free shipping on orders above AED 400. GCC delivery: 2–4 business days."
    }]

    # Grounded reply passes
    grounded_reply = "We offer free shipping on UAE orders above AED 400, with delivery in 1–3 business days."
    ok, _ = validate_output(grounded_reply, context_chunks, "What is your free shipping policy?")
    assert ok

    # Hallucinated number (e.g. 50 AED or 99 days) is rejected
    hallucinated_reply = "We offer free shipping on orders above AED 50, with delivery in 99 business days."
    bad, reason = validate_output(hallucinated_reply, context_chunks, "What is your free shipping policy?")
    assert not bad
    assert "ungrounded number" in reason.lower() or "not found in retrieved" in reason.lower()
