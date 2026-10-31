#!/usr/bin/env python3
"""
scripts/offbox_backup_copy.py
Copies local database backups to an off-box destination / remote mount,
verifying file integrity via SHA-256 hash comparison.
"""

import os
import sys
import hashlib
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def copy_to_offbox(source_file: Path = None, destination_dir: Path = None) -> Path:
    if source_file is None:
        local_backups = sorted(list((BASE_DIR / "data" / "backups").glob("sales_ai_*.db")), key=lambda p: p.stat().st_mtime, reverse=True)
        if not local_backups:
            raise FileNotFoundError("No local backups found in data/backups/")
        source_file = local_backups[0]

    dest_dir = destination_dir or Path(os.getenv("OFFBOX_BACKUP_DEST", str(BASE_DIR / "data" / "offbox_backups")))
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest_path = dest_dir / source_file.name
    print(f"Transferring {source_file} -> {dest_path}...")

    shutil.copy2(source_file, dest_path)

    # Verify SHA-256
    src_hash = sha256_file(source_file)
    dst_hash = sha256_file(dest_path)

    if src_hash != dst_hash:
        dest_path.unlink()
        raise IOError(f"Checksum mismatch on copy! src={src_hash} dst={dst_hash}")

    print(f"✅ Off-box copy verified (SHA256: {dst_hash[:16]}...)")
    return dest_path


def main():
    try:
        dest = copy_to_offbox()
        print(f"Off-box backup completed: {dest}")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Off-box backup failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
