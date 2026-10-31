from typing import Optional, Dict, Any, List
from app.storage.db import get_db_connection
from app.utils.crypto import encrypt_field, decrypt_field


def _decrypt_lead_dict(d: Dict[str, Any]) -> Dict[str, Any]:
    res = dict(d)
    if "name" in res:
        res["name"] = decrypt_field(res["name"])
    if "phone" in res:
        res["phone"] = decrypt_field(res["phone"])
    if "email" in res:
        res["email"] = decrypt_field(res["email"])
    return res


def save_lead(
    sender_id: Optional[str] = None,
    name: Optional[str] = None,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    notes: Optional[str] = None,
    status: str = "new"
) -> int:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO leads (sender_id, name, phone, email, notes, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                sender_id,
                encrypt_field(name),
                encrypt_field(phone),
                encrypt_field(email),
                notes,
                status
            )
        )
        conn.commit()
        return cur.lastrowid or 0
    finally:
        conn.close()


def get_leads(limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM leads ORDER BY created_at DESC LIMIT ?", (limit,))
        return [_decrypt_lead_dict(dict(r)) for r in cur.fetchall()]
    finally:
        conn.close()


def get_latest_lead_by_sender(sender_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT * FROM leads
            WHERE sender_id = ?
            ORDER BY created_at DESC LIMIT 1
            """,
            (sender_id,)
        )
        row = cur.fetchone()
        return _decrypt_lead_dict(dict(row)) if row else None
    finally:
        conn.close()


def set_pending_lead(
    sender_id: str,
    stage: str,
    temp_name: Optional[str] = None,
    temp_phone: Optional[str] = None,
    last_intent: Optional[str] = None
) -> None:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO pending_leads (sender_id, stage, temp_name, temp_phone, last_intent, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(sender_id) DO UPDATE SET
                stage = excluded.stage,
                temp_name = COALESCE(excluded.temp_name, pending_leads.temp_name),
                temp_phone = COALESCE(excluded.temp_phone, pending_leads.temp_phone),
                last_intent = COALESCE(excluded.last_intent, pending_leads.last_intent),
                updated_at = CURRENT_TIMESTAMP
            """,
            (sender_id, stage, encrypt_field(temp_name), encrypt_field(temp_phone), last_intent)
        )
        conn.commit()
    finally:
        conn.close()


def get_pending_lead(sender_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM pending_leads WHERE sender_id = ?", (sender_id,))
        row = cur.fetchone()
        if not row:
            return None
        d = dict(row)
        if "temp_name" in d:
            d["temp_name"] = decrypt_field(d["temp_name"])
        if "temp_phone" in d:
            d["temp_phone"] = decrypt_field(d["temp_phone"])
        return d
    finally:
        conn.close()


def clear_pending_lead(sender_id: str) -> None:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM pending_leads WHERE sender_id = ?", (sender_id,))
        conn.commit()
    finally:
        conn.close()
