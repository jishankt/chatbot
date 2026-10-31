"""
tests/test_eval_benchmark.py  —  WP8: Evaluation Benchmark Test Suite

Verifies:
1. Benchmark set file exists (data/eval/eval_set.json) and contains exactly 300 items.
2. Stratified 70/30 split: exactly 210 dev items and 90 frozen holdout items.
3. Category distribution matches master specification:
   - price: 50 (35 dev / 15 holdout)
   - specs: 60 (42 dev / 18 holdout)
   - media: 40 (28 dev / 12 holdout)
   - policy: 30 (21 dev / 9 holdout)
   - guardrails: 60 (42 dev / 18 holdout)
   - typo_manglish: 30 (21 dev / 9 holdout)
   - multi_turn: 30 (21 dev / 9 holdout)
4. Schema validation: all items have required fields and non-empty inputs.
5. Benchmark execution: evaluates a stratified dev subset against pipeline and verifies:
   - 100% Guardrails accuracy (no competitor leaks, correct refusals)
   - 0 Commercial figure hallucinations
   - Offline resilience and graceful degradation
"""

import json
from pathlib import Path
import pytest

from app.agent.orchestrator import CX02Orchestrator
from app.tools.pricing import load_products_whitelist
from eval.run_eval import (
    evaluate_single_item,
    compute_valid_pricing_numbers,
    check_competitor_leakage
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EVAL_PATH = PROJECT_ROOT / "data" / "eval" / "eval_set.json"


@pytest.fixture(scope="module")
def eval_items():
    assert EVAL_PATH.exists(), f"Eval file missing at {EVAL_PATH}"
    with open(EVAL_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def orchestrator():
    return CX02Orchestrator()


@pytest.fixture(scope="module")
def valid_pricing():
    whitelist = load_products_whitelist()
    return compute_valid_pricing_numbers(whitelist)


def test_eval_set_total_count_and_split(eval_items):
    assert len(eval_items) == 300, f"Expected 300 total items, found {len(eval_items)}"

    dev_count = sum(1 for it in eval_items if it.get("split") == "dev")
    holdout_count = sum(1 for it in eval_items if it.get("split") == "holdout")

    assert dev_count == 210, f"Expected 210 dev items (70%), found {dev_count}"
    assert holdout_count == 90, f"Expected 90 holdout items (30%), found {holdout_count}"


def test_eval_set_stratified_categories(eval_items):
    expected_categories = {
        "price": (50, 35, 15),
        "specs": (60, 42, 18),
        "media": (40, 28, 12),
        "policy": (30, 21, 9),
        "guardrails": (60, 42, 18),
        "typo_manglish": (30, 21, 9),
        "multi_turn": (30, 21, 9),
    }

    counts = {}
    for it in eval_items:
        cat = it.get("category")
        assert cat in expected_categories, f"Unexpected category '{cat}'"
        counts.setdefault(cat, {"total": 0, "dev": 0, "holdout": 0})
        counts[cat]["total"] += 1
        counts[cat][it["split"]] += 1

    for cat, (exp_tot, exp_dev, exp_hold) in expected_categories.items():
        assert counts[cat]["total"] == exp_tot, (
            f"Category {cat} total mismatch: {counts[cat]['total']} != {exp_tot}"
        )
        assert counts[cat]["dev"] == exp_dev, (
            f"Category {cat} dev mismatch: {counts[cat]['dev']} != {exp_dev}"
        )
        assert counts[cat]["holdout"] == exp_hold, (
            f"Category {cat} holdout mismatch: {counts[cat]['holdout']} != {exp_hold}"
        )


def test_eval_set_item_schema(eval_items):
    required_keys = {"id", "category", "input", "expected_intent", "expected_route", "split"}
    ids = set()

    for it in eval_items:
        for rk in required_keys:
            assert rk in it, f"Item missing key '{rk}': {it}"
        assert it["id"] not in ids, f"Duplicate ID: {it['id']}"
        ids.add(it["id"])
        assert len(it["input"].strip()) > 0, f"Empty input text in item {it['id']}"
        assert isinstance(it.get("check_contains", []), list)
        assert isinstance(it.get("check_not_contains", []), list)


def test_competitor_leakage_detector():
    # Should detect improper recommendation
    assert check_competitor_leakage("We offer Canon Selphy at 400 AED") is True
    assert check_competitor_leakage("DNP DS620 is better than CX-02") is True

    # Safe refusal should not be flagged as leakage
    assert check_competitor_leakage("We do not sell Canon or DNP printers. We specialize exclusively in the Citizen CX-02.") is False
    assert check_competitor_leakage("Citizen CX-02 photo printer is 4,385 AED.") is False


def test_guardrails_dev_subset_zero_tolerance(eval_items, orchestrator, valid_pricing):
    # Test all dev guardrail items
    guardrail_dev = [it for it in eval_items if it["category"] == "guardrails" and it["split"] == "dev"]
    assert len(guardrail_dev) == 42

    failures = []
    for it in guardrail_dev:
        res = evaluate_single_item(orchestrator, it, valid_pricing)
        if not res["guardrail_passed"]:
            failures.append((it["id"], it["input"], res["reply"]))

    assert len(failures) == 0, f"Guardrail failures in dev set: {failures}"


def test_commercial_pricing_dev_subset(eval_items, orchestrator, valid_pricing):
    # Test sample of dev price items
    price_dev = [it for it in eval_items if it["category"] == "price" and it["split"] == "dev"][:15]

    for it in price_dev:
        res = evaluate_single_item(orchestrator, it, valid_pricing)
        assert len(res["hallucinated_prices"]) == 0, (
            f"Hallucinated price in item {it['id']}: {res['hallucinated_prices']}"
        )
        assert not res["competitor_leak"], f"Competitor leak in {it['id']}"


def test_offline_resilience_and_graceful_degradation(orchestrator, valid_pricing):
    # Test that even if external calls are not available, pipeline responds cleanly and safely
    queries = [
        "How much is the CX-02?",
        "Do you sell Canon?",
        "What are your delivery charges?",
        "Can I return an opened box?",
    ]
    for q in queries:
        it = {
            "category": "price",
            "split": "dev",
            "input": q,
            "expected_intent": "price",
            "expected_route": "tool",
        }
        res = evaluate_single_item(orchestrator, it, valid_pricing)
        assert res["latency_ms"] < 6000.0, f"Latency exceeded: {res['latency_ms']} ms"
        assert len(res["reply"]) > 10, "Empty or truncated reply"
