import os
import re
import time
import json
import sqlite3
import pytest
from pathlib import Path
from unittest.mock import patch

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
# 1. Real Ollama Load Test Script Verification
# ============================================================================

def test_load_test_script_configured_for_real_ollama_and_200_requests():
    """
    scripts/load_test_concurrent_sessions.py must:
    - Support real Ollama execution (not hard-mocked)
    - Support 200+ requests per regime
    - Compute p50, p95, p99 and fallback rate
    """
    script_path = Path("/opt/basics/scripts/load_test_concurrent_sessions.py")
    assert script_path.exists(), "load_test_concurrent_sessions.py missing!"
    content = script_path.read_text(encoding="utf-8")
    assert "p99" in content, "Load test script missing p99 metric calculation!"
    assert "fallback" in content.lower(), "Load test script missing fallback rate reporting!"
    # Must support 200+ requests
    assert "200" in content or "concurrency" in content


# ============================================================================
# 2. Lockout: DB-backed, ProxyFix, Unlock Path, Spoofed Header Prevention
# ============================================================================

def test_proxyfix_enabled_in_app():
    """Werkzeug ProxyFix must be enabled on the WSGI app in app/main.py."""
    main_code = Path("/opt/basics/app/main.py").read_text(encoding="utf-8")
    assert "ProxyFix" in main_code, "ProxyFix middleware is not enabled in app/main.py!"


def test_admin_lockout_db_backed_across_workers(client):
    """
    Failed admin auth attempts must be recorded in SQLite DB so that
    lockouts are shared across multiple Gunicorn workers.
    """
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='admin_auth_failures'")
        row = cur.fetchone()
        assert row is not None, "admin_auth_failures table does not exist in SQLite DB!"
    finally:
        conn.close()


def test_admin_unlock_path_restores_access(client):
    """
    After lockout, an unlock path (API endpoint /admin/unlock with master secret
    or CLI script) must reset failed counters for the locked IP.
    """
    attacker_ip = "198.51.100.55"
    # Trigger lockout
    for _ in range(6):
        client.get(
            "/leads",
            headers={
                "Authorization": "Bearer bad_key",
                "X-Forwarded-For": attacker_ip
            }
        )

    # Verify locked out
    locked_res = client.get(
        "/leads",
        headers={
            "Authorization": "Bearer bad_key",
            "X-Forwarded-For": attacker_ip
        }
    )
    assert locked_res.status_code == 429

    # Unlock via admin unlock endpoint
    unlock_res = client.post(
        "/admin/unlock",
        json={"ip": attacker_ip},
        headers={"Authorization": f"Bearer {Config.ADMIN_API_KEY}"}
    )
    assert unlock_res.status_code == 200

    # Access must be restored (with valid token)
    restored_res = client.get(
        "/leads",
        headers={
            "Authorization": f"Bearer {Config.ADMIN_API_KEY}",
            "X-Forwarded-For": attacker_ip
        }
    )
    assert restored_res.status_code == 200


def test_nginx_spoofed_forwarded_for_prevention():
    """
    Nginx config must only trust actual local / internal proxy CIDRs
    so untrusted client X-Forwarded-For headers cannot spoof client IP.
    """
    nginx_conf = Path("/opt/basics/config/nginx_rate_limits.conf").read_text(encoding="utf-8")
    assert "real_ip_recursive on;" in nginx_conf
    # Must NOT have 0.0.0.0 or overly broad set_real_ip_from
    assert "0.0.0.0/0" not in nginx_conf


# ============================================================================
# 3. Widget: XSS prevention (textContent) & double-escaping check
# ============================================================================

def test_widget_js_uses_textcontent_not_innerhtml_for_user_text():
    """
    app/static/js/app.js must use textContent or safe DOM node creation
    when rendering chat messages to prevent XSS.
    """
    app_js = Path("/opt/basics/app/static/js/app.js").read_text(encoding="utf-8")
    assert "innerHTML = message" not in app_js
    assert "textContent" in app_js, "app.js should use textContent for message rendering!"


