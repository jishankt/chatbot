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
    if "reply_source" not in cols:
        cur.execute("ALTER TABLE messages ADD COLUMN reply_source TEXT")
    if "fallback_reason" not in cols:
        cur.execute("ALTER TABLE messages ADD COLUMN fallback_reason TEXT")
    if "is_test" not in cols:
        cur.execute("ALTER TABLE messages ADD COLUMN is_test INTEGER DEFAULT 0")

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
            subtotal_fils INTEGER,
            vat_fils INTEGER,
            total_fils INTEGER,
            catalog_version TEXT DEFAULT '2026.1',
            expires_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Check if existing quotes table needs migration
    cur.execute("PRAGMA table_info(quotes)")
    q_cols = [r["name"] for r in cur.fetchall()]
    if "subtotal_fils" not in q_cols:
        cur.execute("ALTER TABLE quotes ADD COLUMN subtotal_fils INTEGER")
    if "vat_fils" not in q_cols:
        cur.execute("ALTER TABLE quotes ADD COLUMN vat_fils INTEGER")
    if "total_fils" not in q_cols:
        cur.execute("ALTER TABLE quotes ADD COLUMN total_fils INTEGER")
    if "catalog_version" not in q_cols:
        cur.execute("ALTER TABLE quotes ADD COLUMN catalog_version TEXT DEFAULT '2026.1'")
    if "expires_at" not in q_cols:
        cur.execute("ALTER TABLE quotes ADD COLUMN expires_at TIMESTAMP")

    # Human Handoffs
    cur.execute("""
        CREATE TABLE IF NOT EXISTS handoffs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id TEXT,
            reason TEXT NOT NULL,
            summary TEXT,
            phone TEXT,
            status TEXT DEFAULT 'pending',
            notification_status TEXT DEFAULT 'pending',
            notification_sent_at TIMESTAMP,
            notification_error TEXT,
            retry_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Check if existing handoffs table needs migration
    cur.execute("PRAGMA table_info(handoffs)")
    h_cols = [r["name"] for r in cur.fetchall()]
    if "notification_status" not in h_cols:
        cur.execute("ALTER TABLE handoffs ADD COLUMN notification_status TEXT DEFAULT 'pending'")
    if "notification_sent_at" not in h_cols:
        cur.execute("ALTER TABLE handoffs ADD COLUMN notification_sent_at TIMESTAMP")
    if "notification_error" not in h_cols:
        cur.execute("ALTER TABLE handoffs ADD COLUMN notification_error TEXT")
    if "retry_count" not in h_cols:
        cur.execute("ALTER TABLE handoffs ADD COLUMN retry_count INTEGER DEFAULT 0")

    # Customer Opt-in/Opt-out Consents (WhatsApp STOP / WP13)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS customer_consents (
            sender_id TEXT PRIMARY KEY,
            phone TEXT,
            opted_out INTEGER DEFAULT 0,
            opt_out_timestamp TIMESTAMP,
            consent_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            notes TEXT
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
            version INTEGER NOT NULL DEFAULT 1,
            quantity INTEGER,
            budget REAL,
            language TEXT DEFAULT 'en',
            current_product TEXT,
            rolling_summary TEXT,
            slots_json TEXT DEFAULT '{}',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("PRAGMA table_info(conversation_states)")
    cs_cols = [r["name"] for r in cur.fetchall()]
    if "quantity" not in cs_cols:
        cur.execute("ALTER TABLE conversation_states ADD COLUMN quantity INTEGER")
    if "budget" not in cs_cols:
        cur.execute("ALTER TABLE conversation_states ADD COLUMN budget REAL")
    if "language" not in cs_cols:
        cur.execute("ALTER TABLE conversation_states ADD COLUMN language TEXT DEFAULT 'en'")
    if "current_product" not in cs_cols:
        cur.execute("ALTER TABLE conversation_states ADD COLUMN current_product TEXT")
    if "rolling_summary" not in cs_cols:
        cur.execute("ALTER TABLE conversation_states ADD COLUMN rolling_summary TEXT")
    if "slots_json" not in cs_cols:
        cur.execute("ALTER TABLE conversation_states ADD COLUMN slots_json TEXT DEFAULT '{}'")

    # Multi-worker DB-backed admin authentication failures
    cur.execute("""
        CREATE TABLE IF NOT EXISTS admin_auth_failures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT NOT NULL,
            endpoint TEXT NOT NULL DEFAULT '/admin',
            attempt_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_auth_failures_ip_time ON admin_auth_failures(ip, attempt_time)")

    # Admission control: multi-process LLM generation concurrency leases
    cur.execute("""
        CREATE TABLE IF NOT EXISTS llm_generation_leases (
            lease_id TEXT PRIMARY KEY,
            worker_id TEXT NOT NULL,
            acquired_at REAL NOT NULL,
            expires_at REAL NOT NULL
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_leases_expires ON llm_generation_leases(expires_at)")

    conn.commit()
    conn.close()


def get_db_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    path = db_path or Config.DATABASE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    first_time = not path.exists()
    
    conn = sqlite3.connect(str(path), timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=15000;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA synchronous=NORMAL;")

    if first_time:
        init_db(path)
    return conn

