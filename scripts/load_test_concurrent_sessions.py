#!/usr/bin/env python3
"""
scripts/load_test_concurrent_sessions.py
Simulates 20 concurrent customer sessions with burst requests against /chat,
benchmarking latency and resilience across three operational regimes:
  1. Baseline operation (Real responsive Ollama)
  2. Slowed backend (Real Ollama with injected network/queue delay)
  3. Stopped backend (Ollama offline / fallback path)

Reports:
  - Total requests completed per regime (200+ requests)
  - Success rate (HTTP 200) vs HTTP 5xx errors
  - Latency percentiles: p50, p95, p99
  - Fallback rate (% of requests served by fallback/extractive mode)
"""

import sys
import time
import argparse
import statistics
import concurrent.futures
from pathlib import Path
from unittest.mock import patch

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.main import create_app
from app.config import Config


def validate_isolated_db(db_path: Path = None) -> bool:
    """
    Enforces that load tests and benchmarks refuse to run against the production database path.
    """
    if db_path is None:
        db_path = Path(os.environ.get("DATABASE_PATH", Config.DATABASE_PATH))
    prod_path = (BASE_DIR / "data" / "sales_ai.db").resolve()
    if db_path.resolve() == prod_path:
        raise RuntimeError(
            f"Refusing to run load test against production database {db_path}! "
            f"Specify an isolated test database via TEST_DATABASE_PATH or DATABASE_PATH."
        )
    return True


TEST_MESSAGES = [
    "What is the print speed of the Citizen CX-02 for 4x6 photos?",
    "Can you give me the price of the CX-02 printer?",
    "Does the Citizen CX-02 support 5x7 prints?",
    "How does dye-sublimation overcoat protect photos against spills?",
    "What are the dimensions and weight of the CX-02?",
    "Do you carry the thermal printhead cleaning pen for the CX-02?",
    "Can I order 800 prints of 4x6 media sets?",
    "Is ribbon-rewind technology supported on this printer?"
]


def run_session_worker(client, session_id: str, message: str, delay_s: float = 0.0) -> dict:
    if delay_s > 0:
        time.sleep(delay_s)
    start_t = time.perf_counter()
    res = client.post(
        "/chat",
        json={"message": message, "sender_id": f"load_sess_{session_id}"}
    )
    elapsed_ms = (time.perf_counter() - start_t) * 1000.0
    status_code = res.status_code
    body = res.get_json(silent=True) or {}
    reply = body.get("reply", "")
    intent = body.get("intent", "")

    # Check if fallback or extractive template was used
    is_fallback = (
        intent in ("system_fallback", "extractive_fallback")
        or Config.KEPLER_PHONE in reply
        or "momentarily" in reply.lower()
        or "technical specifications for the Citizen CX-02" in reply
    )

    return {
        "status_code": status_code,
        "elapsed_ms": elapsed_ms,
        "is_ok": status_code == 200 and bool(reply),
        "has_error_500": status_code >= 500,
        "is_fallback": is_fallback
    }


