import json
import logging
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple
from pydantic import BaseModel, Field

from app.storage.db import get_db_connection
from app.cognitive.reader import ReadContext
from app.cognitive.understander import UnderstandResult
from app.utils.phone import mask_phone

logger = logging.getLogger(__name__)


class SalesState(str, Enum):
    GREETING = "GREETING"
    DISCOVERY = "DISCOVERY"
    RECOMMENDATION = "RECOMMENDATION"
    QUOTING = "QUOTING"
    OBJECTION = "OBJECTION"
    HANDOFF = "HANDOFF"
    CLOSED = "CLOSED"


class SessionSalesState(BaseModel):
    sender_id: str
    current_state: SalesState = SalesState.GREETING
    turn_count: int = 0
    business_type: Optional[str] = None
    delivery_destination: Optional[str] = None
    target_sku: Optional[str] = None
    quote_id: Optional[str] = None
    discovery_questions_asked: List[str] = Field(default_factory=list)
    last_intent: Optional[str] = None


class StateMachineDecision(BaseModel):
    current_state: SalesState
    previous_state: SalesState
    discovery_question: Optional[str] = None
    recommendation_pitch: Optional[str] = None
    handoff_summary: Optional[str] = None
    suppress_upsell: bool = False
    action_notes: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Storage Persistence Helpers
# ---------------------------------------------------------------------------

def load_sales_state(sender_id: str) -> SessionSalesState:
    """Loads existing state from SQLite, or initializes a new GREETING state."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM conversation_states WHERE sender_id = ?", (sender_id,))
        row = cur.fetchone()
        if row:
            raw_asked = row["discovery_questions_asked"]
            asked = json.loads(raw_asked) if raw_asked else []
            return SessionSalesState(
                sender_id=row["sender_id"],
                current_state=SalesState(row["current_state"]),
                turn_count=row["turn_count"],
                business_type=row["business_type"],
                delivery_destination=row["delivery_destination"],
                target_sku=row["target_sku"],
                quote_id=row["quote_id"],
                discovery_questions_asked=asked,
                last_intent=row["last_intent"]
            )
        return SessionSalesState(sender_id=sender_id)
    finally:
        conn.close()


def save_sales_state(state: SessionSalesState) -> None:
    """Persists updated state into SQLite."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO conversation_states (
                sender_id, current_state, turn_count, business_type,
                delivery_destination, target_sku, quote_id,
                discovery_questions_asked, last_intent, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(sender_id) DO UPDATE SET
                current_state = excluded.current_state,
                turn_count = excluded.turn_count,
                business_type = COALESCE(excluded.business_type, conversation_states.business_type),
                delivery_destination = COALESCE(excluded.delivery_destination, conversation_states.delivery_destination),
                target_sku = COALESCE(excluded.target_sku, conversation_states.target_sku),
                quote_id = COALESCE(excluded.quote_id, conversation_states.quote_id),
                discovery_questions_asked = excluded.discovery_questions_asked,
                last_intent = excluded.last_intent,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                state.sender_id,
                state.current_state.value,
                state.turn_count,
                state.business_type,
                state.delivery_destination,
                state.target_sku,
                state.quote_id,
                json.dumps(state.discovery_questions_asked),
                state.last_intent
            )
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Discovery Questions and Recommendations
# ---------------------------------------------------------------------------

DISCOVERY_QUESTIONS = {
    "business_type": "To recommend the ideal media and accessories, are you setting up a photo booth, a portrait studio, or corporate events?",
    "print_size": "Which print size do you plan to offer most frequently (standard 4x6\", or larger 5x7\" / 6x8\")?",
    "mobility": "Will the printer be permanently placed at a studio/kiosk, or transported regularly to event venues?"
}

