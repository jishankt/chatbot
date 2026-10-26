#!/usr/bin/env python3
"""
scripts/audit/eval_audit.py
Independent evaluation rigor audit for Citizen CX-02 Sales AI.
Checks:
1. Question category ratios and phrasing circularity against KB chunks.
2. Eval benchmark assertions inspection (loose assertions like 'or len(chunks) > 0').
3. Strict vs loose RAG evaluation comparison.
4. Mutation testing: 30 realistic colloquial / mutated questions (typos, Manglish, colloquial Arabic-English slang, reordered phrasing).
5. Hallucination scanner across all replies.
"""

import sys
import json
import re
import statistics
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.agent.orchestrator import CX02Orchestrator
from app.agent.pipeline import CX02Pipeline
from app.tools.pricing import load_products_whitelist

EVAL_PATH = PROJECT_ROOT / "data" / "eval" / "questions.jsonl"
CHUNKS_PATH = PROJECT_ROOT / "data" / "chunks.json"


def audit_eval_dataset():
    print("=" * 60)
    print("1. EVALUATION DATASET ANALYSIS")
    print("=" * 60)

    with open(EVAL_PATH, "r", encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]

    total = len(records)
    print(f"Total benchmark questions: {total}")

    types = {}
    expected_tools = {}
    for r in records:
        t = r.get("type", "unknown")
        types[t] = types.get(t, 0) + 1
        et = r.get("expected_tool")
        if et:
            expected_tools[et] = expected_tools.get(et, 0) + 1

    print("\nQuestion Type Breakdown:")
    for t, count in sorted(types.items()):
        print(f"  • {t:12s}: {count:3d} ({count/total*100:.1f}%)")

    print("\nExpected Tool Distribution:")
    for et, count in sorted(expected_tools.items()):
        print(f"  • {et:20s}: {count:3d}")

    # Check for lexical circularity with chunks.json
    with open(CHUNKS_PATH, "r", encoding="utf-8") as f:
        chunks_data = json.load(f)
    all_chunk_text = " ".join([c["text"].lower() for c in chunks_data])

    exact_chunk_substrings = 0
    for r in records:
        q = r["question"].lower()
        # strip punctuation
        q_clean = re.sub(r"[^\w\s]", "", q)
        # 5-gram check
        words = q_clean.split()
        if len(words) >= 5:
            five_gram = " ".join(words[:5])
            if five_gram in all_chunk_text:
                exact_chunk_substrings += 1

    print(f"\nCircularity / Synthetic Overlap:")
    print(f"  • Questions sharing >=5 contiguous words with KB source text: {exact_chunk_substrings}/{total} ({exact_chunk_substrings/total*100:.1f}%)")


def audit_strict_vs_loose_eval():
    print("\n" + "=" * 60)
    print("2. STRICT VS LOOSE EVALUATION BENCHMARK COMPARISON")
    print("=" * 60)

    with open(EVAL_PATH, "r", encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]

    p = CX02Pipeline()

    rag_total = 0
    loose_rag_passed = 0
    strict_rag_passed = 0

    for r in records:
        if r.get("type") == "R":
            rag_total += 1
            res = p.process(user_message=r["question"])
            chunks = res.get("chunks_retrieved", [])
            exp_sec = r.get("expected_section")

            # Loose assertion from run_eval.py line 136:
            retrieved_sections = [c.get("section") for c in chunks]
            loose_hit = (exp_sec in retrieved_sections) or (len(chunks) > 0)
            if loose_hit:
                loose_rag_passed += 1

            # Strict assertion: expected_section MUST be in top retrieved chunk
            strict_hit = len(chunks) > 0 and (chunks[0].get("section") == exp_sec)
            if strict_hit:
                strict_rag_passed += 1

    print(f"Total Knowledge (R) items: {rag_total}")
    print(f"  • Loose Pass Rate (as written in run_eval.py): {loose_rag_passed}/{rag_total} ({loose_rag_passed/rag_total*100:.1f}%)")
    print(f"  • Strict Pass Rate (top-1 section match):     {strict_rag_passed}/{rag_total} ({strict_rag_passed/rag_total*100:.1f}%)")


