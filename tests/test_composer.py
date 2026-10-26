import pytest
from app.cognitive.reader import read_message
from app.cognitive.understander import understand_message
from app.cognitive.state_machine import StateMachineDecision, SalesState
from app.cognitive.composer import compose_response, Templates


def test_composer_templates_rendering():
    # Small talk
    st = Templates.small_talk()
    assert "Kepler Tech LLC" in st
    assert "Citizen CX-02" in st

    # Price template
    pr = Templates.price(
        name="Citizen CX-02 Photo Printer",
        sku="CX-02",
        formatted_price="3,600.00 AED",
        in_stock=True,
        formatted_old_price="3,900.00 AED"
    )
    assert "3,600.00 AED" in pr
    assert "3,900.00 AED" in pr
    assert "In Stock (Dubai)" in pr

    # Product link template
    pl = Templates.product_link("Citizen CX-02 Photo Printer", "https://www.keplertechllc.com/product/citizen-cx-02-photo-printer/")
    assert "https://www.keplertechllc.com" in pl


def test_composer_discovery_augmentation_when_allowed():
    read_ctx = read_message("Tell me about CX-02")
    und = understand_message(read_ctx)
    decision = StateMachineDecision(
        current_state=SalesState.DISCOVERY,
        previous_state=SalesState.GREETING,
        discovery_question="Are you operating a photo booth or studio?",
        suppress_upsell=False
    )

    tools_called = [{
        "tool": "get_price",
        "result": {
            "status": "success",
            "name": "Citizen CX-02 Photo Printer",
            "sku": "CX-02",
            "formatted_price": "3,600.00 AED",
            "in_stock": True
        }
    }]
    # Grounding validator requires numbers in the reply to appear in retrieved
    # context. In production the RAG chunk always carries the price; supply a
    # minimal chunk here so the validator passes and the discovery question is
    # preserved in the composed reply.
    price_chunk = {"section": "Price", "text": "Citizen CX-02 Photo Printer price: 3,600.00 AED. In Stock (Dubai)."}

    composed = compose_response(
        intent="price",
        tools_called=tools_called,
        chunks=[price_chunk],
        decision=decision,
        user_message="Tell me about CX-02",
        read_ctx=read_ctx,
        understand_res=und
    )

    assert "3,600.00 AED" in composed
    assert "💬 Are you operating a photo booth or studio?" in composed


def test_composer_suppresses_upsell_during_objection():
    read_ctx = read_message("Your prices are too high!")
    und = understand_message(read_ctx)
    decision = StateMachineDecision(
        current_state=SalesState.OBJECTION,
        previous_state=SalesState.GREETING,
        discovery_question="Are you operating a photo booth?",
        recommendation_pitch="Buy our bag!",
        suppress_upsell=True
    )

    tools_called = [{
        "tool": "get_price",
        "result": {
            "status": "success",
            "name": "Citizen CX-02 Photo Printer",
            "sku": "CX-02",
            "formatted_price": "3,600.00 AED",
            "in_stock": True
        }
    }]

    composed = compose_response(
        intent="price",
        tools_called=tools_called,
        chunks=[],
        decision=decision,
        user_message="Your prices are too high!",
        read_ctx=read_ctx,
        understand_res=und
    )

    assert "3,600.00 AED" in composed
    assert "💬" not in composed
    assert "Buy our bag!" not in composed


def test_composer_grounding_validation_fallback():
    # If chunks contain technical specs and candidate has ungrounded claims
    chunks = [{
        "section": "Print Speeds",
        "text": "## Print Speeds\n- 4 x 6 inch: 8.4 seconds in High Speed mode; 9.8 seconds in High Quality mode"
    }]
    read_ctx = read_message("How fast is 4x6?")
    und = understand_message(read_ctx)
    decision = StateMachineDecision(
        current_state=SalesState.DISCOVERY,
        previous_state=SalesState.GREETING,
        suppress_upsell=True
    )

    composed = compose_response(
        intent="datasheet",
        tools_called=[],
        chunks=chunks,
        decision=decision,
        user_message="How fast is 4x6?",
        read_ctx=read_ctx,
        understand_res=und
    )

    # Must contain official facts
    assert "8.4" in composed or "9.8" in composed
    assert "Citizen CX-02" in composed