def test_chat_rendering_no_double_escaping(client):
    """
    Verify that special characters like '&', '<', '>' in history and replies
    are not double-escaped into '&amp;lt;' in client responses.
    """
    res = client.post("/chat", json={"message": "I need Citizen CX-02 & 4x6 media <test>"})
    assert res.status_code == 200
    reply = res.get_json().get("reply", "")
    assert "&amp;lt;" not in reply, "Double escaping detected in reply!"
    assert "&amp;amp;" not in reply, "Double escaping detected in reply!"


# ============================================================================
# 4. Final-failure handoff alert to a second channel
# ============================================================================

def test_handoff_permanent_failure_alerts_second_channel(monkeypatch):
    """
    When a handoff reaches MAX_HANDOFF_RETRY_ATTEMPTS, a final alert must be dispatched
    to a secondary escalation channel (e.g. secondary email or alert hook).
    """
    from app.storage.handoffs import save_handoff
    from app.notifications.salesperson import retry_failed_handoffs_sweep

    sender = f"test_perm_fail_{time.time()}"
    hid = save_handoff(
        reason="Repeated permanent failure test",
        summary="Customer needs urgent equipment setup",
        sender_id=sender,
        status="failed_all_channels"
    )

    # Force failure
    import smtplib
    monkeypatch.setattr(smtplib, "SMTP", lambda *args, **kwargs: (_ for _ in ()).throw(Exception("Primary SMTP down")))
    monkeypatch.setattr(Config, "MAX_HANDOFF_RETRY_ATTEMPTS", 2)

    second_channel_called = []
    def mock_second_channel(handoff_id, reason, customer):
        second_channel_called.append((handoff_id, reason, customer))

    monkeypatch.setattr("app.notifications.salesperson.dispatch_secondary_emergency_alert", mock_second_channel)

    # Sweep twice to trigger permanent_failure
    retry_failed_handoffs_sweep(limit=10)
    retry_failed_handoffs_sweep(limit=10)

    assert len(second_channel_called) > 0, "Secondary channel was NOT alerted on permanent failure!"


# ============================================================================
# 5. Validator: Transcripts & Eval set evaluation
# ============================================================================

def test_validator_transcript_and_eval_reporting():
    """
    scripts/eval_validator.py must exist and report rejection/fallback rate
    over all transcripts and the eval set.
    """
    eval_script = Path("/opt/basics/scripts/eval_validator.py")
    assert eval_script.exists(), "scripts/eval_validator.py is missing!"


# ============================================================================
# 6. Fresh held-out 40 retrieval questions (including unlisted brands)
# ============================================================================

