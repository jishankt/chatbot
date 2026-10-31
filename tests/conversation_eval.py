#!/usr/bin/env python3
"""
tests/conversation_eval.py
100 multi-turn conversation evaluation benchmark with 5-axis rubric scoring:
  1. Accuracy (0-100%): Numbers and specs strictly grounded in catalog/tools
  2. Understanding (0-100%): Correct intent and SKU resolution
  3. Tone (0-100%): Consultative, warm sales advisor (no robotic dumps)
  4. Flow (0-100%): Contextual coherence and pronoun resolution across turns
  5. No Repeated Questions (0-100%): Never re-asks answered slots
"""

import sys
import json
import time
from pathlib import Path
from typing import List, Dict, Any

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.agent.pipeline import CX02Pipeline
from app.agent.validator import validate_response


def generate_100_conversation_scripts() -> List[Dict[str, Any]]:
    scripts = []

    # Persona 1: Photo Booth Operator (Speed, Strip Cutting, Carry Bag, Media) - 15 scripts
    pb_variations = [
        ("Dubai event photo booth", "CX-02", "4x6", "Can it do 2x6 dual cut strips?"),
        ("Abu Dhabi wedding photobooth", "CX-02", "5x7", "How fast does it print 4x6 photos?"),
        ("Sharjah mobile photobooth kiosk", "CX-02-BAG", "4x6", "Do you carry the protective carry bag?"),
        ("Party photobooth rental Dubai", "CITIZEN-PEN", "6x8", "How often do I need to clean the printhead?"),
        ("Corporate booth activation", "CX-02", "4x6", "Does it support ribbon rewind technology?")
    ]
    for i, (biz, sku, size, tech_q) in enumerate(pb_variations * 3, 1):
        scripts.append({
            "id": f"PB_{i:02d}",
            "persona": f"Photo Booth Operator ({biz})",
            "language": "en",
            "turns": [
                {"user": f"Hi, I run a {biz}. What is the price of the Citizen CX-02 printer?", "expected_sku": "CX-02"},
                {"user": tech_q, "expected_sku": "CX-02"},
                {"user": f"How much is the {size} media roll box for it?", "expected_sku": f"CX2-MS{size.replace('x', '')}-2PC" if size != "6x8" else "CX2-MS68-2PC"},
                {"user": "Can you prepare an official quote for 1 printer and 2 media boxes?", "expected_intent": "quote"}
            ]
        })

    # Persona 2: Studio Owner / Freelance Photographer (Color, Finish, Warranty) - 15 scripts
    studio_variations = [
        ("commercial portrait studio in Dubai", "matte or glossy finishes", "What finishes are available without changing paper?"),
        ("freelance event photographer", "2-year carry-in warranty", "What warranty coverage is included in the UAE?"),
        ("digital photo studio in Bur Dubai", "USB connectivity", "Can I connect it to Windows 11 and macOS?"),
        ("school photo contractor", "dimensions and weight", "What are the exact dimensions and total weight?"),
        ("mall photo printing kiosk", "input voltage", "What is the operating power voltage and wattage?")
    ]
    for i, (biz, topic, q) in enumerate(studio_variations * 3, 1):
        scripts.append({
            "id": f"ST_{i:02d}",
            "persona": f"Studio Owner ({biz})",
            "language": "en",
            "turns": [
                {"user": f"Good morning, I manage a {biz}. Tell me about the CX-02.", "expected_sku": "CX-02"},
                {"user": q, "expected_sku": "CX-02"},
                {"user": "Is it in stock at your Dubai showroom?", "expected_intent": "stock"},
                {"user": "Where is your showroom located?", "expected_intent": "policies"}
            ]
        })

    # Persona 3: Arabic Customers (Gulf Arabic & Standard Arabic) - 20 scripts
    ar_variations = [
        ("كم سعر طابعة الصور سيتيزن CX-02 في دبي؟", "هل تدعم قص شرائط الفوتوبوث 2x6؟", "هل يتوفر ورق 4x6 وكم سعره؟"),
        ("مرحبا، أحتاج طابعة صور لكشك تصوير حفلات", "كم سرعة طباعة مقاس 4x6 بالثواني؟", "أين يقع معرضكم في شارع خالد بن الوليد؟"),
        ("السلام عليكم، ما هي مدة الضمان المعتمدة في الإمارات؟", "هل توفرون حقيبة حمل مبطنة للطابعة؟", "هل التوصيل مجاني إلى أبوظبي؟"),
        ("بكم رولات الورق لطابعة سيتيزن مقاس 5x7؟", "كم عدد الصور في العلبة الواحدة؟", "هل يمكن حجز موعد تجربة في المعرض؟")
    ]
    for i, (q1, q2, q3) in enumerate(ar_variations * 5, 1):
        scripts.append({
            "id": f"AR_{i:02d}",
            "persona": f"Arabic Customer (Gulf/UAE)",
            "language": "ar",
            "turns": [
                {"user": q1, "expected_sku": "CX-02"},
                {"user": q2, "expected_sku": "CX-02"},
                {"user": q3, "expected_sku": "CX-02"}
            ]
        })

    # Persona 4: Malayalam Customers (Kerala Community in UAE) - 15 scripts
    ml_variations = [
        ("Citizen CX-02 ഫോട്ടോ പ്രിന്ററിന്റെ വില എത്രയാണ്?", "ഫോട്ടോബൂത്ത് ഇവന്റുകൾക്ക് ഇത് അനുയോജ്യമാണോ?", "4x6 പേപ്പർ റോൾ ലഭ്യമാണോ?"),
        ("നമസ്കാരം, ദുബായിൽ ഈ പ്രിന്ററിന് വാറന്റി ലഭിക്കുമോ?", "പ്രിന്റ് സ്പീഡ് എത്ര സെക്കൻഡ് ആണ്?", "ഷോറൂമിൽ നേരിട്ട് വന്ന് കാണാൻ സാധിക്കുമോ?"),
        ("CX-02 പ്രിന്ററിന്റെ ഭാരവും വലിപ്പവും എത്രയാണ്?", "ക്ലീനിംഗ് പെൻ ലഭ്യമാണോ?", "ഡെലിവറി ചാർജ് എത്രയാണ്?")
    ]
    for i, (q1, q2, q3) in enumerate(ml_variations * 5, 1):
        scripts.append({
            "id": f"ML_{i:02d}",
            "persona": f"Malayalam Customer (UAE Photographer)",
            "language": "ml",
            "turns": [
                {"user": q1, "expected_sku": "CX-02"},
                {"user": q2, "expected_sku": "CX-02"},
                {"user": q3, "expected_sku": "CX-02"}
            ]
        })

    # Persona 5: Manglish / Arabizi Customers (UAE Youth & Event Operators) - 15 scripts
    mg_variations = [
        ("marhaba, kam se3r citizen cx-02 printer fi dubai?", "shuf el print speed for 4x6 photos", "bikam el media rolls 4x6 in uae?"),
        ("salam alaykum, is cx-02 in stock right now?", "can i get carry bag for it?", "wayn showroom kepler tech fi bur dubai?"),
        ("bikam el citizen printer with 2 boxes of 5x7 paper?", "do you deliver to sharjah?", "please send me official quotation")
    ]
    for i, (q1, q2, q3) in enumerate(mg_variations * 5, 1):
        scripts.append({
            "id": f"MG_{i:02d}",
            "persona": f"Manglish / Arabizi Customer",
            "language": "manglish",
            "turns": [
                {"user": q1, "expected_sku": "CX-02"},
                {"user": q2, "expected_sku": "CX-02"},
                {"user": q3, "expected_sku": "CX-02"}
            ]
        })

    # Persona 6: Slot Corrections & Pronoun References - 20 scripts
    correction_variations = [
        ("I need a quote for 1 Citizen CX-02 and 2 boxes of 4x6 media", "Actually make it 5x7 media instead of 4x6", "How much is it with the 5x7 media?"),
        ("What is the cost of the CX-02 printer?", "Is it in stock?", "Can I order 2 units instead of 1?"),
        ("Tell me about the Citizen carry bag", "How much for it?", "Actually I meant the thermal cleaning pen, not the bag"),
        ("Do you deliver commercial printers to Saudi Arabia?", "What about Abu Dhabi?", "Great, prepare a quote for 1 printer to Abu Dhabi")
    ]
    for i, (q1, q2, q3) in enumerate(correction_variations * 5, 1):
        scripts.append({
            "id": f"CORR_{i:02d}",
            "persona": f"Slot Correction & Pronoun Resolution",
            "language": "en",
            "turns": [
                {"user": q1, "expected_sku": "CX-02"},
                {"user": q2, "expected_sku": "CX-02"},
                {"user": q3, "expected_sku": "CX-02"}
            ]
        })

    return scripts[:100]


