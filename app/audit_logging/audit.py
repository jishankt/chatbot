import json
import datetime
from pathlib import Path
from typing import Dict, Any
from app.config import Config

AUDIT_LOG_FILE = Config.AUDIT_LOG_PATH


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
    """
    AUDIT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "phone": phone,
        "user_message": user_message,
        "reply": reply,
        "intent": intent,
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
