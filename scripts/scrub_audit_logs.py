#!/usr/bin/env python3
"""
scripts/scrub_audit_logs.py
Scans and scrubs legacy plaintext audit log files.
Replaces plaintext message bodies with HMAC-SHA256 digests and lengths,
and ensures phone numbers are masked.
"""

import os
import sys
import json
import hmac
import hashlib
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.config import Config
from app.utils.phone import mask_phone_number


def scrub_record(rec: dict, hmac_key: bytes) -> tuple[dict, bool]:
    changed = False

    # 1. Scrub user message
    if "user_message" in rec:
        raw_msg = rec.pop("user_message")
        msg_bytes = str(raw_msg).encode("utf-8")
        rec["user_message_len"] = len(raw_msg)
        rec["user_message_hmac"] = hmac.new(hmac_key, msg_bytes, hashlib.sha256).hexdigest()[:16]
        rec["user_message_hash"] = rec["user_message_hmac"]
        changed = True

    # 2. Scrub bot reply
    if "reply" in rec:
        raw_reply = rec.pop("reply")
        reply_bytes = str(raw_reply).encode("utf-8")
        rec["reply_len"] = len(raw_reply)
        rec["reply_hmac"] = hmac.new(hmac_key, reply_bytes, hashlib.sha256).hexdigest()[:16]
        rec["reply_hash"] = rec["reply_hmac"]
        changed = True

    # 3. Ensure HMAC is present if plain SHA256 was used
    if "user_message_hash" in rec and "user_message_hmac" not in rec:
        rec["user_message_hmac"] = rec["user_message_hash"]
        changed = True
    if "reply_hash" in rec and "reply_hmac" not in rec:
        rec["reply_hmac"] = rec["reply_hash"]
        changed = True

    # 4. Mask phone number if plaintext
    if "phone" in rec and rec["phone"] and "***" not in rec["phone"]:
        rec["phone"] = mask_phone_number(rec["phone"])
        changed = True

    return rec, changed


def scrub_file(file_path: Path, hmac_key: bytes, dry_run: bool = False) -> tuple[int, int]:
    if not file_path.exists():
        return 0, 0

    lines = file_path.read_text(encoding="utf-8").splitlines()
    scrubbed_lines = []
    modified_count = 0

    for idx, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            rec, changed = scrub_record(rec, hmac_key)
            if changed:
                modified_count += 1
            scrubbed_lines.append(json.dumps(rec))
        except Exception as e:
            print(f"Warning: skipping invalid JSON line {idx + 1} in {file_path}: {e}", file=sys.stderr)
            scrubbed_lines.append(line)

    if modified_count > 0 and not dry_run:
        tmp_file = file_path.with_suffix(".scrub.tmp")
        tmp_file.write_text("\n".join(scrubbed_lines) + "\n", encoding="utf-8")
        tmp_file.replace(file_path)

    return len(lines), modified_count


def scrub_all_audit_logs(target_dir: Path = None, dry_run: bool = False):
    audit_file = Config.AUDIT_LOG_PATH
    log_dir = target_dir or audit_file.parent
    raw_key = getattr(Config, "AUDIT_HMAC_KEY", None) or Config.SECRET_KEY or "kepler_audit_fallback_key"
    hmac_key = raw_key.encode("utf-8")

    if not log_dir.exists():
        print(f"Log directory not found: {log_dir}")
        return

    pattern = f"{audit_file.stem}*"
    matching_files = list(log_dir.glob(pattern))

    if not matching_files:
        print(f"No audit files matching '{pattern}' in {log_dir}")
        return

    print(f"Starting audit scrub in {log_dir} (dry_run={dry_run}):")
    total_records = 0
    total_modified = 0

    for f in matching_files:
        total, modified = scrub_file(f, hmac_key, dry_run=dry_run)
        total_records += total
        total_modified += modified
        status = f"scrubbed {modified} records" if not dry_run else f"would scrub {modified} records"
        print(f"  • {f.name}: {total} total records, {status}")

    print(f"\nCompleted: {total_modified}/{total_records} records sanitized across {len(matching_files)} file(s).")


if __name__ == "__main__":
    dry_run_flag = "--dry-run" in sys.argv
    scrub_all_audit_logs(dry_run=dry_run_flag)
