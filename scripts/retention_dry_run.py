#!/usr/bin/env python3
"""
scripts/retention_dry_run.py
Performs a non-destructive audit of data retention compliance across all
conversation, quotation, and handoff tables based on DATA_RETENTION_DAYS.
Reports exactly how many rows exceed the retention threshold without deleting anything.
"""

import sys
import sqlite3
import datetime
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.config import Config
from app.storage.db import get_db_connection


def retention_dry_run(retention_days: int = None) -> dict:
    days = retention_days or Config.DATA_RETENTION_DAYS
    cutoff_dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    cutoff_str = cutoff_dt.strftime("%Y-%m-%d %H:%M:%S")

    print(f"========================================================")
    print(f"Data Retention Audit (DRY-RUN)")
    print(f"Configured Retention Window: {days} days")
    print(f"Cutoff Timestamp (UTC)     : {cutoff_str}")
    print(f"========================================================")

    tables = [
        ("messages", "timestamp"),
        ("quotes", "created_at"),
        ("handoffs", "created_at"),
        ("leads", "created_at"),
        ("pending_leads", "updated_at")
    ]

    conn = get_db_connection()
    audit_report = {}

    try:
        cur = conn.cursor()
        for table, date_col in tables:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                total_rows = cur.fetchone()[0]

                cur.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE {date_col} < ?",
                    (cutoff_str,)
                )
                expired_rows = cur.fetchone()[0]

                audit_report[table] = {
                    "total": total_rows,
                    "expired": expired_rows,
                    "retained": total_rows - expired_rows
                }

                print(f"  • {table:<16}: {total_rows:>5} total | {expired_rows:>5} expired (> {days}d) | {total_rows - expired_rows:>5} retained")
            except sqlite3.OperationalError as e:
                print(f"  • {table:<16}: Skipped ({e})")
    finally:
        conn.close()

    print(f"========================================================")
    print("✅ Dry-run completed. NO records were deleted or modified.")
    return audit_report


def main():
    retention_dry_run()


if __name__ == "__main__":
    main()