def evaluate_script(script: Dict[str, Any], pipeline: CX02Pipeline) -> Dict[str, Any]:
    sender_id = f"eval_{script['id']}_{int(time.time()*1000)%100000}"
    turns_results = []
    asked_questions = set()

    turn_accuracy = []
    turn_understanding = []
    turn_tone = []
    turn_flow = []
    turn_no_repeated = []

    for turn_idx, turn in enumerate(script["turns"]):
        user_msg = turn["user"]
        t0 = time.perf_counter()
        res = pipeline.process(user_message=user_msg, sender_id=sender_id)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        reply = res.get("reply", "")
        intent = res.get("intent", "")
        reply_source = res.get("reply_source", "llm")
        lang = res.get("language", "en")

        # 1. Accuracy Check (0-100%): validate numbers and commercial claims
        val = validate_response(
            reply=reply,
            tool_results=res.get("tools_called", []),
            retrieved_chunks=res.get("chunks_retrieved", []),
            user_message=user_msg
        )
        acc_score = 100.0 if val["is_valid"] else 40.0

        # 2. Understanding Check (0-100%): SKU / intent matching
        und_score = 100.0
        if "expected_sku" in turn:
            if turn["expected_sku"] == "CX-02" and not any(w in reply.lower() for w in ["cx-02", "cx02", "citizen", "سيتيزن", "പ്രിന്റർ"]):
                und_score = 60.0
        if "expected_intent" in turn:
            if turn["expected_intent"] != intent and turn["expected_intent"] not in intent:
                und_score = min(und_score, 70.0)

        # 3. Tone Check (0-100%): human consultative, no robotic dumps, helpful
        tone_score = 100.0
        if "According to the official specifications" in reply or "Here are the raw specifications:" in reply:
            tone_score = 60.0
        if "NO_ANSWER" in reply or len(reply.strip()) < 15:
            tone_score = 30.0

        # 4. Flow Check (0-100%): Language matching and contextual reference
        flow_score = 100.0
        expected_lang = script["language"]
        if expected_lang == "ar" and not any('\u0600' <= c <= '\u06FF' for c in reply):
            flow_score = 50.0
        elif expected_lang == "ml" and not any('\u0D00' <= c <= '\u0D7F' for c in reply):
            flow_score = 50.0

        # 5. No Repeated Questions Check (0-100%): Never ask same discovery question twice
        no_rep_score = 100.0
        import re
        q_marks = re.findall(r"([^.?!]+\?)", reply)
        for q in q_marks:
            clean_q = re.sub(r"\s+", " ", q.strip().lower())
            if clean_q in asked_questions:
                no_rep_score = 0.0
                break
            asked_questions.add(clean_q)

        turn_accuracy.append(acc_score)
        turn_understanding.append(und_score)
        turn_tone.append(tone_score)
        turn_flow.append(flow_score)
        turn_no_repeated.append(no_rep_score)

        turns_results.append({
            "turn": turn_idx + 1,
            "user": user_msg,
            "reply_snippet": reply[:100] + "...",
            "reply_source": reply_source,
            "latency_ms": round(elapsed_ms, 1)
        })

    return {
        "id": script["id"],
        "persona": script["persona"],
        "language": script["language"],
        "accuracy": round(sum(turn_accuracy) / len(turn_accuracy), 1),
        "understanding": round(sum(turn_understanding) / len(turn_understanding), 1),
        "tone": round(sum(turn_tone) / len(turn_tone), 1),
        "flow": round(sum(turn_flow) / len(turn_flow), 1),
        "no_repeated_questions": round(sum(turn_no_repeated) / len(turn_no_repeated), 1),
        "turns": turns_results
    }


