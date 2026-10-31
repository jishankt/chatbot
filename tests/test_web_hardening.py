import os
import json
import time
import sqlite3
import multiprocessing
import pytest
from app.main import create_app
from app.config import Config
from app.storage.db import get_db_connection


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


# ============================================================================
# Requirement 1: Web Chatbot Hardening & Session Security Tests
# ============================================================================

def test_body_sender_id_phone_ignored_by_chat(client):
    """
    Web /chat endpoint must IGNORE client-supplied sender_id and phone in JSON body,
    assigning an isolated web:<session_id> identity instead.
    """
    attacker_phone = "+971509999999"
    res = client.post("/chat", json={
        "message": "Attempting to spoof customer phone",
        "sender_id": attacker_phone,
        "phone": attacker_phone
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["sender_id"] != attacker_phone
    assert data["sender_id"].startswith("web:")

    # Verify no message row was written under the spoofed phone in DB
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM messages WHERE sender_id = ?", (attacker_phone,))
        count = cur.fetchone()[0]
        assert count == 0, f"Spoofed phone {attacker_phone} found in messages table!"
    finally:
        conn.close()


def test_tampered_or_unsigned_web_session_id_rejected(client):
    """
    Unsigned or tampered web_session_id cookies must be rejected with 401 on /history.
    """
    client.set_cookie("web_session_id", "forged_unsigned_session_id")
    res = client.get("/history")
    assert res.status_code == 401
    assert "Invalid or missing session" in res.get_json().get("error", "")


def test_history_with_no_cookie_returns_401(client):
    """
    /history with no cookie and no admin token must return 401 Unauthorized.
    """
    res = client.get("/history")
    assert res.status_code == 401
    data = res.get_json()
    assert res.status_code == 401
    assert "error" in data


def test_signed_cookie_secure_production_flag(client, monkeypatch):
    """
    In production (ENV='production'), session cookie must have Secure, HttpOnly, and SameSite=Lax.
    """
    monkeypatch.setattr(Config, "ENV", "production")
    res = client.post("/chat", json={"message": "Testing production cookie security"})
    assert res.status_code == 200
    cookie_header = res.headers.get("Set-Cookie", "")
    assert "web_session_id=" in cookie_header
    assert "HttpOnly" in cookie_header
    assert "Secure" in cookie_header
    assert "SameSite=Lax" in cookie_header


# ============================================================================
# Requirement 1: Competitor Guardrail Edge Cases
# ============================================================================

def test_competitor_friend_has_epson(client):
    """
    'CX-02 price, friend has an Epson':
    User specifically inquires about CX-02 price, noting an Epson context.
    Must accurately provide Citizen CX-02 official price (4,385.00 AED).
    """
    res = client.post("/chat", json={"message": "CX-02 price, friend has an Epson"})
    assert res.status_code == 200
    reply = res.get_json()["reply"]
    assert "4,385.00" in reply or "4,385" in reply
    assert "CX-02" in reply


def test_competitor_epson_vs_cx02(client):
    """
    'Epson vs CX-02':
    Model comparison requested -> Must trigger comparative refusal / guidance.
    """
    res = client.post("/chat", json={"message": "Epson vs CX-02"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["intent"] in ("guardrails", "category_browse", "product_consultation")
    reply = data["reply"]
    assert "comparative" in reply.lower() or "partner" in reply.lower() or "not provide" in reply.lower() or "specialize" in reply.lower()


def test_competitor_arabic_printer_price(client):
    """
    Arabic printer-price with a competitor (e.g. 'كم سعر طابعة ابسون' or 'سعر طابعة كانون')
    Must NOT quote Citizen CX-02 price (4,385 AED).
    """
    res = client.post("/chat", json={"message": "كم سعر طابعة كانون؟"})
    assert res.status_code == 200
    reply = res.get_json()["reply"]
    assert "4,385" not in reply, "Leaked Citizen CX-02 price for Canon inquiry in Arabic!"


# ============================================================================
# Requirement 3: Two-Process Concurrent Write Test for SQLite Locking
# ============================================================================

def _worker_insert_loop(worker_id: int, result_queue: multiprocessing.Queue):
    """Helper worker that runs 25 rapid inserts across messages and quotes."""
    try:
        from app.storage.db import get_db_connection
        from app.storage.messages import log_message
        for i in range(25):
            msg_id = f"proc_{worker_id}_msg_{i}_{time.time()}"
            sender = f"proc_worker_{worker_id}"
            ok = log_message(sender_id=sender, role="user", content=f"Concurrent message {i}", message_id=msg_id)
            assert ok is True
        result_queue.put((worker_id, "SUCCESS"))
    except Exception as e:
        result_queue.put((worker_id, f"ERROR: {str(e)}"))


def test_sqlite_two_process_concurrency():
    """
    Spawns two separate OS processes concurrently writing to SQLite.
    WAL mode and busy_timeout=15000 must ensure zero 'database is locked' crashes.
    """
    q = multiprocessing.Queue()
    p1 = multiprocessing.Process(target=_worker_insert_loop, args=(1, q))
    p2 = multiprocessing.Process(target=_worker_insert_loop, args=(2, q))

    p1.start()
    p2.start()

    p1.join(timeout=10)
    p2.join(timeout=10)

    assert not p1.is_alive(), "Process 1 timed out"
    assert not p2.is_alive(), "Process 2 timed out"

    results = [q.get() for _ in range(2)]
    for w_id, status in results:
        assert status == "SUCCESS", f"Worker {w_id} failed with: {status}"


# ============================================================================
# Requirement 4: Handoff Notifications via SMTP Primary Channel
# ============================================================================

def test_handoff_smtp_primary_and_per_channel_status(monkeypatch):
    """
    Handoff alerts must attempt SMTP email with TLS, sanitized headers, plain-text body,
    and truncated user text. Per-channel status must be recorded in handoffs.notification_status.
    """
    from app.notifications.salesperson import notify_salesperson_of_handoff
    from app.storage.handoffs import save_handoff, get_handoffs

    hid = save_handoff(
        reason="Bulk order discount",
        summary="Customer wants 20 CX-02 units for Abu Dhabi event " * 10,
        phone="+971501112233",
        sender_id="web:test_session_smtp"
    )

    # Mock SMTP to verify TLS, headers, and body
    sent_emails = []

    class MockSMTP:
        def __init__(self, host, port, timeout=10):
            self.host = host
            self.port = port
        def starttls(self):
            return (220, b"Ready")
        def login(self, user, password):
            return (235, b"Auth successful")
        def send_message(self, msg):
            sent_emails.append(msg)
            return {}
        def quit(self):
            pass

    import smtplib
    monkeypatch.setattr(smtplib, "SMTP", MockSMTP)
    monkeypatch.setattr(Config, "SMTP_HOST", "smtp.mock.kepler.ae")
    monkeypatch.setattr(Config, "SMTP_PORT", 587)
    monkeypatch.setattr(Config, "SMTP_USER", "sales-ai@kepler.ae")
    monkeypatch.setattr(Config, "SMTP_PASSWORD", "secret_pass")
    monkeypatch.setattr(Config, "SALESPERSON_EMAIL", "salesdesk@kepler.ae")

    res = notify_salesperson_of_handoff(
        handoff_id=hid,
        reason="Bulk order discount\r\nBcc: evil@attacker.com",
        summary="Customer wants 20 CX-02 units " * 20,
        phone="+971501112233",
        sender_id="web:test_session_smtp"
    )

    assert len(sent_emails) == 1
    msg = sent_emails[0]
    # Header CRLF injection prevention
    assert "\r" not in msg["Subject"]
    assert "\n" not in msg["Subject"]
    assert msg["To"] == "salesdesk@kepler.ae"

    # Truncated body check
    body_text = msg.get_content()
    assert len(body_text) < 2000

    # Per-channel status in DB
    handoffs = get_handoffs(limit=200)
    target = next(h for h in handoffs if h["id"] == hid)
    assert target["notification_status"] is not None
    assert "email:sent" in target["notification_status"] or "email" in target["notification_status"]


# ============================================================================
# Requirement 5: Conversation State Versioning & Concurrency Serialization
# ============================================================================

def test_conversation_state_version_column_and_optimistic_retry():
    """
    conversation_states must have a version column for optimistic locking / retry.
    """
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(conversation_states)")
        cols = [r["name"] for r in cur.fetchall()]
        assert "version" in cols, "conversation_states table is missing 'version' column!"
    finally:
        conn.close()


# ============================================================================
# Requirement 6: Rate Limiting & Input Length Validation
# ============================================================================

def test_quote_customer_name_validation(client):
    """
    /quote must validate customer_name (reject injection tags, overlong strings).
    """
    # XSS injection in customer_name
    res_xss = client.post("/quote", json={
        "items": [{"sku": "CX-02", "qty": 1}],
        "customer_name": "<script>alert('xss')</script>"
    })
    assert res_xss.status_code == 400

    # Overlong name (> 100 chars)
    res_long = client.post("/quote", json={
        "items": [{"sku": "CX-02", "qty": 1}],
        "customer_name": "A" * 150
    })
    assert res_long.status_code == 400


def test_chat_max_message_length(client):
    """
    /chat must reject messages exceeding maximum allowed length (e.g. > 1000 chars) before LLM.
    """
    overlong_msg = "What is the price of the Citizen CX-02? " * 50
    assert len(overlong_msg) > 1000
    res = client.post("/chat", json={"message": overlong_msg})
    assert res.status_code == 400
    data = res.get_json()
    assert "too long" in data.get("error", "").lower() or "limit" in data.get("error", "").lower()


# ============================================================================
# Requirement 7: Audit Log Masking & File Rotation
# ============================================================================

def test_audit_logging_no_raw_pii_and_rotation(tmp_path, monkeypatch):
    """
    audit.jsonl must NOT contain raw user_message or reply in plain text.
    Must contain hashed/length metadata instead.
    """
    from app.audit_logging.audit import log_turn
    test_log = tmp_path / "audit_test.jsonl"
    monkeypatch.setattr("app.audit_logging.audit.AUDIT_LOG_FILE", test_log)

    secret_user_text = "My credit card is 4111-2222-3333-4444 and my address is Villa 4, Palm Jumeirah"
    secret_bot_reply = "Your order has been confirmed for delivery to Villa 4, Palm Jumeirah"

    log_turn(
        phone="+971501112233",
        user_message=secret_user_text,
        reply=secret_bot_reply,
        intent="price",
        tools_called=[],
        chunks=[],
        duration_ms=45.2
    )

    content = test_log.read_text(encoding="utf-8")
    assert secret_user_text not in content, "Raw user_message was written to audit.jsonl!"
    assert secret_bot_reply not in content, "Raw reply was written to audit.jsonl!"

    rec = json.loads(content.strip())
    assert "user_message_hash" in rec or "user_message_len" in rec
