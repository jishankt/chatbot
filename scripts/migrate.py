#!/usr/bin/env python3
"""
Simple SQLite migration runner for Kepler Tech Sales AI.
Applies pending SQL migration files in migrations/*.sql in alphabetical order.
"""

import sys
import sqlite3
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.config import Config
from app.storage.db import get_db_connection

MIGRATIONS_DIR = BASE_DIR / "migrations"


def run_migrations(db_path: Path = None):
    conn = get_db_connection(db_path)
    cur = conn.cursor()

    # Ensure schema_migrations tracker table exists
    cur.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version VARCHAR(255) PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

    cur.execute("SELECT version FROM schema_migrations")
    applied = set(row[0] for row in cur.fetchall())

    if not MIGRATIONS_DIR.exists():
        print(f"Migrations directory does not exist: {MIGRATIONS_DIR}")
        return

    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not migration_files:
        print("No migration files found.")
        return

    pending = [f for f in migration_files if f.name not in applied]
    if not pending:
        print(f"All {len(applied)} migrations already applied. Database is up to date.")
        return

    print(f"Found {len(pending)} pending migration(s):")
    for sql_file in pending:
        version = sql_file.name
        print(f"  -> Applying: {version}...")
        sql_content = sql_file.read_text(encoding="utf-8")
        
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.executescript(sql_content)
            conn.execute("INSERT INTO schema_migrations (version) VALUES (?)", (version,))
            conn.commit()
            print(f"  ✓ Applied: {version}")
        except Exception as e:
            conn.rollback()
            print(f"  ✗ Failed to apply {version}: {e}", file=sys.stderr)
            raise


if __name__ == "__main__":
    try:
        run_migrations()
        print("Migration run completed successfully.")
    except Exception as e:
        sys.exit(1)
