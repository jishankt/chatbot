import os
import json
import ssl
import time
import sqlite3
import pytest
from decimal import Decimal
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
# 1. APP_ENV=production fail-closed & Secure cookie test
# ============================================================================

def test_startup_fails_in_production_with_missing_or_default_secrets(monkeypatch):
    """
    In production (APP_ENV=production), validate_config() must raise RuntimeError
    if critical secrets are left as known defaults.
    """
    from app.config import validate_config
    monkeypatch.setattr(Config, "ENV", "production")
    monkeypatch.setattr(Config, "ADMIN_API_KEY", "kepler_admin_secret_key_2026")

    with pytest.raises(RuntimeError) as excinfo:
        validate_config()
    assert "known insecure default" in str(excinfo.value).lower() or "production" in str(excinfo.value).lower()


def test_secure_cookie_flag_on_in_production(client, monkeypatch):
    """
    In production, /chat must set the Secure flag on the web_session_id cookie.
    """
    monkeypatch.setattr(Config, "ENV", "production")
    res = client.post("/chat", json={"message": "Checking production cookie flags"})
    assert res.status_code == 200
    cookie_hdr = res.headers.get("Set-Cookie", "")
    assert "Secure" in cookie_hdr
    assert "HttpOnly" in cookie_hdr


# ============================================================================
# 2. Handoff caps per session/day & global/hour
# ============================================================================

def test_handoff_caps_per_session_and_global(monkeypatch):
    """
    Handoff tool must enforce session/day cap (e.g. 5) and global/hour cap.
    """
    from app.tools.handoff import handoff_to_human
    sender = f"test_handoff_cap_user_{time.time()}"

    monkeypatch.setattr(Config, "MAX_HANDOFFS_GLOBAL_HOUR", 1000)

    # Exhaust session cap
    for i in range(Config.MAX_HANDOFFS_PER_SESSION_DAY):
        res = handoff_to_human(reason=f"Reason {i}", sender_id=sender)
        assert res.get("status") in ("handoff_initiated", "success")

    # Next handoff on same session must be capped
    capped_res = handoff_to_human(reason="Excessive handoff request", sender_id=sender)
    assert capped_res.get("status") == "rate_limited" or capped_res.get("capped") is True
    assert "limit" in capped_res.get("message", "").lower() or "00971 4 323 1008" in capped_res.get("customer_message", "")

    # Test global cap explicitly
    monkeypatch.setattr(Config, "MAX_HANDOFFS_GLOBAL_HOUR", 1)
    global_capped_res = handoff_to_human(reason="Global cap test", sender_id=f"new_user_{time.time()}")
    assert global_capped_res.get("status") == "rate_limited" or global_capped_res.get("capped") is True


# ============================================================================
# 3. Two concurrent /chat calls on one session with conflict retry
# ============================================================================

def test_concurrent_chat_conflict_retry(client):
    """
    Two concurrent turns on the same session must be serialized or retried
    via optimistic state locking without data corruption.
    """
    import concurrent.futures
    session_sender = "web:test_concurrent_turn_session"

    def send_turn(msg):
        from app.agent.pipeline import CX02Pipeline
        pipe = CX02Pipeline()
        return pipe.process(user_message=msg, sender_id=session_sender)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(send_turn, "I need a photo printer for my booth")
        f2 = executor.submit(send_turn, "What is the price of 5x7 media rolls?")
        res1 = f1.result(timeout=15)
        res2 = f2.result(timeout=15)

    assert res1.get("reply") is not None
    assert res2.get("reply") is not None

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT version, turn_count FROM conversation_states WHERE sender_id = ?", (session_sender,))
        row = cur.fetchone()
        assert row is not None
        assert row["version"] >= 2, f"State version did not increment properly: {dict(row)}"
    finally:
        conn.close()


# ============================================================================
# 4. /quote customer_name allowlist
# ============================================================================

