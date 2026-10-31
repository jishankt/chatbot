"""
app/agent/admission.py — Admission Control & Multi-Worker Concurrency Capping.

Provides distributed lease-based rate limiting across multiple Gunicorn workers
for resource-intensive operations (such as LLM generation and dense vector retrieval).

Key guarantees:
1. Concurrency cap sized from capacity measurements (default 2 concurrent slots).
2. Shared across workers using SQLite leases in llm_generation_leases table.
3. Queue wait budget: if a slot cannot be acquired within QUEUE_WAIT_BUDGET_SECONDS,
   fails fast to deterministic reply with fallback_reason="queue_wait_timeout".
"""

import time
import uuid
import sqlite3
import logging
from typing import Optional

from app.config import Config
from app.storage.db import get_db_connection

logger = logging.getLogger(__name__)

DEFAULT_MAX_CONCURRENT = 2
DEFAULT_QUEUE_WAIT_BUDGET = 1.0
LEASE_DURATION_SECONDS = 30.0  # Safe auto-expiration for stale worker crashes


def get_active_generation_count() -> int:
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        now = time.time()
        cur.execute("SELECT COUNT(*) FROM llm_generation_leases WHERE expires_at > ?", (now,))
        count = cur.fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        logger.warning(f"Failed to check active generation count: {e}")
        return 0


def acquire_generation_slot(worker_id: str = "worker", wait_timeout: Optional[float] = None) -> Optional[str]:
    """
    Attempts to acquire an LLM generation slot.
    Polls until wait_timeout (default Config.QUEUE_WAIT_BUDGET_SECONDS) expires.
    Returns lease_id if acquired, or None if queue budget exceeded.
    """
    max_slots = getattr(Config, "MAX_CONCURRENT_GENERATIONS", DEFAULT_MAX_CONCURRENT)
    timeout = getattr(Config, "QUEUE_WAIT_BUDGET_SECONDS", DEFAULT_QUEUE_WAIT_BUDGET) if wait_timeout is None else wait_timeout

    start_time = time.perf_counter()
    lease_id = str(uuid.uuid4())

    while (time.perf_counter() - start_time) <= timeout:
        now = time.time()
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            # Clean expired stale leases
            cur.execute("DELETE FROM llm_generation_leases WHERE expires_at <= ?", (now,))

            # Check current active leases
            cur.execute("SELECT COUNT(*) FROM llm_generation_leases WHERE expires_at > ?", (now,))
            active_count = cur.fetchone()[0]

            if active_count < max_slots:
                expires_at = now + LEASE_DURATION_SECONDS
                cur.execute(
                    """
                    INSERT INTO llm_generation_leases (lease_id, worker_id, acquired_at, expires_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (lease_id, str(worker_id), now, expires_at)
                )
                conn.commit()
                return lease_id
        except sqlite3.OperationalError:
            pass  # Busy/locked — retry after small sleep
        finally:
            conn.close()

        time.sleep(0.05)

    return None


def release_generation_slot(lease_id: Optional[str]):
    """Releases an acquired generation lease."""
    if not lease_id:
        return
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM llm_generation_leases WHERE lease_id = ?", (lease_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"Failed to release generation lease {lease_id}: {e}")
