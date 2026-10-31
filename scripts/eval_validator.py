#!/usr/bin/env python3
"""
scripts/eval_validator.py
Evaluates claim-level validator across conversation transcripts and the benchmark evaluation set.
Computes:
  - Total queries evaluated
  - Pass vs Rejection / Fallback rates
  - Identified rejection reasons (ungrounded numbers, banned claims, competitor mentions)
  - Identifies any false rejections on valid commercial answers
"""

import sys
import json
import sqlite3
from pathlib import Path
from typing import List, Dict, Any

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.agent.validator import validate_response
from app.agent.pipeline import CX02Pipeline
from app.storage.db import get_db_connection


def eval_validator_over_db_messages(limit: int = 200) -> Dict[str, Any]:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, sender_id, role, content
            FROM messages
            WHERE content IS NOT NULL AND content != ''
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit * 2,)
        )
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    # Pair user and assistant turns
    pairs = []
    for i in range(len(rows) - 1):
        if rows[i]["role"] == "assistant" and rows[i + 1]["role"] == "user":
            pairs.append((rows[i + 1]["content"], rows[i]["content"]))
        if len(pairs) >= limit:
            break

    total = len(pairs)
    passed = 0
    rejected = 0
    rejection_reasons = {}
    false_rejections = []

    for msg, reply in pairs:
        val = validate_response(
            reply=reply,
            tool_results=[],
            retrieved_chunks=[],
            user_message=msg
        )

        if val["is_valid"]:
            passed += 1
        else:
            rejected += 1
            reason = val.get("reason", "Unknown")
            cat = reason.split(":")[0]
            rejection_reasons[cat] = rejection_reasons.get(cat, 0) + 1

            # Check if this was a false rejection (e.g. valid greeting, price tool reply, or category link)
            if "kepler" in reply.lower() and "unauthorized" not in reason.lower() and "banned" not in reason.lower():
                false_rejections.append({
                    "user_message": msg,
                    "reply": reply[:100] + "...",
                    "reason": reason
                })

    return {
        "source": "database_messages",
        "total_evaluated": total,
        "passed": passed,
        "rejected_or_fallback": rejected,
        "fallback_rate_pct": round((rejected / total * 100.0) if total else 0.0, 2),
        "rejection_reasons": rejection_reasons,
        "false_rejections": false_rejections[:5]
    }


def eval_validator_over_eval_set(eval_path: Path = None, sample_size: int = 100) -> Dict[str, Any]:
    path = eval_path or (BASE_DIR / "data" / "eval" / "eval_set.json")
    if not path.exists():
        return {"error": "eval_set.json not found"}

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    sample = data[:sample_size]
    pipeline = CX02Pipeline()

    total = len(sample)
    passed = 0
    rejected = 0
    rejection_reasons = {}
    false_rejections = []

    from unittest.mock import patch
    with patch("app.rag.hybrid.embed_text", return_value=None), patch("app.rag.embed.embed_text", return_value=None):
        for item in sample:
            inp = item.get("input", "")
            # Process through pipeline
            try:
                res = pipeline.process(user_message=inp, sender_id="eval_validator")
                reply = res.get("reply", "")
                val = validate_response(
                    reply=reply,
                    tool_results=res.get("tools_called", []),
                    retrieved_chunks=res.get("chunks_retrieved", []),
                    user_message=inp
                )
                if val["is_valid"]:
                    passed += 1
                else:
                    rejected += 1
                    reason = val.get("reason", "Unknown")
                    cat = reason.split(":")[0]
                    rejection_reasons[cat] = rejection_reasons.get(cat, 0) + 1
            except Exception as e:
                rejected += 1
                rejection_reasons[f"Pipeline error: {str(e)[:30]}"] = rejection_reasons.get("error", 0) + 1

    return {
        "source": "eval_set_sample",
        "total_evaluated": total,
        "passed": passed,
        "rejected_or_fallback": rejected,
        "fallback_rate_pct": round((rejected / total * 100.0) if total else 0.0, 2),
        "rejection_reasons": rejection_reasons,
        "false_rejections": false_rejections
    }


def main():
    print("========================================================")
    print("Running Validator Audit across Transcripts & Eval Benchmark")
    print("========================================================")

    res_db = eval_validator_over_db_messages(limit=250)
    print(f"\n1. Database Transcripts Audit ({res_db['total_evaluated']} turns):")
    print(f"  • Passed Validation    : {res_db['passed']}")
    print(f"  • Fallback / Rejection : {res_db['rejected_or_fallback']} ({res_db['fallback_rate_pct']}%)")
    print(f"  • Top Rejection Categories:")
    for k, v in res_db["rejection_reasons"].items():
        print(f"      - {k}: {v}")

    res_eval = eval_validator_over_eval_set(sample_size=60)
    print(f"\n2. Eval Benchmark Audit ({res_eval['total_evaluated']} test queries):")
    print(f"  • Passed Validation    : {res_eval['passed']}")
    print(f"  • Fallback / Rejection : {res_eval['rejected_or_fallback']} ({res_eval['fallback_rate_pct']}%)")
    print(f"  • False Rejections     : {len(res_eval['false_rejections'])}")

    report = {
        "transcripts": res_db,
        "eval_set": res_eval
    }

    out_file = BASE_DIR / "data" / "eval" / "validator_eval_report.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n✅ Report written to {out_file}")


if __name__ == "__main__":
    main()
