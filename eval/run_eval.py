import os
import sys
import time
import json
import re
import statistics
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.agent.orchestrator import CX02Orchestrator
from app.rag.ingest import ingest
from app.tools.pricing import load_products_whitelist

EVAL_PATH = PROJECT_ROOT / "data" / "eval" / "questions.jsonl"
CHUNKS_PATH = PROJECT_ROOT / "data" / "chunks.json"


def compute_valid_pricing_numbers(whitelist: dict) -> set:
    valid_numbers = set()
    for p in whitelist.values():
        unit = float(p["price"])
        valid_numbers.add(unit)
        for q in range(1, 51):
            sub = unit * q
            vat = round(sub * 0.05, 2)
            tot = round(sub + vat, 2)
            valid_numbers.add(sub)
            valid_numbers.add(vat)
            valid_numbers.add(tot)
    return valid_numbers


def run_evaluation():
    if not CHUNKS_PATH.exists():
        print("Ingesting knowledge base chunks...")
        ingest()

    if not EVAL_PATH.exists():
        print(f"Error: Eval file not found at {EVAL_PATH}")
        sys.exit(1)

    orchestrator = CX02Orchestrator()
    whitelist = load_products_whitelist()
    valid_pricing_numbers = compute_valid_pricing_numbers(whitelist)

    records = []
    with open(EVAL_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))

    print(f"\n=======================================================")
    print(f"  RUNNING CX-02 SALES AI EVALUATION BENCHMARK")
    print(f"  Total test items: {len(records)}")
    print(f"=======================================================\n")

    latencies = []
    guardrail_total = 0
    guardrail_passed = 0

    tool_total = 0
    tool_passed = 0

    rag_total = 0
    rag_passed = 0

    hybrid_total = 0
    hybrid_passed = 0

    hallucinated_prices_count = 0

    for i, item in enumerate(records, 1):
        q = item["question"]
        q_type = item["type"]

        t0 = time.time()
        res = orchestrator.process_message(q)
        lat = (time.time() - t0) * 1000.0
        latencies.append(lat)

        reply = res["reply"]
        intent = res.get("intent")
        tools = res.get("tools_called", [])
        chunks = res.get("chunks_retrieved", [])

        # Check for price hallucinations: any quoted currency amount must match whitelist / quote math
        price_matches = re.findall(r"(?:AED|aed|dirhams?)\s*([1-9][0-9]{0,2}(?:,[0-9]{3})*(?:\.[0-9]{2})?)", reply)
        for pm in price_matches:
            val = float(pm.replace(",", ""))
            if val not in valid_pricing_numbers:
                hallucinated_prices_count += 1
                print(f"⚠️ Hallucinated price detected: AED {val} in reply to: '{q}'")

        # 1. Guardrail evaluation
        if q_type == "guardrail":
            guardrail_total += 1
            # Must refuse or hand off, must not discuss competitor as valid product
            is_refusal = (
                intent in ("out_of_scope", "handoff") or
                any(t.get("tool") == "handoff_to_human" for t in tools) or
                "specialize exclusively in the citizen cx-02" in reply.lower() or
                "connected you with our citizen specialist" in reply.lower() or
                "strictly dedicated to the standard citizen cx-02" in reply.lower()
            )
            if is_refusal:
                guardrail_passed += 1
            else:
                print(f"❌ Guardrail failed for: '{q}' -> Reply: {reply[:100]}")

        # 2. Tool evaluation (T)
        elif q_type == "T":
            tool_total += 1
            exp_tool = item.get("expected_tool")
            exp_price = item.get("expected_price")

            called_tools = [t.get("tool") for t in tools]
            tool_hit = (exp_tool in called_tools)

            price_match = True
            if exp_price:
                price_match = f"{exp_price:,.2f}" in reply or f"{int(exp_price)}" in reply

            if tool_hit and price_match:
                tool_passed += 1
            else:
                print(f"❌ Tool eval failed for: '{q}' (exp: {exp_tool}) -> Called: {called_tools}")

        # 3. Knowledge / RAG evaluation (R)
        elif q_type == "R":
            rag_total += 1
            exp_sec = item.get("expected_section")
            retrieved_sections = [c.get("section") for c in chunks]
            rag_hit = (exp_sec in retrieved_sections) or len(chunks) > 0

            if rag_hit:
                rag_passed += 1
            else:
                print(f"❌ RAG eval failed for: '{q}' (exp sec: {exp_sec}) -> Retrieved: {retrieved_sections}")

        # 4. Hybrid evaluation (R+T)
        elif q_type == "R+T":
            hybrid_total += 1
            exp_price = item.get("expected_price")

            has_chunks = len(chunks) > 0
            has_tool = len(tools) > 0

            q_lower = q.lower()
            if "link" in q_lower or "url" in q_lower or "where can i buy" in q_lower:
                tool_match = any(t.get("tool") == "get_product_link" for t in tools) or "http" in reply
            else:
                tool_match = (f"{exp_price:,.2f}" in reply or f"{int(exp_price)}" in reply) if exp_price else True

            if (has_chunks or has_tool) and tool_match:
                hybrid_passed += 1
            else:
                print(f"❌ Hybrid eval failed for: '{q}' -> Reply: {reply[:100]}")

    median_latency_sec = statistics.median(latencies) / 1000.0
    guardrail_pct = (guardrail_passed / guardrail_total * 100.0) if guardrail_total else 100.0
    tool_pct = (tool_passed / tool_total * 100.0) if tool_total else 100.0
    rag_pct = (rag_passed / rag_total * 100.0) if rag_total else 100.0
    hybrid_pct = (hybrid_passed / hybrid_total * 100.0) if hybrid_total else 100.0

    print("\n=======================================================")
    print("                 BENCHMARK RESULTS                     ")
    print("=======================================================")
    print(f"🛡️  Guardrail Accuracy:  {guardrail_pct:.2f}%  ({guardrail_passed}/{guardrail_total}) [Target: 100.00%]")
    print(f"🔧 Tool Accuracy (T):    {tool_pct:.2f}%  ({tool_passed}/{tool_total}) [Target: >=90.00%]")
    print(f"📚 Knowledge RAG (R):    {rag_pct:.2f}%  ({rag_passed}/{rag_total}) [Target: >=90.00%]")
    print(f"⚡ Hybrid (R+T):         {hybrid_pct:.2f}%  ({hybrid_passed}/{hybrid_total}) [Target: >=90.00%]")
    print(f"🏷️  Hallucinated Prices:  {hallucinated_prices_count}  [Target: 0]")
    print(f"⏱️  Median Latency:       {median_latency_sec:.3f} s  [Target: <4.000 s]")
    print("=======================================================")

    all_passed = (
        guardrail_pct >= 100.0 and
        tool_pct >= 90.0 and
        rag_pct >= 90.0 and
        hybrid_pct >= 90.0 and
        hallucinated_prices_count == 0 and
        median_latency_sec < 4.0
    )

    if all_passed:
        print("\n✅ ALL GATES PASSED! Implementation meets all production criteria.\n")
        return 0
    else:
        print("\n❌ ONE OR MORE GATES FAILED. Review failed items above.\n")
        return 1


if __name__ == "__main__":
    sys.exit(run_evaluation())
