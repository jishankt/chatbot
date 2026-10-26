import sqlite3
import json
import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from app.config import Config

SESSION_TIMEOUT_HOURS = 24
MAX_HISTORY_TURNS = 10


class SessionManager:
    def __init__(self, db_path: Path = None):
        self.db_path = db_path or Config.DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        with self.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    phone TEXT PRIMARY KEY,
                    created_at TIMESTAMP,
                    last_activity TIMESTAMP,
                    quote_state TEXT DEFAULT '{}'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone TEXT,
                    role TEXT,
                    content TEXT,
                    timestamp TIMESTAMP,
                    FOREIGN KEY (phone) REFERENCES sessions(phone)
                )
            """)
            conn.commit()

    def get_or_create_session(self, phone: str) -> Dict[str, Any]:
        now = datetime.datetime.now(datetime.timezone.utc)
        cutoff = now - datetime.timedelta(hours=SESSION_TIMEOUT_HOURS)

        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM sessions WHERE phone = ?", (phone,))
            row = cur.fetchone()

            if row:
                last_activity = datetime.datetime.fromisoformat(row["last_activity"])
                if last_activity < cutoff:
                    # Expire old session: clear messages and reset
                    cur.execute("DELETE FROM messages WHERE phone = ?", (phone,))
                    cur.execute(
                        "UPDATE sessions SET created_at = ?, last_activity = ?, quote_state = '{}' WHERE phone = ?",
                        (now.isoformat(), now.isoformat(), phone)
                    )
                    conn.commit()
                    return {"phone": phone, "quote_state": {}}
                else:
                    cur.execute("UPDATE sessions SET last_activity = ? WHERE phone = ?", (now.isoformat(), phone))
                    conn.commit()
                    return {"phone": phone, "quote_state": json.loads(row["quote_state"] or "{}")}
            else:
                cur.execute(
                    "INSERT INTO sessions (phone, created_at, last_activity, quote_state) VALUES (?, ?, ?, '{}')",
                    (phone, now.isoformat(), now.isoformat())
                )
                conn.commit()
                return {"phone": phone, "quote_state": {}}

    def append_message(self, phone: str, role: str, content: str):
        self.get_or_create_session(phone)
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self.get_connection() as conn:
            conn.execute(
                "INSERT INTO messages (phone, role, content, timestamp) VALUES (?, ?, ?, ?)",
                (phone, role, content, now)
            )
            conn.commit()

    def get_history(self, phone: str, limit: int = MAX_HISTORY_TURNS) -> List[Dict[str, str]]:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT role, content FROM messages WHERE phone = ? ORDER BY id DESC LIMIT ?",
                (phone, limit)
            )
            rows = cur.fetchall()
            history = [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
            return history

    def update_quote_state(self, phone: str, quote_data: Dict[str, Any]):
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE sessions SET quote_state = ? WHERE phone = ?",
                (json.dumps(quote_data), phone)
            )
            conn.commit()
