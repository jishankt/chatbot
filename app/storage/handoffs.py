from typing import Optional, Dict, Any, List
from app.storage.db import get_db_connection
from app.utils.crypto import encrypt_field, decrypt_field


def _decrypt_handoff_dict(d: Dict[str, Any]) -> Dict[str, Any]:
    res = dict(d)
    if "phone" in res:
        res["phone"] = decrypt_field(res["phone"])
    return res


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
            (sender_id, reason, summary, encrypt_field(phone), status)
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
        return [_decrypt_handoff_dict(dict(r)) for r in cur.fetchall()]
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
        return _decrypt_handoff_dict(dict(row)) if row else None
    finally:
        conn.close()


def update_handoff_notification(
    handoff_id: int,
    status: str,
    error: Optional[str] = None
) -> None:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE handoffs
            SET notification_status = ?,
                notification_sent_at = CURRENT_TIMESTAMP,
                notification_error = ?
            WHERE id = ?
            """,
            (status, error, handoff_id)
        )
        conn.commit()
    finally:
        conn.close()


def get_pending_handoffs_for_retry(limit: int = 50) -> List[Dict[str, Any]]:
    """
    Retrieves handoffs eligible for notification retry, excluding resolved, sent,
    permanent_failure, alert_abandoned, and archived_test records.
    """
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, reason, summary, phone, sender_id, COALESCE(retry_count, 0) as retry_count, status
            FROM handoffs
            WHERE status NOT IN ('permanent_failure', 'alert_abandoned', 'resolved', 'sent', 'archived_test')
              AND (
                  notification_status LIKE '%failed%'
                  OR notification_status LIKE '%no_successful_channel%'
                  OR status = 'failed_all_channels'
                  OR notification_status = 'pending'
              )
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,)
        )
        return [_decrypt_handoff_dict(dict(r)) for r in cur.fetchall()]
    finally:
        conn.close()


record_handoff = save_handoff

