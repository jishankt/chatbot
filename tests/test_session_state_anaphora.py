import pytest
from app.cognitive.state_machine import SessionSalesState, load_sales_state, save_sales_state, SalesState
from app.cognitive.reader import read_message
from app.agent.pipeline import CX02Pipeline


def test_session_state_structured_slots_persistence():
    sender_id = "test_slots_persist_01"
    state = load_sales_state(sender_id)
    state.brand = "Citizen"
    state.category = "photo"
    state.update_model("CX-02")
    state.update_model("CY-02")
    state.paper_size = "4x6"
    state.volume = "200 prints/day"
    state.print_only_vs_mfp = "print_only"
    state.budget = 5000.0
    state.lead_info = {"name": "Rashid", "phone": "0501112233"}
    state.last_bot_question = "volume"

    saved = save_sales_state(state)
    assert saved is True

    # Reload from DB and verify all structured slots are intact
    reloaded = load_sales_state(sender_id)
    assert reloaded.brand == "Citizen"
    assert reloaded.category == "photo"
    assert reloaded.current_model == "CY-02"
    assert "CX-02" in reloaded.compared_models
    assert "CY-02" in reloaded.compared_models
    assert reloaded.paper_size == "4x6"
    assert reloaded.volume == "200 prints/day"
    assert reloaded.print_only_vs_mfp == "print_only"
    assert reloaded.budget == 5000.0
    assert reloaded.lead_info["name"] == "Rashid"
    assert reloaded.lead_info["phone"] == "0501112233"
    assert reloaded.last_bot_question == "volume"


def test_category_switch_resets_filters_preserves_lead():
    state = SessionSalesState(
        sender_id="test_switch_01",
        category="cad_plotter",
        brand="Epson",
        current_model="SC-T3100",
        compared_models=["SC-T3100", "SC-T5100"],
        paper_size="A1",
        volume="100 prints/day",
        print_only_vs_mfp="print_only",
        lead_info={"name": "Fatima", "email": "fatima@arch.ae"}
    )
    
    # Switch category to photo
    state.switch_category_or_brand(new_category="photo")
    assert state.category == "photo"
    assert state.paper_size is None
    assert state.volume is None
    assert state.current_model is None
    assert state.compared_models == []
    # Lead info MUST be preserved
    assert state.lead_info["name"] == "Fatima"
    assert state.lead_info["email"] == "fatima@arch.ae"


def test_anaphora_resolution_from_sales_state():
    state = SessionSalesState(
        sender_id="test_anaphora_01",
        current_model="CY-02",
        compared_models=["CX-02", "CY-02"]
    )
    
    # 1. "it" / "this" resolves to CY-02
    ctx_single = read_message("how much is it?", sales_state=state)
    assert ctx_single.resolved_model == "CY-02"
    assert ctx_single.is_anaphora is True

    # 2. "first one" resolves to CX-02
    ctx_first = read_message("tell me about the first one", sales_state=state)
    assert ctx_first.resolved_model == "CX-02"
    assert ctx_first.reference_type == "first"

    # 3. "second one" resolves to CY-02
    ctx_second = read_message("what about the second one?", sales_state=state)
    assert ctx_second.resolved_model == "CY-02"
    assert ctx_second.reference_type == "second"

    # 4. "its media" resolves to consumables for CY-02
    ctx_media = read_message("what about its media?", sales_state=state)
    assert ctx_media.resolved_model == "CY-02"
    assert ctx_media.reference_type == "consumables"

    # 5. "why this" resolves to why for CY-02
    ctx_why = read_message("why this printer?", sales_state=state)
    assert ctx_why.resolved_model == "CY-02"
    assert ctx_why.reference_type == "why"


def test_self_correction_parsing():
    # 1. Paper size correction
    ctx_size = read_message("actually A1 not A0")
    assert ctx_size.is_correction is True
    assert ctx_size.correction_slot == "paper_size"
    assert ctx_size.correction_val == "A1"

    # 2. Volume correction
    ctx_vol = read_message("sorry it's 200 prints per day")
    assert ctx_vol.is_correction is True
    assert ctx_vol.correction_slot == "volume"
    assert "200" in str(ctx_vol.correction_val)

    # 3. Category correction
    ctx_cat = read_message("no, photo printer not cad")
    assert ctx_cat.is_correction is True
    assert ctx_cat.correction_slot == "category"
    assert ctx_cat.correction_val == "photo"


def test_chip_and_bare_number_inheritance():
    state = SessionSalesState(
        sender_id="test_chip_01",
        last_bot_question="volume"
    )
    
    # Bare number "100" after volume question
    ctx_vol = read_message("100", sales_state=state)
    assert ctx_vol.interpreted_context is not None
    assert "100 prints per day" in ctx_vol.interpreted_context

    # Bare size after paper size question
    state.last_bot_question = "paper_size"
    ctx_size = read_message("A1", sales_state=state)
    assert ctx_size.interpreted_context is not None
    assert "A1" in ctx_size.interpreted_context


def test_pipeline_multi_turn_anaphora_flow():
    pipeline = CX02Pipeline()
    sender_id = "test_mt_flow_01"

    # Turn 1: recommend kiosk printer
    r1 = pipeline.process("I run a busy mall kiosk and don't want to refill all the time", sender_id=sender_id)
    assert "CY-02" in r1["reply"]

    # Turn 2: "why this?" -> must explain CY-02 roll capacity
    r2 = pipeline.process("why this?", sender_id=sender_id)
    assert "Citizen CY-02" in r2["reply"]
    assert "700 prints per roll" in r2["reply"]

    # Turn 3: "its media?" -> must return CY-02 media sets
    r3 = pipeline.process("its media?", sender_id=sender_id)
    assert "CY-02 Genuine Media Sets" in r3["reply"]
    assert "CY-MS46" in r3["reply"]

    # Turn 4: self-correction: "actually 5x7"
    r4 = pipeline.process("actually 5x7", sender_id=sender_id)
    assert "5x7" in r4["reply"]
