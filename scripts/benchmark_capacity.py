#!/usr/bin/env python3
"""
scripts/benchmark_capacity.py
Measures single-request and multi-concurrency latency on real Ollama (p50/p95/p99)
across concurrency levels C=1 (sequential), C=2, C=4, C=8.
Tracks and reports exact fallback reason breakdown:
  - timeout
  - validator_reject
  - circuit_open
  - queue_wait
"""

import sys
import time
import statistics
import concurrent.futures
from pathlib import Path
from typing import List, Dict, Any

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.main import create_app
from app.config import Config


def validate_isolated_db(db_path: Path = None) -> bool:
    """
    Enforces that capacity benchmarks refuse to run against the production database path.
    """
    import os
    if db_path is None:
        db_path = Path(os.environ.get("DATABASE_PATH", Config.DATABASE_PATH))
    prod_path = (BASE_DIR / "data" / "sales_ai.db").resolve()
    if db_path.resolve() == prod_path:
        raise RuntimeError(
            f"Refusing to run load test against production database {db_path}! "
            f"Specify an isolated test database via TEST_DATABASE_PATH or DATABASE_PATH."
        )
    return True


BENCHMARK_PROMPTS = [
    "How does dye-sublimation overcoat protect photos against spills and UV fading?",
    "Can you explain the thermal printhead cleaning procedure for the CX-02?",
    "What are the dimensions and weight of the Citizen CX-02 printer?",
    "How fast does the Citizen CX-02 produce a 4x6 inch photo print?",
    "Does the Citizen CX-02 support 5x7 prints and what is the roll capacity?",
    "Can the CX-02 operate cleanly in a mobile event photo booth setup?",
    "What finishes are available on the Citizen CX-02 without changing paper?",
    "How does ribbon-rewind technology eliminate media waste on 6x8 rolls?"
]


def execute_request(client, prompt: str, session_id: str) -> Dict[str, Any]:
    t0 = time.perf_counter()
    res = client.post(
        "/chat",
        json={"message": prompt, "sender_id": f"bench_{session_id}"}
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    body = res.get_json(silent=True) or {}
    reply = body.get("reply", "")
    intent = body.get("intent", "")
    fallback_reason = body.get("fallback_reason")

    if not fallback_reason:
        if intent in ("system_fallback", "extractive_fallback"):
            fallback_reason = "extractive_template"
        elif "specifications for the Citizen CX-02" in reply:
            fallback_reason = "extractive_fallback"
        else:
            fallback_reason = "none"

    return {
        "status_code": res.status_code,
        "elapsed_ms": elapsed_ms,
        "reply_len": len(reply),
        "intent": intent,
        "fallback_reason": fallback_reason,
        "is_fallback": fallback_reason != "none"
    }


def run_benchmark_regime(name: str, client, concurrency: int, total_requests: int) -> Dict[str, Any]:
    print(f"\n--- Running: {name} (Concurrency={concurrency}, Total Requests={total_requests}) ---")
    results = []

    def task_worker(idx: int):
        prompt = BENCHMARK_PROMPTS[idx % len(BENCHMARK_PROMPTS)]
        return execute_request(client, prompt, session_id=f"sess_{idx}")

    t_start = time.perf_counter()
    if concurrency <= 1:
        for i in range(total_requests):
            results.append(task_worker(i))
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [executor.submit(task_worker, i) for i in range(total_requests)]
            for f in concurrent.futures.as_completed(futures):
                results.append(f.result())
    wall_sec = time.perf_counter() - t_start

    latencies = [r["elapsed_ms"] for r in results]
    latencies.sort()
    n = len(latencies)
    p50 = latencies[int(n * 0.50)]
    p95 = latencies[int(n * 0.95)]
    p99 = latencies[int(n * 0.99)]

    reason_counts = {}
    for r in results:
        reason = r["fallback_reason"]
        reason_counts[reason] = reason_counts.get(reason, 0) + 1

    fallbacks = sum(1 for r in results if r["is_fallback"])
    fallback_pct = (fallbacks / total_requests) * 100.0

    print(f"  Completed {total_requests} in {wall_sec:.2f}s ({total_requests/wall_sec:.2f} req/s)")
    print(f"  Latency p50: {p50:.1f}ms | p95: {p95:.1f}ms | p99: {p99:.1f}ms")
    print(f"  Fallback Rate: {fallbacks}/{total_requests} ({fallback_pct:.1f}%)")
    print(f"  Reason Breakdown: {reason_counts}")

    return {
        "regime": name,
        "concurrency": concurrency,
        "total": total_requests,
        "wall_sec": round(wall_sec, 2),
        "rps": round(total_requests / wall_sec, 2),
        "p50_ms": round(p50, 1),
        "p95_ms": round(p95, 1),
        "p99_ms": round(p99, 1),
        "fallback_pct": round(fallback_pct, 1),
        "reasons": reason_counts
    }


def main():
    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()

    print("================================================================================")
    print("REAL OLLAMA CAPACITY & LATENCY BENCHMARK")
    print(f"Model: {Config.OLLAMA_CHAT_MODEL} at {Config.OLLAMA_BASE_URL}")
    print("================================================================================")

    # 1. Single request sequential (no concurrency)
    res_c1_seq = run_benchmark_regime("Sequential Single-Request (No Concurrency)", client, concurrency=1, total_requests=6)

    # 2. Concurrency = 2
    res_c2 = run_benchmark_regime("Concurrency C=2", client, concurrency=2, total_requests=6)

    # 3. Concurrency = 4
    res_c4 = run_benchmark_regime("Concurrency C=4", client, concurrency=4, total_requests=8)

    # 4. Concurrency = 8
    res_c8 = run_benchmark_regime("Concurrency C=8", client, concurrency=8, total_requests=8)

    print("\n================================================================================")
    print(f"{'Regime':<35} | {'C':<2} | {'p50 (ms)':<9} | {'p95 (ms)':<9} | {'Fallback %':<10} | {'Throughput'}")
    print("-" * 80)
    for r in [res_c1_seq, res_c2, res_c4, res_c8]:
        print(f"{r['regime']:<35} | {r['concurrency']:<2} | {r['p50_ms']:<9} | {r['p95_ms']:<9} | {r['fallback_pct']:<10}% | {r['rps']:.1f} req/s")
    print("================================================================================")


if __name__ == "__main__":
    main()
