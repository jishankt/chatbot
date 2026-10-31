#!/usr/bin/env python3
"""
scripts/check_quote_fils_mismatch.py
Audits quote rows in the database to verify mathematical parity between
legacy REAL columns (subtotal, vat_amount, total) and INTEGER columns (subtotal_fils, vat_fils, total_fils).
Outputs any discrepancy and exits with code 1 if discrepancies are found.
"""

import sys
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.storage.db import get_db_connection

FILS_PER_AED = Decimal("100")


def to_expected_fils(val) -> int:
    if val is None:
        return 0
    return int((Decimal(str(val)) * FILS_PER_AED).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def check_quote_fils_mismatch() -> tuple[int, list]:
    conn = get_db_connection()
    discrepancies = []
    total_inspected = 0

    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, quote_id, subtotal, vat_amount, total, subtotal_fils, vat_fils, total_fils
            FROM quotes
            """
        )
        rows = [dict(r) for r in cur.fetchall()]
        total_inspected = len(rows)

        for r in rows:
            qid = r["quote_id"]
            row_id = r["id"]

            exp_sub = to_expected_fils(r["subtotal"])
            exp_tot = to_expected_fils(r["total"])
            exp_vat = to_expected_fils(r["vat_amount"]) if r["vat_amount"] is not None else None

            act_sub = r["subtotal_fils"]
            act_tot = r["total_fils"]
            act_vat = r["vat_fils"]

            diffs = []
            if act_sub is None or act_sub != exp_sub:
                diffs.append(f"subtotal mismatch: stored_fils={act_sub}, expected_fils={exp_sub} (real={r['subtotal']})")
            if act_tot is None or act_tot != exp_tot:
                diffs.append(f"total mismatch: stored_fils={act_tot}, expected_fils={exp_tot} (real={r['total']})")
            if r["vat_amount"] is not None and (act_vat is None or act_vat != exp_vat):
                diffs.append(f"vat mismatch: stored_fils={act_vat}, expected_fils={exp_vat} (real={r['vat_amount']})")

            if diffs:
                discrepancies.append({
                    "id": row_id,
                    "quote_id": qid,
                    "issues": diffs
                })

        return total_inspected, discrepancies
    finally:
        conn.close()


def main():
    print("Checking quote records for REAL vs INTEGER fils parity...")
    total, discrepancies = check_quote_fils_mismatch()
    print(f"Inspected {total} quote record(s).")

    if not discrepancies:
        print("✅ SUCCESS: 100% parity verified. No fils discrepancies detected.")
        sys.exit(0)
    else:
        print(f"❌ WARNING: Found {len(discrepancies)} quote record(s) with discrepancies:")
        for d in discrepancies[:20]:
            print(f"  • Quote #{d['id']} ({d['quote_id']}): {'; '.join(d['issues'])}")
        if len(discrepancies) > 20:
            print(f"  ... and {len(discrepancies) - 20} more.")
        sys.exit(1)


if __name__ == "__main__":
    main()
