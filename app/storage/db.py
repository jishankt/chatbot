import sqlite3
from pathlib import Path
from typing import Optional
from app.config import Config


def init_db(db_path: Optional[Path] = None) -> None:
    path = db_path or Config.DATABASE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Message log & deduplication
    cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id TEXT UNIQUE,
            sender_id TEXT NOT NULL,
            channel TEXT NOT NULL DEFAULT 'web',
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Check if existing messages table needs migration
    cur.execute("PRAGMA table_info(messages)")
    cols = [r["name"] for r in cur.fetchall()]
    if "sender_id" not in cols:
        cur.execute("ALTER TABLE messages ADD COLUMN sender_id TEXT DEFAULT 'web_user'")
    if "message_id" not in cols:
        cur.execute("ALTER TABLE messages ADD COLUMN message_id TEXT")
    if "channel" not in cols:
        cur.execute("ALTER TABLE messages ADD COLUMN channel TEXT DEFAULT 'web'")

    # Customer leads
    cur.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id TEXT,
            name TEXT,
            phone TEXT,
            email TEXT,
            notes TEXT,
            status TEXT DEFAULT 'new',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Generated Quotes
    cur.execute("""
        CREATE TABLE IF NOT EXISTS quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quote_id TEXT UNIQUE NOT NULL,
            sender_id TEXT,
            customer_name TEXT,
            phone TEXT,
            items_json TEXT NOT NULL,
            subtotal REAL NOT NULL,
            vat_amount REAL,
            total REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Human Handoffs
    cur.execute("""
        CREATE TABLE IF NOT EXISTS handoffs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id TEXT,
            reason TEXT NOT NULL,
            summary TEXT,
            phone TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Multi-turn lead capture state machine
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pending_leads (
            sender_id TEXT PRIMARY KEY,
            stage TEXT NOT NULL,
            temp_name TEXT,
            temp_phone TEXT,
            last_intent TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Sales policy state machine
    cur.execute("""
        CREATE TABLE IF NOT EXISTS conversation_states (
            sender_id TEXT PRIMARY KEY,
            current_state TEXT NOT NULL DEFAULT 'GREETING',
            turn_count INTEGER NOT NULL DEFAULT 0,
            business_type TEXT,
            delivery_destination TEXT,
            target_sku TEXT,
            quote_id TEXT,
            discovery_questions_asked TEXT DEFAULT '[]',
            last_intent TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


def get_db_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    path = db_path or Config.DATABASE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    first_time = not path.exists()
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    if first_time:
        conn.close()
        init_db(path)
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
    else:
        # Check if quotes table exists or if messages has sender_id
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(messages)")
        cols = [r["name"] for r in cur.fetchall()]
        if "sender_id" not in cols:
            conn.close()
            init_db(path)
            conn = sqlite3.connect(str(path))
            conn.row_factory = sqlite3.Row
    return conn
