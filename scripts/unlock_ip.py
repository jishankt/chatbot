#!/usr/bin/env python3
"""
scripts/unlock_ip.py
CLI tool to unlock an IP address locked out due to repeated failed admin authentication attempts.
Usage:
    ./venv/bin/python scripts/unlock_ip.py <IP_ADDRESS>
"""

import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.storage.db import get_db_connection


def unlock_ip(ip: str) -> int:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM admin_auth_failures WHERE ip = ?", (ip,))
        count = cur.rowcount
        conn.commit()
        return count
    finally:
        conn.close()


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/unlock_ip.py <IP_ADDRESS>", file=sys.stderr)
        sys.exit(1)

    ip = sys.argv[1].strip()
    removed = unlock_ip(ip)
    print(f"✅ Successfully unlocked IP '{ip}' (removed {removed} failure record(s)).")


if __name__ == "__main__":
    main()