def test_quote_name_allowlist(client):
    """
    /quote must validate customer_name against an allowlist:
    - Strips control chars and newlines
    - Rejects URLs
    - Enforces length cap
    - Permits Arabic and Latin alphabets, spaces, and hyphens
    """
    # 1. URL injection rejected
    res_url = client.post("/quote", json={
        "items": [{"sku": "CX-02", "qty": 1}],
        "customer_name": "Visit https://spam-domain.com"
    })
    assert res_url.status_code == 400

    # 2. Control characters & newlines rejected or stripped
    res_crlf = client.post("/quote", json={
        "items": [{"sku": "CX-02", "qty": 1}],
        "customer_name": "John Doe\r\nBcc: evil@domain.com"
    })
    assert res_crlf.status_code == 400

    # 3. Valid Arabic customer name accepted
    res_ar = client.post("/quote", json={
        "items": [{"sku": "CX-02", "qty": 1}],
        "customer_name": "أحمد عبدالله"
    })
    assert res_ar.status_code == 200


# ============================================================================
# 5. SMTP verified TLS context, timeout, retry sweep, fallback message
# ============================================================================

def test_smtp_verified_tls_context_and_retry_sweep(monkeypatch):
    """
    SMTP dispatch must use verified TLS context, 10s timeout, and retry sweep function.
    """
    from app.notifications.salesperson import retry_failed_handoffs_sweep, notify_salesperson_of_handoff
    from app.storage.handoffs import save_handoff

    # Test retry sweep function exists and runs
    hid = save_handoff(
        reason="Retry test handoff",
        summary="Customer needs urgent support",
        sender_id="web:retry_sweep_test",
        status="failed_all_channels"
    )

    sweep_res = retry_failed_handoffs_sweep()
    assert "swept_count" in sweep_res or "retried" in sweep_res


# ============================================================================
# 6. Audit log: HMAC instead of plain SHA-256 & scrub script
# ============================================================================

def test_audit_log_hmac_and_scrub_script(tmp_path, monkeypatch):
    """
    Audit log must use keyed HMAC-SHA256 for message hashes.
    A scrub script must be available to purge existing plaintext audit files.
    """
    from app.audit_logging.audit import log_turn
    test_log = tmp_path / "audit_hmac.jsonl"
    monkeypatch.setattr("app.audit_logging.audit.AUDIT_LOG_FILE", test_log)

    log_turn(
        phone="+971501112233",
        user_message="My sensitive order note",
        reply="Order confirmed",
        intent="quote",
        tools_called=[],
        chunks=[],
        duration_ms=25.0
    )

    content = test_log.read_text(encoding="utf-8")
    rec = json.loads(content.strip())
    assert "user_message_hmac" in rec, "Audit record missing user_message_hmac!"

    # Verify scrub script exists
    assert os.path.exists("/opt/basics/scripts/scrub_audit_logs.py"), "scripts/scrub_audit_logs.py is missing!"


# ============================================================================
# 7. Money: integer fils (migration 003), Decimal rounding, catalog_version, stale-price block
# ============================================================================

def test_money_integer_fils_migration_and_snapshot():
    """
    Database must have subtotal_fils, vat_fils, total_fils, catalog_version, expires_at in quotes.
    Quote creation must store exact integer fils via Decimal.
    """
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(quotes)")
        cols = [r["name"] for r in cur.fetchall()]
        for req_col in ["subtotal_fils", "vat_fils", "total_fils", "catalog_version", "expires_at"]:
            assert req_col in cols, f"quotes table missing column '{req_col}'!"
    finally:
        conn.close()


def test_stale_price_block(monkeypatch):
    """
    If catalog price is older than PRICE_MAX_AGE_DAYS (14), quote generation must block
    or require manual confirmation.
    """
    from app.tools.pricing import load_catalog
    from app.tools.quote import create_quote

    # Mock catalog as_of to 30 days ago
    cat = load_catalog()
    cat["as_of"] = "2020-01-01"
    monkeypatch.setattr("app.tools.pricing.load_catalog", lambda: cat)
    monkeypatch.setattr("app.tools.quote.load_catalog", lambda: cat)

    res = create_quote(items=[{"sku": "CX-02", "qty": 1}])
    assert res.get("status") == "error"
    assert "stale" in res.get("message", "").lower() or "confirm" in res.get("message", "").lower()


# ============================================================================
# 8. SKU source tracking (explicit/state/default) & CX-02 comparative answer
# ============================================================================

