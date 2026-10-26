import pytest
from app.cognitive.reader import read_message
from app.cognitive.understander import understand_message
from app.cognitive.state_machine import (
    load_sales_state,
    save_sales_state,
    transition_sales_state,
    build_handoff_summary,
    SalesState,
    SessionSalesState
)
from app.agent.pipeline import CX02Pipeline


import time

def test_state_machine_persistence():
    sender = f"test_persistence_user_{int(time.time() * 1000)}"
    state = load_sales_state(sender)
    assert state.current_state == SalesState.GREETING
    assert state.turn_count == 0

    state.current_state = SalesState.QUOTING
    state.business_type = "photobooth"
    state.delivery_destination = "UAE"
    state.target_sku = "CX-02"
    save_sales_state(state)

    reloaded = load_sales_state(sender)
    assert reloaded.current_state == SalesState.QUOTING
    assert reloaded.business_type == "photobooth"
    assert reloaded.delivery_destination == "UAE"
    assert reloaded.target_sku == "CX-02"


def test_max_one_discovery_question_per_turn():
    sender = "test_discovery_user_202"
    state = SessionSalesState(sender_id=sender)

    # Turn 1: Generic inquiry with unknown business type
    read_ctx1 = read_message("Tell me about the Citizen CX-02 printer")
    und1 = understand_message(read_ctx1)
    dec1 = transition_sales_state(state, und1, read_ctx1)

    assert dec1.current_state == SalesState.DISCOVERY
    assert dec1.discovery_question is not None
    assert "business_type" in state.discovery_questions_asked

    # Turn 2: Customer asks another general question without answering business_type
    read_ctx2 = read_message("What are its main advantages?")
    und2 = understand_message(read_ctx2)
    dec2 = transition_sales_state(state, und2, read_ctx2)

    # Should not repeat the business_type question
    if dec2.discovery_question:
        assert dec2.discovery_question != dec1.discovery_question


def test_cross_sell_suppression_during_objection():
    sender = "test_objection_user_303"
    state = SessionSalesState(sender_id=sender)

    read_ctx = read_message("Your delivery is delayed and the price is completely unacceptable!")
    und = understand_message(read_ctx)
    dec = transition_sales_state(state, und, read_ctx)

    assert dec.current_state in (SalesState.OBJECTION, SalesState.HANDOFF)
    assert dec.suppress_upsell is True
    assert dec.recommendation_pitch is None


def test_immediate_handoff_on_guardrails_or_threats():
    sender = "test_handoff_user_404"
    state = SessionSalesState(sender_id=sender)

    # Competitor comparison
    read_ctx = read_message("How does CX-02 compare to DNP DS620?")
    und = understand_message(read_ctx)
    dec = transition_sales_state(state, und, read_ctx)

    assert dec.current_state == SalesState.HANDOFF
    assert dec.suppress_upsell is True
    assert dec.handoff_summary is not None
    assert "Competitor Mentioned" in dec.handoff_summary


def test_immediate_handoff_outside_gcc():
    sender = "test_outside_gcc_user_505"
    state = SessionSalesState(sender_id=sender)

    read_ctx = read_message("Can you ship 2 printers to Nairobi Kenya in Africa?")
    und = understand_message(read_ctx)
    dec = transition_sales_state(state, und, read_ctx)

    assert dec.current_state == SalesState.HANDOFF
    assert "outside_gcc" in dec.handoff_summary.lower()


def test_quoting_state_flow():
    sender = "test_quoting_user_606"
    state = SessionSalesState(sender_id=sender)

    read_ctx = read_message("Please send a quote for 4 boxes of 5x7 media")
    und = understand_message(read_ctx)
    dec = transition_sales_state(state, und, read_ctx)

    assert dec.current_state == SalesState.QUOTING
    assert dec.suppress_upsell is True  # In quoting flow, avoid distracting upsells


def test_recommendation_flow_for_photobooth():
    sender = "test_rec_user_707"
    state = SessionSalesState(sender_id=sender)

    read_ctx = read_message("We operate a wedding photo booth company in Dubai")
    und = understand_message(read_ctx)
    dec = transition_sales_state(state, und, read_ctx)

    assert dec.current_state == SalesState.RECOMMENDATION
    assert dec.recommendation_pitch is not None
    assert "Photo Booths" in dec.recommendation_pitch
    assert "CX2-MS46-2PC" in dec.recommendation_pitch


def test_pipeline_sales_state_integration():
    pipeline = CX02Pipeline()
    sender = "test_pipeline_state_user_808"

    # Turn 1: Initial greeting / general inquiry
    res1 = pipeline.process("Hello, I am interested in Citizen CX-02", sender_id=sender)
    assert "sales_state" in res1
    assert "state_decision" in res1
    assert res1["sales_state"] in ("GREETING", "DISCOVERY")

    # Turn 2: Customer requests a quote
    res2 = pipeline.process("Can you quote 3 units of 5x7 media?", sender_id=sender)
    assert res2["sales_state"] == "QUOTING"
    assert "Quotation" in res2["reply"]
