#!/usr/bin/env python3
"""
scripts/backfill_quote_fils.py
Backfills legacy quote records that have NULL integer fils columns
(subtotal_fils, vat_fils, total_fils) using Decimal arithmetic (ROUND_HALF_UP).
"""

import sys
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.storage.db import get_db_connection

FILS_PER_AED = Decimal("100")


def to_fils(val) -> int:
    if val is None:
        return 0
    return int((Decimal(str(val)) * FILS_PER_AED).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def backfill_quote_fils(dry_run: bool = False) -> tuple[int, int]:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, quote_id, subtotal, vat_amount, total, subtotal_fils, vat_fils, total_fils
            FROM quotes
            WHERE subtotal_fils IS NULL OR total_fils IS NULL
            """
        )
        rows = [dict(r) for r in cur.fetchall()]
        total_found = len(rows)
        updated_count = 0

        for r in rows:
            sub_fils = to_fils(r["subtotal"])
            vat_fils = to_fils(r["vat_amount"]) if r["vat_amount"] is not None else None
            tot_fils = to_fils(r["total"])

            if not dry_run:
                cur.execute(
                    """
                    UPDATE quotes
                    SET subtotal_fils = ?, vat_fils = ?, total_fils = ?
                    WHERE id = ?
                    """,
                    (sub_fils, vat_fils, tot_fils, r["id"])
                )
            updated_count += 1

        if not dry_run:
            conn.commit()

        return total_found, updated_count
    finally:
        conn.close()


def main():
    dry_run = "--dry-run" in sys.argv
    print(f"Starting quote integer fils backfill (dry_run={dry_run})...")
    found, updated = backfill_quote_fils(dry_run=dry_run)
    print(f"Backfill finished: {found} legacy rows identified, {updated} rows updated.")


if __name__ == "__main__":
    main()