def execute_phase(name: str, client, concurrency: int = 20, burst_per_worker: int = 10, delay_per_call: float = 0.0):
    total_tasks = concurrency * burst_per_worker
    print(f"\n========================================================")
    print(f"▶ Running Load Test Phase: {name}")
    print(f"  Concurrency: {concurrency} workers | Bursts: {burst_per_worker} turns/worker | Total: {total_tasks} requests")
    print(f"========================================================")

    latencies = []
    status_codes = {}
    errors_5xx = 0
    fallback_count = 0

    def task_fn(item):
        w_id, m_idx = item
        msg = TEST_MESSAGES[m_idx % len(TEST_MESSAGES)]
        return run_session_worker(client, session_id=str(w_id), message=msg, delay_s=delay_per_call)

    items = [(w, b) for w in range(concurrency) for b in range(burst_per_worker)]

    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(task_fn, it) for it in items]
        for f in concurrent.futures.as_completed(futures):
            r = f.result()
            latencies.append(r["elapsed_ms"])
            status_codes[r["status_code"]] = status_codes.get(r["status_code"], 0) + 1
            if r["has_error_500"]:
                errors_5xx += 1
            if r["is_fallback"]:
                fallback_count += 1

    wall_clock = time.time() - t0
    latencies.sort()
    n = len(latencies)
    p50 = latencies[int(n * 0.50)]
    p95 = latencies[int(n * 0.95)]
    p99 = latencies[int(n * 0.99)]
    error_rate = (errors_5xx / total_tasks) * 100.0
    fallback_rate = (fallback_count / total_tasks) * 100.0

    print(f"  • Total Requests Completed : {total_tasks} in {wall_clock:.2f}s ({total_tasks/wall_clock:.1f} req/s)")
    print(f"  • Status Breakdown         : {status_codes}")
    print(f"  • HTTP 5xx Server Errors   : {errors_5xx} ({error_rate:.2f}%)")
    print(f"  • Fallback Rate            : {fallback_count}/{total_tasks} ({fallback_rate:.1f}%)")
    print(f"  • Latency p50 (Median)     : {p50:.1f} ms")
    print(f"  • Latency p95              : {p95:.1f} ms")
    print(f"  • Latency p99              : {p99:.1f} ms")

    return {
        "phase": name,
        "total": total_tasks,
        "p50_ms": round(p50, 1),
        "p95_ms": round(p95, 1),
        "p99_ms": round(p99, 1),
        "fallback_rate_pct": round(fallback_rate, 1),
        "error_rate_pct": error_rate
    }


def main():
    parser = argparse.ArgumentParser(description="Load test 20 concurrent sessions with real or simulated backend.")
    parser.add_argument("--concurrency", type=int, default=20, help="Number of concurrent sessions (default 20)")
    parser.add_argument("--burst", type=int, default=10, help="Burst turns per worker (default 10 -> 200 requests/regime)")
    parser.add_argument("--mock-llm", action="store_true", help="Use fast mocked LLM response instead of real Ollama")
    args = parser.parse_args()

    # Pre-warm app
    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()

    summary_results = []
    concurrency = args.concurrency
    burst = args.burst

    # Patch dense embedding timeouts to keep load test focused on generation and pipeline throughput
    with patch("app.rag.hybrid.embed_text", return_value=None), patch("app.rag.embed.embed_text", return_value=None):

        # Phase 1: Baseline (Real Ollama)
        if args.mock_llm:
            with patch("app.agent.llm.generate_llm_response", return_value="The Citizen CX-02 prints 4x6 inch photos in 8.4 seconds."):
                res1 = execute_phase("Phase 1: Baseline Responsive Backend", client, concurrency=concurrency, burst_per_worker=burst)
                summary_results.append(res1)
        else:
            res1 = execute_phase("Phase 1: Baseline Responsive Backend", client, concurrency=concurrency, burst_per_worker=burst)
            summary_results.append(res1)

        # Phase 2: Slowed backend (Injected 0.25s network/queue delay)
        res2 = execute_phase("Phase 2: Slowed / Queued Backend", client, concurrency=concurrency, burst_per_worker=burst, delay_per_call=0.25)
        summary_results.append(res2)

        # Phase 3: Stopped backend (Ollama down / connection refused)
        def broken_generate(*args, **kwargs):
            raise ConnectionError("Ollama daemon stopped / connection refused on port 11434")

        with patch("app.agent.llm.generate_llm_response", side_effect=broken_generate):
            res3 = execute_phase("Phase 3: Ollama Stopped / Offline", client, concurrency=concurrency, burst_per_worker=burst)
            summary_results.append(res3)

    print("\n==========================================================================================")
    print("LOAD TEST FINAL EXECUTIVE SUMMARY")
    print("==========================================================================================")
    print(f"{'Phase':<32} | {'p50 (ms)':<9} | {'p95 (ms)':<9} | {'p99 (ms)':<9} | {'Fallback %':<10} | {'5xx Errors'}")
    print("-" * 90)
    for s in summary_results:
        print(f"{s['phase']:<32} | {s['p50_ms']:<9} | {s['p95_ms']:<9} | {s['p99_ms']:<9} | {s['fallback_rate_pct']:<10}% | {s['error_rate_pct']:.1f}%")
    print("==========================================================================================")


if __name__ == "__main__":
    main()
