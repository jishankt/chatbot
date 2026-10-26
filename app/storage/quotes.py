import json
from typing import Optional, Dict, Any, List
from app.storage.db import get_db_connection


def save_quote(
    quote_id: str,
    items: List[Dict[str, Any]],
    subtotal: float,
    total: float,
    vat_amount: Optional[float] = None,
    sender_id: Optional[str] = None,
    customer_name: Optional[str] = None,
    phone: Optional[str] = None
) -> int:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO quotes (quote_id, sender_id, customer_name, phone, items_json, subtotal, vat_amount, total)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (quote_id, sender_id, customer_name, phone, json.dumps(items), subtotal, vat_amount, total)
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
            d = dict(row)
            d["items"] = json.loads(d["items_json"])
            return d
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
            d = dict(row)
            d["items"] = json.loads(d["items_json"])
            return d
        return None
    finally:
        conn.close()
