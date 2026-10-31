"""
tests/test_batch7_hardening.py
Batch 7 test suite:
1. Separate DB enforcement (load test refuses production path).
2. Archived test handoffs skipped by retry sweep.
3. validate_config forbids mock mode / unconfigured secrets in production.
4. Queue wait timeout does not increment circuit breaker failures.
5. Lease auto-reclaim after simulated worker crash.
6. Scope gating on 50 in-scope multilingual questions (0% false rejection).
"""

import os
import time
import pytest
from pathlib import Path
from unittest.mock import patch

from app.main import create_app
from app.config import Config


# ============================================================================
# 1. Load test refuses production DB
# ============================================================================

def test_load_test_refuses_production_db():
    """
    scripts/load_test_concurrent_sessions.py and scripts/benchmark_capacity.py
    MUST refuse to execute if DATABASE_PATH points to the production data/sales_ai.db.
    """
    from scripts.load_test_concurrent_sessions import validate_isolated_db
    
    prod_path = Path("/opt/basics/data/sales_ai.db")
    with pytest.raises(RuntimeError, match="Refusing to run load test against production database"):
        validate_isolated_db(prod_path)

    test_path = Path("/opt/basics/data/test_isolated.db")
    assert validate_isolated_db(test_path) is True


# ============================================================================
# 2. Archived test handoffs ignored by retry sweep
# ============================================================================

def test_archived_test_handoffs_ignored_by_retry_sweep():
    """
    The handoff retry sweep must completely ignore handoffs with status='archived_test'.
    """
    from app.storage.handoffs import get_pending_handoffs_for_retry, record_handoff
    from app.storage.db import get_db_connection

    # Create a test handoff and mark as archived_test
    ho_id = record_handoff(sender_id="test_archive_user", reason="Test archiving", summary="Archive summary")
    
    conn = get_db_connection()
    conn.execute("UPDATE handoffs SET status = 'archived_test' WHERE id = ?", (ho_id,))
    conn.commit()
    conn.close()

    pending = get_pending_handoffs_for_retry()
    pending_ids = [row["id"] for row in pending]
    assert ho_id not in pending_ids, f"Archived test handoff {ho_id} was picked up by retry sweep!"


# ============================================================================
# 3. validate_config forbids mock mode in production
# ============================================================================

def test_validate_config_forbids_mock_in_production(monkeypatch):
    """
    validate_config() must raise ValueError if APP_ENV=production and WHATSAPP_DEV_OVERRIDE is True.
    """
    from app.config import validate_config
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("WHATSAPP_DEV_OVERRIDE", "true")
    monkeypatch.setenv("SECRET_KEY", "real_production_secret_key_32_chars_long_12345")
    monkeypatch.setenv("AUDIT_HMAC_KEY", "real_production_audit_hmac_key_32_chars_12345")
    monkeypatch.setenv("ADMIN_API_KEY", "real_production_admin_key_32_chars_long_12345")
    monkeypatch.setenv("PII_ENCRYPTION_KEY", "dGVzdF9waWlfZW5jcnlwdGlvbl9rZXlfMzJieXRlczE=")

    with pytest.raises(ValueError, match="Mock mode .* forbidden in production"):
        validate_config()


# ============================================================================
# 4. Queue wait does NOT trip the Ollama circuit breaker
# ============================================================================

def test_queue_wait_does_not_trip_circuit_breaker():
    """
    Admission control queue-wait timeout (fallback_reason='queue_wait_timeout')
    is a capacity shedding mechanism, NOT an Ollama failure.
    It MUST NOT increment circuit_breaker.failure_count.
    """
    from app.cognitive.understander import circuit_breaker
    from app.agent.llm import generate_llm_response

    initial_failures = circuit_breaker.failure_count
    
    # Mock acquire_generation_slot to simulate queue wait timeout (returns None)
    with patch("app.agent.admission.acquire_generation_slot", return_value=None):
        reply = generate_llm_response(
            user_message="Explain printhead cleaning",
            context_chunks=[{"section": "Maintenance", "text": "Clean head regularly"}]
        )
        assert "verified details" in reply or "technical specifications" in reply
        # Circuit breaker must not be penalized
        assert circuit_breaker.failure_count == initial_failures, "Queue wait timeout incremented Ollama circuit breaker!"


# ============================================================================
# 5. Lease auto-reclaim after worker crash
# ============================================================================

def test_lease_expiry_reclaims_slot_after_crash():
    """
    Simulate worker crashing while holding an LLM slot (abandoned lease).
    After the lease duration expires, acquire_generation_slot must clean up
    the dead lease and successfully acquire the slot.
    """
    from app.agent.admission import acquire_generation_slot, release_generation_slot
    from app.storage.db import get_db_connection

    # Insert an expired lease simulating dead PID
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO llm_generation_leases (lease_id, worker_id, acquired_at, expires_at) VALUES (?, ?, ?, ?)",
        ("crashed_worker_lease", "pid_99999", time.time() - 40, time.time() - 10)
    )
    conn.commit()
    conn.close()

    # Should clean up expired lease and acquire
    new_lease = acquire_generation_slot(worker_id="recovering_worker", wait_timeout=0.2)
    assert new_lease is not None, "Failed to acquire slot after worker crash!"
    release_generation_slot(new_lease)


