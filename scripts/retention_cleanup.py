#!/usr/bin/env python3
"""
Data Retention Cleanup Job for Kepler Tech Sales AI (cx02-sales-ai).
Purges historical conversation messages, pending states, and audit records
older than the configured retention period (default 90 days).

Usage:
    python scripts/retention_cleanup.py [--days 90] [--dry-run]
"""

import sys
import os
import json
import argparse
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.config import Config
from app.storage.db import get_db_connection


def purge_database_records(conn: sqlite3.Connection, cutoff_iso: str, dry_run: bool = False):
    cur = conn.cursor()
    tables = [
        ("messages", "created_at"),
        ("conversation_states", "updated_at"),
        ("pending_leads", "updated_at"),
        ("handoffs", "created_at"),
        ("quotes", "created_at")
    ]

    report = {}
    for table, col in tables:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} < ?", (cutoff_iso,))
            count = cur.fetchone()[0]
            report[table] = count
            if not dry_run and count > 0:
                cur.execute(f"DELETE FROM {table} WHERE {col} < ?", (cutoff_iso,))
        except sqlite3.OperationalError:
            # Table might not exist in some environments
            report[table] = 0

    if not dry_run:
        conn.commit()

    return report


def purge_audit_log(cutoff_dt: datetime, dry_run: bool = False):
    audit_file = Config.AUDIT_LOG_PATH
    if not audit_file.exists():
        return {"retained": 0, "purged": 0}

    purged = 0
    retained_lines = []

    try:
        with open(audit_file, "r", encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if not line_str:
                    continue
                try:
                    record = json.loads(line_str)
                    ts_str = record.get("timestamp")
                    if ts_str:
                        rec_dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        if rec_dt < cutoff_dt:
                            purged += 1
                            continue
                except Exception:
                    pass
                retained_lines.append(line_str)

        if not dry_run and purged > 0:
            with open(audit_file, "w", encoding="utf-8") as f:
                for l in retained_lines:
                    f.write(l + "\n")

        return {"retained": len(retained_lines), "purged": purged}
    except Exception as e:
        print(f"Error purging audit log: {e}")
        return {"retained": 0, "purged": 0}


def run_cleanup(days: int, dry_run: bool = False):
    cutoff_dt = datetime.now(timezone.utc) - timedelta(days=days)
    cutoff_iso = cutoff_dt.strftime("%Y-%m-%d %H:%M:%S")

    mode_str = "[DRY-RUN] " if dry_run else ""
    print(f"{mode_str}Starting data retention cleanup (Cutoff: {cutoff_iso}, Retention: {days} days)")

    conn = get_db_connection()
    try:
        db_report = purge_database_records(conn, cutoff_iso, dry_run=dry_run)
    finally:
        conn.close()

    audit_report = purge_audit_log(cutoff_dt, dry_run=dry_run)

    print("\nDatabase Purge Results:")
    for table, count in db_report.items():
        print(f"  • {table}: {count} records {'would be deleted' if dry_run else 'deleted'}")

    print("\nAudit Log Purge Results:")
    print(f"  • {audit_report['purged']} log records {'would be pruned' if dry_run else 'pruned'}")
    print(f"  • {audit_report['retained']} log records retained")

    print(f"\n{mode_str}Retention cleanup completed successfully.")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Purge old conversation and audit data.")
    parser.add_argument(
        "--days",
        type=int,
        default=Config.DATA_RETENTION_DAYS,
        help=f"Retention window in days (default: {Config.DATA_RETENTION_DAYS})"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate purge without deleting records"
    )

    args = parser.parse_args()
    return run_cleanup(days=args.days, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
