from typing import Optional, Dict, Any
from app.storage.db import get_db_connection
from app.utils.crypto import encrypt_field, decrypt_field


def is_opted_out(sender_id: str) -> bool:
    """Returns True if customer has explicitly opted out via STOP / unsubscribe."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT opted_out FROM customer_consents WHERE sender_id = ?",
            (sender_id,)
        )
        row = cur.fetchone()
        if row and row["opted_out"]:
            return True
        return False
    finally:
        conn.close()


def set_opt_out(
    sender_id: str,
    phone: Optional[str] = None,
    notes: str = "WhatsApp STOP / unsubscribe requested"
) -> None:
    """Records opt-out for customer and marks them inactive for automated sales messages."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO customer_consents (sender_id, phone, opted_out, opt_out_timestamp, notes)
            VALUES (?, ?, 1, CURRENT_TIMESTAMP, ?)
            ON CONFLICT(sender_id) DO UPDATE SET
                opted_out = 1,
                opt_out_timestamp = CURRENT_TIMESTAMP,
                notes = excluded.notes,
                phone = COALESCE(excluded.phone, customer_consents.phone)
            """,
            (sender_id, encrypt_field(phone), notes)
        )
        conn.commit()
    finally:
        conn.close()


def set_opt_in(
    sender_id: str,
    phone: Optional[str] = None,
    notes: str = "Customer re-subscribed via START / opt-in"
) -> None:
    """Records opt-in for customer, re-enabling automated sales messages."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO customer_consents (sender_id, phone, opted_out, consent_timestamp, notes)
            VALUES (?, ?, 0, CURRENT_TIMESTAMP, ?)
            ON CONFLICT(sender_id) DO UPDATE SET
                opted_out = 0,
                consent_timestamp = CURRENT_TIMESTAMP,
                notes = excluded.notes,
                phone = COALESCE(excluded.phone, customer_consents.phone)
            """,
            (sender_id, encrypt_field(phone), notes)
        )
        conn.commit()
    finally:
        conn.close()


def get_consent_status(sender_id: str) -> Optional[Dict[str, Any]]:
    """Fetches customer consent record."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM customer_consents WHERE sender_id = ?",
            (sender_id,)
        )
        row = cur.fetchone()
        if not row:
            return None
        res = dict(row)
        if "phone" in res:
            res["phone"] = decrypt_field(res["phone"])
        return res
    finally:
        conn.close()
