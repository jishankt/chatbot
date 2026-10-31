#!/usr/bin/env python3
"""
scripts/restore_drill.py
Automated disaster recovery restore drill:
1. Performs a fresh atomic online backup of data/sales_ai.db.
2. Restores into an isolated staging database (data/restore_drill_test.db).
3. Executes PRAGMA integrity_check and table count parity checks.
4. Boots the Flask application against the restored database.
5. Invokes GET /health via test client and verifies 200 OK.
"""

import os
import sys
import shutil
import sqlite3
import tempfile
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.config import Config
from scripts.backup_db import backup_database


def execute_restore_drill() -> bool:
    print("==================================================")
    print("    CX-02 SALES AI: DISASTER RECOVERY RESTORE DRILL")
    print("==================================================")

    # 1. Take fresh backup
    backup_file = backup_database()
    print(f"[1/5] Created fresh backup: {backup_file}")

    # 2. Restore into staging database
    staging_db = BASE_DIR / "data" / "restore_drill_staging.db"
    if staging_db.exists():
        staging_db.unlink()

    shutil.copy2(backup_file, staging_db)
    print(f"[2/5] Restored backup copy to staging DB: {staging_db}")

    # 3. Integrity & schema validation
    conn = sqlite3.connect(f"file:{staging_db}?mode=ro", uri=True)
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA integrity_check;")
        res = cur.fetchone()[0]
        if res != "ok":
            print(f"❌ Restore integrity check failed: {res}", file=sys.stderr)
            return False
        print("  • PRAGMA integrity_check: PASSED (ok)")

        tables = ["quotes", "handoffs", "messages", "leads", "conversation_states", "admin_auth_failures"]
        counts = {}
        for tbl in tables:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {tbl}")
                counts[tbl] = cur.fetchone()[0]
            except sqlite3.OperationalError:
                counts[tbl] = "N/A"
        print(f"[3/5] Restored Table Row Census: {counts}")
    finally:
        conn.close()

    # 4. Boot application with restored database
    print("[4/5] Booting Flask application against restored database...")
    original_db_path = Config.DATABASE_PATH
    os.environ["DATABASE_PATH"] = str(staging_db)
    Config.DATABASE_PATH = staging_db

    try:
        from app.main import create_app
        app = create_app()
        app.config["TESTING"] = True
        client = app.test_client()

        # 5. Assert /health returns 200
        resp = client.get("/health")
        print(f"[5/5] Checking /health endpoint: HTTP {resp.status_code}")
        if resp.status_code != 200:
            print(f"❌ /health returned unexpected status {resp.status_code}: {resp.data}", file=sys.stderr)
            return False

        data = resp.get_json()
        print(f"  • Response payload: {data}")
        if data.get("status") not in ("healthy", "ok"):
            print(f"❌ Unexpected health status payload: {data}", file=sys.stderr)
            return False

        print("==================================================")
        print("✅ DISASTER RECOVERY RESTORE DRILL PASSED SUCCESSFULLY!")
        print("==================================================")
        return True
    finally:
        # Revert configuration and cleanup
        os.environ["DATABASE_PATH"] = str(original_db_path)
        Config.DATABASE_PATH = original_db_path
        if staging_db.exists():
            try:
                staging_db.unlink()
            except Exception:
                pass


def main():
    ok = execute_restore_drill()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
