import sqlite3
from typing import List, Dict, Any, Optional
from app.storage.db import get_db_connection
from app.utils.crypto import encrypt_field, decrypt_field


def is_message_duplicate(message_id: str) -> bool:
    if not message_id:
        return False
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM messages WHERE message_id = ?", (message_id,))
        row = cur.fetchone()
        return row is not None
    finally:
        conn.close()


def log_message(
    sender_id: str,
    role: str,
    content: str,
    message_id: Optional[str] = None,
    channel: str = "web",
    reply_source: Optional[str] = None,
    fallback_reason: Optional[str] = None
) -> bool:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(messages)")
        cols = [r["name"] for r in cur.fetchall()]
        time_col = "timestamp" if "timestamp" in cols else ("created_at" if "created_at" in cols else None)
        stored_content = encrypt_field(content)

        fields = ["message_id", "sender_id", "channel", "role", "content"]
        values = [message_id, sender_id, channel, role, stored_content]

        if "reply_source" in cols:
            fields.append("reply_source")
            values.append(reply_source)
        if "fallback_reason" in cols:
            fields.append("fallback_reason")
            values.append(fallback_reason)
        if "is_test" in cols:
            is_test_val = 1 if (sender_id.startswith("test_") or sender_id.startswith("eval_") or "test" in sender_id.lower() or "eval" in sender_id.lower()) else 0
            fields.append("is_test")
            values.append(is_test_val)
        if time_col:
            fields.append(time_col)
            # Use raw SQL datetime('now')
            placeholders = ", ".join(["?" for _ in values] + ["datetime('now')"])
        else:
            placeholders = ", ".join(["?" for _ in values])

        cur.execute(
            f"INSERT INTO messages ({', '.join(fields)}) VALUES ({placeholders})",
            values
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        # Duplicate message_id
        return False
    finally:
        conn.close()


def get_conversation_history(sender_id: str, limit: int = 50, include_timestamp: bool = False) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(messages)")
        cols = [r["name"] for r in cur.fetchall()]
        time_col = "timestamp" if "timestamp" in cols else ("created_at" if "created_at" in cols else "id")
        cur.execute(
            f"""
            SELECT role, content, {time_col} AS ts FROM messages
            WHERE sender_id = ?
            ORDER BY {time_col} DESC, id DESC LIMIT ?
            """,
            (sender_id, limit)
        )
        rows = cur.fetchall()
        # Reverse to get chronological order and decrypt content seamlessly
        if include_timestamp:
            return [{"role": r["role"], "content": decrypt_field(r["content"]), "timestamp": r["ts"]} for r in reversed(rows)]
        return [{"role": r["role"], "content": decrypt_field(r["content"])} for r in reversed(rows)]
    finally:
        conn.close()
