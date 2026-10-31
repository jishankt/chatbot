#!/usr/bin/env python3
"""
scripts/retry_handoffs.py
Executes periodic retry sweep for failed human handoff notifications.
Designed for execution via cron or systemd timer.
"""

import sys
from pathlib import Path

# Add project root to path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.notifications.salesperson import retry_failed_handoffs_sweep


def main():
    print("Starting human handoff retry sweep...")
    result = retry_failed_handoffs_sweep(limit=50)
    print(
        f"Sweep completed: {result['swept_count']} inspected, "
        f"{result['retried']} retried, {result['succeeded']} succeeded, "
        f"{result.get('permanent_failures', 0)} marked permanent failure."
    )


if __name__ == "__main__":
    main()
