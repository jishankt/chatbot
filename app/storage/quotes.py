import json
from typing import Optional, Dict, Any, List
from app.storage.db import get_db_connection
from app.utils.crypto import encrypt_field, decrypt_field


def _decrypt_quote_dict(d: Dict[str, Any]) -> Dict[str, Any]:
    res = dict(d)
    if "customer_name" in res:
        res["customer_name"] = decrypt_field(res["customer_name"])
    if "phone" in res:
        res["phone"] = decrypt_field(res["phone"])
    if "items_json" in res:
        res["items"] = json.loads(res["items_json"])
    return res


def save_quote(
    quote_id: str,
    items: List[Dict[str, Any]],
    subtotal: float,
    total: float,
    vat_amount: Optional[float] = None,
    sender_id: Optional[str] = None,
    customer_name: Optional[str] = None,
    phone: Optional[str] = None,
    subtotal_fils: Optional[int] = None,
    vat_fils: Optional[int] = None,
    total_fils: Optional[int] = None,
    catalog_version: Optional[str] = "2026.1",
    expires_at: Optional[str] = None
) -> int:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO quotes (
                quote_id, sender_id, customer_name, phone, items_json,
                subtotal, vat_amount, total,
                subtotal_fils, vat_fils, total_fils, catalog_version, expires_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                quote_id,
                sender_id,
                encrypt_field(customer_name),
                encrypt_field(phone),
                json.dumps(items),
                subtotal,
                vat_amount,
                total,
                subtotal_fils,
                vat_fils,
                total_fils,
                catalog_version,
                expires_at
            )
        )
        conn.commit()
        return cur.lastrowid or 0
    finally:
        conn.close()


def get_quote(quote_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM quotes WHERE quote_id = ?", (quote_id,))
        row = cur.fetchone()
        if row:
            return _decrypt_quote_dict(dict(row))
        return None
    finally:
        conn.close()


def get_latest_quote_by_sender(sender_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT * FROM quotes
            WHERE sender_id = ?
            ORDER BY created_at DESC LIMIT 1
            """,
            (sender_id,)
        )
        row = cur.fetchone()
        if row:
            return _decrypt_quote_dict(dict(row))
        return None
    finally:
        conn.close()
