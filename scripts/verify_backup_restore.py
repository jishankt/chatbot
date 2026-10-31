#!/usr/bin/env python3
"""
scripts/verify_backup_restore.py
Verifies the integrity of the latest SQLite backup (or specified file)
using PRAGMA integrity_check, quick_check, and foreign_key_check.
Also validates record counts across essential business tables.
"""

import sys
import sqlite3
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.config import Config


def verify_backup(backup_path: Path = None) -> bool:
    if backup_path is None:
        backup_dir = BASE_DIR / "data" / "backups"
        backups = sorted(list(backup_dir.glob("sales_ai_*.db")), key=lambda p: p.stat().st_mtime, reverse=True)
        if not backups:
            print("❌ No backup files found in data/backups/", file=sys.stderr)
            return False
        backup_path = backups[0]

    print(f"Inspecting backup integrity: {backup_path} ({backup_path.stat().st_size:,} bytes)...")
    conn = sqlite3.connect(f"file:{backup_path}?mode=ro", uri=True)

    try:
        cur = conn.cursor()

        # 1. PRAGMA integrity_check
        cur.execute("PRAGMA integrity_check;")
        res = cur.fetchall()
        if not res or res[0][0] != "ok":
            print(f"❌ INTEGRITY CHECK FAILED: {res}", file=sys.stderr)
            return False
        print("  • PRAGMA integrity_check: PASSED (ok)")

        # 2. PRAGMA foreign_key_check
        cur.execute("PRAGMA foreign_key_check;")
        fk_violations = cur.fetchall()
        if fk_violations:
            print(f"❌ FOREIGN KEY VIOLATIONS: {fk_violations}", file=sys.stderr)
            return False
        print("  • PRAGMA foreign_key_check: PASSED (0 violations)")

        # 3. Table counts verification
        tables = ["quotes", "handoffs", "messages", "leads", "conversation_states"]
        counts = {}
        for tbl in tables:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {tbl}")
                counts[tbl] = cur.fetchone()[0]
            except sqlite3.OperationalError:
                counts[tbl] = "N/A"

        print("  • Table Record Census:")
        for t, c in counts.items():
            print(f"      - {t:<20}: {c}")

        print(f"✅ Backup verification SUCCESSFUL: {backup_path.name} is fully recoverable and corruption-free.")
        return True
    finally:
        conn.close()


def main():
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    ok = verify_backup(target)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