# ============================================================================
# 6. Scope gating: 50 in-scope multilingual questions (0% false rejection)
# ============================================================================

def test_positive_scope_gating_50_in_scope_multilingual():
    """
    50 legitimate customer inquiries across English, Arabic, Malayalam, and Manglish
    must successfully retrieve CX-02 catalog context with a 0% false-rejection rate.
    """
    from app.rag.retriever import retrieve

    in_scope_questions = [
        # English (CX-02 Hardware & Performance)
        "What is the print speed of the Citizen CX-02 for 4x6 photos?",
        "Does the Citizen CX-02 support 5x7 inch prints?",
        "What are the dimensions and total weight of the CX-02 printer?",
        "How fast can it print a 6x8 photo in high speed mode?",
        "What is the input power voltage and wattage during active printing?",
        "Explain the thermal dye sublimation process and overcoat protection",
        "Does this printer have ribbon rewind technology to prevent paper waste?",
        "Can I connect the CX-02 to a Windows 11 PC via USB 2.0?",
        "Are macOS drivers available for the Citizen CX-02?",
        "Is there Linux CUPS support for this photo printer?",
        "What finishes can I choose: matte, glossy, or luster?",
        "Can the printer produce 2x6 photo booth strips with dual-cut?",
        "How many prints can I get from a 4x6 media roll?",
        "What is the yield of the 5x7 media set CX2-MS57-2PC?",
        "What is the part number for the 6x8 media box?",
        "Do you supply the official Citizen carry bag for the CX-02?",
        "What is the price of the thermal printhead cleaning pen?",
        "How often should I clean the thermal printhead?",
        "Where is your Dubai showroom located on Khalid Bin Waleed Road?",
        "What are your business operating hours in Dubai?",
        "Is Kepler Tech an authorized Citizen distributor in the UAE?",
        "What warranty coverage is included with the Citizen CX-02?",
        "Can you ship the printer to Abu Dhabi?",
        "Do you deliver commercial printers to Saudi Arabia and GCC?",
        "Can I schedule a live showroom demonstration in Dubai?",

        # Arabic (الفصحى والخليجية)
        "كم سرعة طباعة الصور مقاس 4x6 في طابعة سيتيزن CX-02؟",
        "هل تدعم طابعة سيتيزن مقاس 5x7 وكم عدد الصور في الرول؟",
        "ما هي أبعاد ووزن طابعة الصور سيتيزن في دبي؟",
        "كيف تحمي طبقة الأوفركوت الصور من الماء والبهتان؟",
        "هل تتوفر تقنية توفير الريبان في مقاس 6x8؟",
        "ما هو سعر قلم تنظيف رأس الطباعة الحراري؟",
        "هل يتوفر لديكم رول ورق 4x6 لطابعة CX-02؟",
        "ما هي ساعات عمل معرض كيبلر تك في شارع خالد بن الوليد؟",
        "هل طابعة سيتيزن مناسبة لكشك تصوير الحفلات والفوتوبوث؟",
        "كم مدة الضمان لطابعة الصور في الإمارات؟",
        "هل توفرون خدمة التوصيل إلى أبوظبي والشارقة؟",
        "هل يمكن تجربة الطابعة في المعرض قبل الشراء؟",
        "ما هي دقة الطباعة المتوفرة 300 و 600 نقطة؟",
        "هل تعمل الطابعة على نظام ويندوز وماك؟",
        "أريد شراء حقيبة حمل مبطنة لطابعة CX-02",

        # Malayalam
        "സിറ്റിസൺ CX-02 ഫോട്ടോ പ്രിന്ററിന്റെ പ്രിന്റ് സ്പീഡ് എത്രയാണ്?",
        "4x6 ഫോട്ടോ പ്രിന്റ് ചെയ്യാൻ എത്ര സമയം എടുക്കും?",
        "CX-02 പ്രിന്ററിന്റെ ഭാരവും വലിപ്പവും എത്രയാണ്?",
        "ഫോട്ടോബൂത്ത് ഇവന്റുകൾക്ക് ഈ പ്രിന്റർ അനുയോജ്യമാണോ?",
        "പ്രിന്റ്ഹെഡ് ക്ലീനിംഗ് പെൻ ലഭ്യമാണോ?",
        "ദുബായിൽ വാറന്റി ലഭിക്കുമോ?",

        # Manglish / Arabizi
        "kam se3r citizen cx-02 printer fi dubai?",
        "shuf el print speed for 4x6 photos marhaba",
        "bikam el media rolls 4x6 for cx-02 in uae?",
        "wayn showroom kepler tech fi dubai khalid bin waleed?"
    ]

    assert len(in_scope_questions) == 50, f"Expected 50 questions, got {len(in_scope_questions)}"

    misses = []
    for q in in_scope_questions:
        res = retrieve(q, top_k=2, use_dense=False)
        if len(res) == 0:
            misses.append(q)

    assert len(misses) == 0, f"False rejections detected on in-scope questions ({len(misses)}/50): {misses}"
