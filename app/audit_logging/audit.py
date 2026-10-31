import json
import hmac
import hashlib
import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from app.config import Config
from app.utils.phone import mask_phone_number

AUDIT_LOG_FILE = Config.AUDIT_LOG_PATH
MAX_AUDIT_LOG_BYTES = 10 * 1024 * 1024  # 10 MB per file
MAX_ROTATED_BACKUPS = 5


def _rotate_audit_log_if_needed():
    """Rotates audit log file if it exceeds MAX_AUDIT_LOG_BYTES."""
    if not AUDIT_LOG_FILE.exists():
        return
    try:
        if AUDIT_LOG_FILE.stat().st_size >= MAX_AUDIT_LOG_BYTES:
            for i in range(MAX_ROTATED_BACKUPS - 1, 0, -1):
                sfn = AUDIT_LOG_FILE.with_name(f"{AUDIT_LOG_FILE.name}.{i}")
                dfn = AUDIT_LOG_FILE.with_name(f"{AUDIT_LOG_FILE.name}.{i + 1}")
                if sfn.exists():
                    sfn.rename(dfn)
            AUDIT_LOG_FILE.rename(AUDIT_LOG_FILE.with_name(f"{AUDIT_LOG_FILE.name}.1"))
    except Exception:
        pass


def log_turn(
    phone: str,
    user_message: str,
    reply: str,
    intent: str,
    tools_called: list,
    chunks: list,
    duration_ms: float
):
    """
    Appends an immutable audit record for each conversation turn.
    PRIVACY / COMPLIANCE HARDENING:
    Does NOT store raw user_message or bot reply in plain text.
    Stores cryptographically keyed HMAC identifiers and lengths for compliance and forensics.
    """
    AUDIT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    _rotate_audit_log_if_needed()

    msg_bytes = (user_message or "").encode("utf-8")
    reply_bytes = (reply or "").encode("utf-8")
    raw_key = getattr(Config, "AUDIT_HMAC_KEY", None) or Config.SECRET_KEY or "kepler_audit_fallback_key"
    hmac_key = raw_key.encode("utf-8")

    user_hmac = hmac.new(hmac_key, msg_bytes, hashlib.sha256).hexdigest()[:16]
    reply_hmac = hmac.new(hmac_key, reply_bytes, hashlib.sha256).hexdigest()[:16]

    record = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "phone": mask_phone_number(phone) if phone else "unknown",
        "user_message_len": len(user_message or ""),
        "user_message_hmac": user_hmac,
        "user_message_hash": user_hmac,
        "reply_len": len(reply or ""),
        "reply_hmac": reply_hmac,
        "reply_hash": reply_hmac,
        "intent": intent,
        "prompt_version": Config.PROMPT_VERSION,
        "tools_called": [
            {
                "tool": t.get("tool"),
                "status": t.get("result", {}).get("status", "unknown")
            }
            for t in tools_called
        ],
        "rag_retrievals": len(chunks),
        "duration_ms": round(duration_ms, 2)
    }

    with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