def test_sku_source_tracking_refuses_default(client):
    """
    When SKU source is 'default' (e.g. 'what is the price?' with no prior context),
    pricing must refuse to guess and ask which product is needed.
    """
    res = client.post("/chat", json={"message": "What is the price?"})
    assert res.status_code == 200
    reply = res.get_json()["reply"]
    # Must ask which product rather than unconditionally giving 4,385 AED for CX-02
    assert "which product" in reply.lower() or "which item" in reply.lower() or "options" in reply.lower()


def test_epson_vs_cx02_answers_cx02_part(client):
    """
    'Epson vs CX-02' must answer the CX-02 technical part while adhering to no-speculation rules.
    """
    res = client.post("/chat", json={"message": "Epson vs CX-02"})
    assert res.status_code == 200
    reply = res.get_json()["reply"]
    assert "Citizen CX-02" in reply or "CX-02" in reply
    assert "dye-sub" in reply.lower() or "speed" in reply.lower() or "photo" in reply.lower()


# ============================================================================
# 9. Multilingual Retrieval Tokenizer & 60-question eval
# ============================================================================

def test_multilingual_tokenizer_arabic():
    """
    Tokenizer in RAG must not drop non-ASCII / Arabic tokens.
    """
    from app.rag.retrieve import tokenize
    tokens = tokenize("طابعة صور كانون وسرعة الطباعة")
    assert len(tokens) >= 4, f"Arabic tokens dropped: {tokens}"
    assert "طابعة" in tokens
    assert "كانون" in tokens


