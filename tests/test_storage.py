import pytest
import tempfile
from pathlib import Path
from app.config import Config
from app.storage.db import init_db, get_db_connection
from app.storage.messages import is_message_duplicate, log_message, get_conversation_history
from app.storage.leads import save_lead, get_leads, set_pending_lead, get_pending_lead, clear_pending_lead
from app.storage.quotes import save_quote, get_quote
from app.storage.handoffs import save_handoff, get_handoffs


@pytest.fixture
def temp_db(monkeypatch):
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        temp_path = Path(tf.name)
    monkeypatch.setattr(Config, "DATABASE_PATH", temp_path)
    init_db(temp_path)
    yield temp_path
    if temp_path.exists():
        temp_path.unlink()


def test_message_deduplication_and_history(temp_db):
    assert not is_message_duplicate("msg_100")

    # Log user message
    ok1 = log_message(sender_id="user_1", role="user", content="Hello", message_id="msg_100")
    assert ok1 is True
    assert is_message_duplicate("msg_100") is True

    # Duplicate should fail to insert
    ok2 = log_message(sender_id="user_1", role="user", content="Hello again", message_id="msg_100")
    assert ok2 is False

    # Log assistant message
    log_message(sender_id="user_1", role="assistant", content="Hi! How can I help?", message_id="msg_101")

    history = get_conversation_history("user_1", limit=5)
    assert len(history) == 2
    assert history[0] == {"role": "user", "content": "Hello"}
    assert history[1] == {"role": "assistant", "content": "Hi! How can I help?"}


def test_pending_leads_state(temp_db):
    assert get_pending_lead("user_2") is None

    set_pending_lead("user_2", stage="awaiting_name", temp_phone="+971501234567", last_intent="quote")
    pending = get_pending_lead("user_2")
    assert pending is not None
    assert pending["stage"] == "awaiting_name"
    assert pending["temp_phone"] == "+971501234567"

    # Update state
    set_pending_lead("user_2", stage="completed", temp_name="John Doe")
    pending2 = get_pending_lead("user_2")
    assert pending2["stage"] == "completed"
    assert pending2["temp_name"] == "John Doe"
    assert pending2["temp_phone"] == "+971501234567"

    clear_pending_lead("user_2")
    assert get_pending_lead("user_2") is None


def test_quote_storage(temp_db):
    items = [{"sku": "CX-02", "name": "Citizen CX-02", "qty": 1, "price": 4385.0, "line_total": 4385.0}]
    qid = "Q-TEST-001"
    save_quote(
        quote_id=qid,
        items=items,
        subtotal=4385.0,
        total=4385.0,
        vat_amount=None,
        sender_id="user_3",
        customer_name="Alice",
        phone="+971500000000"
    )

    retrieved = get_quote(qid)
    assert retrieved is not None
    assert retrieved["quote_id"] == qid
    assert retrieved["customer_name"] == "Alice"
    assert len(retrieved["items"]) == 1
    assert retrieved["items"][0]["sku"] == "CX-02"


def test_handoff_storage(temp_db):
    hid = save_handoff(reason="Asked for DNP printer", summary="Can I buy DNP DS620?", phone="+971550001122", sender_id="user_4")
    assert hid > 0

    handoffs = get_handoffs(10)
    assert len(handoffs) == 1
    assert handoffs[0]["reason"] == "Asked for DNP printer"
    assert handoffs[0]["phone"] == "+971550001122"


def test_aes_gcm_encryption_at_rest(temp_db):
    import sqlite3
    raw_phone = "+971508901641"
    raw_name = "Tariq Al-Mansoor"
    raw_email = "tariq@example.ae"
    raw_content = "Please quote me 5 units of Citizen CX-02 printer."

    # 1. Store via app storage functions
    log_message(sender_id="user_enc", role="user", content=raw_content, message_id="msg_enc_1")
    save_lead(sender_id="user_enc", name=raw_name, phone=raw_phone, email=raw_email, notes="VIP client")
    save_quote(quote_id="Q-ENC-1", items=[{"sku": "CX-02", "qty": 5}], subtotal=21925.0, total=21925.0, sender_id="user_enc", customer_name=raw_name, phone=raw_phone)
    hid = save_handoff(reason="Bulk order discount", summary="Wants special pricing for 5 units", phone=raw_phone, sender_id="user_enc")

    # 2. Inspect raw SQLite database directly - verify encrypted at rest
    conn = sqlite3.connect(str(temp_db))
    cur = conn.cursor()

    cur.execute("SELECT content FROM messages WHERE message_id = 'msg_enc_1'")
    db_content = cur.fetchone()[0]
    assert db_content.startswith("enc:v1:")
    assert raw_content not in db_content

    cur.execute("SELECT name, phone, email FROM leads WHERE sender_id = 'user_enc'")
    db_name, db_phone, db_email = cur.fetchone()
    assert db_name.startswith("enc:v1:")
    assert db_phone.startswith("enc:v1:")
    assert db_email.startswith("enc:v1:")
    assert raw_name not in db_name
    assert raw_phone not in db_phone

    cur.execute("SELECT customer_name, phone FROM quotes WHERE quote_id = 'Q-ENC-1'")
    db_qname, db_qphone = cur.fetchone()
    assert db_qname.startswith("enc:v1:")
    assert db_qphone.startswith("enc:v1:")

    cur.execute("SELECT phone FROM handoffs WHERE id = ?", (hid,))
    db_hphone = cur.fetchone()[0]
    assert db_hphone.startswith("enc:v1:")
    conn.close()

    # 3. Verify seamless app decryption
    history = get_conversation_history("user_enc")
    assert history[0]["content"] == raw_content

    leads = get_leads(limit=5)
    matching_lead = next(l for l in leads if l["sender_id"] == "user_enc")
    assert matching_lead["name"] == raw_name
    assert matching_lead["phone"] == raw_phone
    assert matching_lead["email"] == raw_email

    quote = get_quote("Q-ENC-1")
    assert quote["customer_name"] == raw_name
    assert quote["phone"] == raw_phone

    handoffs = get_handoffs(limit=5)
    matching_handoff = next(h for h in handoffs if h["id"] == hid)
    assert matching_handoff["phone"] == raw_phone


def test_aes_gcm_backward_compatibility(temp_db):
    import sqlite3
    # Insert legacy unencrypted records directly
    conn = sqlite3.connect(str(temp_db))
    cur = conn.cursor()
    cur.execute("INSERT INTO messages (message_id, sender_id, channel, role, content) VALUES ('legacy_1', 'user_leg', 'web', 'user', 'Legacy unencrypted text')")
    cur.execute("INSERT INTO leads (sender_id, name, phone, email, notes) VALUES ('user_leg', 'Legacy User', '+971501112233', 'legacy@kepler.ae', 'legacy')")
    conn.commit()
    conn.close()

    # App read functions should gracefully handle unencrypted data
    history = get_conversation_history("user_leg")
    assert history[0]["content"] == "Legacy unencrypted text"

    leads = get_leads(limit=5)
    matching = next(l for l in leads if l["sender_id"] == "user_leg")
    assert matching["name"] == "Legacy User"
    assert matching["phone"] == "+971501112233"