RECOMMENDATIONS = {
    "photobooth": (
        "💡 *Recommended Setup for Photo Booths*:\n"
        "• *Citizen CX-02 Photo Printer* (Ultra-compact 12 kg chassis, 9.8s per 4x6 print)\n"
        "• *4x6\" Media Set (CX2-MS46-2PC)*: 800 prints per box for maximum volume\n"
        "• *Citizen CX-02 Protective Carry Bag (CX-02-BAG)*: Padded protection for transport"
    ),
    "studio": (
        "💡 *Recommended Setup for Portrait Studios*:\n"
        "• *Citizen CX-02 Photo Printer* (Premium 300 & 600 dpi resolution)\n"
        "• *5x7\" Media Set (CX2-MS57-2PC)*: 460 prints per box for professional studio portraits\n"
        "• *Citizen Thermal Head Cleaning Pen (CITIZEN-PEN)*: Routine maintenance for clean thermal output"
    ),
    "event": (
        "💡 *Recommended Setup for Event Photographers*:\n"
        "• *Citizen CX-02 Photo Printer* (Energy-saving sleep mode & rapid warmup)\n"
        "• *4x6\" Media Set (CX2-MS46-2PC)* or *6x8\" Media Set (CX2-MS68-2PC)*\n"
        "• *Citizen CX-02 Protective Carry Bag (CX-02-BAG)* for safe on-site transport"
    )
}


def build_handoff_summary(
    state: SessionSalesState,
    understand_res: UnderstandResult,
    phone: Optional[str] = None,
    customer_name: Optional[str] = None
) -> str:
    """Produces structured handoff summary for human sales rep."""
    masked = mask_phone(phone) if phone else "Not provided"
    name = customer_name or "Valued Customer"
    sku = state.target_sku or understand_res.entities.sku or "CX-02"
    qty = understand_res.entities.quantity or 1
    dest = state.delivery_destination or understand_res.entities.delivery_destination or "UAE (Default)"
    b_type = state.business_type or understand_res.entities.business_type or "General Commercial"
    readiness = understand_res.commercial_readiness.upper()

    summary_lines = [
        "📋 *Kepler Tech Sales Desk Handoff Summary*:",
        f"• Customer: {name} ({masked})",
        f"• Channel / Sender: {state.sender_id}",
        f"• Stage at Handoff: {state.current_state.value}",
        f"• Primary Intent: {understand_res.intent.primary_intent}",
        f"• Business Use Case: {b_type}",
        f"• Delivery Destination: {dest}",
        f"• Focus Product: {sku} (Qty: {qty})",
        f"• Commercial Readiness: {readiness}",
        f"• Urgency: {understand_res.urgency.upper()}",
        f"• Sentiment: {understand_res.sentiment.capitalize()}"
    ]

    risks = []
    if understand_res.risk_flags.competitor_mentioned:
        risks.append("Competitor Mentioned")
    if understand_res.risk_flags.legal_threat:
        risks.append("Legal / Regulatory Threat")
    if understand_res.risk_flags.anger_frustration:
        risks.append("Customer Frustration")
    if understand_res.risk_flags.churn_risk:
        risks.append("Churn / Cancellation Risk")
    if understand_res.risk_flags.prompt_injection:
        risks.append("Prompt Injection Blocked")

    if risks:
        summary_lines.append(f"• ⚠️ Risk Flags: {', '.join(risks)}")

    return "\n".join(summary_lines)


# ---------------------------------------------------------------------------
# State Transition Engine (Cognitive Step 3: THINK)
# ---------------------------------------------------------------------------