def audit_30_mutations():
    print("\n" + "=" * 60)
    print("3. MUTATION TESTING: 30 REALISTIC & ADVERSARIAL VARIANTS")
    print("=" * 60)

    mutations = [
        # Typos / Misspellings
        {"category": "Typo", "q": "What is the prce of citizen cx02?", "expected_intent": "price"},
        {"category": "Typo", "q": "how fast is the pringer?", "expected_intent": "datasheet"},
        {"category": "Typo", "q": "Cost per prnt for 4x6", "expected_intent": "media_yield_cost"},
        {"category": "Typo", "q": "Do u have stock of cx 02 bag?", "expected_intent": "stock"},
        {"category": "Typo", "q": "Need qoutation for 2 printers", "expected_intent": "quote"},
        
        # UAE English / Colloquial / Manglish
        {"category": "Manglish/UAE", "q": "Ya brother how much last price for cx-02?", "expected_intent": "discount_negotiation"},
        {"category": "Manglish/UAE", "q": "Brother please give best rate citizen printer", "expected_intent": "discount_negotiation"},
        {"category": "Manglish/UAE", "q": "Habibi send me quote for 5 boxes 4x6 roll", "expected_intent": "quote"},
        {"category": "Manglish/UAE", "q": "Is CX02 ready in stock in Dubai warehouse?", "expected_intent": "stock"},
        {"category": "Manglish/UAE", "q": "Can do cash on delivery to Sharjah?", "expected_intent": "policies"},
        {"category": "Manglish/UAE", "q": "Can I visit your shop in Bur Dubai today?", "expected_intent": "human_demo_reserve"},
        {"category": "Manglish/UAE", "q": "Boss give me phone number of Kepler Tech", "expected_intent": "human_demo_reserve"},
        {"category": "Manglish/UAE", "q": "Give me citizen cx02 link to buy online", "expected_intent": "link"},
        {"category": "Manglish/UAE", "q": "What is per photo cost in UAE dirhams?", "expected_intent": "media_yield_cost"},
        {"category": "Manglish/UAE", "q": "Does this machine run on 220v Dubai electricity?", "expected_intent": "datasheet"},

        # Multi-intent & Complex Syntax
        {"category": "Complex Syntax", "q": "I want to purchase CX-02 but before that what is its total weight in kg?", "expected_intent": "datasheet"},
        {"category": "Complex Syntax", "q": "Give me pricing details including carry bag and 5x7 roll", "expected_intent": "bundle_catalog"},
        {"category": "Complex Syntax", "q": "Is the warranty 1 year or 2 years for the printhead?", "expected_intent": "datasheet"},
        {"category": "Complex Syntax", "q": "If I buy 3 units can you deliver to Abu Dhabi?", "expected_intent": "quote"},
        {"category": "Complex Syntax", "q": "What is the size in centimeters of this unit?", "expected_intent": "datasheet"},

        # Support & Troubleshooting (Expect Support/Handoff)
        {"category": "Support", "q": "My printer is showing red error light", "expected_intent": "human_demo_reserve"},
        {"category": "Support", "q": "Paper jam inside the front cover, how to fix?", "expected_intent": "human_demo_reserve"},
        {"category": "Support", "q": "Driver installation failed on Windows 11", "expected_intent": "datasheet"},
        {"category": "Support", "q": "Where to download the Mac OS driver for CX-02?", "expected_intent": "datasheet"},

        # Unanswerable / Boundary Queries
        {"category": "Boundary", "q": "Can CX-02 print panoramic 6x14 or 6x20 photos?", "expected_intent": "rag"},
        {"category": "Boundary", "q": "Can I use DNP RX1 paper inside Citizen CX-02?", "expected_intent": "guardrails"},
        {"category": "Boundary", "q": "Is Citizen CX-02 faster than DNP DS620?", "expected_intent": "guardrails"},
        {"category": "Boundary", "q": "What is the cost of replacing a damaged thermal head?", "expected_intent": "rag"},
        {"category": "Boundary", "q": "Can I connect this printer via Bluetooth or WiFi?", "expected_intent": "rag"},
        {"category": "Boundary", "q": "Does this printer support passport biometric photo cutting?", "expected_intent": "rag"}
    ]

    p = CX02Pipeline()
    passed = 0
    failures = []

    for i, m in enumerate(mutations, 1):
        q = m["q"]
        exp = m["expected_intent"]
        res = p.process(user_message=q, sender_id="audit_mutation")
        act = res.get("intent")

        # Intent match check
        success = (act == exp)
        # Special tolerance: if exp is discount and act is discount_negotiation
        if exp == act:
            success = True
        elif exp == "human_demo_reserve" and "specialized sales" in res.get("reply", "").lower():
            success = True
        elif exp == "quote" and any(t.get("tool") == "create_quote" for t in res.get("tools_called", [])):
            success = True

        if success:
            passed += 1
            status = "PASS"
        else:
            status = "FAIL"
            failures.append({
                "index": i,
                "category": m["category"],
                "question": q,
                "expected": exp,
                "actual": act,
                "reply_snippet": res.get("reply", "")[:120].replace("\n", " ")
            })

        print(f"[{status:4s}] #{i:02d} ({m['category']:14s}) '{q}' -> Intent: {act} (Exp: {exp})")

    print(f"\nMutation Robustness Score: {passed}/{len(mutations)} ({passed/len(mutations)*100:.1f}%)")
    if failures:
        print(f"\nDetected {len(failures)} Router Fragility Failures:")
        for f in failures:
            print(f"  • #{f['index']} [{f['category']}]: '{f['question']}'")
            print(f"    Expected: {f['expected']} | Actual: {f['actual']}")
            print(f"    Reply: {f['reply_snippet']}...")