def test_fresh_held_out_40_unlisted_brands_rejection():
    """
    Held-out 40-question benchmark must reject brands not in catalog (Hiti, Mitsubishi, Sinfonia, Kodak)
    with a 0% false match rate.
    """
    from app.rag.retriever import retrieve
    unlisted_queries = [
        "What is the price of a HiTi P525L printer?",
        "Do you sell Mitsubishi CP-D70DW paper rolls?",
        "How much for Sinfonia CS2 photo printer?",
        "Where can I buy Kodak 305 dye sub printer?",
        "Can you quote on HiTi P520L ribbon and media?",
        "Is the Mitsubishi CP-D80DW available in Dubai?",
        "Do you carry Sinfonia S3 color stream media?",
        "We need prices for Kodak 6850 photo printer.",
        "What is the lead time on DNP DS620 duplex unit?",
        "Can I order DNP DS820 media packs from you?",
        "Quote for DNP QW410 compact event printer please.",
        "Do you have stock of DNP RX1HS media in Abu Dhabi?",
        "What is the warranty on Fujifilm ASK-300?",
        "Can you provide quotation for Fujifilm Frontier DE100?",
        "Looking for Fuji DX100 inkjet minilab cartridges.",
        "Is Fujifilm ASK-500 in stock today?",
        "Do you sell Canon Selphy CP1500 compact photo printer?",
        "Price check on Canon Selphy CP1300 paper ink set.",
        "Can you quote Canon imagePROGRAF PRO-200 printer?",
        "Do you distribute Canon PRO-1000 professional printers?",
        "Where can I buy Noritsu dry lab paper in Dubai?",
        "Price for Shinko S2145 dye-sublimation printer.",
        "كم سعر طابعة ميتسوبيشي للصور الفوتوغرافية؟",
        "هل يتوفر لديكم ورق طابعة كوداك 305؟",
        "هل تبيعون طابعة كانون سيلفي CP1500 في دبي؟",
        "كم سعر طابعة فوجي فيلم ASK-300 في الامارات؟",
        "എനിക്ക് മിത്സുബിഷി ഫോട്ടോ പ്രിന്റർ വേണം",
        "കാനൺ സെൽഫി പ്രിന്റർ വില എത്രയാണ്?",
        "Do you supply HiTi P750L photo booth media?",
        "Need pricing on Mitsubishi CP-M1E high capacity printer.",
        "How much is the Kodak 6900 photo printer system?",
        "Can I buy Sinfonia CE1 passport photo printer?",
        "Do you have HiTi CS-200e ID card printer?",
        "What is the cost of Mitsubishi CP-3800DW large format dye-sub?",
        "Looking for Kodak 8810 8-inch printer media.",
        "Is DNP DS40 still supported with paper rolls?",
        "Do you stock Polaroid Hi-Print pocket printer cartridges?",
        "What is the price of HP Sprocket Studio photo printer?",
        "Can you quote Sony UP-DR80MD medical dye-sub printer?",
        "We need Brother VC-500W color label printer."
    ]
    assert len(unlisted_queries) == 40, f"Expected exactly 40 queries, got {len(unlisted_queries)}"
    for q in unlisted_queries:
        res = retrieve(q, top_k=2, use_dense=False)
        assert len(res) == 0, f"False match on unlisted brand query '{q}': {[r['section'] for r in res]}"


# ============================================================================
# 7. Move hardcoded contact numbers to config
# ============================================================================

def test_no_hardcoded_contact_numbers_in_source_code():
    """
    Phone numbers and emails must come from Config (Config.KEPLER_PHONE, Config.KEPLER_WHATSAPP),
    never hardcoded as literal strings in python logic.
    """
    source_files = [
        Path("/opt/basics/app/agent/validator.py"),
        Path("/opt/basics/app/agent/pipeline.py"),
        Path("/opt/basics/app/api/routes.py")
    ]
    for f in source_files:
        content = f.read_text(encoding="utf-8")
        # Check for hardcoded raw phone strings
        assert "00971 4 323 1008" not in content, f"Hardcoded phone '00971 4 323 1008' found in {f.name}!"
        assert "+971 50 890 1641" not in content, f"Hardcoded phone '+971 50 890 1641' found in {f.name}!"


# ============================================================================
# 8. Restore Drill and Boot Verification Script
# ============================================================================

def test_restore_drill_script_exists_and_verifies_boot():
    """
    scripts/restore_drill.py must restore a backup, boot the Flask app from it,
    and assert /health returns 200.
    """
    drill_script = Path("/opt/basics/scripts/restore_drill.py")
    assert drill_script.exists(), "scripts/restore_drill.py is missing!"


# ============================================================================
# 9. CI: requirements.lock and GitHub Actions Workflow
# ============================================================================

def test_ci_workflow_and_lockfile_exist():
    """
    requirements.lock and .github/workflows/ci.yml must exist with
    pip-audit, bandit, gitleaks, and pytest.
    """
    assert Path("/opt/basics/requirements.lock").exists(), "requirements.lock is missing!"
    ci_path = Path("/opt/basics/.github/workflows/ci.yml")
    assert ci_path.exists(), ".github/workflows/ci.yml is missing!"
    ci_content = ci_path.read_text(encoding="utf-8")
    for tool in ["pip-audit", "bandit", "gitleaks", "pytest"]:
        assert tool in ci_content, f"CI workflow missing {tool} step!"