def transition_sales_state(
    state: SessionSalesState,
    understand_res: UnderstandResult,
    read_ctx: ReadContext,
    phone: Optional[str] = None,
    customer_name: Optional[str] = None
) -> StateMachineDecision:
    """
    Executes deterministic state transition logic, enjoining hard operational rules:
      1. Immediate handoff on guardrails, discounts, out-of-scope, legal/churn risk, outside GCC, or unknown SKUs.
      2. Maximum 1 discovery question per turn.
      3. Strict cross-sell suppression during objections, complaints, or policy inquiries.
    """
    prev_state = state.current_state
    notes = []

    # 1. Update entities in state
    if understand_res.entities.business_type and understand_res.entities.business_type != "unknown":
        state.business_type = understand_res.entities.business_type
    if understand_res.entities.delivery_destination:
        state.delivery_destination = understand_res.entities.delivery_destination
    if understand_res.entities.sku:
        state.target_sku = understand_res.entities.sku

    state.turn_count += 1
    state.last_intent = understand_res.intent.primary_intent

    primary_intent = understand_res.intent.primary_intent
    risk = understand_res.risk_flags

    # 2. Check for Immediate Handoff Triggers
    is_handoff_trigger = (
        primary_intent in ("guardrails", "human_demo_reserve", "discount_negotiation") or
        risk.legal_threat or
        risk.anger_frustration or
        risk.churn_risk or
        (state.delivery_destination == "outside_gcc") or
        (understand_res.entities.quantity and understand_res.entities.quantity >= 10 and state.target_sku == "CX-02")
    )

    if is_handoff_trigger:
        state.current_state = SalesState.HANDOFF
        notes.append(f"Transitioned to HANDOFF due to intent='{primary_intent}' or risk flags")
        handoff_summary = build_handoff_summary(state, understand_res, phone=phone, customer_name=customer_name)
        save_sales_state(state)
        return StateMachineDecision(
            current_state=state.current_state,
            previous_state=prev_state,
            suppress_upsell=True,
            handoff_summary=handoff_summary,
            action_notes=notes
        )

    # 3. Check for Objection Triggers
    is_objection = (
        understand_res.sentiment in ("frustrated", "negative") or
        (primary_intent == "policies" and understand_res.intent.sub_intent == "warranty")
    )

    if is_objection:
        state.current_state = SalesState.OBJECTION
        notes.append("Customer sentiment or policy objection; suppress upsell")
        save_sales_state(state)
        return StateMachineDecision(
            current_state=state.current_state,
            previous_state=prev_state,
            suppress_upsell=True,
            action_notes=notes
        )

    # 4. Check for Quoting / Pricing Triggers
    is_quoting = (
        primary_intent in ("quote", "price", "link") or
        understand_res.commercial_readiness == "high" or
        (understand_res.entities.quantity and understand_res.entities.quantity > 1)
    )

    if is_quoting:
        state.current_state = SalesState.QUOTING
        notes.append("Customer in high-intent commercial flow (QUOTING)")
        save_sales_state(state)
        return StateMachineDecision(
            current_state=state.current_state,
            previous_state=prev_state,
            suppress_upsell=True,  # Never distract when quoting
            action_notes=notes
        )

    # 5. Check for Recommendation Triggers
    if state.business_type and state.business_type in RECOMMENDATIONS:
        state.current_state = SalesState.RECOMMENDATION
        notes.append(f"Profile known ({state.business_type}); active RECOMMENDATION state")
        rec_pitch = RECOMMENDATIONS[state.business_type]
        save_sales_state(state)
        return StateMachineDecision(
            current_state=state.current_state,
            previous_state=prev_state,
            recommendation_pitch=rec_pitch,
            suppress_upsell=False,
            action_notes=notes
        )

    # 6. Check for Discovery Triggers (Max 1 question per turn)
    if state.business_type is None and "business_type" not in state.discovery_questions_asked:
        state.current_state = SalesState.DISCOVERY
        state.discovery_questions_asked.append("business_type")
        notes.append("Discovery step: asking business_type (1 max question per turn)")
        save_sales_state(state)
        return StateMachineDecision(
            current_state=state.current_state,
            previous_state=prev_state,
            discovery_question=DISCOVERY_QUESTIONS["business_type"],
            suppress_upsell=False,
            action_notes=notes
        )

    # Default: maintain greeting or previous state
    if prev_state == SalesState.GREETING and primary_intent == "small_talk":
        state.current_state = SalesState.GREETING
    else:
        state.current_state = SalesState.DISCOVERY

    save_sales_state(state)
    return StateMachineDecision(
        current_state=state.current_state,
        previous_state=prev_state,
        action_notes=notes
    )
