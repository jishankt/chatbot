#!/usr/bin/env python3
"""
scripts/profile_turn_latency.py
Profiles per-turn latency breakdown (NLU, embed, generate, validate) at C=1
and prints ollama ps processor status.
"""

import sys
import time
import subprocess
from pathlib import Path
from typing import List, Dict, Any

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.agent.pipeline import CX02Pipeline
from app.cognitive.reader import read_message
from app.cognitive.understander import understand_message
from app.rag.retriever import retrieve
from app.agent.llm import generate_llm_response
from app.agent.validator import validate_response


PROFILE_PROMPTS = [
    "What is the print speed of the Citizen CX-02 for 4x6 photos?",
    "Can you give me the price of the CX-02 printer?",
    "Does the Citizen CX-02 support 5x7 prints and what is the roll capacity?",
    "How does dye-sublimation overcoat protect photos against spills?",
    "What are the dimensions and total weight of the CX-02?",
    "Do you carry the thermal printhead cleaning pen for the CX-02?",
    "What warranty coverage is included with the Citizen CX-02 in Dubai?",
    "Can the CX-02 printer produce 2x6 photo booth strips with dual-cut?",
    "Where is Kepler Tech showroom located in Dubai?",
    "What are your business operating hours in Dubai?",
    "How fast can it print a 6x8 photo in high speed mode?",
    "Can I connect the CX-02 to a Windows 11 PC via USB 2.0?",
    "What finishes can I choose: matte, glossy, or luster?",
    "How many prints can I get from a 4x6 media roll?",
    "What is the yield of the 5x7 media set CX2-MS57-2PC?",
    "What is the part number for the 6x8 media box?",
    "كم سرعة طباعة الصور مقاس 4x6 في طابعة سيتيزن CX-02؟",
    "ما هي أبعاد ووزن طابعة الصور سيتيزن في دبي؟",
    "هل يتوفر لديكم رول ورق 4x6 لطابعة CX-02؟",
    "ശീഘ്ര പ്രിന്റ് സ്പീഡ് എത്രയാണ് Citizen CX-02 ന്?"
]


def check_ollama_ps():
    print("================================================================================")
    print("OLLAMA PS STATUS (PROCESSOR & VRAM):")
    try:
        out = subprocess.check_output(["ollama", "ps"], text=True)
        print(out.strip())
    except Exception as e:
        print(f"Error checking ollama ps: {e}")
    print("================================================================================\n")


def profile_turn(prompt: str, pipeline: CX02Pipeline) -> Dict[str, Any]:
    t_start = time.perf_counter()

    # Stage 1: NLU (Read & Understand)
    t0 = time.perf_counter()
    read_ctx = read_message(prompt)
    understand_res = understand_message(read_ctx)
    t_nlu_ms = (time.perf_counter() - t0) * 1000.0

    # Stage 2: Embed / Retrieval
    t0 = time.perf_counter()
    chunks = retrieve(prompt, top_k=2, use_dense=True)
    t_embed_ms = (time.perf_counter() - t0) * 1000.0

    # Stage 3: Full Pipeline Process (including Generate & Validate)
    t0 = time.perf_counter()
    res = pipeline.process(user_message=prompt, sender_id="profiler_turn")
    t_pipeline_ms = (time.perf_counter() - t0) * 1000.0

    # Stage 4: Validate
    t0 = time.perf_counter()
    val = validate_response(
        reply=res.get("reply", ""),
        tool_results=res.get("tools_called", []),
        retrieved_chunks=res.get("chunks_retrieved", []),
        user_message=prompt
    )
    t_val_ms = (time.perf_counter() - t0) * 1000.0

    total_ms = (time.perf_counter() - t_start) * 1000.0

    return {
        "prompt": prompt,
        "nlu_ms": round(t_nlu_ms, 1),
        "embed_ms": round(t_embed_ms, 1),
        "pipeline_ms": round(t_pipeline_ms, 1),
        "val_ms": round(t_val_ms, 1),
        "total_ms": round(total_ms, 1),
        "intent": res.get("intent"),
        "reply_source": res.get("reply_source", "llm" if "specifications for the Citizen CX-02" not in res.get("reply", "") else "extractive_fallback"),
        "fallback_reason": res.get("fallback_reason", "none")
    }


def main():
    check_ollama_ps()
    pipeline = CX02Pipeline()

    print(f"Profiling {len(PROFILE_PROMPTS)} sequential requests at C=1...\n")
    results = []

    print(f"{'#':<3} | {'Prompt':<45} | {'NLU (ms)':<9} | {'Embed (ms)':<10} | {'Gen (ms)':<10} | {'Val (ms)':<8} | {'Total (ms)':<10} | {'Source'}")
    print("-" * 125)

    for idx, p in enumerate(PROFILE_PROMPTS, 1):
        r = profile_turn(p, pipeline)
        results.append(r)
        short_p = (p[:42] + "...") if len(p) > 45 else p
        print(f"{idx:<3} | {short_p:<45} | {r['nlu_ms']:<9.1f} | {r['embed_ms']:<10.1f} | {r['pipeline_ms']:<10.1f} | {r['val_ms']:<8.1f} | {r['total_ms']:<10.1f} | {r['reply_source']}")

    nlu_avg = sum(r["nlu_ms"] for r in results) / len(results)
    embed_avg = sum(r["embed_ms"] for r in results) / len(results)
    gen_avg = sum(r["pipeline_ms"] for r in results) / len(results)
    val_avg = sum(r["val_ms"] for r in results) / len(results)
    total_avg = sum(r["total_ms"] for r in results) / len(results)

    print("-" * 125)
    print(f"AVERAGE LATENCY PER STAGE (C=1, 20 requests):")
    print(f"  • NLU Stage       : {nlu_avg:.1f} ms")
    print(f"  • Embed / RAG     : {embed_avg:.1f} ms")
    print(f"  • Generate        : {gen_avg:.1f} ms")
    print(f"  • Validate        : {val_avg:.1f} ms")
    print(f"  • TOTAL Turn Time : {total_avg:.1f} ms\n")


if __name__ == "__main__":
    main()
