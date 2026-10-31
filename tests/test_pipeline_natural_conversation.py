import pytest
from app.agent.pipeline import CX02Pipeline
from app.storage.db import init_db
from app.config import Config
import tempfile
from pathlib import Path


@pytest.fixture
def clean_pipeline(monkeypatch):
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        temp_path = Path(tf.name)
    monkeypatch.setattr(Config, "DATABASE_PATH", temp_path)
    init_db(temp_path)
    pipeline = CX02Pipeline()
    yield pipeline
    if temp_path.exists():
        temp_path.unlink()


def test_multi_item_quote_quantities(clean_pipeline):
    res = clean_pipeline.process(
        user_message="Quote me 2 CX-02 printers and 4 boxes of 4x6 media",
        sender_id="user_multi_quote_test"
    )
    reply = res["reply"]
    # 1. Must quote 2x CX-02
    assert "2x Citizen CX-02 Photo Printer" in reply
    # 2. Must quote 4x 4x6 media
    assert "4x Citizen CX-02 4x6\" Media Set" in reply
    # 3. Correct subtotal: 2*4385 + 4*490 = 8770 + 1960 = 10,730.00 AED
    assert "10,730.00 AED" in reply
    # 4. Must NOT dump technical spec text above quote
    assert "official specifications for the *Citizen CX-02* (Official Accessories" not in reply


def test_scanner_context_anaphora_no_default_cx02(clean_pipeline):
    # Turn 1: Customer asks for scanner
    clean_pipeline.process("no , ineed a scanner", sender_id="user_scanner_test")
    # Turn 2: Customer asks for price of these
    res2 = clean_pipeline.process("what is the price of these?", sender_id="user_scanner_test")
    reply2 = res2["reply"]
    # Must NOT quote 4x6 media set or 490 AED
    assert "490.00" not in reply2
    assert "4x6" not in reply2
    # Must mention scanners
    assert "scanner" in reply2.lower()


def test_consultative_objection_handling(clean_pipeline):
    res = clean_pipeline.process("dont this one", sender_id="user_objection_test")
    reply = res["reply"]
    # Must be consultative, not a cold handoff with office address
    assert "requirements or applications" in reply.lower()
    assert "📍 Office" not in reply


def test_company_website_link(clean_pipeline):
    res = clean_pipeline.process("your compnay website link?", sender_id="user_website_test")
    reply = res["reply"]
    assert "https://www.keplertechllc.com/" in reply
