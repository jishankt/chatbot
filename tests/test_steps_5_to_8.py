import pytest
from app.agent.pipeline import CX02Pipeline
from app.storage.db import get_db_connection, init_db
from app.storage.messages import log_message

def test_step5_chip_bare_number_parsing():
    pipeline = CX02Pipeline()
    # Turn 1: Ask about roll sizes
    res1 = pipeline.process("Which roll sizes are available for CX-02?", sender_id="test_chip_user_1")
    assert "reply" in res1
    
    # Turn 2: bare chip input "4x6"
    res2 = pipeline.process("4x6", sender_id="test_chip_user_1")
    assert "4x6" in res2["reply"].lower() or "ms46" in res2["reply"].lower()

def test_step6_frustration_acknowledgement_and_slot_restate():
    pipeline = CX02Pipeline()
    sender = "test_frustrated_customer_99"
    # Establish context: photo printer, 5x7
    pipeline.process("Looking for a photo printer for 5x7 prints", sender_id=sender)
    
    # Express frustration
    res_frustrated = pipeline.process("You don't understand, stop repeating useless answers!", sender_id=sender)
    reply = res_frustrated["reply"]
    # Check: apology, restatement of recorded context, no sales pitch, specialist handoff
    assert "apologize" in reply.lower() or "misunderstanding" in reply.lower()
    assert "context recorded" in reply.lower() or "photo" in reply.lower() or "5x7" in reply.lower()
    assert "specialist" in reply.lower() or "team" in reply.lower() or "notified" in reply.lower()
    assert res_frustrated["intent"] == "frustration_handoff"

def test_step7_multilingual_sku_preservation():
    pipeline = CX02Pipeline()
    # Arabic inquiry with Latin SKU
    res_ar = pipeline.process("كم سعر طابعة CX-02 مع الشحن لدبي؟", sender_id="test_arabic_sku_1")
    assert "cx-02" in res_ar["reply"].lower() or "2,850" in res_ar["reply"] or "aed" in res_ar["reply"].lower()
    
    # Malayalam/Manglish query with Epson SKU
    res_mal = pipeline.process("Epson SC-T3100 price ethrayaanu?", sender_id="test_mal_sku_1")
    assert "t3100" in res_mal["reply"].lower() or "sc-t3100" in res_mal["reply"].lower() or "4,200" in res_mal["reply"]

def test_step8_analytics_test_flag():
    init_db()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(messages)")
    cols = [r["name"] for r in cur.fetchall()]
    assert "is_test" in cols
    
    # Log test message
    log_message(sender_id="test_eval_run_999", role="user", content="Test message")
    cur.execute("SELECT is_test FROM messages WHERE sender_id = 'test_eval_run_999'")
    row = cur.fetchone()
    assert row is not None
    assert row["is_test"] == 1
    
    # Log real customer message
    log_message(sender_id="+971501234567", role="user", content="Real inquiry")
    cur.execute("SELECT is_test FROM messages WHERE sender_id = '+971501234567'")
    row2 = cur.fetchone()
    assert row2 is not None
    assert row2["is_test"] == 0
    conn.close()