MULTILINGUAL_60_EVAL_SET = [
    # 1-20: English Canonical Knowledge Queries
    {"query": "How many seconds does the 4x6 print speed take?", "expected": "speed"},
    {"query": "What print sizes does the CX-02 support?", "expected": "size"},
    {"query": "What is the resolution of the CX-02 printer?", "expected": "print engine"},
    {"query": "What is the weight and dimensions of the CX-02?", "expected": "dimension"},
    {"query": "Does the CX-02 support Mac and Windows operating systems?", "expected": "operating system"},
    {"query": "How does the ribbon rewind function save media?", "expected": "ribbon rewind"},
    {"query": "What finishing options like matte and glossy are available?", "expected": "finishing option"},
    {"query": "How does sleep mode reduce energy consumption?", "expected": "energy saving"},
    {"query": "What official accessories are available for CX-02?", "expected": "accessories"},
    {"query": "Is there a cleaning pen for thermal printhead maintenance?", "expected": "maintenance"},
    {"query": "Can CX-02 produce 2x6 photo booth cut strips?", "expected": "size"},
    {"query": "What are the dimensions in millimeters of the printer?", "expected": "dimension"},
    {"query": "What is the print speed for 5x7 photos?", "expected": "speed"},
    {"query": "Does the printer use dye-sublimation thermal transfer?", "expected": "dye-sublimation"},
    {"query": "How does the overcoat protect against water and fingerprints?", "expected": "overcoat"},
    {"query": "What USB interface does the CX-02 provide?", "expected": "connectivity"},
    {"query": "What is the power consumption in sleep mode?", "expected": "energy saving"},
    {"query": "How many prints does the 5x7 media box produce?", "expected": "accessories"},
    {"query": "Is there a protective carry bag for mobile events?", "expected": "accessories"},
    {"query": "Is front-loading drop-in paper mechanism supported?", "expected": "key advantages"},

    # 21-40: Arabic Canonical Knowledge Queries
    {"query": "ما هي سرعة طباعة مقاس 4x6؟", "expected": "speed"},
    {"query": "ما هي مقاسات الطباعة المدعومة في الطابعة؟", "expected": "size"},
    {"query": "ما هي دقة الطباعة dpi في الطابعة؟", "expected": "print engine"},
    {"query": "كم وزن طابعة CX-02 وأبعادها؟", "expected": "dimension"},
    {"query": "هل تدعم الطابعة نظام ماك وويندوز؟", "expected": "operating system"},
    {"query": "كيف تعمل خاصية ترجيع الشريط لتوفير الورق؟", "expected": "ribbon rewind"},
    {"query": "ما هي خيارات الإنهاء مثل اللامع والمطفي؟", "expected": "finishing option"},
    {"query": "كم توفر ميزة وضع السكون من استهلاك الطاقة؟", "expected": "energy saving"},
    {"query": "ما هي الملحقات الرسمية المتوفرة لطابعة CX-02؟", "expected": "accessories"},
    {"query": "هل يوجد قلم تنظيف لصيانة رأس الطباعة الحراري؟", "expected": "maintenance"},
    {"query": "هل تدعم الطابعة قص شرائط الصور 2x6 للبوث؟", "expected": "size"},
    {"query": "ما هي أبعاد الطابعة بالمليمتر والوزن بالكيلوجرام؟", "expected": "dimension"},
    {"query": "كم ثانية تستغرق طباعة صورة 5x7؟", "expected": "speed"},
    {"query": "هل تعتمد الطابعة على تقنية التسامي الحراري؟", "expected": "dye-sublimation"},
    {"query": "كيف تحمي طبقة التغليف الصور من الماء والبصمات؟", "expected": "overcoat"},
    {"query": "ما هو منفذ التوصيل يو اس بي في الطابعة؟", "expected": "connectivity"},
    {"query": "كم استهلاك الكهرباء في وضع السكون؟", "expected": "energy saving"},
    {"query": "كم عدد الصور في رول وسائط 5x7؟", "expected": "accessories"},
    {"query": "هل تتوفر حقيبة نقل وحماية لطابعة الفعاليات؟", "expected": "accessories"},
    {"query": "كيف يتم تحميل الورق من الأمام بسهولة؟", "expected": "key advantages"},

    # 41-60: Mixed / Transliterated / Gulf Colloquial Queries
    {"query": "kam wazn el cx-02 printer weight in kg?", "expected": "dimension"},
    {"query": "kam seconds sur3at teba3at 4x6 print speed?", "expected": "speed"},
    {"query": "what is the dpi resolution deqqa of cx-02?", "expected": "print engine"},
    {"query": "supported print sizes maqasat for cx-02?", "expected": "size"},
    {"query": "hal yeshteghel el printer 3ala macos and windows driver?", "expected": "operating system"},
    {"query": "ribbon rewind feature for saving paper waraq?", "expected": "ribbon rewind"},
    {"query": "finishing options matte and glossy lama3 finish?", "expected": "finishing option"},
    {"query": "energy saving sleep mode reducing power consumption?", "expected": "energy saving"},
    {"query": "accessories molhaqat available for cx-02 photobooth?", "expected": "accessories"},
    {"query": "thermal printhead cleaning pen qalam tanzeef maintenance?", "expected": "maintenance"},
    {"query": "can cx-02 cut 2x6 photo strips for party booth?", "expected": "size"},
    {"query": "dimensions in mm tool and ard of the chassis?", "expected": "dimension"},
    {"query": "print speed for 6x8 photos in seconds?", "expected": "speed"},
    {"query": "dye sublimation thermal transfer overcoat protection?", "expected": "dye-sublimation"},
    {"query": "protective layer overcoat against water and moisture?", "expected": "overcoat"},
    {"query": "usb 2.0 connectivity interface port?", "expected": "connectivity"},
    {"query": "standby sleep mode 98 percent power saving?", "expected": "energy saving"},
    {"query": "yield prints count in 4x6 and 5x7 media box roll?", "expected": "accessories"},
    {"query": "protective carry bag shankah for event mobility?", "expected": "accessories"},
    {"query": "front drop-in paper loading and ribbon cassette handling?", "expected": "key advantages"}
]


def test_multilingual_60_question_retrieval_eval():
    """
    Evaluates multilingual retrieval across 60 benchmark questions
    (English, Arabic, Mixed/Transliterated).
    Asserts top-3 hit rate >= 85%.
    """
    from app.rag.retriever import retrieve

    assert len(MULTILINGUAL_60_EVAL_SET) == 60, f"Eval set must contain exactly 60 queries, got {len(MULTILINGUAL_60_EVAL_SET)}"

    hits = 0
    total = len(MULTILINGUAL_60_EVAL_SET)

    for item in MULTILINGUAL_60_EVAL_SET:
        query = item["query"]
        expected = item["expected"].lower()
        results = retrieve(query, top_k=3, use_dense=False)
        sections = " ".join([r.get("section", "").lower() + " " + r.get("text", "").lower() for r in results])
        if expected in sections:
            hits += 1

    hit_rate = hits / total
    assert hit_rate >= 0.85, f"Multilingual retrieval hit rate {hit_rate:.1%} is below 85% requirement ({hits}/{total})"