def audit_hallucinations_on_eval():
    print("\n" + "=" * 60)
    print("4. HALLUCINATION & FACTUAL ACCURACY AUDIT ACROSS ALL 220 ITEMS")
    print("=" * 60)

    with open(EVAL_PATH, "r", encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]

    whitelist = load_products_whitelist()
    valid_prices = set()
    for p in whitelist.values():
        valid_prices.add(p["price"])
        if p.get("old_price"):
            valid_prices.add(p["old_price"])
        # quote multiples
        for q in range(1, 100):
            valid_prices.add(round(p["price"] * q, 2))

    p = CX02Pipeline()
    unverified_claims = []

    for i, r in enumerate(records, 1):
        q = r["question"]
        res = p.process(user_message=q, sender_id=f"audit_hallucination_{i}")
        reply = res["reply"]

        # Check for ungrounded AED prices
        price_matches = re.findall(r"([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?)\s*AED", reply, re.IGNORECASE)
        for pm in price_matches:
            val = float(pm.replace(",", ""))
            if val not in valid_prices:
                unverified_claims.append({
                    "item": i,
                    "question": q,
                    "claim": f"{val} AED",
                    "type": "unrecognized_price"
                })

        # Check for unauthorized competitor brand leakage
        for comp in ["dnp", "fujifilm", "fuji", "hiti", "sinfonia", "mitsubishi", "epson"]:
            # If competitor mentioned in reply without refusal language
            if re.search(r"\b" + comp + r"\b", reply, re.IGNORECASE):
                if "we do not provide information or comparisons regarding other brands" not in reply.lower():
                    unverified_claims.append({
                        "item": i,
                        "question": q,
                        "claim": comp,
                        "type": "competitor_leakage"
                    })

    print(f"Total benchmark questions scanned: {len(records)}")
    print(f"Hallucinated prices found: {len([c for c in unverified_claims if c['type'] == 'unrecognized_price'])}")
    print(f"Competitor leakage found: {len([c for c in unverified_claims if c['type'] == 'competitor_leakage'])}")
    if unverified_claims:
        for c in unverified_claims:
            print(f"  • #{c['item']}: '{c['question']}' -> {c['type']}: {c['claim']}")
    else:
        print("✅ Zero hallucinations or competitor leaks detected across all 220 items.")


if __name__ == "__main__":
    audit_eval_dataset()
    audit_strict_vs_loose_eval()
    audit_30_mutations()
    audit_hallucinations_on_eval()
