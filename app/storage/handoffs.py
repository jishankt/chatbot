from typing import Optional, Dict, Any, List
from app.storage.db import get_db_connection


def save_handoff(
    reason: str,
    summary: Optional[str] = None,
    phone: Optional[str] = None,
    sender_id: Optional[str] = None,
    status: str = "pending"
) -> int:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO handoffs (sender_id, reason, summary, phone, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (sender_id, reason, summary, phone, status)
        )
        conn.commit()
        return cur.lastrowid or 0
    finally:
        conn.close()


def get_handoffs(limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM handoffs ORDER BY created_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_latest_handoff_by_sender(sender_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT * FROM handoffs
            WHERE sender_id = ?
            ORDER BY created_at DESC LIMIT 1
            """,
            (sender_id,)
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()