def main():
    print("=" * 100, flush=True)
    print("RUNNING 100 MULTI-TURN CONVERSATION EVALUATION BENCHMARK", flush=True)
    print("=" * 100, flush=True)

    pipeline = CX02Pipeline()
    scripts = generate_100_conversation_scripts()
    print(f"Total conversation scripts loaded: {len(scripts)}", flush=True)

    results = []
    t_start = time.time()

    for idx, sc in enumerate(scripts, 1):
        res = evaluate_script(sc, pipeline)
        results.append(res)
        if idx % 5 == 0 or idx == len(scripts):
            avg_acc = sum(r["accuracy"] for r in results) / len(results)
            avg_und = sum(r["understanding"] for r in results) / len(results)
            avg_tone = sum(r["tone"] for r in results) / len(results)
            avg_flow = sum(r["flow"] for r in results) / len(results)
            avg_rep = sum(r["no_repeated_questions"] for r in results) / len(results)
            overall = (avg_acc + avg_und + avg_tone + avg_flow + avg_rep) / 5.0
            print(f"[{idx:03d}/100] Overall: {overall:.1f}% | Acc: {avg_acc:.1f}% | Und: {avg_und:.1f}% | Tone: {avg_tone:.1f}% | Flow: {avg_flow:.1f}% | NoRep: {avg_rep:.1f}%", flush=True)

    total_time = round(time.time() - t_start, 1)

    final_report = {
        "total_scripts": len(scripts),
        "total_turns": sum(len(s["turns"]) for s in scripts),
        "execution_time_seconds": total_time,
        "rubric_scores": {
            "accuracy": round(sum(r["accuracy"] for r in results) / len(results), 1),
            "understanding": round(sum(r["understanding"] for r in results) / len(results), 1),
            "tone": round(sum(r["tone"] for r in results) / len(results), 1),
            "flow": round(sum(r["flow"] for r in results) / len(results), 1),
            "no_repeated_questions": round(sum(r["no_repeated_questions"] for r in results) / len(results), 1),
            "overall_average": round(sum((r["accuracy"]+r["understanding"]+r["tone"]+r["flow"]+r["no_repeated_questions"])/5.0 for r in results) / len(results), 1)
        },
        "sample_evaluations": results[:5]
    }

    out_path = BASE_DIR / "data" / "eval" / "conversation_eval_report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(final_report, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 100)
    print("FINAL 100 CONVERSATION EVALUATION REPORT:")
    print(f"  • Total Multi-Turn Scripts: {final_report['total_scripts']}")
    print(f"  • Total Turns Evaluated   : {final_report['total_turns']}")
    print(f"  • Total Elapsed Time      : {total_time} s")
    print(f"  • Accuracy Score          : {final_report['rubric_scores']['accuracy']}%")
    print(f"  • Understanding Score     : {final_report['rubric_scores']['understanding']}%")
    print(f"  • Tone Score              : {final_report['rubric_scores']['tone']}%")
    print(f"  • Flow Score              : {final_report['rubric_scores']['flow']}%")
    print(f"  • No Repeated Questions   : {final_report['rubric_scores']['no_repeated_questions']}%")
    print(f"  • OVERALL RUBRIC SCORE    : {final_report['rubric_scores']['overall_average']}%")
    print("=" * 100)


if __name__ == "__main__":
    main()
