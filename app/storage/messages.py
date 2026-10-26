import sqlite3
from typing import List, Dict, Any, Optional
from app.storage.db import get_db_connection


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
    channel: str = "web"
) -> bool:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO messages (message_id, sender_id, channel, role, content)
            VALUES (?, ?, ?, ?, ?)
            """,
            (message_id, sender_id, channel, role, content)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        # Duplicate message_id
        return False
    finally:
        conn.close()


def get_conversation_history(sender_id: str, limit: int = 8) -> List[Dict[str, str]]:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT role, content FROM messages
            WHERE sender_id = ?
            ORDER BY id DESC LIMIT ?
            """,
            (sender_id, limit)
        )
        rows = cur.fetchall()
        # Reverse to get chronological order
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
    finally:
        conn.close()
