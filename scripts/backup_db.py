#!/usr/bin/env python3
"""
scripts/backup_db.py
Performs a live, consistent online backup of the SQLite database
using the native sqlite3 online backup API (.backup), ensuring safe,
non-blocking snapshots during active application writes.
"""

import os
import sys
import sqlite3
import datetime
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.config import Config


def backup_database(destination_dir: Path = None, max_retained_days: int = 14) -> Path:
    source_db_path = Path(Config.DATABASE_PATH)
    if not source_db_path.exists():
        raise FileNotFoundError(f"Database not found at {source_db_path}")

    backup_dir = destination_dir or (BASE_DIR / "data" / "backups")
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    target_backup_path = backup_dir / f"sales_ai_{timestamp}.db"

    print(f"Starting online SQLite backup from {source_db_path} -> {target_backup_path}...")
    source_conn = sqlite3.connect(str(source_db_path), timeout=30.0)
    target_conn = sqlite3.connect(str(target_backup_path))

    try:
        # sqlite3 .backup API copies pages atomically with retry handling
        source_conn.backup(target_conn, pages=100, sleep=0.01)
        print(f"✅ Backup completed successfully: {target_backup_path} ({target_backup_path.stat().st_size:,} bytes)")
    finally:
        target_conn.close()
        source_conn.close()

    # Retention rotation of old backups
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=max_retained_days)
    for f in backup_dir.glob("sales_ai_*.db"):
        try:
            mtime = datetime.datetime.fromtimestamp(f.stat().st_mtime, tz=datetime.timezone.utc)
            if mtime < cutoff:
                print(f"Purging old backup: {f.name} (age > {max_retained_days} days)")
                f.unlink()
        except Exception as e:
            print(f"Warning: could not prune {f.name}: {e}", file=sys.stderr)

    return target_backup_path


def main():
    try:
        dest = backup_database()
        print(f"Backup operation successful: {dest}")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Backup failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
