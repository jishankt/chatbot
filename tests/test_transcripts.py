import json
import pytest
from pathlib import Path
from app.agent.pipeline import CX02Pipeline

FORBIDDEN_PHRASES = [
    "we do not sell",
    "we do not supply",
    "specialize exclusively",
    "excl. vat"
]


@pytest.fixture
def pipeline():
    return CX02Pipeline()


def test_transcript_replay_no_forbidden_strings(pipeline):
    transcript_file = Path(__file__).parent / "transcripts" / "sample_chat.json"
    with open(transcript_file, "r", encoding="utf-8") as f:
        turns = json.load(f)

    sender_id = "test_transcript_user_wp06"

    for idx, turn in enumerate(turns):
        user_msg = turn["input"]
        res = pipeline.process(user_message=user_msg, sender_id=sender_id)
        reply = res["reply"]
        reply_lower = reply.lower()

        # Assert no forbidden phrases
        for fp in FORBIDDEN_PHRASES:
            assert fp not in reply_lower, (
                f"Turn {idx} ('{user_msg}') contained forbidden phrase '{fp}'. Reply: {reply}"
            )


def test_epson_printers_answered_from_sources(pipeline):
    res = pipeline.process("Do you sell Epson printers?", sender_id="user_epson_test")
    reply = res["reply"]
    reply_lower = reply.lower()

    assert "epson" in reply_lower
    assert "https://" in reply  # Provides catalog category link
    assert any(term in reply_lower for term in ["sales", "team", "specialist"])  # Offers salesperson
    for fp in FORBIDDEN_PHRASES:
        assert fp not in reply_lower


def test_printer_repair_answered_from_sources(pipeline):
    res = pipeline.process("Do you do printer repair?", sender_id="user_repair_test")
    reply = res["reply"]
    reply_lower = reply.lower()

    assert "repair" in reply_lower
    assert any(term in reply_lower for term in ["maintenance", "amc", "service", "parts"])
    assert "https://" in reply  # Service page link
    assert res["intent"] == "service_enquiry"
    # Service inquiry creates lead and hands off
    assert any(t["tool"] == "create_lead" for t in res["tools_called"])
    assert any(t["tool"] == "handoff_to_human" for t in res["tools_called"])
    for fp in FORBIDDEN_PHRASES:
        assert fp not in reply_lower


def test_ship_to_kuwait_answered_from_sources(pipeline):
    res = pipeline.process("Do you ship to Kuwait?", sender_id="user_kuwait_test")
    reply = res["reply"]
    reply_lower = reply.lower()

    assert "kuwait" in reply_lower
    assert "business days" in reply_lower or "days" in reply_lower
    assert "confirm" in reply_lower  # Mentions our team will confirm
    assert res["intent"] == "coverage"
    for fp in FORBIDDEN_PHRASES:
        assert fp not in reply_lower
