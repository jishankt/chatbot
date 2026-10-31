import re
import logging
from typing import Dict, Any, List, Optional
from app.config import Config
from app.agent.router import classify_intent, PRICE_KEYWORDS, DATASHEET_KEYWORDS
from app.agent.guardrails import check_pre_guardrails, check_post_guardrails
import app.agent.llm as llm_module
from app.agent.validator import make_extractive_fallback
from app.rag.retriever import retrieve, retrieve_company
from app.tools.pricing import get_price, check_stock, list_products, calculate_cost_per_print
from app.tools.links import get_product_link
from app.tools.quote import create_quote
from app.tools.policies import get_policy
from app.tools.handoff import handoff_to_human, create_lead
from app.storage.messages import log_message, get_conversation_history
from app.storage.leads import set_pending_lead, get_pending_lead, clear_pending_lead

from app.utils.quantity import parse_quantity, parse_multi_item_quantities
from app.cognitive.reader import read_message, ReadContext
from app.cognitive.understander import understand_message, UnderstandResult
from app.cognitive.state_machine import load_sales_state, save_sales_state, transition_sales_state, SalesState

logger = logging.getLogger(__name__)


def determine_target_sku(text: str, read_ctx: Optional[ReadContext] = None) -> Optional[str]:
    # 0. If read_ctx already resolved a specific SKU, honor it only if not default source
    if read_ctx:
        if read_ctx.sku_source == "default":
            return None
        if read_ctx.resolved_sku:
            return read_ctx.resolved_sku
        if read_ctx.is_anaphora or any(an in text.lower() for an in ["these", "those", "them", "this one", "that one"]):
            return None

    raw_lower = text.lower()
    t = raw_lower.replace(" ", "").replace("-", "").replace(".", "").replace("\"", "").replace("×", "x").replace("*", "x")

    # 0.5 Check for non-CX-02 models like CX-01, CX-03, CX-04
    cx_m = re.search(r"\bcx[-_]?(0?[0-9]+)\b", raw_lower)
    if cx_m:
        num = int(cx_m.group(1))
        if num != 2:
            return f"CX-{num:02d}"

    # 1. Direct SKU and accessory matching
    if "bag" in t or "case" in t:
        return "CX-02-BAG"
    if "pen" in t or "cleaning" in t:
        return "CITIZEN-PEN"
    if "6x9" in t:
        return "6x9"
    if "ms46" in t or "4x6" in t or "cx24x6" in t:
        return "CX2-MS46-2PC"
    if "ms57" in t or "5x7" in t or "cx0257" in t:
        return "CX2-MS57-2PC"
    if "ms68" in t or "6x8" in t or "cx26x8" in t:
        return "CX2-MS68-2PC"

    # 2. Unsupported accessories / items or other brands
    unsupported_items = ["tripod", "cable", "adapter", "battery", "scanner", "stand", "bluetooth", "wireless", "xyz", "epson"]
    if any(u in raw_lower for u in unsupported_items):
        return None

    # 3. Queries asking about media in general or recommending media
    if any(gm in raw_lower for gm in ["what media", "which media", "media does", "types of media", "media should"]):
        return None

    # 4. Media without specific size defaults to standard 4x6 media
    if any(m in raw_lower for m in ["media", "paper", "consumable", "rolls"]):
        return "CX2-MS46-2PC"

    # 5. Explicit CX-02 inquiry
    if any(p in raw_lower for p in ["cx-02", "cx02"]):
        return "CX-02"

    # 6. General pricing / purchase inquiry without product specification returns None
    if any(q in raw_lower for q in ["price", "cost", "how much", "rate", "quote", "buy", "order", "link", "url"]):
        return None

    return None


def extract_phone_and_name(text: str) -> Dict[str, Optional[str]]:
    phone_match = re.search(r"(\+?\d[\d\s-]{7,15}\d)", text)
    phone = phone_match.group(1).replace(" ", "").replace("-", "") if phone_match else None

    name_match = re.search(r"(?:my name is|i am|this is)\s+([a-zA-Z\s]+)", text, re.IGNORECASE)
    name = name_match.group(1).strip() if name_match else None

    return {"phone": phone, "name": name}


PRODUCT_CARD_DEFS = {
    # 4 Core Photo Printers (Citizen lineup)
    "CX-02": {
        "sku": "CX-02",
        "title": "Citizen CX-02",
        "full_name": "Citizen CX-02 Photo Printer",
        "badge": "Flagship Photo",
        "price_display": "4,385.00 AED",
        "price_quote_text": "Commercial Quote on Request",
        "recommendation": "Flagship ultra-compact dye-sub photo printer for event booths & studios.",
        "image_url": "/static/img/citizen_cx02_card.webp",
        "url": "https://www.keplertechllc.com/product/citizen-cx-02-photo-printer/",
        "in_stock": True,
        "compare_query": "Compare Citizen CX-02 specifications"
    },
    "CX-02W": {
        "sku": "CX-02W",
        "title": "Citizen CX-02W",
        "full_name": "Citizen CX-02W Wide Photo Printer",
        "badge": "Wide Format",
        "price_display": "6,820.00 AED",
        "price_quote_text": "Commercial Quote on Request",
        "recommendation": "Wide dye-sublimation format supporting 8x10\" and 8x12\" professional prints.",
        "image_url": "/static/img/citizen_cx02_card.webp",
        "url": "https://www.keplertechllc.com/product/citizen-cx-02w-photo-printer/",
        "in_stock": True,
        "compare_query": "Compare Citizen CX-02W specifications"
    },
    "CY-02": {
        "sku": "CY-02",
        "title": "Citizen CY-02",
        "full_name": "Citizen CY-02 Photo Printer",
        "badge": "High Capacity",
        "price_display": "3,400.00 AED",
        "price_quote_text": "Commercial Quote on Request",
        "recommendation": "High capacity event printer (700 prints per 4x6 roll) for heavy kiosk volume.",
        "image_url": "/static/img/citizen_cx02_card.webp",
        "url": "https://www.keplertechllc.com/product/citizen-cy-02-photo-printer/",
        "in_stock": True,
        "compare_query": "Compare Citizen CY-02 specifications"
    },
    "CZ-01": {
        "sku": "CZ-01",
        "title": "Citizen CZ-01",
        "full_name": "Citizen CZ-01 Photo Printer",
        "badge": "Ultra Compact",
        "price_display": "3,200.00 AED",
        "price_quote_text": "Commercial Quote on Request",
        "recommendation": "Lightweight 5.8kg compact photo printer for small booths, popups, and passports.",
        "image_url": "/static/img/citizen_cx02_card.webp",
        "url": "https://www.keplertechllc.com/product/citizen-cz-01-photo-printer/",
        "in_stock": True,
        "compare_query": "Compare Citizen CZ-01 specifications"
    },

    # 4 Core Consumables & Maintenance (Like CX-02)
    "CX2-MS46-2PC": {
        "sku": "CX2-MS46-2PC",
        "title": "4x6\" Media Set",
        "full_name": "Citizen CX-02 4x6\" Media Set (CX2-MS46-2PC)",
        "badge": "Consumable",
        "price_display": "490.00 AED",
        "price_quote_text": "490.00 AED",
        "recommendation": "Genuine dye-sublimation media (approx. 800 prints per box, 2 rolls).",
        "image_url": "/static/img/citizen_media_4x6.webp",
        "url": "https://www.keplertechllc.com/product/citizen-cx-02-4x6-printer-media/",
        "in_stock": True,
        "compare_query": "Tell me more about 4x6 media"
    },
    "CX2-MS57-2PC": {
        "sku": "CX2-MS57-2PC",
        "title": "5x7\" Media Set",
        "full_name": "Citizen CX-02 5x7\" Media Set (CX2-MS57-2PC)",
        "badge": "Consumable",
        "price_display": "500.00 AED",
        "price_quote_text": "500.00 AED",
        "recommendation": "Genuine Citizen OEM media (460 verified prints per set, 2 rolls).",
        "image_url": "/static/img/citizen_media_5x7.jpg",
        "url": "https://www.keplertechllc.com/product/citizen-cx-02-5x7-media-set-2-roll/",
        "in_stock": True,
        "compare_query": "Tell me more about 5x7 media"
    },
    "CX2-MS68-2PC": {
        "sku": "CX2-MS68-2PC",
        "title": "6x8\" Media Set",
        "full_name": "Citizen CX-02 6x8\" Media Set (CX2-MS68-2PC)",
        "badge": "Consumable",
        "price_display": "500.00 AED",
        "price_quote_text": "500.00 AED",
        "recommendation": "Genuine dye-sublimation media (approx. 400 prints per box, 2 rolls).",
        "image_url": "/static/img/citizen_media_6x8.webp",
        "url": "https://www.keplertechllc.com/product/citizen-cx-02-printer-6x8-media/",
        "in_stock": True,
        "compare_query": "Tell me more about 6x8 media"
    },
    "CITIZEN-PEN": {
        "sku": "CITIZEN-PEN",
        "title": "Cleaning Pen",
        "full_name": "Citizen Thermal Head Cleaning Pen",
        "badge": "Maintenance",
        "price_display": "190.00 AED",
        "price_quote_text": "190.00 AED",
        "recommendation": "OEM thermal printhead maintenance pen to prolong printhead life.",
        "image_url": "/static/img/citizen_pen_card.webp",
        "url": "https://www.keplertechllc.com/product/citizen-thermal-head-cleaning-pen/",
        "in_stock": True,
        "compare_query": "Tell me how to use the Citizen cleaning pen"
    },
    "CX-02-BAG": {
        "sku": "CX-02-BAG",
        "title": "CX-02 Carry Bag",
        "full_name": "Citizen CX-02 Protective Carry Bag",
        "badge": "Accessory",
        "price_display": "350.00 AED",
        "price_quote_text": "350.00 AED",
        "recommendation": "Protective padded bag engineered specifically for CX-02.",
        "image_url": "/static/img/citizen_bag_card.webp",
        "url": "https://www.keplertechllc.com/product/citizen-cx-02-printer-carry-bag/",
        "in_stock": True,
        "compare_query": "Tell me more about the CX-02 carry bag"
    }
}


def build_matched_cards(target_sku: Optional[str], intent: str, user_msg: str, tools_called: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    msg_l = user_msg.lower()
    cards = []

    # 1. Multi-item Quote
    for tc in tools_called:
        if tc.get("tool") == "create_quote":
            quote_res = tc.get("result", {})
            for item in quote_res.get("items", []):
                sku = item.get("sku")
                if sku in PRODUCT_CARD_DEFS:
                    c = dict(PRODUCT_CARD_DEFS[sku])
                    c["price_subtext"] = "Commercial Quote on Request"
                    c["recommendation"] = f"Official Quote Item ({item.get('quantity', 1)} unit{'s' if item.get('quantity', 1) > 1 else ''})."
                    if not any(x["sku"] == c["sku"] for x in cards):
                        cards.append(c)
            if cards:
                return cards

    # 2. Consumables & Media Sets Browse (4 items like CX-02 media)
    is_consumables_query = any(w in msg_l for w in [
        "consumable", "consumables", "media", "media sets", "rolls", "paper and ribbon", "paper & ribbon", "paper and rolls", "ink", "ribbon"
    ]) and not any(w in msg_l for w in ["printer only", "hardware only"])

    if is_consumables_query:
        for sku in ["CX2-MS46-2PC", "CX2-MS57-2PC", "CX2-MS68-2PC", "CITIZEN-PEN"]:
            if sku in PRODUCT_CARD_DEFS:
                c = dict(PRODUCT_CARD_DEFS[sku])
                c["price_subtext"] = c["price_display"]
                cards.append(c)
        return cards

    # 3. Explicit "like cx 02", "items like cx 02", "printers like cx 02", or general printers query (4 printer items)
    is_printers_query = any(w in msg_l for w in [
        "like cx 02", "like cx02", "like cx-02", "items like cx 02", "items like cx02", "printers like cx 02",
        "printers like cx02", "printers", "printer", "photo printers", "photo printer", "citizen printers",
        "which printers", "what printers", "show printers", "list printers", "all printers", "models",
        "dye sub", "dye-sub", "dyesub", "sublimation", "thermal photo",
        "داي سب", "سبليميشن", "سبلميشن", "سوبليميشن", "تسامي", "طابعة حرارية", "طابعات حرارية"
    ]) or (
        intent in ("category_browse", "bundle_catalog") and any(w in msg_l for w in [
            "citizen", "photo", "booth", "kiosk", "event", "printer", "dye", "sublim", "داي", "سبليم", "تسامي"
        ])
    )

    is_direct_single_sku = target_sku and target_sku in PRODUCT_CARD_DEFS and not any(p in msg_l for p in [
        "like cx", "other", "all", "compare", "printers", "options", "models", "alternatives"
    ])

    if is_printers_query and not is_direct_single_sku:
        # Return 4 printer cards (CX-02, CX-02W, CY-02, CZ-01)
        for sku in ["CX-02", "CX-02W", "CY-02", "CZ-01"]:
            if sku in PRODUCT_CARD_DEFS:
                c = dict(PRODUCT_CARD_DEFS[sku])
                c["price_subtext"] = c["price_display"]
                cards.append(c)
        return cards

    # 4. Direct SKU match
    if target_sku and target_sku in PRODUCT_CARD_DEFS:
        c = dict(PRODUCT_CARD_DEFS[target_sku])
        c["price_subtext"] = "Commercial Quote on Request" if intent == "quote" else c["price_display"]
        cards.append(c)
        return cards

    # 5. Contextual photo booth / event / specs match (fallback to CX-02)
    cx02_terms = ["cx-02", "cx02", "photo booth", "photobooth", "event", "wedding", "speed", "dimension", "dimensions", "resolution", "dpi", "specs", "specification"]
    if any(t in msg_l for t in cx02_terms) and not any(u in msg_l for u in ["epson", "scanner", "dnp", "fujifilm"]):
        c = dict(PRODUCT_CARD_DEFS["CX-02"])
        c["price_subtext"] = "Commercial Quote on Request" if intent == "quote" else c["price_display"]
        cards.append(c)

    return cards


class CX02Pipeline:

    def __init__(self):
        pass

    def process(
        self,
        user_message: str,
        sender_id: str = "web_user",
        channel: str = "web",
        phone: Optional[str] = None,
        message_id: Optional[str] = None
    ) -> Dict[str, Any]:
        # 1. Check WP13: WhatsApp STOP / Opt-out & Opt-in commands
        from app.storage.consents import is_opted_out, set_opt_out, set_opt_in
        stripped = user_message.strip()
        stop_match = re.match(r"^(stop|unsubscribe|cancel|quit|opt[\s-]?out|توقف|الغاء)[\s.!,]*$", stripped, re.IGNORECASE)
        if stop_match:
            set_opt_out(sender_id, phone=phone, notes=f"Opted out via command: '{stripped}'")
            clear_pending_lead(sender_id)
            reply = (
                "You have been successfully unsubscribed from automated messages from Kepler Tech LLC. "
                f"To re-subscribe or speak with our sales desk, text START or contact us at {Config.KEPLER_WHATSAPP}."
            )
            log_message(sender_id=sender_id, role="user", content=user_message, channel=channel, message_id=message_id)
            log_message(sender_id=sender_id, role="assistant", content=reply, channel=channel)
            return {
                "reply": reply,
                "intent": "opt_out",
                "priority": "low",
                "tools_called": [{"tool": "set_opt_out", "result": {"status": "opted_out"}}],
                "chunks_retrieved": [],
                "prompt_version": Config.PROMPT_VERSION
            }

        start_match = re.match(r"^(start|subscribe|unstop|انضم|بدء)[\s.!,]*$", stripped, re.IGNORECASE)
        if start_match:
            set_opt_in(sender_id, phone=phone, notes=f"Re-subscribed via command: '{stripped}'")
            reply = (
                "Welcome back to Kepler Tech LLC! How can we assist you today with the Citizen CX-02 photo printer, media sets, or official accessories?"
            )
            log_message(sender_id=sender_id, role="user", content=user_message, channel=channel, message_id=message_id)
            log_message(sender_id=sender_id, role="assistant", content=reply, channel=channel)
            return {
                "reply": reply,
                "intent": "opt_in",
                "priority": "low",
                "tools_called": [{"tool": "set_opt_in", "result": {"status": "opted_in"}}],
                "chunks_retrieved": [],
                "prompt_version": Config.PROMPT_VERSION
            }

        if is_opted_out(sender_id):
            reply = (
                "You are currently unsubscribed from automated messages from Kepler Tech LLC. "
                f"Reply START to re-subscribe, or contact our sales team at {Config.KEPLER_WHATSAPP}."
            )
            return {
                "reply": reply,
                "intent": "opted_out_blocked",
                "priority": "low",
                "tools_called": [],
                "chunks_retrieved": [],
                "prompt_version": Config.PROMPT_VERSION
            }

        # 1. Fetch conversation history (last 8 turns) and structured session state
        history = get_conversation_history(sender_id, limit=8)
        sales_state = load_sales_state(sender_id)

        # 2. Cognitive Step 1: READ (Normalization, Language, Anaphora, Quantity, Reference)
        read_ctx = read_message(user_message, history=history, sales_state=sales_state)
        user_msg = read_ctx.normalized_text
        if read_ctx.interpreted_context:
            user_msg = f"{read_ctx.normalized_text} ({read_ctx.interpreted_context})"
        msg_lower = user_msg.lower()
        tools_called = []
        chunks = []

        # Update sales state with model, brand, category, and requirements from read_ctx
        if read_ctx.detected_brand:
            sales_state.brand = read_ctx.detected_brand
        if read_ctx.detected_category:
            sales_state.category = read_ctx.detected_category
        if read_ctx.detected_paper_size:
            sales_state.paper_size = read_ctx.detected_paper_size
        if read_ctx.detected_volume:
            sales_state.volume = read_ctx.detected_volume
        if read_ctx.detected_budget:
            sales_state.budget = read_ctx.detected_budget
        if read_ctx.resolved_model:
            sales_state.update_model(read_ctx.resolved_model, brand=read_ctx.detected_brand, category=read_ctx.detected_category)
        elif read_ctx.resolved_sku:
            sales_state.update_model(read_ctx.resolved_sku, brand=read_ctx.detected_brand, category=read_ctx.detected_category)

        # Handle Phantom Model Detection (Explicit refusal + closest real options, never silent substitution)
        if read_ctx.phantom_model:
            reply = read_ctx.phantom_model["reply"]
            sales_state.last_bot_question = "model_clarification"
            save_sales_state(sales_state)
            log_message(sender_id=sender_id, role="user", content=user_msg, message_id=message_id, channel=channel)
            log_message(sender_id=sender_id, role="assistant", content=reply, channel=channel)
            return {
                "reply": reply,
                "intent": "out_of_scope",
                "priority": "normal",
                "tools_called": [],
                "chunks_retrieved": [],
                "cards": [],
                "language": read_ctx.language,
                "resolved_sku": None,
                "is_anaphora": False,
                "understanding": understand_message(read_ctx).model_dump(),
                "sales_state": sales_state.current_state.value if hasattr(sales_state.current_state, "value") else str(sales_state.current_state),
                "prompt_version": Config.PROMPT_VERSION
            }

        # Handle Ambiguous Model Disambiguation (Exactly 1 clarifying question)
        if read_ctx.disambiguation:
            reply = read_ctx.disambiguation["question"]
            sales_state.last_bot_question = "disambiguation_p8500"
            save_sales_state(sales_state)
            log_message(sender_id=sender_id, role="user", content=user_msg, message_id=message_id, channel=channel)
            log_message(sender_id=sender_id, role="assistant", content=reply, channel=channel)
            return {
                "reply": reply,
                "intent": "clarification",
                "priority": "normal",
                "tools_called": [],
                "chunks_retrieved": [],
                "cards": [],
                "language": read_ctx.language,
                "resolved_sku": None,
                "is_anaphora": False,
                "understanding": understand_message(read_ctx).model_dump(),
                "sales_state": sales_state.current_state.value if hasattr(sales_state.current_state, "value") else str(sales_state.current_state),
                "prompt_version": Config.PROMPT_VERSION
            }

        # Handle self-correction
        correction_prefix = ""
        if read_ctx.is_correction and read_ctx.correction_slot:
            if read_ctx.correction_slot == "paper_size":
                sales_state.paper_size = read_ctx.correction_val
                correction_prefix = f"Understood, updating your size requirement to **{read_ctx.correction_val}**.\n\n"
            elif read_ctx.correction_slot == "volume":
                sales_state.volume = read_ctx.correction_val
                correction_prefix = f"Got it, updating your print volume to **{read_ctx.correction_val}**.\n\n"
            elif read_ctx.correction_slot == "category":
                sales_state.switch_category_or_brand(new_category=read_ctx.correction_val)
                cat_name = "Photo Printers" if read_ctx.correction_val == "photo" else str(read_ctx.correction_val).replace("_", " ").title()
                correction_prefix = f"Understood, switching to **{cat_name}** for your workflow.\n\n"

        # 3. Cognitive Step 2: UNDERSTAND (Structured NLU, Entities, Risk Flags)
        understand_res = understand_message(read_ctx)

        # 4. Cognitive Step 3: THINK (Deterministic Sales Policy State Machine)
        decision = transition_sales_state(
            state=sales_state,
            understand_res=understand_res,
            read_ctx=read_ctx,
            phone=phone
        )

        # Handle Customer Frustration: Acknowledge, restate understood slots, course correct, suppress pitch
        if understand_res.risk_flags.anger_frustration:
            understood_slots = []
            if sales_state.category:
                cat_display = "Photo Printers" if sales_state.category == "photo" else str(sales_state.category).replace("_", " ").title()
                understood_slots.append(f"category: {cat_display}")
            if sales_state.paper_size:
                understood_slots.append(f"size: {sales_state.paper_size}")
            if sales_state.volume:
                understood_slots.append(f"volume: {sales_state.volume}")
            slots_summary = f" (Current context recorded: {', '.join(understood_slots)})" if understood_slots else ""

            ho = handoff_to_human(reason="Customer expressed frustration or bot misunderstanding", summary=user_msg, phone=phone, sender_id=sender_id)
            tools_called.append({"tool": "handoff_to_human", "result": ho})
            reply = (
                f"I apologize for the misunderstanding{slots_summary}. "
                "I want to ensure you get the exact commercial solution without any back-and-forth. "
                "I have notified our senior commercial printing team at Kepler Tech Dubai to assist you directly:\n\n"
                f"{ho['customer_message']}"
            )
            save_sales_state(sales_state)
            log_message(sender_id=sender_id, role="user", content=user_msg, message_id=message_id, channel=channel)
            log_message(sender_id=sender_id, role="assistant", content=reply, channel=channel)
            return {
                "reply": reply,
                "intent": "frustration_handoff",
                "priority": "high",
                "tools_called": tools_called,
                "chunks_retrieved": [],
                "cards": [],
                "language": read_ctx.language,
                "resolved_sku": None,
                "is_anaphora": False,
                "understanding": understand_res.model_dump(),
                "sales_state": decision.current_state.value if hasattr(decision.current_state, "value") else str(decision.current_state),
                "state_decision": decision.model_dump(),
                "prompt_version": Config.PROMPT_VERSION
            }


        # 5. Check pending lead state
        pending = get_pending_lead(sender_id)
        if pending and pending.get("stage") == "awaiting_contact":
            contact = extract_phone_and_name(user_msg)
            captured_phone = contact["phone"] or phone or pending.get("temp_phone")
            captured_name = contact["name"] or pending.get("temp_name") or "Valued Customer"

            if captured_phone:
                create_lead(
                    name=captured_name,
                    phone=captured_phone,
                    notes=f"Captured via pending state. Last intent: {pending.get('last_intent')}",
                    sender_id=sender_id
                )
                clear_pending_lead(sender_id)
                reply = (
                    f"Thank you, {captured_name}! I have recorded your details ({captured_phone}). "
                    f"A Kepler Tech specialist will get in touch with you shortly."
                )
                log_message(sender_id=sender_id, role="user", content=user_msg, message_id=message_id, channel=channel)
                log_message(sender_id=sender_id, role="assistant", content=reply, channel=channel)
                return {
                    "reply": reply,
                    "intent": "lead_captured",
                    "priority": 0,
                    "tools_called": [{"tool": "create_lead", "args": {"name": captured_name, "phone": captured_phone}}],
                    "chunks_retrieved": []
                }

        # 5. Router Intent Classification (Priority 1 to 14)
        routing = classify_intent(user_msg)
        intent = understand_res.intent.primary_intent or routing["intent"]
        priority = routing["priority"]

        # Conflict Resolution & Recommendation Disambiguation
        has_large_format = any(w in msg_lower for w in ["8x10", "8x12", "8 inch", "8\"", "large format", "large prints", "studio portrait", "graduation portrait"])
        has_high_roll_capacity = any(w in msg_lower for w in ["700 prints", "high capacity roll", "high roll capacity", "roll capacity", "unattended", "avoid refill", "no refill", "frequent refill", "refill often", "less refills"]) or (
            any(r in msg_lower for r in ["refill", "refills", "reloading", "paper change"]) and any(w in msg_lower for w in ["frequent", "often", "cannot afford", "minimize", "reduce", "avoid", "less", "downtime", "theme park", "kiosk", "busy"])
        ) or bool(re.search(r"\b700\b", msg_lower) and not any(t in msg_lower for t in ["7700", "t7700", "sc-t7700"]))
        has_ultra_light = any(w in msg_lower for w in ["5.8", "5.8kg", "ultra-compact", "ultra compact", "ultra lightweight", "ultra light", "under 6kg", "under 6 kg"])

        # Conflict 1: 8x10 large format AND 700 prints per roll capacity
        if has_large_format and has_high_roll_capacity:
            reply = (
                "There is a technical trade-off between large print format and roll capacity in the Citizen lineup:\n\n"
                "• **Citizen CX-02W**: Our wide-format 8-inch printer engineered specifically for **8×10\"** and **8×12\"** large studio portraits (yields 110–120 prints per roll).\n"
                "• **Citizen CY-02**: Our high-capacity commercial workhorse holding up to **700 prints per roll**, but designed for standard **4×6\"** (and 6×8\") media.\n\n"
                "To recommend the right model: Is producing **8×10\" large prints** your primary requirement, or is **700-print roll capacity** to minimize reloading downtime more important for your operation?"
            )
            cards = [dict(PRODUCT_CARD_DEFS[s]) for s in ["CX-02W", "CY-02"] if s in PRODUCT_CARD_DEFS]
            log_message(sender_id=sender_id, role="user", content=user_msg, message_id=message_id, channel=channel)
            log_message(sender_id=sender_id, role="assistant", content=reply, channel=channel)
            return {
                "reply": reply,
                "intent": "conflict_resolution",
                "priority": priority,
                "tools_called": tools_called,
                "chunks_retrieved": [],
                "cards": cards,
                "language": read_ctx.language,
                "resolved_sku": None,
                "is_anaphora": False,
                "understanding": understand_res.model_dump(),
                "sales_state": decision.current_state.value if hasattr(decision.current_state, "value") else str(decision.current_state),
                "state_decision": decision.model_dump(),
                "prompt_version": Config.PROMPT_VERSION
            }

        # Conflict 2: Ultra-lightweight (<6kg) AND 8x10 large format
        if has_ultra_light and has_large_format:
            reply = (
                "There is a technical trade-off between ultra-lightweight portability and wide-format printing:\n\n"
                "• **Citizen CZ-01**: Ultra-compact and portable at just **5.8 kg** (with built-in anti-curl technology), supporting standard **4×6\"** and square **4×4\"** prints.\n"
                "• **Citizen CX-02W**: Engineered for large **8×10\"** and **8×12\"** studio portraits, weighing **14 kg**.\n\n"
                "Which is your main priority: **ultra-lightweight portability (5.8 kg)** for mobile on-site shooting, or **8×10\" wide-format** studio capabilities?"
            )
            cards = [dict(PRODUCT_CARD_DEFS[s]) for s in ["CZ-01", "CX-02W"] if s in PRODUCT_CARD_DEFS]
            log_message(sender_id=sender_id, role="user", content=user_msg, message_id=message_id, channel=channel)
            log_message(sender_id=sender_id, role="assistant", content=reply, channel=channel)
            return {
                "reply": reply,
                "intent": "conflict_resolution",
                "priority": priority,
                "tools_called": tools_called,
                "chunks_retrieved": [],
                "cards": cards,
                "language": read_ctx.language,
                "resolved_sku": None,
                "is_anaphora": False,
                "understanding": understand_res.model_dump(),
                "sales_state": decision.current_state.value if hasattr(decision.current_state, "value") else str(decision.current_state),
                "state_decision": decision.model_dump(),
                "prompt_version": Config.PROMPT_VERSION
            }

        # Single-Requirement Matches (when customer states specific operational requirement without conflict)
        if has_high_roll_capacity and not has_large_format:
            reply = (
                "For high-volume retail kiosks, amusement attractions, and unattended operations where minimizing reloading downtime is critical, "
                "our primary recommendation is the **Citizen CY-02 Photo Printer**:\n\n"
                "• **High Roll Capacity**: Holds up to **700 prints per roll** on 4×6\" (over double standard capacity), drastically reducing refill downtime.\n"
                "• **Media Formats**: Supports 4×6\" (CY-MS46) and 6×8\" (CY-MS68) genuine media sets.\n"
                "• **Heavy-Duty Commercial Design**: Built for continuous, high-duty commercial kiosk installations.\n\n"
                "Would you like official pricing or genuine media set details for the CY-02?"
            )
            cards = [dict(PRODUCT_CARD_DEFS[s]) for s in ["CY-02"] if s in PRODUCT_CARD_DEFS]
            log_message(sender_id=sender_id, role="user", content=user_msg, message_id=message_id, channel=channel)
            log_message(sender_id=sender_id, role="assistant", content=reply, channel=channel)
            return {
                "reply": reply,
                "intent": "recommendation_cy02",
                "priority": priority,
                "tools_called": tools_called,
                "chunks_retrieved": [],
                "cards": cards,
                "language": read_ctx.language,
                "resolved_sku": "CY-02",
                "is_anaphora": False,
                "understanding": understand_res.model_dump(),
                "sales_state": decision.current_state.value if hasattr(decision.current_state, "value") else str(decision.current_state),
                "state_decision": decision.model_dump(),
                "prompt_version": Config.PROMPT_VERSION
            }

        if has_ultra_light and not has_large_format:
            reply = (
                "For mobile event photographers, pop-up events, and tight photo booth spaces requiring maximum portability, "
                "our top recommendation is the **Citizen CZ-01 Photo Printer**:\n\n"
                "• **Ultra-Lightweight & Compact**: Only **5.8 kg** and compact dimensions, making it effortlessly portable.\n"
                "• **Anti-Curl Mechanism**: Keeps photo prints completely flat even when using roll media.\n"
                "• **Photo Formats**: Supports standard 4×6\" prints and compact 4×4\" square photos.\n\n"
                "Would you like pricing or protective carry bag options for the CZ-01?"
            )
            cards = [dict(PRODUCT_CARD_DEFS[s]) for s in ["CZ-01"] if s in PRODUCT_CARD_DEFS]
            log_message(sender_id=sender_id, role="user", content=user_msg, message_id=message_id, channel=channel)
            log_message(sender_id=sender_id, role="assistant", content=reply, channel=channel)
            return {
                "reply": reply,
                "intent": "recommendation_cz01",
                "priority": priority,
                "tools_called": tools_called,
                "chunks_retrieved": [],
                "cards": cards,
                "language": read_ctx.language,
                "resolved_sku": "CZ-01",
                "is_anaphora": False,
                "understanding": understand_res.model_dump(),
                "sales_state": decision.current_state.value if hasattr(decision.current_state, "value") else str(decision.current_state),
                "state_decision": decision.model_dump(),
                "prompt_version": Config.PROMPT_VERSION
            }

        if has_large_format and not has_high_roll_capacity and not has_ultra_light:
            reply = (
                "For portrait studios, professional event photographers, and fine art studios requiring wide-format dye-sub output, "
                "our top recommendation is the **Citizen CX-02W Photo Printer**:\n\n"
                "• **Wide-Format Dye-Sub**: Specialized 8-inch chassis engineered for **8×10\"** and **8×12\"** large studio portraits.\n"
                "• **Lab-Grade Color Quality**: Rich dynamic range and grey calibration with durable protective overcoat.\n"
                "• **Compact Footprint**: Full studio portrait capability in a transportable 14 kg unit.\n\n"
                "Would you like official pricing or genuine 8×12 media roll details for the CX-02W?"
            )
            cards = [dict(PRODUCT_CARD_DEFS[s]) for s in ["CX-02W"] if s in PRODUCT_CARD_DEFS]
            log_message(sender_id=sender_id, role="user", content=user_msg, message_id=message_id, channel=channel)
            log_message(sender_id=sender_id, role="assistant", content=reply, channel=channel)
            return {
                "reply": reply,
                "intent": "recommendation_cx02w",
                "priority": priority,
                "tools_called": tools_called,
                "chunks_retrieved": [],
                "cards": cards,
                "language": read_ctx.language,
                "resolved_sku": "CX-02W",
                "is_anaphora": False,
                "understanding": understand_res.model_dump(),
                "sales_state": decision.current_state.value if hasattr(decision.current_state, "value") else str(decision.current_state),
                "state_decision": decision.model_dump(),
                "prompt_version": Config.PROMPT_VERSION
            }

        # Architectural CAD / Blueprints / Plotter Match
        if any(w in msg_lower for w in ["cad", "blueprint", "blueprints", "architectural", "technical drawings"]) and not any(cx in msg_lower for cx in ["cx-02", "cx02"]):
            reply = (
                "For CAD blueprints, engineering plans, and architectural line drawings, our primary recommendation is the **Epson SureColor SC-T3100**:\n\n"
                "• **Precision CAD Output**: High-resolution 2,400 × 1,200 DPI with UltraChrome XD2 all-pigment archival inks for crisp, smudge-resistant lines\n"
                "• **Media Formats**: 24-inch wide roll-fed plotter supporting A1, A2, A3, and A4 cut sheets\n"
                "• **Fast Printing**: A1 technical line drawings printed in as fast as **34 seconds**\n"
                "• **Commercial Pricing**: **3,880.00 AED + VAT** (Available at Kepler Tech Dubai)\n\n"
                "Would you like an official commercial quotation or technical datasheet for the SC-T3100?"
            )
            cards = [dict(PRODUCT_CARD_DEFS[s]) for s in ["SC-T3100"] if s in PRODUCT_CARD_DEFS]
            log_message(sender_id=sender_id, role="user", content=user_msg, message_id=message_id, channel=channel)
            log_message(sender_id=sender_id, role="assistant", content=reply, channel=channel)
            return {
                "reply": reply,
                "intent": "recommendation_cad",
                "priority": priority,
                "tools_called": tools_called,
                "chunks_retrieved": [],
                "cards": cards,
                "language": read_ctx.language,
                "resolved_sku": "SC-T3100",
                "is_anaphora": False,
                "understanding": understand_res.model_dump(),
                "sales_state": decision.current_state.value if hasattr(decision.current_state, "value") else str(decision.current_state),
                "state_decision": decision.model_dump(),
                "prompt_version": Config.PROMPT_VERSION
            }

        # Document Scanner Match
        if any(w in msg_lower for w in ["document scanner", "sheetfed scanner", "scan records", "office scanner"]) and not any(cx in msg_lower for cx in ["cx-02", "cx02"]):
            reply = (
                "For fast business record archiving and sheetfed scanning, our top recommendation is the **Epson WorkForce DS-530II Document Scanner**:\n\n"
                "• **Speed**: Fast duplex scanning at **35 ppm / 70 ipm**\n"
                "• **Capacity**: 50-sheet Automatic Document Feeder (ADF)\n"
                "• **Media Support**: Handles business cards, ID cards, receipts, and extra-long documents\n"
                "• **Official Distributor**: Distributed and serviced in the UAE by Kepler Tech LLC\n\n"
                "Would you like an official quotation or details on our high-speed scanners?"
            )
            cards = [dict(PRODUCT_CARD_DEFS[s]) for s in ["DS-530II"] if s in PRODUCT_CARD_DEFS]
            log_message(sender_id=sender_id, role="user", content=user_msg, message_id=message_id, channel=channel)
            log_message(sender_id=sender_id, role="assistant", content=reply, channel=channel)
            return {
                "reply": reply,
                "intent": "recommendation_scanner",
                "priority": priority,
                "tools_called": tools_called,
                "chunks_retrieved": [],
                "cards": cards,
                "language": read_ctx.language,
                "resolved_sku": "DS-530II",
                "is_anaphora": False,
                "understanding": understand_res.model_dump(),
                "sales_state": decision.current_state.value if hasattr(decision.current_state, "value") else str(decision.current_state),
                "state_decision": decision.model_dump(),
                "prompt_version": Config.PROMPT_VERSION
            }

        # Open-ended or broad printer inquiries without specific model or category
        has_specific_product = any(m in msg_lower for m in [
            "cx-02", "cx02", "cy-02", "cy02", "cz-01", "cz01", "cx-02w", "cx02w",
            "t3100", "t5100", "t7700", "p700", "p900", "c5890", "ds-530", "ds-770"
        ])
        is_broad_printer_inquiry = (
            re.match(r"^(i\s+need|looking\s+for|we\s+need|want\s+to\s+buy|want|do\s+you\s+have)\s+(a\s+)?printers?[\s.?!]*$", msg_lower)
            or any(p in msg_lower for p in [
                "what printers do you have", "what printers do you sell", "what printers do you offer",
                "what kind of printers", "types of printers", "printers in stock", "commercial printers available"
            ])
        ) and not has_specific_product and not any(kw in msg_lower for kw in ["photo", "cad", "plotter", "scanner", "office", "blueprint", "sublimation"])

        if is_broad_printer_inquiry:
            reply = (
                "Welcome to Kepler Tech! We are an authorized distributor in Dubai for **Citizen** and **Epson** commercial printing systems.\n\n"
                "To recommend the right equipment for your workflow, could you clarify:\n\n"
                "1. **Primary Application**:\n"
                "   • **Event Photo Booths & Kiosks**: Citizen CX-02, CY-02, CZ-01 (instant 4×6\", 5×7\", 6×8\" roll photo prints)\n"
                "   • **Architectural CAD / Blueprints / Posters**: Epson SureColor Large Format Plotters (SC-T3100, SC-T5100)\n"
                "   • **High-Speed Office MFPs & Document Scanners**: Epson WorkForce & Sheetfed Scanners\n\n"
                "2. **Format & Volume**: What print sizes and estimated monthly volume do you plan to produce?\n\n"
                "Once you share your use case, I will guide you to the exact model, official specifications, and commercial pricing!"
            )
            cards = [dict(PRODUCT_CARD_DEFS[s]) for s in ["CX-02", "CY-02", "CZ-01", "CX-02W"] if s in PRODUCT_CARD_DEFS]
            log_message(sender_id=sender_id, role="user", content=user_msg, message_id=message_id, channel=channel)
            log_message(sender_id=sender_id, role="assistant", content=reply, channel=channel)
            return {
                "reply": reply,
                "intent": "clarification_recommendation",
                "priority": priority,
                "tools_called": tools_called,
                "chunks_retrieved": [],
                "cards": cards,
                "language": read_ctx.language,
                "resolved_sku": None,
                "is_anaphora": False,
                "understanding": understand_res.model_dump(),
                "sales_state": decision.current_state.value if hasattr(decision.current_state, "value") else str(decision.current_state),
                "state_decision": decision.model_dump(),
                "prompt_version": Config.PROMPT_VERSION
            }

        # Ambiguous Recommendation: User asks generally "which printer should I buy / recommend a printer" without specs
        is_general_recommendation = any(p in msg_lower for p in [
            "which printer should i buy", "which printer do you recommend", "recommend a printer",
            "what printer do you suggest", "suggest a printer", "help me choose a printer",
            "which one is best for me", "which model should i choose", "which citizen printer", "what printer should i",
            "recommend a photo printer", "which photo printer", "best photo printer", "suggest a photo printer",
            "need a photo printer", "looking for a photo printer", "printer for my photo booth", "printer for photobooth",
            "i need a dye sub printer", "need a dye sub printer", "looking for a dye sub printer", "recommend a dye sub printer",
            "which dye sub printer", "best dye sub printer", "i need a dyesub printer", "looking for a dyesub printer",
            "طابعة صور", "طابعه صور", "طابعة للفعاليات", "طابعه للفعاليات", "طابعة لحفلات", "طابعه لحفلات", "طابعة زفاف", "طابعه زفاف", "طابعة للاعراس", "طابعه للاعراس", "افضل طابعة صور", "افضل طابعه صور",
            "احتاج طابعة داي سب", "احتاج طابعه داي سب", "احتاج طابعة سبليميشن", "احتاج طابعه سبليميشن", "احتاج طابعة تسامي", "احتاج طابعه تسامي", "افضل طابعة داي سب", "افضل طابعه داي سب", "طابعة داي سب", "طابعه داي سب"
        ]) and not has_specific_product

        if is_general_recommendation and not has_large_format and not has_high_roll_capacity and not has_ultra_light:
            # If the user specifically mentions photo booth / weddings / event party booths, connect directly to Citizen CX-02!
            if any(pb in msg_lower for pb in [
                "photo booth", "photobooth", "booth", "event party", "wedding",
                "حفلات", "زفاف", "أعراس", "اعراس", "فعاليات", "مناسبات", "فوتوبوث", "كشك تصوير"
            ]):
                if read_ctx.language == "ar":
                    reply = (
                        "لطابعات صور الفعاليات وأكشاك التصوير وحفلات الزفاف، خيارنا الأساسي المعتمد هو **Citizen CX-02**:\n\n"
                        "• **سرعة فائقة**: طباعة مقاس 4×6 بوصة في **8.4 ثوانٍ** فقط بجودة معملية ممتازة\n"
                        "• **تصميم مدمج**: هيكل معدني متين بوزن 12 كجم مناسب تماماً لأكشاك التصوير المتنقلة والسيارات\n"
                        "• **خاصية إعادة لف الشريط**: طباعة مقاسات متعددة (4×6 و 5×7 و 6×8) دون إهدار الشريط الحراري\n"
                        "• **السعر الرسمي**: **4,385.00 درهم إماراتي + 5% ضريبة** (متوفرة في مستودع دبي)\n"
                        "• **رولات الورق الأصلية**: طقم وسائط 4×6 بوصة (CX2-MS46-2PC) بسعر **490.00 درهم** (~800 صورة تقديراً)\n\n"
                        "هل تود الحصول على عرض أسعار رسمي لطابعة CX-02 مع رولات الورق أو حقيبة النقل؟"
                    )
                else:
                    reply = (
                        "For photo booth operators and event photographers, our primary recommendation is the **Citizen CX-02 Photo Printer**:\n\n"
                        "• **High Speed**: Lab-quality 4×6\" photos in just **8.4 seconds**\n"
                        "• **Ultra-Compact Chassis**: Only 12 kg metal chassis, engineered for mobile booth enclosures and tight setups\n"
                        "• **Ribbon Rewind**: Print 4×6\", 5×7\", and 6×8\" formats from standard media without wasting unused ribbon\n"
                        "• **Official Pricing**: **4,385.00 AED + VAT** (In stock at our Dubai warehouse)\n"
                        "• **Genuine Media**: 4×6\" Media Set (CX2-MS46-2PC) at **490.00 AED** (~800 prints estimate)\n\n"
                        "Would you like an official quote for the CX-02 with media packs, or a carry bag for mobile transport?"
                    )
                cards = [dict(PRODUCT_CARD_DEFS[s]) for s in ["CX-02", "CX2-MS46-2PC", "CX-02-BAG"] if s in PRODUCT_CARD_DEFS]
            else:
                if read_ctx.language == "ar":
                    reply = (
                        "لتحديد طابعة الصور الحرارية (Dye-Sublimation) الأنسب من سيتيزن (Citizen) لمشروعك، يرجى توضيح:\n\n"
                        "1. **أحجام الطباعة المطلوبة**: هل تحتاج مقاس 4×6 بوصة التقليدي للفعاليات، أو صور مربعة 4×4، أو مقاسات استوديو كبيرة 8×10 و 8×12 بوصة؟\n"
                        "2. **الأولوية الرئيسية في التشغيل**:\n"
                        "   • **سهولة النقل وخفة الوزن**: طابعة CZ-01 فائقة الخفة (5.8 كجم)\n"
                        "   • **سعة الرول العالية للأكشاك المزدحمة**: طابعة CY-02 (حتى 700 صورة لكل رول لتقليل فترات التبديل)\n"
                        "   • **السرعة القياسية وأكشاك التصوير الشاملة**: طابعة CX-02 الرائدة (طباعة 4×6 في 8.4 ثوانٍ مع خاصية توفير الشريط)\n"
                        "   • **الأحجام الكبيرة للاستوديوهات والمعارض**: طابعة CX-02W العريضة\n\n"
                        "بمجرد تحديد احتياجاتك، سأزودك بكافة المواصفات والأسعار ومجموعات الوسائط الأصلية!"
                    )
                else:
                    reply = (
                        "To recommend the ideal Citizen commercial photo printer for your business, could you clarify:\n\n"
                        "1. **Print Formats**: Do you need standard 4×6\" event prints, compact 4×4\" square prints, or large 8×10\" / 8×12\" studio portraits?\n"
                        "2. **Primary Priority**: Is your main priority **mobility** (ultra-lightweight 5.8 kg CZ-01), **maximum roll capacity** to minimize refills (up to 700 prints CY-02), **large format** (CX-02W), or **fast all-around event booth printing** (CX-02)?\n\n"
                        "Once you share your preference, I will guide you to the exact model and genuine consumables!"
                    )
                cards = [dict(PRODUCT_CARD_DEFS[s]) for s in ["CX-02", "CY-02", "CZ-01", "CX-02W"] if s in PRODUCT_CARD_DEFS]
            log_message(sender_id=sender_id, role="user", content=user_msg, message_id=message_id, channel=channel)
            log_message(sender_id=sender_id, role="assistant", content=reply, channel=channel)
            return {
                "reply": reply,
                "intent": "clarification_recommendation",
                "priority": priority,
                "tools_called": tools_called,
                "chunks_retrieved": [],
                "cards": cards,
                "language": read_ctx.language,
                "resolved_sku": "CX-02" if "CX-02" in reply else None,
                "is_anaphora": False,
                "understanding": understand_res.model_dump(),
                "sales_state": decision.current_state.value if hasattr(decision.current_state, "value") else str(decision.current_state),
                "state_decision": decision.model_dump(),
                "prompt_version": Config.PROMPT_VERSION
            }

        # Branch 0: Anaphoric / Contextual Reference Handling (why this?, its media?)
        if read_ctx.reference_type == "why":
            model = read_ctx.resolved_model or sales_state.current_model or "Citizen CX-02"
            if "cy-02" in model.lower() or "cy02" in model.lower():
                reply = (
                    "We recommended the **Citizen CY-02 Photo Printer** because of its high media roll capacity (up to 700 prints per roll on 4x6\"), "
                    "which minimizes refill downtime for busy retail photo kiosks and high-volume operations.\n\n"
                    "Would you like pricing or media set details for the CY-02?"
                )
            elif "cz-01" in model.lower() or "cz01" in model.lower():
                reply = (
                    "We recommended the **Citizen CZ-01 Photo Printer** because of its ultra-compact 5.8 kg lightweight design and portability, "
                    "making it ideal for tight photo booths and mobile on-site event photographers needing standard 4x6\" and 4x4\" square prints.\n\n"
                    "Would you like pricing or carry bag details for the CZ-01?"
                )
            elif "cx-02w" in model.lower() or "cx02w" in model.lower():
                reply = (
                    "We recommended the **Citizen CX-02W Photo Printer** because it supports wide-format 8×10\" and 8×12\" dye-sub prints, "
                    "providing studio-grade large portraits while remaining easily transportable.\n\n"
                    "Would you like pricing or 8x12 media details for the CX-02W?"
                )
            else:
                reply = (
                    "We recommended the **Citizen CX-02 Photo Printer** because of its fast 8.4-second 4x6 print speed, compact 12 kg metal chassis, "
                    "and patented ribbon-rewind feature that prints multiple photo sizes (4x6\", 5x7\", 6x8\") without wasting unused ribbon.\n\n"
                    "Would you like pricing, media pack costs, or a sample comparison?"
                )
            intent = "explain_recommendation"
        elif read_ctx.reference_type == "consumables":
            model = read_ctx.resolved_model or sales_state.current_model or "Citizen CX-02"
            if "cy-02" in model.lower():
                reply = (
                    "**Citizen CY-02 Genuine Media Sets**:\n"
                    "• **4x6\" Media Set (CY-MS46)**: 2 rolls, up to 700 prints per roll (high-capacity kiosk)\n"
                    "• **6x8\" Media Set (CY-MS68)**: 2 rolls, up to 350 prints per roll\n"
                    "• **Citizen Thermal Head Cleaning Pen**: Available for printhead maintenance\n\n"
                    "Our sales team can confirm official box pricing and stock availability."
                )
            elif "cz-01" in model.lower():
                reply = (
                    "**Citizen CZ-01 Genuine Media Sets**:\n"
                    "• **4x4\" Media Set (CZ-MS44)**: Compact matched rolls for square photobook prints\n"
                    "• **4x6\" Media Set (CZ-MS46)**: Compact matched rolls for standard 4x6 photo prints\n"
                    "• **Citizen Thermal Head Cleaning Pen**: Available for printhead maintenance\n\n"
                    "Our sales team can confirm official box pricing and stock availability."
                )
            elif "cx-02w" in model.lower():
                reply = (
                    "**Citizen CX-02W Genuine Media Sets**:\n"
                    "• **8x10\" Media Set**: Large format portrait photo rolls\n"
                    "• **8x12\" Media Set (CX2W 812)**: Wide-format studio and event prints\n"
                    "• **Citizen Thermal Head Cleaning Pen**: Available for printhead maintenance\n\n"
                    "Our sales team can confirm official box pricing and stock availability."
                )
            else:
                reply = (
                    "**Citizen CX-02 Genuine Media Sets**:\n"
                    "• **4x6\" Media Set (CX2-MS46-2PC)**: 490.00 AED (~800 prints approx. / unverified estimate)\n"
                    "• **5x7\" Media Set (CX2-MS57-2PC)**: 500.00 AED (460 prints verified)\n"
                    "• **6x8\" Media Set (CX2-MS68-2PC)**: 500.00 AED (~400 prints approx. / unverified estimate)\n"
                    "• **Citizen Thermal Head Cleaning Pen**: 190.00 AED\n\n"
                    "All media sets include 2 matched paper rolls and dye-sub ribbons."
                )
            intent = "bundle_catalog"
        # Branch 1: Guardrails
        elif intent == "guardrails":
            fixed_resp = routing.get("fixed_response", "This query violates CX-02 operational guidelines.")
            fail_type = routing.get("failure_type")
            if fail_type in ("privacy_violation", "prompt_injection"):
                reply = fixed_resp
            else:
                ho = handoff_to_human(reason=routing.get("reason", "Guardrail breach"), summary=user_msg, phone=phone, sender_id=sender_id)
                tools_called.append({"tool": "handoff_to_human", "result": ho})
                reply = f"{fixed_resp}\n\n{ho['customer_message']}"

        # Branch 2: Meta Chat (Who built this, Are you a robot, Understanding check)
        elif intent == "meta_chat":
            if any(w in msg_lower for w in ["who built", "who build", "who made"]):
                reply = (
                    "I am **Kepler Assistant**, an enterprise AI product specialist built specifically for **Kepler Tech LLC** (Dubai). "
                    "I assist business clients across the GCC with Citizen photo printers, official media sets, technical specifications, and quotations. "
                    f"You can also connect directly with our human specialists at {Config.KEPLER_PHONE} or WhatsApp {Config.KEPLER_WHATSAPP}."
                )
            elif any(w in msg_lower for w in ["are you a robot", "are you ai", "are you human"]):
                reply = (
                    "I am an automated AI sales assistant for Kepler Tech LLC (Dubai). "
                    "I can help you with product specifications, pricing, stock, media yields, and quotations. "
                    "If you would prefer to speak with a human specialist, I can connect you with our Dubai team immediately."
                )
            else:
                reply = (
                    "My apologies if my previous response was not clear! Let me assist you directly. "
                    "Could you specify what details you need regarding the Citizen CX-02 printer, official media sets (4x6, 5x7, 6x8), or technical specifications? "
                    f"Our Dubai technical desk is also available directly at {Config.KEPLER_PHONE}."
                )

        # Branch 3: Polite Closure & Acknowledgments
        elif intent == "polite_closure":
            reply = "You're very welcome! If you need any further assistance with Citizen photo printers, media, or quotes, feel free to ask anytime. Have a wonderful day!"

        # Branch 3b: Small Talk & Greetings
        elif intent == "small_talk":
            reply = (
                "Hello! Welcome to **Kepler Tech LLC**. I am your commercial printing solutions specialist in Dubai.\n\n"
                "How can I assist you today? Whether you are looking for the high-speed **Citizen CX-02** photo printer, "
                "genuine media sets (4x6\", 5x7\", 6x8\"), or complete event and photo booth setups, I'm here to help!"
            )

        # Branch 3c: Human Specialist, Showroom Demonstration, Reservation
        elif intent == "human_demo_reserve":
            ho = handoff_to_human(reason="Customer requested showroom demonstration or human specialist", summary=user_msg, phone=phone, sender_id=sender_id)
            tools_called.append({"tool": "handoff_to_human", "result": ho})
            reply = (
                "We would be delighted to welcome you to our Dubai showroom for a hands-on live demonstration of the Citizen CX-02!\n\n"
                "📍 **Kepler Tech Showroom & Office**:\n"
                f"{Config.KEPLER_ADDRESS}\n"
                f"🕒 **Working Hours**: {Config.KEPLER_HOURS}\n"
                f"📞 **Phone**: {Config.KEPLER_PHONE} | 💬 **WhatsApp**: {Config.KEPLER_WHATSAPP}\n\n"
                f"{ho['customer_message']}"
            )
        elif intent == "handoff":
            ho = handoff_to_human(
                reason=routing.get("reason", "Customer requested sales specialist or restocking assistance"),
                summary=user_msg,
                phone=phone,
                sender_id=sender_id
            )
            tools_called.append({"tool": "handoff_to_human", "result": ho})
            reply = (
                f"{ho['customer_message']}"
            )

        # Branch 3d: Out of Scope
        elif intent == "out_of_scope":
            reply = routing.get("fixed_response") or (
                "Currently, we do not provide that product. That product is not part of the Kepler Tech commercial catalogue. "
                "At present, Kepler Tech supplies the official Citizen commercial photo printer lineup "
                "(Citizen CX-02, CX-02W, CY-02, and CZ-01) and genuine media consumables. "
                "Would you like details on our Citizen photo printers, or can I connect you with our Dubai sales desk?"
            )

        # Branch 3e: Services & Solutions (Repair, Rental, Leasing, MPS, ERP)
        elif intent == "service_enquiry":
            if any(w in msg_lower for w in ["repair", "fix", "service center", "maintenance"]):
                lead = create_lead(name="Valued Customer", phone=phone or "Not provided", notes=f"Repair service inquiry: {user_msg}", sender_id=sender_id)
                tools_called.append({"tool": "create_lead", "result": lead})
                ho = handoff_to_human(reason=f"Printer repair service inquiry: {user_msg}", summary=user_msg, phone=phone, sender_id=sender_id)
                tools_called.append({"tool": "handoff_to_human", "result": ho})
                reply = (
                    "Yes, Kepler Tech provides comprehensive commercial printer repair and maintenance services, "
                    "including on-site technical servicing across the UAE.\n\n"
                    "Explore our technical repair services:\n"
                    "🔗 https://www.keplertechllc.com/services/\n\n"
                    "Which printer model and issue are you encountering? Our certified Dubai service team will assist you promptly."
                )
            elif any(w in msg_lower for w in ["rent", "rental", "hire"]):
                lead = create_lead(name="Valued Customer", phone=phone or "Not provided", notes=f"Printer rental inquiry: {user_msg}", sender_id=sender_id)
                tools_called.append({"tool": "create_lead", "result": lead})
                reply = (
                    "Yes, we provide flexible short-term printer rentals for weddings, corporate events, and photo booths across the UAE. "
                    "Our event packages include hardware, setup guidance, and optional media sets.\n\n"
                    "What event dates and print volume are you planning for?"
                )
            elif any(w in msg_lower for w in ["lease", "leasing"]):
                lead = create_lead(name="Valued Customer", phone=phone or "Not provided", notes=f"Printer leasing inquiry: {user_msg}", sender_id=sender_id)
                tools_called.append({"tool": "create_lead", "result": lead})
                reply = (
                    "Yes, Kepler Tech offers long-term commercial equipment leasing with full maintenance coverage, "
                    "replacement backup units, and scheduled media supply included for corporate accounts and photo studios."
                )
            elif any(w in msg_lower for w in ["mps", "managed print"]):
                lead = create_lead(name="Valued Customer", phone=phone or "Not provided", notes=f"MPS inquiry: {user_msg}", sender_id=sender_id)
                tools_called.append({"tool": "create_lead", "result": lead})
                reply = (
                    "Managed Print Services (MPS) is our turnkey enterprise fleet solution covering hardware deployment, "
                    "automated consumable replenishment, ongoing servicing, and predictable per-print costs.\n\n"
                    "You can explore our MPS programs here:\n"
                    "🔗 https://www.keplertechllc.com/services/managed-print-services/\n"
                    "Our enterprise solutions team in Dubai will gladly evaluate your fleet requirements."
                )
            elif any(w in msg_lower for w in ["erp", "erpnext", "odoo", "sap"]):
                lead = create_lead(name="Valued Customer", phone=phone or "Not provided", notes=f"ERP solutions inquiry: {user_msg}", sender_id=sender_id)
                tools_called.append({"tool": "create_lead", "result": lead})
                reply = (
                    "Yes! Beyond commercial printing systems, Kepler Tech LLC provides enterprise ERP implementation "
                    "(including ERPNext and business workflow consulting) and Adobe corporate licensing. "
                    "I will connect you directly with our specialized digital solutions team."
                )
            else:
                lead = create_lead(name="Valued Customer", phone=phone or "Not provided", notes=f"General service inquiry: {user_msg}", sender_id=sender_id)
                tools_called.append({"tool": "create_lead", "result": lead})
                reply = (
                    "Kepler Tech offers a full suite of commercial technology services across the UAE, including printer repairs, "
                    "event rentals, long-term leasing, and managed print solutions.\n\n"
                    "How can our Dubai service team assist you today?"
                )

        # Branch 3f: Bulk & Wholesale Orders
        elif intent == "bulk_order":
            ho = handoff_to_human(reason="Commercial bulk/wholesale quantity inquiry", summary=user_msg, phone=phone, sender_id=sender_id)
            tools_called.append({"tool": "handoff_to_human", "result": ho})
            reply = (
                "Kepler Tech LLC is an authorized regional distributor offering tiered volume discounts for bulk media orders "
                "and multi-unit printer deployments across the UAE, GCC, and Africa.\n\n"
                "Our corporate sales management in Dubai will prepare an official wholesale proposal with dedicated pricing:\n"
                f"{ho['customer_message']}"
            )

        # Branch 3g: Geographic Shipping Coverage
        elif intent == "coverage":
            if any(w in msg_lower for w in ["kuwait", "oman", "saudi", "ksa", "qatar", "bahrain", "gcc"]):
                reply = (
                    "Yes, Kepler Tech ships across all GCC countries!\n"
                    "• **Kuwait**: 4 to 6 business days delivery\n"
                    "• **Oman**: 4 to 7 business days delivery\n"
                    "• **Saudi Arabia**: 5 to 8 business days delivery\n"
                    "• **Bahrain & Qatar**: 4 to 6 business days delivery\n\n"
                    "Shipping fees and delivery schedules are confirmed by our logistics desk at order placement."
                )
            elif any(w in msg_lower for w in ["africa", "kenya", "nigeria", "ghana", "tanzania", "uganda", "egypt"]):
                reply = (
                    "Kepler Tech regularly supplies commercial clients across Africa (Nigeria, Kenya, Ghana, South Africa, Egypt, and beyond) "
                    "via international air freight and commercial ocean cargo with complete export documentation. "
                    "Our export logistics team will coordinate freight arrangements for your destination."
                )
            else:
                reply = (
                    "Kepler Tech delivers across all UAE Emirates (Dubai, Abu Dhabi, Sharjah, Ajman, RAK, Fujairah, UAQ):\n"
                    "• **Delivery Time**: 1 to 3 business days across the UAE\n"
                    "• **Free Delivery**: On UAE orders over 400 AED\n"
                    "• **Local Pickup**: Free local pickup from our Dubai showroom (D79 Khalid Bin Waleed Rd, ready in 1 to 2 business days)."
                )

        # Branch 3h: Partner Products & Catalog Browse
        elif intent == "category_browse":
            if any(m in msg_lower for m in ["cx-02w", "cx02w", "cx 02w"]):
                if any(c in msg_lower for c in ["consumable", "consumbles", "media", "paper", "ribbon", "roll"]):
                    reply = (
                        "**Citizen CX-02W Consumables & Media Sets**:\n"
                        "The wide-format Citizen CX-02W uses official genuine Citizen large-format media sets:\n"
                        "• **8x10\" Media Set**: Matched paper and ribbon rolls for large portrait prints\n"
                        "• **8x12\" Media Set**: Matched paper and ribbon rolls for wide-format studio and event prints\n"
                        "• **Citizen Thermal Head Cleaning Pen**: Available for printhead maintenance\n\n"
                        "For commercial box pricing and stock availability on CX-02W media, our Kepler Tech Dubai sales desk will be pleased to assist you directly:\n"
                        f"📞 Phone: {Config.KEPLER_PHONE} | 💬 WhatsApp: {Config.KEPLER_WHATSAPP}"
                    )
                else:
                    reply = (
                        "**Citizen CX-02W Photo Printer** (Official Kepler Tech Lineup):\n"
                        "• **Description**: Wide-format dye-sublimation photo printer designed for producing larger professional photo prints.\n"
                        "• **Print Formats**: Large-format 8×10\" and 8×12\" media formats with multiple large-format print size options\n"
                        "• **Print Speed**: High-speed printing from 33.7 seconds\n"
                        "• **Surface Finishes**: Glossy, Matte, and Lustre finish options\n"
                        "• **Print Modes**: High-Speed and High-Quality modes (300×300 dpi up to 600×300 dpi)\n"
                        "• **Connectivity & OS**: USB interface, compatible with Windows 10/11 and macOS\n\n"
                        "For commercial pricing and availability on the CX-02W, CY-02, or CZ-01, our Dubai sales desk can assist you immediately:\n"
                        f"📞 Phone: {Config.KEPLER_PHONE} | 💬 WhatsApp: {Config.KEPLER_WHATSAPP}"
                    )
            elif any(m in msg_lower for m in ["cy-02", "cy02", "cy 02"]):
                if any(c in msg_lower for c in ["consumable", "consumbles", "media", "paper", "ribbon", "roll"]):
                    reply = (
                        "**Citizen CY-02 Consumables & Media Sets**:\n"
                        "The high-capacity Citizen CY-02 uses genuine Citizen commercial media rolls:\n"
                        "• **4x6\" Media Set**: High-capacity rolls (up to 700 prints per roll)\n"
                        "• **6x8\" Media Set**: High-capacity rolls (up to 350 prints per roll)\n"
                        "• **Citizen Thermal Head Cleaning Pen**: Available for printhead maintenance\n\n"
                        "For commercial box pricing and stock availability on CY-02 media, our Kepler Tech Dubai sales desk will be pleased to assist you directly:\n"
                        f"📞 Phone: {Config.KEPLER_PHONE} | 💬 WhatsApp: {Config.KEPLER_WHATSAPP}"
                    )
                else:
                    reply = (
                        "**Citizen CY-02 Photo Printer** (Official Kepler Tech Lineup):\n"
                        "• **Description**: Professional dye-sublimation photo printer offering flexible media options and fast photo production.\n"
                        "• **Print Formats**: Supports 4×6\" and 6×8\" media formats with multiple print size options for flexible output\n"
                        "• **Print Speed**: High-speed printing from 14.9 seconds\n"
                        "• **High Capacity**: Up to 700 prints per roll — ideal for busy mall kiosks to minimize refills\n"
                        "• **Surface Finishes**: Glossy and Matte finish options\n"
                        "• **Print Modes**: High-Speed and High-Quality modes (300×300 dpi up to 600×300 dpi)\n"
                        "• **Connectivity & OS**: USB interface, compatible with Windows 10/11 and macOS\n\n"
                        "For commercial pricing and availability on the CX-02W, CY-02, or CZ-01, our Dubai sales desk can assist you immediately:\n"
                        f"📞 Phone: {Config.KEPLER_PHONE} | 💬 WhatsApp: {Config.KEPLER_WHATSAPP}"
                    )
            elif any(m in msg_lower for m in ["cz-01", "cz01", "cz 01"]):
                if any(c in msg_lower for c in ["consumable", "consumbles", "media", "paper", "ribbon", "roll"]):
                    reply = (
                        "**Citizen CZ-01 Consumables & Media Sets**:\n"
                        "The ultra-compact Citizen CZ-01 uses genuine Citizen compact media sets:\n"
                        "• **4x4\" Media Set**: Matched paper and ribbon rolls for square event prints\n"
                        "• **4x6\" Media Set**: Matched paper and ribbon rolls for standard photo prints\n"
                        "• **Citizen Thermal Head Cleaning Pen**: Available for printhead maintenance\n\n"
                        "For commercial pricing and availability on CZ-01 media, please contact our Kepler Tech Dubai sales desk:\n"
                        f"📞 Phone: {Config.KEPLER_PHONE} | 💬 WhatsApp: {Config.KEPLER_WHATSAPP}"
                    )
                else:
                    reply = (
                        "**Citizen CZ-01 Photo Printer** (Official Kepler Tech Lineup):\n"
                        "• **Description**: Compact and portable dye-sublimation photo printer ideal for fast, high-quality photo output.\n"
                        "• **Print Formats**: Supports 4×4\" square prints and 4×6\" media sizes with multiple print size options\n"
                        "• **Print Speed**: High-speed printing from 16.3 seconds\n"
                        "• **Design**: Ultra-compact and lightweight (5.8 kg) design for maximum mobility\n"
                        "• **Surface Finishes**: Glossy and Matte finish options\n"
                        "• **Print Modes**: High-Speed and High-Quality modes (300×300 dpi up to 600×300 dpi)\n"
                        "• **Connectivity & OS**: USB interface, compatible with Windows 10/11 and macOS\n\n"
                        "For commercial pricing and availability on the CX-02W, CY-02, or CZ-01, our Dubai sales desk can assist you immediately:\n"
                        f"📞 Phone: {Config.KEPLER_PHONE} | 💬 WhatsApp: {Config.KEPLER_WHATSAPP}"
                    )
            elif any(k in msg_lower for k in ["mall kiosk", "refill all the time", "refill all time", "busy kiosk", "without refilling"]):
                reply = (
                    "For a busy mall kiosk or retail photo setup where minimizing refill downtime is essential, we strongly recommend the **Citizen CY-02 Photo Printer**:\n"
                    "• **High Capacity**: Produces up to **700 prints per roll** (4x6\"), minimizing media roll changes during busy peak hours.\n"
                    "• **Fast Production**: High-speed printing from 14.9 seconds.\n"
                    "• **Formats**: Supports flexible 4x6\" and 6x8\" print sizes.\n"
                    "• **Finishes**: Both Glossy and Matte finishes selectable directly from the driver without changing media.\n\n"
                    "Would you like our technical sales desk to prepare quotation and allocation details for the Citizen CY-02?"
                )
            elif any(k in msg_lower for k in ["big framed prints", "bigger than normal", "large framed prints", "framed prints"]):
                reply = (
                    "For larger framed prints and studio enlargements beyond standard 4x6 / 6x8 sizes, Kepler Tech offers the **Citizen CX-02W Wide-Format Photo Printer**:\n"
                    "• **Large Formats**: Designed specifically for professional **8x10\"** and **8x12\"** dye-sublimation prints.\n"
                    "• **High-Speed Output**: Fast printing from 33.7 seconds for 8x10 / 8x12 photos.\n"
                    "• **Finishes**: Glossy, Matte, and Lustre finish options.\n"
                    "*(Note: For larger fine art canvas or exhibition posters up to 24\"/44\", Kepler Tech also supplies Epson SureColor large-format plotters).* \n\n"
                    "Would you like to explore the Citizen CX-02W or Epson large-format solutions?"
                )
            elif any(k in msg_lower for k in ["weddings and need small", "small prints fast", "fast small prints"]):
                reply = (
                    "For wedding events and on-site guest prints where fast turnaround and portability are key, we recommend two Citizen solutions:\n"
                    "• **Citizen CX-02** (Flagship): Rapid **8.4-second** 4x6\" prints, compact 12 kg chassis, supports 4x6, 5x5, 5x7, 6x6, and 6x8.\n"
                    "• **Citizen CZ-01**: Ultra-compact and lightweight (5.8 kg) for tight spaces, supporting 4x4\" square photobook prints and 4x6\" photos in 16.3s.\n\n"
                    "Would you like to compare sample print quality or pricing for your event workflow?"
                )
            elif any(w in msg_lower for w in [
                "mug", "mugs", "t-shirt", "t-shirts", "tshirt", "tshirts", "shirt", "shirts",
                "cup", "cups", "tumbler", "tumblers", "heat press", "apparel", "textile", "textiles", "fabric", "fabrics",
                "اكواب", "أكواب", "كوب", "تيشرت", "تيشرتات", "ملابس", "قميص", "قماش", "مكبس حراري"
            ]) and any(s in msg_lower for s in ["sublimation", "sublim", "dye sub", "dyesub", "سبليميشن", "سبلميشن", "داي سب", "تسامي"]):
                if read_ctx.language == "ar":
                    reply = (
                        "لطباعة التسامي الحراري على الأكواب، والتيشرتات، والهدايا الدعائية، توفر شركة كيبلر تك طابعة **Epson SureColor SC-F100** المكتبية للسبليميشن (**1,950.00 درهم**) وطابعة **Epson SureColor SC-F500** مقاس 24 بوصة.\n\n"
                        "*(تنويه: طابعات سيتيزن مثل CX-02 و CY-02 هي طابعات صور حرارية مخصصة للصور الفوتوغرافية وأكشاك التصوير مباشرة، وليست للطباعة على الأكواب والأقمشة بالمكبس الحراري).*\n\n"
                        "هل تود الحصول على المواصفات الفنية أو عرض أسعار لطابعة إبسون SC-F100؟"
                    )
                else:
                    reply = (
                        "For mug, apparel, and gift sublimation transfer printing, Kepler Tech supplies the **Epson SureColor SC-F100** desktop dye-sublimation printer (**1,950.00 AED**) and the 24\" **Epson SureColor SC-F500**.\n\n"
                        "*(Note: Citizen CX-02, CY-02, and CZ-01 are thermal dye-sub printers engineered specifically for direct photo booth and studio photo prints, not transfer heat-pressing onto mugs or fabrics).*\n\n"
                        "Would you like technical specifications or an official commercial quote for the Epson SC-F100?"
                    )
            elif "citizen" in msg_lower or any(w in msg_lower for w in [
                "dye sub", "dyesub", "dye-sub", "sublimation", "thermal photo", "photo printer", "photo printers",
                "داي سب", "سبليميشن", "سبلميشن", "سوبليميشن", "تسامي", "حرارية"
            ]):
                if read_ctx.language == "ar":
                    reply = (
                        "توفر شركة كيبلر تك (Kepler Tech) في دبي مجموعة طابعات الصور الحرارية داي-سبليميشن (Dye-Sublimation) الأصلية من **سيتيزن (Citizen)**:\n\n"
                        "• **Citizen CX-02** (الرائدة للفعاليات واستوديوهات التصوير): **4,385.00 درهم** — طباعة سريعة 8.4 ثوانٍ لأحجام 4x6 و 5x7 و 6x8 بوصة.\n"
                        "• **Citizen CX-02W** (لأحجام الصور العريضة): **6,820.00 درهم** — لأحجام 8x10 و 8x12 بوصة.\n"
                        "• **Citizen CY-02** (سعة عالية للأكشاك): **3,400.00 درهم** — سعة حتى 700 صورة لكل رول لتقليل فترات التبديل.\n"
                        "• **Citizen CZ-01** (خفيفة الوزن ومتنقلة 5.8 كجم): **3,200.00 درهم** — لأحجام 4x4 و 4x6 بوصة.\n\n"
                        "الأسعار خاضعة لضريبة القيمة المضافة 5% وتأكيد مكتب المبيعات. أي طابعة تناسب متطلبات مشروعك؟"
                    )
                else:
                    reply = (
                        "Kepler Tech supplies the complete Citizen commercial dye-sublimation photo printer lineup in Dubai:\n\n"
                        "• **Citizen CX-02** (Active Flagship): **4,385.00 AED** — Compact 4x6\", 5x7\", 6x8\" dye-sub printer for event photo booths & studios.\n"
                        "• **Citizen CX-02W** (Wide Format): **6,820.00 AED** — Large format dye-sublimation printer supporting 8x10\" and 8x12\" prints.\n"
                        "• **Citizen CY-02** (High Capacity): **3,400.00 AED** — High-capacity commercial kiosk printer producing 700 prints per roll.\n"
                        "• **Citizen CZ-01** (Ultra Compact): **3,200.00 AED** — Lightweight 5.8kg compact event printer for 4x4\" and 4x6\" photos.\n\n"
                        "All prices are subject to 5% UAE VAT and confirmation by our sales desk. Which printer best fits your event or kiosk setup?"
                    )
            elif any(ep in msg_lower for ep in ["epson", "plotter", "surecolor", "workforce", "large format"]):
                reply = (
                    "Kepler Tech LLC is an authorized partner for **Epson** commercial printing systems and scanners in the UAE:\n"
                    "• **CAD & Technical Plotters**: SureColor **SC-T3100** (24\" — **3,880.00 AED**), **SC-T5100** (36\" — **9,700.00 AED**), **SC-T7700D** (dual-roll — Pricing via official quotation)\n"
                    "• **Photo & Fine Art**: SureColor **SC-P700** (13\" — **3,400.00 AED**), **SC-P900** (17\" — **4,880.00 AED**), **SC-P9500** (44\" — Pricing via official quotation)\n"
                    "• **Dye Sublimation**: SureColor **SC-F100** (A4 — **1,950.00 AED**), **SC-F500** (24\" — Pricing via official quotation)\n"
                    "• **Office & Enterprise MFP**: WorkForce Pro **WF-C5890** (**1,656.00 AED**), WorkForce Enterprise **AM-C4000/C5000/C6000** (Pricing via official quotation)\n"
                    "• **Document Scanners**: WorkForce **DS-530II**, **DS-770II** (Pricing via official quotation)\n\n"
                    "🔗 Browse Epson Systems: https://www.keplertechllc.com/product-category/printers/epson-large-format-inkjet-printer/\n\n"
                    "Verified prices are subject to 5% UAE VAT and confirmation by our sales desk. Would you like our technical sales specialist to prepare specifications or an official quote for any of these systems?"
                )
            elif any(w in msg_lower for w in ["aircast", "aircastpro", "wireless"]):
                reply = (
                    "The Citizen CX-02 features a direct USB 2.0 interface. "
                    "For seamless wireless printing from iPhones, iPads, and Android devices, Kepler Tech supplies the **AirCastPro 3 Wireless Print Server**:\n"
                    "🔗 https://www.keplertechllc.com/product/aircastpro-3/"
                )
            elif any(med in msg_lower for med in ["innova", "olmec", "korejet", "fine art", "sublimation paper"]):
                reply = (
                    "Kepler Tech distributes premier commercial digital media including **Innova Art** archival fine art papers, "
                    "**Olmec** photo papers, and **Korejet** dye-sublimation media across the UAE and GCC."
                )
            else:
                reply = (
                    "Kepler Tech LLC supplies leading commercial printing technologies:\n"
                    "• **Citizen Photo Printers**: CX-02, CX-02W, CY-02, CZ-01\n"
                    "• **Epson Commercial Systems**: SureColor fine art plotters and WorkForce office printers\n"
                    "• **Specialized Media**: Genuine Citizen media sets, Innova Art, Olmec, and Korejet\n"
                    "• **Wireless Bridges**: AirCastPro 3 print servers\n\n"
                    "Which category can I assist you with?"
                )

        # Branch 4: Unanswerable & Boundary Questions (No guessing)
        elif intent == "unanswerable_boundary":
            if "loud" in msg_lower:
                reply = (
                    "Specific acoustic decibel (dB) sound levels for the Citizen CX-02 are not published in official Citizen engineering datasheets. "
                    "The unit is engineered for quiet indoor photo booth and retail kiosk operation. Our Dubai technical desk can arrange a live demonstration."
                )
            elif "canon" in msg_lower:
                reply = (
                    "The Citizen CX-02 operates with official Citizen printer drivers (Windows, macOS, Linux). "
                    "Direct compatibility with proprietary Canon camera or capture software depends on standard OS print drivers and is unverified. "
                    "Our technical team can verify your specific software workflow."
                )
            elif "resale" in msg_lower:
                reply = (
                    "Kepler Tech supplies brand new, authorized commercial printing equipment and does not provide speculative resale valuations for used hardware. "
                    "All our printers come with full local UAE distributor warranty and factory packaging."
                )
            elif "power supply" in msg_lower:
                reply = (
                    "The Citizen CX-02 operates on standard AC power (100–240V). "
                    "Detailed internal power supply unit (PSU) specifications are not listed in public datasheets. "
                    "Our Dubai technical service team can assist with technical power requirements."
                )
            else:
                reply = (
                    "Kepler Tech offers direct authorized distributor pricing with verified UAE warranty and dedicated local technical support. "
                    "We do not offer one-off retail price matching. For custom corporate tenders or bulk deployments, our sales desk can assist you."
                )

        # Branch 5: Conversational Discovery & Vague Queries
        elif intent == "conversational_discovery":
            reply = (
                "Welcome to **Kepler Tech LLC**! We are official distributors for commercial printing solutions in Dubai, "
                "including the high-speed **Citizen CX-02** dye-sublimation photo printer, commercial business scanners, and large-format plotters.\n\n"
                "To assist you best, could you tell me:\n"
                "1. What is your intended application (e.g. photo booth events, wedding photography studio, or office document printing)?\n"
                "2. Which print sizes do you need (4x6\", 5x7\", 6x8\", or large format)?"
            )

        # Branch 6: Troubleshooting & Technical Maintenance
        elif intent == "troubleshooting":
            if any(w in msg_lower for w in ["white line", "white lines", "streak", "streaks"]):
                reply = (
                    "White lines or missing streaks on prints typically indicate dust, dye buildup, or thermal residue on the printhead.\n\n"
                    "• **Recommended Action**: Kepler Tech strongly advises cleaning the thermal printhead each time a new roll of media is installed.\n"
                    "• **Tool**: Use the official **Citizen Thermal Head Cleaning Pen** (SKU: CITIZEN-PEN, 190.00 AED) with the printer powered off.\n"
                    "• If white lines persist after cleaning, or if the head has a physical scratch, our Dubai service center can inspect the hardware."
                )
            elif any(w in msg_lower for w in ["noise", "sound"]):
                reply = (
                    "Please check that the paper scrap box is emptied and the ribbon take-up spool is wound taut with no slack. "
                    f"If unusual grinding or loud mechanical clicking persists, disconnect power and contact our Dubai service center at {Config.KEPLER_PHONE}."
                )
            elif "jam" in msg_lower:
                reply = (
                    "To resolve paper jams, ensure the paper roll flanges (blue and white) are correctly seated in their matching holders, "
                    "and that the paper edge is cut clean and straight before feeding through the rollers. "
                    "If paper jamming continues, please contact our technical support team."
                )
            elif any(w in msg_lower for w in ["turn on", "not turning on", "power"]):
                reply = (
                    "I understand your concern. Please verify that the rear AC power switch is switched ON and the power cord is securely plugged in. "
                    "If the unit will not power on, please provide your order details or invoice number so our service team can arrange diagnostic testing."
                )
            elif "driver" in msg_lower:
                reply = (
                    "Official Citizen CX-02 printer drivers for Windows 10/11, macOS, and Linux CUPS are available for direct download "
                    "from Citizen's official photo portal:\n"
                    "🔗 https://www.citizen.photo/ or https://citizen-systems.com/en/products/printer/photo/cx-02"
                )
            elif "ribbon" in msg_lower:
                reply = (
                    "To install the ribbon:\n"
                    "1. Pull the front release lever to open the cover.\n"
                    "2. Insert the yellow supply spool into the rear holders and snap the clear take-up spool into the front.\n"
                    "3. Rotate the take-up spool forward to eliminate any slack before closing the cover."
                )
            elif "drop" in msg_lower:
                reply = (
                    "Accidental physical damage from dropping is not covered under the manufacturer warranty. "
                    "Our certified Dubai service center at D79 Khalid Bin Waleed Road can inspect the internal chassis, alignment, and printhead to provide a repair quotation."
                )
            elif "epson" in msg_lower and "fix" in msg_lower:
                create_lead(name="Valued Customer", phone=phone or "Not provided", notes=f"Epson repair inquiry: {user_msg}", sender_id=sender_id)
                reply = (
                    "Yes! Kepler Tech LLC provides authorized maintenance, printhead servicing, and on-site repairs for Epson commercial and large-format printers across the UAE.\n"
                    "Could you share your specific Epson printer model and the issue you are experiencing? Our technical service team will follow up promptly."
                )
            elif "broken" in msg_lower:
                reply = (
                    "If an item arrives damaged or defective, Kepler Tech policy requires notification within 2 business days of delivery "
                    "with delivery packaging unopened. Our logistics team will inspect the case and arrange prompt replacement or refund."
                )
            elif "changed my mind" in msg_lower:
                reply = (
                    "Per Kepler Tech store policy, order cancellation is accepted within 24 hours of placing the order before dispatch. "
                    "Once shipped, standard return policies apply (unopened packaging, notification within 2 days)."
                )
            elif "nothing arrived" in msg_lower or "paid but" in msg_lower:
                reply = (
                    "We apologize for any delivery delay! You can check your shipment via our Track Your Order page on keplertech.ae. "
                    "Our customer support and tracking desk at +971 521 21 4898 will investigate your shipment immediately. Please share your order number."
                )
            else:
                ho = handoff_to_human(reason=f"Technical support inquiry: {user_msg}", summary=user_msg, phone=phone, sender_id=sender_id)
                tools_called.append({"tool": "handoff_to_human", "result": ho})
                reply = f"Our Dubai technical support team is ready to assist you with your equipment.\n\n{ho['customer_message']}"

        # Branch 7: Sales Objections & Value Consultation
        elif intent == "sales_objection":
            if "expensive" in msg_lower or "worth" in msg_lower:
                reply = (
                    "The **Citizen CX-02** is an industrial-grade dye-sublimation printer built for heavy commercial duty:\n"
                    "• **Instant Dry Output**: Photos exit completely dry with a durable glossy/matte protective overcoat in 8.4 seconds.\n"
                    "• **Zero Liquid Ink**: No liquid cartridges to dry out, clog, or smear during event transport.\n"
                    "• **Economical Running Cost**: Consistent ~0.61 AED per 4x6\" print estimate, far lower than desktop ink cartridges.\n"
                    "• **Local Warranty & Service**: Backed by official UAE warranty and direct factory-trained technicians at our Dubai service center.\n\n"
                    "Would you like a formal quotation for a starter package?"
                )
            elif "amazon" in msg_lower or "why buy from you" in msg_lower:
                reply = (
                    "Buying directly from **Kepler Tech LLC** guarantees:\n"
                    "• **100% Genuine Authorized Stock**: We are official authorized distributors for Citizen and Epson in the UAE.\n"
                    "• **Verified Local Warranty**: Direct local manufacturer warranty without grey-market import risks.\n"
                    "• **Dubai Service & Spare Parts**: Immediate access to our certified repair facility (D79 Khalid Bin Waleed Rd) and ongoing technical support."
                )
            elif "cleaning pen" in msg_lower:
                reply = (
                    "The official Citizen Thermal Cleaning Pen (190 AED) contains a specialized solvent formulated to dissolve thermal dye buildup "
                    "without scratching delicate micro-heating elements, preventing costly printhead replacements (which can cost thousands of dirhams)."
                )
            elif any(w in msg_lower for w in ["inkjet", "انكجت", "انك جت", "طابعة حبر", "حبر نفاث"]):
                if read_ctx.language == "ar":
                    reply = (
                        "لتطبيقات أكشاك التصوير والفعاليات واستوديوهات التصوير السريع، تتفوق طابعات داي-سبليميشن (Dye-Sublimation) على طابعات الحبر النفاث (Inkjet) بعدة مميزات رئيسية:\n"
                        "• **السرعة**: طباعة الصورة مقاس 4×6 في **8.4 ثوانٍ** فقط مقابل دقيقة أو أكثر في طابعات الحبر.\n"
                        "• **الجفاف الفوري**: صور جافة ومقاومة للماء وبصمات الأصابع تماماً بفضل طبقة الحماية الشفافة فور خروجها.\n"
                        "• **الاعتمادية العالية**: لا توجد رؤوس حبر سائل معرضة للجفاف أو الانسداد أثناء التوقف بين الفعاليات.\n"
                        "• **تكلفة ثابتة ومحسوبة**: رولات الورق والشريط الحراري المتطابقة تضمن تكلفة دقيقة وثابتة لكل صورة.\n\n"
                        "(أما للمطبوعات الفنية الكبيرة والبوسترات العريضة Fine Art، فإن طابعات إبسون Inkjet الكبيرة تظل الخيار الأمثل)."
                    )
                else:
                    reply = (
                        "For event and photo booth workflows, dye-sublimation offers key advantages over inkjet:\n"
                        "• Fast 8.4s print speed vs minutes on inkjet.\n"
                        "• Instant dry waterproof overcoat with fingerprint resistance.\n"
                        "• Continuous roll feed prevents paper feed jams common with inkjet photo sheets.\n"
                        "• No liquid ink to clog or dry out between events.\n\n"
                        "For fine art gallery portraits and large posters over 12 inches, our Epson large-format inkjet printers are the preferred choice."
                    )
            elif "dnp" in msg_lower:
                reply = (
                    "We do not make competitor claims. The Citizen CX-02 is chosen by professionals for its ultra-compact 12 kg chassis, "
                    "patented ribbon-save rewind feature (eliminating wasted ribbon), and instant glossy/matte switching on the same media roll."
                )
            elif any(w in msg_lower for w in ["20%", "match", "lowest", "3800", "4000"]):
                reply = (
                    "Our published price of **4,385.00 AED** is our standard direct distributor rate with official local warranty. "
                    "We do not offer one-off retail discounts or informal price matching. "
                    "Volume tier pricing is available for commercial orders of 10+ units through our corporate sales team."
                )
            else:
                reply = (
                    "Kepler Tech supplies authorized Citizen photo printers with guaranteed stock, manufacturer warranty, and certified Dubai technical support. "
                    "How can I assist you with model selection or a formal quotation?"
                )

        # Branch 8: Indirect Product Need (Consultation & Sizing)
        elif intent == "product_consultation":
            if any(w in msg_lower for w in ["photo booth", "photobooth", "wedding", "studio"]):
                reply = (
                    "The **Citizen CX-02** is the premier choice for photo booth operators and wedding photographers:\n"
                    "• Ultra-compact (275 × 366 × 170 mm) and lightweight (12 kg), easy to carry in any vehicle.\n"
                    "• Rapid 8.4-second print speed for 4x6\" prints keeps event lines moving.\n"
                    "• Instant dry protective overcoat produces smudge-free, waterproof memories for guests.\n\n"
                    "What print formats do you plan to offer (e.g. 2x6\" photostrips, 4x6\", or 5x7\"), and what is your typical event volume?"
                )
            elif any(w in msg_lower for w in ["portable", "events", "fit in", "car"]):
                reply = (
                    "Yes! The Citizen CX-02 is specifically engineered for mobile events, weighing only 12 kg with dimensions of 275 × 366 × 170 mm. "
                    "It fits easily in the trunk or passenger seat of any car. "
                    "We recommend pairing it with the official **Citizen CX-02 Protective Carry Bag** (AED 350.00) for safe transport."
                )
            elif any(w in msg_lower for w in ["passport", "id photo"]):
                reply = (
                    "The Citizen CX-02 can print 2x2 inch and 35x45 mm passport and ID photos using standard passport software layouts on 4x6\" media sets. "
                    "The maximum paper width is 6 inches. For specialized biometric passport capture systems, our team can advise."
                )
            elif any(w in msg_lower for w in ["poster", "big poster", "posters"]):
                reply = (
                    "The Citizen CX-02 supports formats up to 6x9 inches. "
                    "For large posters, blueprints, and fine art displays (e.g. A2, A1, 24\", 44\"), Kepler Tech supplies **Epson SureColor Large Format Printers**:\n"
                    "🔗 https://www.keplertechllc.com/product-category/printers/epson-large-format-inkjet-printer/"
                )
            elif any(w in msg_lower for w in ["both documents", "document and photo"]):
                reply = (
                    "The Citizen CX-02 is a specialized dye-sublimation photo printer and cannot print plain paper office documents. "
                    "For business document printing combined with scanning, Kepler Tech provides commercial **Epson WorkForce** business printers:\n"
                    "🔗 https://www.keplertechllc.com/product-category/printers/business-printer/"
                )
            elif "ink" in msg_lower:
                reply = (
                    "No liquid ink is required! The Citizen CX-02 utilizes thermal dye-sublimation media sets containing matched rolls of ribbon and paper. "
                    "There are no cartridges, no printhead clogs, and zero liquid ink to leak."
                )
            elif any(w in msg_lower for w in ["phone", "wireless", "ipad", "iphone"]):
                reply = (
                    "The Citizen CX-02 features a direct USB 2.0 interface. "
                    "To print wirelessly from iPhones, iPads, and Android devices, Kepler Tech supplies the **AirCastPro 3 Wireless Print Server**:\n"
                    "🔗 https://www.keplertechllc.com/product/aircastpro-3/"
                )
            elif any(w in msg_lower for w in ["roll last", "how long"]):
                reply = (
                    "Each media set contains 2 rolls:\n"
                    "• **4x6\" (CX2-MS46-2PC)**: 800 prints estimate (400 prints/roll)\n"
                    "• **5x7\" (CX2-MS57-2PC)**: 460 prints verified (230 prints/roll)\n"
                    "• **6x8\" (CX2-MS68-2PC)**: 400 prints estimate (200 prints/roll)"
                )
            else:
                reply = (
                    "To start printing with the Citizen CX-02, you need:\n"
                    "1. Citizen CX-02 Printer: 4,385.00 AED\n"
                    "2. Media Set (e.g. 4x6\" 800 prints): 490.00 AED\n"
                    "3. Thermal Head Cleaning Pen: 190.00 AED\n"
                    "4. Optional Carry Bag: 350.00 AED\n\n"
                    "Which print size and event volume are you planning for?"
                )

        # Branch 9: Budget & Cost Consultations
        elif intent == "budget_cost":
            if "5000" in msg_lower or "budget" in msg_lower:
                reply = (
                    "With a 5,000 AED budget, the ideal commercial starter bundle is:\n"
                    "• **1x Citizen CX-02 Photo Printer**: 4,385.00 AED\n"
                    "• **1x 4x6\" Media Set (800 prints estimate)**: 490.00 AED\n"
                    "• **Total Starter Package**: **4,875.00 AED** (fits within your 5,000 AED budget).\n"
                    "Prices are in AED and subject to confirmation. What is your estimated monthly print volume?"
                )
            elif any(w in msg_lower for w in ["total for everything", "everything"]):
                reply = (
                    "A complete all-inclusive commercial package includes:\n"
                    "• Citizen CX-02 Photo Printer: 4,385.00 AED\n"
                    "• 4x6\" Media Set (800 prints): 490.00 AED\n"
                    "• 5x7\" Media Set (460 prints): 500.00 AED\n"
                    "• 6x8\" Media Set (400 prints): 500.00 AED\n"
                    "• Protective Carry Bag: 350.00 AED\n"
                    "• Thermal Head Cleaning Pen: 190.00 AED\n"
                    "• **Total Full Kit**: **6,415.00 AED**."
                )
            elif "3000" in msg_lower:
                reply = (
                    "For 3,000 standard 4x6\" photos, you will need 4 media boxes (each box yields ~800 prints) at 490 AED per box, "
                    "costing approximately **1,960.00 AED** (~0.61 AED per print estimate). For 5x7\" or 6x8\", our team can calculate exact media requirements."
                )
            elif "cheapest" in msg_lower:
                reply = (
                    "The most cost-effective way to get started is the **Citizen CX-02 Printer (4,385.00 AED)** paired with a **4x6\" Media Set (490.00 AED)**, "
                    "totaling **4,875.00 AED**."
                )
            elif "installment" in msg_lower or "pay half" in msg_lower:
                reply = (
                    "Standard online store orders require full payment via credit card or PayPal upon placement. "
                    "Commercial business installment leasing is available for corporate accounts subject to credit approval by our finance desk."
                )
            elif "dollar" in msg_lower:
                reply = (
                    "All Kepler Tech official prices are quoted in **UAE Dirhams (AED)**. "
                    "We do not convert or fix USD pricing in automated chat; transactions are processed in AED."
                )
            else:
                reply = (
                    "The current official price for the Citizen CX-02 is **4,385.00 AED** (original: ~4,900 AED~). "
                    "Previous promotional pricing cannot be guaranteed once expired."
                )

        # Branch 10: Company Info (Name, About Kepler, Head Office Location, Contact Numbers)
        elif intent == "company_info":
            chunks = retrieve_company(user_msg, top_k=2)
            clean_q = user_msg.lower()
            if any(w in clean_q for w in ["who is kepler", "about kepler", "about your company", "who are you"]):
                reply = (
                    "**Kepler Tech LLC** is a premier business solutions provider headquartered in Dubai, specializing in commercial printing supplies, "
                    "photo printers, large-format plotters, IT hardware, and ERP solutions. Founded in 2016, we have over 10 years of industry experience serving clients across the UAE, GCC, and Africa."
                )
            elif any(w in clean_q for w in ["location", "located", "address", "where are you", "showroom", "office"]):
                reply = (
                    "🏢 **Kepler Tech Head Office & Showroom Location**:\n"
                    "Office No.1, Abdulla Al Awar Building, D79 Khalid Bin Waleed Road, Dubai, United Arab Emirates.\n"
                    "Local pickup is available from our Dubai distribution showroom."
                )
            elif any(w in clean_q for w in ["hours", "timings", "timing", "working hours", "opening hours"]):
                reply = (
                    "🕒 **Kepler Tech Working Hours**:\n"
                    "• Monday to Friday: 8:30 AM – 5:30 PM\n"
                    "• Saturday: 8:30 AM – 1:00 PM\n"
                    "• Sunday: Closed"
                )
            elif any(w in clean_q for w in ["whatsapp", "phone", "contact", "number", "call", "reach"]):
                reply = (
                    "📞 **Kepler Tech Contact Details**:\n"
                    f"• **Sales WhatsApp**: {Config.KEPLER_WHATSAPP}\n"
                    f"• **Dubai Landline**: {Config.KEPLER_PHONE}\n"
                    f"• **Email**: {Config.KEPLER_EMAIL}"
                )
            elif "email" in clean_q:
                reply = "Our official corporate email address is: **info@keplertech.ae**."
            elif any(w in clean_q for w in ["brands", "which brands", "what brands"]):
                reply = (
                    "Kepler Tech LLC carries premier international brands including **Citizen**, **Epson**, **Innova Art**, **Olmec photo paper**, and **Korejet** sublimation media."
                )
            elif any(w in clean_q for w in ["authorized", "authorised", "dealer", "partner"]):
                reply = "Yes, Kepler Tech LLC is an official authorized partner for both **Epson** and **Citizen** commercial printing hardware and consumables in the UAE."
            elif any(w in clean_q for w in ["industries", "who do you serve"]):
                reply = "Kepler Tech serves corporate businesses, healthcare institutions, education, government agencies, architecture/engineering firms, and retail photography kiosks across the GCC and Africa."
            elif any(w in clean_q for w in ["reviews", "rating", "google reviews"]):
                reply = "Kepler Tech LLC has **198 Google customer reviews** from business clients across the UAE and GCC."
            elif any(w in clean_q for w in ["how long", "since when", "founded"]):
                reply = "Kepler Tech LLC was established in **2016**, bringing over 10 years of dedicated commercial printing and technology expertise to the region."
            elif any(w in clean_q for w in ["real company", "is this a real"]):
                reply = "Yes, Kepler Tech LLC is a licensed UAE commercial technology and printing solutions distributor founded in 2016 with physical offices on Khalid Bin Waleed Road, Dubai."
            elif any(w in clean_q for w in ["original", "genuine"]):
                reply = "All products supplied by Kepler Tech LLC are 100% genuine, authorized OEM hardware and consumables directly backed by manufacturer warranties."
            elif "abu dhabi" in clean_q:
                reply = "Our main showroom and distribution center is located in Dubai (D79 Khalid Bin Waleed Rd). We provide direct on-site delivery and support across Abu Dhabi and all UAE Emirates."
            elif "individual" in clean_q:
                reply = "Kepler Tech primarily serves commercial businesses, photo studios, and event operators, but also assists individual professionals. Our sales desk will be pleased to confirm order requirements."
            elif "training" in clean_q:
                reply = "We provide standard technical guidance and driver setup instructions. Formal staff training packages can be arranged through our enterprise sales team."
            else:
                reply = (
                    "**Kepler Tech LLC** is an authorized distributor and solutions provider for Citizen photo printers, Epson commercial plotters, and specialized media in Dubai.\n"
                    f"• Location: {Config.KEPLER_ADDRESS}\n"
                    f"• Phone: {Config.KEPLER_PHONE} | WhatsApp: {Config.KEPLER_WHATSAPP}\n"
                    "• Online Store: https://www.keplertech.ae/"
                )

        # Branch 10: Policies (Delivery charges, payment methods, returns)
        elif intent == "policies":
            pol_key = routing.get("policy_name", "warranty")
            country = None
            for non_gcc in ["kenya", "nigeria", "africa", "uk", "usa", "europe", "india", "egypt"]:
                if non_gcc in msg_lower:
                    country = non_gcc
                    break
            pol_res = get_policy(pol_key, country=country)
            tools_called.append({"tool": "get_policy", "args": {"policy_name": pol_key, "country": country}, "result": pol_res})
            if pol_res.get("handoff"):
                ho = handoff_to_human(reason=f"Policy inquiry for '{pol_key}' (requires sales confirmation)", summary=user_msg, phone=phone, sender_id=sender_id)
                tools_called.append({"tool": "handoff_to_human", "result": ho})
                reply = f"{pol_res['message']}\n\n{ho['customer_message']}"
            else:
                reply = pol_res.get("message", str(pol_res.get("details")))

        # Branch 11: Discount / Negotiation -> Handoff
        elif intent == "discount_negotiation":
            ho = handoff_to_human(reason="Customer requested commercial discount / negotiation", summary=user_msg, phone=phone, sender_id=sender_id)
            tools_called.append({"tool": "handoff_to_human", "result": ho})
            reply = (
                "Kepler Tech LLC offers commercial tier pricing for bulk media orders and multi-unit printer deployments. "
                "Discounts and commercial terms must be approved directly by our sales management.\n\n"
                f"{ho['customer_message']}"
            )

        # Branch 12: Stock Availability
        elif intent == "stock":
            target_sku = determine_target_sku(user_msg, read_ctx=read_ctx)
            if target_sku is None:
                ho = handoff_to_human(
                    reason=f"Stock inquiry for item: {user_msg}",
                    summary=user_msg,
                    phone=phone,
                    sender_id=sender_id
                )
                tools_called.append({"tool": "handoff_to_human", "result": ho})
                reply = (
                    "Kepler Tech supplies official Citizen and Epson printing solutions. "
                    "For real-time stock availability on this model, our sales desk can assist you immediately.\n\n"
                    f"{ho['customer_message']}"
                )
            else:
                stock_res = check_stock(target_sku)
                tools_called.append({"tool": "check_stock", "args": {"sku": target_sku}, "result": stock_res})
                if stock_res.get("status") == "success":
                    reply = f"📦 *Stock Status for {stock_res['name']}*:\n{stock_res['stock_status']}."
                else:
                    reply = stock_res.get("message", "Stock status unavailable.")

        # Branch 10: Media Yield / Running Cost
        elif intent == "media_yield_cost":
            size = "4x6"
            if "5x7" in user_msg:
                size = "5x7"
            elif "6x8" in user_msg:
                size = "6x8"
            elif "6x9" in user_msg:
                size = "6x9"

            cost_res = calculate_cost_per_print(size=size)
            tools_called.append({"tool": "calculate_cost_per_print", "args": {"size": size}, "result": cost_res})
            chunks = retrieve(user_msg, top_k=2)

            if cost_res.get("status") == "success":
                reply = (
                    f"📊 *Running Cost Calculation ({cost_res['size']})*:\n"
                    f"• Media SKU: {cost_res['media_name']} ({cost_res['media_sku']})\n"
                    f"• Box Price: {cost_res['media_box_price']:,.2f} AED\n"
                    f"• Yield: {cost_res['prints_per_box']} prints/box {cost_res['estimate_note']}\n"
                    f"• *Cost per Print: {cost_res['formatted_cost_per_print']}*"
                )

            else:
                ho = handoff_to_human(reason="Media cost inquiry for unsupported media (6x9)", summary=user_msg, phone=phone, sender_id=sender_id)
                tools_called.append({"tool": "handoff_to_human", "result": ho})
                reply = f"{cost_res.get('message')}\n\n{ho['customer_message']}"

        # Branch 11: Bundle / Catalog / Consumables
        elif intent == "bundle_catalog":
            cat_res = list_products()
            tools_called.append({"tool": "list_products", "result": cat_res})

            is_consumable_req = any(c in msg_lower for c in ["consumable", "consumables", "media", "paper", "ribbon", "ink", "roll", "rolls", "refill", "refills"])
            active_model = (read_ctx.resolved_model or (sales_state.current_model if sales_state else "") or "").lower()

            if is_consumable_req:
                if any(ep in msg_lower for ep in ["epson", "cad", "plotter", "t3100", "t5100"]) or "sc-t" in active_model:
                    reply = (
                        "For Epson SureColor CAD plotters (such as SC-T3100 and SC-T5100), "
                        "Kepler Tech supplies genuine **UltraChrome XD2** archival all-pigment ink cartridges (Black, Cyan, Magenta, Yellow), "
                        "replacement auto cutter blades, maintenance boxes, and wide-format bond paper rolls.\n\n"
                        "Please share your plotter model or ink part code, and our Dubai sales desk will confirm current pack pricing!"
                    )
                    cards = [dict(PRODUCT_CARD_DEFS[s]) for s in ["SC-T3100"] if s in PRODUCT_CARD_DEFS]
                elif "cy-02" in active_model or "cy02" in active_model or "cy-02" in msg_lower or "cy02" in msg_lower:
                    reply = (
                        "**Citizen CY-02 Genuine Media Sets** (High-Capacity Kiosk):\n\n"
                        "• **4×6\" Media Set (CY-MS46)**: 2 rolls, up to 700 prints per roll (1,400 prints per box)\n"
                        "• **6×8\" Media Set (CY-MS68)**: 2 rolls, up to 350 prints per roll (700 prints per box)\n"
                        "• **Citizen Thermal Head Cleaning Pen (CITIZEN-PEN)**: **190.00 AED**\n\n"
                        "All media sets include matched dye-sub ribbons and paper rolls."
                    )
                    cards = [dict(PRODUCT_CARD_DEFS[s]) for s in ["CY-02", "CITIZEN-PEN"] if s in PRODUCT_CARD_DEFS]
                elif "cz-01" in active_model or "cz01" in active_model or "cz-01" in msg_lower or "cz01" in msg_lower:
                    reply = (
                        "**Citizen CZ-01 Genuine Media Sets** (Ultra-Compact Mobile):\n\n"
                        "• **4×6\" Media Set (CZ-MS46)**: Compact matched rolls for standard 4×6 photo prints\n"
                        "• **4×4\" Media Set (CZ-MS44)**: Compact matched rolls for square photobook prints\n"
                        "• **Citizen Thermal Head Cleaning Pen (CITIZEN-PEN)**: **190.00 AED**\n\n"
                        "All media sets include matched dye-sub ribbons and paper rolls."
                    )
                    cards = [dict(PRODUCT_CARD_DEFS[s]) for s in ["CZ-01", "CITIZEN-PEN"] if s in PRODUCT_CARD_DEFS]
                elif "cx-02w" in active_model or "cx02w" in active_model or "cx-02w" in msg_lower or "cx02w" in msg_lower:
                    reply = (
                        "**Citizen CX-02W Genuine Media Sets** (Wide-Format Studio Portrait):\n\n"
                        "• **8×10\" Media Set**: Studio portrait rolls yielding 120 prints per roll\n"
                        "• **8×12\" Media Set (CX2W 812)**: Wide-format studio and event prints yielding 110 prints per roll\n"
                        "• **Citizen Thermal Head Cleaning Pen (CITIZEN-PEN)**: **190.00 AED**\n\n"
                        "All media sets include matched dye-sub ribbons and paper rolls."
                    )
                    cards = [dict(PRODUCT_CARD_DEFS[s]) for s in ["CX-02W", "CITIZEN-PEN"] if s in PRODUCT_CARD_DEFS]
                else:
                    reply = (
                        "We supply genuine **Citizen CX-02** thermal dye-sublimation media sets and official consumables (In Stock, Dubai warehouse):\n\n"
                        "• **4×6\" Media Set (CX2-MS46-2PC)**: **490.00 AED** (~800 prints estimate / 2 rolls per box)\n"
                        "• **5×7\" Media Set (CX2-MS57-2PC)**: **500.00 AED** (460 prints verified / 2 rolls per box)\n"
                        "• **6×8\" Media Set (CX2-MS68-2PC)**: **500.00 AED** (~400 prints estimate / 2 rolls per box)\n"
                        "• **Citizen Thermal Head Cleaning Pen (CITIZEN-PEN)**: **190.00 AED**\n"
                        "• **Citizen CX-02 Protective Carry Bag (CX-02-BAG)**: **325.00 AED**\n\n"
                        "All prices are subject to 5% UAE VAT. Which photo format do you need for your operations?"
                    )
                    cards = [dict(PRODUCT_CARD_DEFS[s]) for s in ["CX2-MS46-2PC", "CX2-MS57-2PC", "CX2-MS68-2PC", "CITIZEN-PEN", "CX-02-BAG"] if s in PRODUCT_CARD_DEFS]
            else:
                reply = (
                    "📋 **Kepler Tech LLC — Commercial Printing Solutions Catalog** (Dubai Distribution):\n\n"
                    "• **Citizen Photo Printers**:\n"
                    "  - **Citizen CX-02** (Flagship 4×6, 5×7, 6×8): **4,385.00 AED**\n"
                    "  - **Citizen CX-02W** (Wide-format 8×10, 8×12): **6,820.00 AED**\n"
                    "  - **Citizen CY-02** (High-capacity 700 prints/roll): **3,400.00 AED**\n"
                    "  - **Citizen CZ-01** (Ultra-compact 5.8kg): **3,200.00 AED**\n\n"
                    "• **Citizen CX-02 Media & Consumables**:\n"
                    "  - 4×6\" Media Set (CX2-MS46-2PC): **490.00 AED**\n"
                    "  - 5×7\" Media Set (CX2-MS57-2PC): **500.00 AED**\n"
                    "  - 6×8\" Media Set (CX2-MS68-2PC): **500.00 AED**\n"
                    "  - Thermal Head Cleaning Pen: **190.00 AED**\n"
                    "  - Protective Carry Bag: **325.00 AED**\n\n"
                    "• **Epson CAD Plotters & Document Scanners**:\n"
                    "  - **Epson SureColor SC-T3100** (24\" CAD Plotter): **3,880.00 AED**\n"
                    "  - **Epson SureColor SC-T5100** (36\" CAD Plotter): **9,700.00 AED**\n"
                    "  - **Epson WorkForce DS-530II Scanner**: Pricing via official quotation\n\n"
                    "Which equipment or consumable category best matches your business workflow?"
                )
                cards = [dict(PRODUCT_CARD_DEFS[s]) for s in ["CX-02", "CX2-MS46-2PC", "SC-T3100", "DS-530II"] if s in PRODUCT_CARD_DEFS]

        # General Multi-intent / Hybrid Handling (Pricing, Quotes, Links, and Knowledge RAG)
        else:
            is_rejection = any(rej in msg_lower for rej in ["dont this", "don't this", "dont want this", "don't want this", "not this one", "not this printer", "something else", "different one", "different model"])
            if is_rejection:
                reply = (
                    "Understood! Could you let me know what specific printing requirements or applications you are looking for "
                    "(e.g., photo booth events, office business documents, wide-format CAD/posters, or high-volume kiosk)? "
                    "Kepler Tech carries a comprehensive range of Citizen and Epson printing systems, and I would be delighted to recommend the perfect model for your needs."
                )
                log_message(sender_id=sender_id, role="user", content=user_msg, message_id=message_id, channel=channel)
                log_message(sender_id=sender_id, role="assistant", content=reply, channel=channel)
                return {
                    "reply": reply,
                    "intent": intent,
                    "priority": priority,
                    "tools_called": tools_called,
                    "chunks_retrieved": chunks,
                    "cards": [],
                    "language": read_ctx.language,
                    "resolved_sku": read_ctx.resolved_sku,
                    "is_anaphora": read_ctx.is_anaphora,
                    "understanding": understand_res.model_dump(),
                    "sales_state": decision.current_state.value,
                    "state_decision": decision.model_dump(),
                    "prompt_version": Config.PROMPT_VERSION
                }


            if any(w in msg_lower for w in ["f100", "sc-f100", "sc f100"]):
                reply = (
                    "Kepler Tech LLC is an authorized partner for both **Citizen** and **Epson** commercial printing hardware in the UAE.\n\n"
                    "For dye-sublimation craft and textile printers like the **Epson SureColor SC-F100**, our commercial desk can assist with current model allocation and orders.\n"
                    "If you are looking for on-site event and photo booth photo printing, our flagship solution is the high-speed **Citizen CX-02** compact dye-sub photo printer (4,385.00 AED)!\n\n"
                    "Would you like more details on the CX-02 or assistance with the F100?"
                )
                log_message(sender_id=sender_id, role="user", content=user_msg, message_id=message_id, channel=channel)
                log_message(sender_id=sender_id, role="assistant", content=reply, channel=channel)
                return {
                    "reply": reply,
                    "intent": "category_browse",
                    "priority": priority,
                    "tools_called": tools_called,
                    "chunks_retrieved": [],
                    "cards": [],
                    "language": read_ctx.language,
                    "resolved_sku": None,
                    "is_anaphora": False,
                    "understanding": understand_res.model_dump(),
                    "sales_state": decision.current_state.value,
                    "state_decision": decision.model_dump(),
                    "prompt_version": Config.PROMPT_VERSION
                }

            if any(w in msg_lower for w in [
                "photo printers", "photo printer", "printers like cx 02", "printers like cx02", "items like cx 02", "items like cx02",
                "citizen printers", "which printers", "what printers", "show printers", "view printers", "our printers", "printer lineup",
                "dye sub printers", "dye sub printer", "dyesub printers", "dyesub printer", "dye sublimation printers", "dye sublimation printer",
                "thermal photo printers", "thermal photo printer", "داي سب", "سبليميشن", "سبلميشن", "سوبليميشن", "تسامي"
            ]) or (
                msg_lower.strip() in ["printer", "printers", "printers?", "photo printers?", "models", "dye sub", "dyesub", "sublimation"]
            ):
                if read_ctx.language == "ar":
                    reply = (
                        "توفر شركة كيبلر تك (Kepler Tech) في دبي مجموعة طابعات الصور الحرارية داي-سبليميشن (Dye-Sublimation) الأصلية من **سيتيزن (Citizen)**:\n\n"
                        "• **Citizen CX-02** (الرائدة للفعاليات واستوديوهات التصوير): **4,385.00 درهم** — طباعة سريعة 8.4 ثوانٍ لأحجام 4x6 و 5x7 و 6x8 بوصة.\n"
                        "• **Citizen CX-02W** (لأحجام الصور العريضة): **6,820.00 درهم** — لأحجام 8x10 و 8x12 بوصة.\n"
                        "• **Citizen CY-02** (سعة عالية للأكشاك): **3,400.00 درهم** — سعة حتى 700 صورة لكل رول لتقليل فترات التبديل.\n"
                        "• **Citizen CZ-01** (خفيفة الوزن ومتنقلة 5.8 كجم): **3,200.00 درهم** — لأحجام 4x4 و 4x6 بوصة.\n\n"
                        "الأسعار خاضعة لضريبة القيمة المضافة 5% وتأكيد مكتب المبيعات. أي طابعة تناسب متطلبات مشروعك؟"
                    )
                else:
                    reply = (
                        "Kepler Tech supplies the complete Citizen commercial photo printer lineup in Dubai:\n\n"
                        "• **Citizen CX-02** (Active Flagship): **4,385.00 AED** — Compact 4x6\", 5x7\", 6x8\" dye-sub printer for event photo booths & studios.\n"
                        "• **Citizen CX-02W** (Wide Format): **6,820.00 AED** — Large format dye-sublimation printer supporting 8x10\" and 8x12\" prints.\n"
                        "• **Citizen CY-02** (High Capacity): **3,400.00 AED** — High-capacity commercial kiosk printer producing 700 prints per roll.\n"
                        "• **Citizen CZ-01** (Ultra Compact): **3,200.00 AED** — Lightweight 5.8kg compact event printer for 4x4\" and 4x6\" photos.\n\n"
                        "All prices are subject to 5% UAE VAT and confirmation by our sales desk. Which printer best fits your event or kiosk setup?"
                    )
                cards = [dict(PRODUCT_CARD_DEFS[s]) for s in ["CX-02", "CX-02W", "CY-02", "CZ-01"] if s in PRODUCT_CARD_DEFS]
                log_message(sender_id=sender_id, role="user", content=user_msg, message_id=message_id, channel=channel)
                log_message(sender_id=sender_id, role="assistant", content=reply, channel=channel)
                return {
                    "reply": reply,
                    "intent": "category_browse",
                    "priority": priority,
                    "tools_called": tools_called,
                    "chunks_retrieved": [],
                    "cards": cards,
                    "language": read_ctx.language,
                    "resolved_sku": None,
                    "is_anaphora": False,
                    "understanding": understand_res.model_dump(),
                    "sales_state": decision.current_state.value,
                    "state_decision": decision.model_dump(),
                    "prompt_version": Config.PROMPT_VERSION
                }

            if (any(w in msg_lower for w in ["consumable", "consumables", "i need media", "need media", "which media", "what media", "paper and ribbon", "media rolls", "rolls and ribbon"]) or (
                "media" in msg_lower and not any(s in msg_lower for s in ["4x6", "5x7", "6x8", "6x9", "cost", "yield", "box", "roll", "price", "how much"])
            )) and "6x9" not in msg_lower:
                reply = (
                    "We supply genuine Citizen CX-02 thermal dye-sublimation media sets (each box includes 2 matched rolls of ribbon and paper):\n\n"
                    "• **4x6\" Media Set (CX2-MS46-2PC)**: **490.00 AED** (~800 prints estimate)\n"
                    "• **5x7\" Media Set (CX2-MS57-2PC)**: **500.00 AED** (460 prints verified)\n"
                    "• **6x8\" Media Set (CX2-MS68-2PC)**: **500.00 AED** (~400 prints estimate)\n"
                    "• **Thermal Head Cleaning Pen (CITIZEN-PEN)**: **190.00 AED**\n\n"
                    "All media sets are stocked in our Dubai distribution warehouse. Which print size works best for your setup?"
                )
                cards = [dict(PRODUCT_CARD_DEFS[s]) for s in ["CX2-MS46-2PC", "CX2-MS57-2PC", "CX2-MS68-2PC", "CITIZEN-PEN"] if s in PRODUCT_CARD_DEFS]
                log_message(sender_id=sender_id, role="user", content=user_msg, message_id=message_id, channel=channel)
                log_message(sender_id=sender_id, role="assistant", content=reply, channel=channel)
                return {
                    "reply": reply,
                    "intent": "bundle_catalog",
                    "priority": priority,
                    "tools_called": tools_called,
                    "chunks_retrieved": [],
                    "cards": cards,
                    "language": read_ctx.language,
                    "resolved_sku": None,
                    "is_anaphora": False,
                    "understanding": understand_res.model_dump(),
                    "sales_state": decision.current_state.value,
                    "state_decision": decision.model_dump(),
                    "prompt_version": Config.PROMPT_VERSION
                }

            is_6x9_inquiry = "6x9" in msg_lower and any(w in msg_lower for w in ["sell", "have", "buy", "media", "paper", "order", "roll", "stock", "get", "cost", "price"])
            has_price_terms = is_6x9_inquiry or any(re.search(r"\b" + re.escape(p) + r"\b", msg_lower) for p in [
                "price", "how much", "cost", "rate", "aed", "dirham", "dirhams", "quote", "quotation", "link", "url", "where can i buy", "where to buy", "website"
            ])
            has_knowledge_terms = any(k in msg_lower for k in [
                "spec", "dpi", "resolution", "weight", "dimension", "dimensions", "size", "sizes", "speed", "fast",
                "seconds", "ribbon", "paper", "media", "roll", "prints", "overcoat", "glossy",
                "matte", "luster", "warranty", "mac", "windows", "cups", "driver", "drivers", "usb",
                "photobooth", "photo booth", "rewind", "cleaning", "pen", "bag", "power", "watt", "wattage", "sleep",
                "dye sub", "sublimation", "wedding", "kiosk", "event", "technology", "feature", "benefits",
                "information", "details", "why", "how does", "tell me about", "suitable"
            ])


            parts = []

            # 1. Execute tool if pricing or quote or link is asked
            if intent in ("price", "quote", "link") or has_price_terms:
                target_sku = determine_target_sku(user_msg, read_ctx=read_ctx)
                if sales_state and sales_state.category == "scanner" and not any(m in msg_lower for m in ["cx-02", "cx02", "cy-02", "cz-01", "ms46", "ms57", "ms68"]):
                    target_sku = None

                if target_sku is None:
                    unsupported_inquiry = any(u in msg_lower for u in ["adapter", "tripod", "cable", "battery", "stand", "bluetooth", "wireless", "xyz"])
                    user_history_text = " ".join([h.get("content", "") for h in (history or [])[-3:] if h.get("role") == "user"]).lower()

                    if ("company" in msg_lower or "corporate" in msg_lower or "kepler" in msg_lower) and any(w in msg_lower for w in ["website", "site", "link", "url", "page"]):
                        parts.append(
                            "You can visit the official Kepler Tech corporate website and online store here:\n"
                            "• Corporate Website: https://www.keplertechllc.com/\n"
                            "• Online Store: https://www.keplertech.ae/"
                        )
                    elif not unsupported_inquiry and (any(sc in user_history_text for sc in ["scanner", "scanning"]) or (sales_state and sales_state.category == "scanner")):
                        parts.append(
                            "Kepler Tech supplies official commercial document scanners and multifunction scanning solutions. "
                            "Pricing for scanners is determined based on scanning volume, resolution, and feed capacity.\n\n"
                            "Our enterprise team in Dubai is available to provide a customized model proposal:\n"
                            f"📞 Phone: {Config.KEPLER_PHONE} | 💬 WhatsApp: {Config.KEPLER_WHATSAPP} | 📧 {Config.KEPLER_EMAIL}"
                        )
                    elif not unsupported_inquiry and any(ep in user_history_text for ep in ["epson", "plotter", "workforce", "heat-free"]):
                        parts.append(
                            "Kepler Tech is an authorized partner for Epson commercial inkjet printers and large-format plotters. "
                            "Pricing and volume discounts for Epson hardware are quoted directly by our sales management.\n\n"
                            "Please contact our sales desk for an official proposal:\n"
                            f"📞 Phone: {Config.KEPLER_PHONE} | 💬 WhatsApp: {Config.KEPLER_WHATSAPP} | 📧 {Config.KEPLER_EMAIL}"
                        )
                    elif unsupported_inquiry:
                        ho = handoff_to_human(
                            reason=f"Unrecognized or ambiguous product inquiry: {user_msg}",
                            summary=user_msg,
                            phone=phone,
                            sender_id=sender_id
                        )
                        tools_called.append({"tool": "handoff_to_human", "result": ho})
                        parts.append(
                            "Kepler Tech supplies official Citizen and Epson commercial printers and accessories. "
                            "I could not identify the specific product from your message. "
                            f"Our sales desk will be happy to confirm availability and options for you.\n\n{ho['customer_message']}"
                        )
                    elif any(w in msg_lower for w in ["f100", "sc-f100", "sc f100"]):
                        parts.append(
                            "Kepler Tech LLC is an authorized partner for both **Citizen** and **Epson** commercial printing hardware in the UAE.\n\n"
                            "For dye-sublimation craft and textile printers like the **Epson SureColor SC-F100**, our commercial desk can assist with current model allocation and orders.\n"
                            "If you are looking for on-site event and photo booth photo printing, our flagship solution is the high-speed **Citizen CX-02** compact dye-sub photo printer (4,385.00 AED)!\n\n"
                            "Would you like more details on the CX-02 or assistance with the F100?"
                        )
                    elif any(w in msg_lower for w in ["consumable", "consumables", "i need media", "need media", "which media", "what media", "paper and ribbon", "media rolls", "rolls and ribbon"]) or (
                        "media" in msg_lower and not any(s in msg_lower for s in ["4x6", "5x7", "6x8", "cost", "yield", "box", "roll"])
                    ):
                        parts.append(
                            "We supply genuine Citizen CX-02 thermal dye-sublimation media sets (each box includes 2 matched rolls of ribbon and paper):\n\n"
                            "• **4x6\" Media Set (CX2-MS46-2PC)**: **490.00 AED** (~800 prints estimate)\n"
                            "• **5x7\" Media Set (CX2-MS57-2PC)**: **500.00 AED** (460 prints verified)\n"
                            "• **6x8\" Media Set (CX2-MS68-2PC)**: **500.00 AED** (~400 prints estimate)\n"
                            "• **Thermal Head Cleaning Pen (CITIZEN-PEN)**: **190.00 AED**\n\n"
                            "All media is in stock at our Dubai distribution warehouse. Which print size do you require for your setup?"
                        )
                    elif read_ctx and read_ctx.sku_source == "default":
                        parts.append(
                            "Which product or accessory would you like pricing for? We offer the Citizen CX-02 photo printer and official accessories:\n\n"
                            "• **Citizen CX-02 Photo Printer** (SKU: CX-02)\n"
                            "• **4x6\" Media Set** (CX2-MS46-2PC)\n"
                            "• **5x7\" Media Set** (CX2-MS57-2PC)\n"
                            "• **6x8\" Media Set** (CX2-MS68-2PC)\n"
                            "• **Protective Carry Bag** (CX-02-BAG)\n"
                            "• **Printhead Cleaning Pen** (CITIZEN-PEN)\n\n"
                            "Please let me know which product or accessory options you need pricing for!"
                        )
                    else:
                        ho = handoff_to_human(
                            reason=f"Unrecognized or ambiguous product inquiry: {user_msg}",
                            summary=user_msg,
                            phone=phone,
                            sender_id=sender_id
                        )
                        tools_called.append({"tool": "handoff_to_human", "result": ho})
                        parts.append(
                            "Kepler Tech supplies official Citizen and Epson commercial printers and accessories. "
                            "I could not identify the specific product from your message. "
                            f"Our sales desk will be happy to confirm availability and options for you.\n\n{ho['customer_message']}"
                        )
                elif ("quote" in msg_lower or "quotation" in msg_lower or "draft" in msg_lower):
                    qty = (read_ctx.resolved_qty if read_ctx else None) or parse_quantity(user_msg) or 1
                    multi_items = parse_multi_item_quantities(user_msg)
                    if multi_items:
                        quote_items = multi_items
                    elif ("printer" in msg_lower or "unit" in msg_lower) and any(m in msg_lower for m in ["4x6", "5x7", "6x8", "paper", "media", "bag", "pen"]):
                        quote_items = [{"sku": "CX-02", "qty": 1}]
                        if "4x6" in msg_lower or "ms46" in msg_lower:
                            quote_items.append({"sku": "CX2-MS46-2PC", "qty": 1})
                        elif "5x7" in msg_lower or "ms57" in msg_lower:
                            quote_items.append({"sku": "CX2-MS57-2PC", "qty": 1})
                        elif "6x8" in msg_lower or "ms68" in msg_lower:
                            quote_items.append({"sku": "CX2-MS68-2PC", "qty": 1})
                        elif "bag" in msg_lower:
                            quote_items.append({"sku": "CX-02-BAG", "qty": 1})
                        elif "pen" in msg_lower:
                            quote_items.append({"sku": "CITIZEN-PEN", "qty": 1})
                    else:
                        quote_items = [{"sku": target_sku, "qty": qty}]

                    quote_res = create_quote(
                        items=quote_items,
                        customer_name="Valued Customer",
                        phone=phone,
                        sender_id=sender_id
                    )
                    tools_called.append({"tool": "create_quote", "result": quote_res})
                elif read_ctx and read_ctx.resolved_qty and read_ctx.resolved_qty > 1:
                    qty = read_ctx.resolved_qty
                    price_res = get_price(target_sku)
                    tools_called.append({"tool": "get_price", "args": {"sku": target_sku}, "result": price_res})
                    if price_res.get("status") == "success":
                        unit_p = price_res["price"]
                        total_p = unit_p * qty
                        p_name = price_res["name"]
                        parts.append(
                            f"For **{qty}x {p_name}** (SKU: {target_sku}), the total is **{total_p:,.2f} AED** "
                            f"({qty} × {unit_p:,.2f} AED).\n"
                            f"Availability: In Stock (Dubai showroom).\n\n"
                            f"Would you like me to prepare an official draft quotation for your order?"
                        )
                    else:
                        parts.append(price_res.get("message", "Pricing unavailable."))
                elif ("company" in msg_lower or "corporate" in msg_lower or "kepler" in msg_lower) and any(w in msg_lower for w in ["website", "site", "link", "url", "page"]):
                    parts.append(
                        "You can visit the official Kepler Tech corporate website and online store here:\n"
                        "• Corporate Website: https://www.keplertechllc.com/\n"
                        "• Online Store: https://www.keplertech.ae/"
                    )
                elif "link" in msg_lower or "website" in msg_lower or "url" in msg_lower or "where to buy" in msg_lower or "where can i buy" in msg_lower:
                    link_res = get_product_link(target_sku)
                    tools_called.append({"tool": "get_product_link", "args": {"sku": target_sku}, "result": link_res})
                else:
                    price_res = get_price(target_sku)
                    tools_called.append({"tool": "get_price", "args": {"sku": target_sku}, "result": price_res})

            # 2. Retrieve RAG chunks if knowledge is asked (skip for 6x9 purchase inquiry)
            if is_6x9_inquiry:
                chunks = []
            elif intent in ("datasheet", "rag") or has_knowledge_terms:
                chunks = retrieve(user_msg, top_k=4, category=sales_state.category, model=sales_state.current_model)
                if any(s in msg_lower for s in ["speed", "fast", "seconds", "second"]) and not any("speed" in c.get("section", "").lower() for c in chunks):
                    speed_c = retrieve(f"{user_msg} print speed seconds", top_k=1, category=sales_state.category, model=sales_state.current_model)
                    if speed_c:
                        chunks = chunks + speed_c

            # 3. Synthesize response combining RAG and Tool results
            is_quote_called = any(tr.get("tool") == "create_quote" for tr in tools_called)
            is_price_called = any(tr.get("tool") == "get_price" for tr in tools_called)
            is_pure_price_inquiry = is_price_called and not any(t in msg_lower for t in [
                "speed", "fast", "seconds", "dpi", "resolution", "weight", "dimension", "dimensions",
                "watt", "rewind", "overcoat", "maintenance", "cleaning", "difference", "compare", "why"
            ])
            technical_asked = any(t in msg_lower for t in [
                "spec", "resolution", "dpi", "dimension", "dimensions", "weight", "speed", "size",
                "difference", "compare", "why", "technology", "how fast", "how does"
            ]) and not is_pure_price_inquiry

            is_dye_sub_education = any(w in msg_lower for w in [
                "what is dye sub", "what is dyesub", "what is dye sublimation",
                "how does dye sub work", "how does dyesub work", "how dye sublimation works",
                "explain dye sub", "explain dye sublimation", "how does dye-sublimation work",
                "what is thermal dye sub", "dye sub technology", "dyesub technology"
            ]) or (
                any(d in msg_lower for d in ["dye sub", "dyesub", "dye sublimation", "داي سب", "سبليميشن", "تسامي"])
                and any(q in msg_lower for q in ["what is", "how does", "how it works", "explain", "ما هي", "ما هو", "كيف تعمل", "كيف يشتغل", "وش هو", "ايش هو"])
            )

            if is_dye_sub_education:
                if read_ctx.language == "ar":
                    parts.append(
                        "تقنية داي-سبليميشن (Dye-Sublimation / التسامي الحراري) تعتمد على نقل الصبغة من شريط حراري إلى ورق الصور مباشرة باستخدام درجات حرارة دقيقة، مع إضافة طبقة حماية شفافة (Overcoat).\n\n"
                        "**أهم مميزات هذه التقنية**:\n"
                        "• **جفاف فوري ومقاومة للماء**: الصور تخرج جافة تماماً ومقاومة للماء وبصمات الأصابع فور خروجها من الطابعة.\n"
                        "• **جودة معملية متصلة (Continuous-Tone)**: ألوان ناعمة وحقيقية بدون نقاط حبر مرئية (بخلاف طابعات الحبر النفاث Inkjet).\n"
                        "• **طبقة حماية عازلة**: تحمي الصور من الرطوبة والبهتان والأشعة فوق البنفسجية لسنوات طويلة.\n"
                        "• **سرعة استثنائية**: طابعة Citizen CX-02 تطبع مقاس 4×6 بوصة في **8.4 ثوانٍ** فقط، مع إمكانية التبديل بين اللامع (Glossy) والمطفي (Matte) من إعدادات البرنامج مباشرة.\n\n"
                        "هل تبحث عن طابعة صور لكشك تصوير (Photo Booth) أو استوديو تصوير فوتوغرافي؟"
                    )
                else:
                    parts.append(
                        "Dye-sublimation (thermal dye-diffusion transfer) uses heat to infuse solid dye from a ribbon directly into specially coated photo paper. "
                        "It applies Cyan, Magenta, Yellow, plus a clear protective overcoat layer (OP).\n\n"
                        "**Key Advantages for Events & Studios**:\n"
                        "• **Instant Dry & Durable**: 100% water-resistant, fingerprint-proof, and smudge-free immediately upon ejecting.\n"
                        "• **Continuous-Tone Lab Quality**: Smooth photographic transitions without visible inkjet droplets.\n"
                        "• **Protective Overcoat**: UV and moisture barrier that protects prints for decades.\n"
                        "• **Rapid Output**: The Citizen CX-02 prints a 4×6\" photo in just **8.4 seconds** with driver-selectable Glossy and Matte finishes without changing media rolls.\n\n"
                        "Are you considering dye-sub for an event photo booth, photography studio, or commercial kiosk?"
                    )
            elif chunks and not is_quote_called and (technical_asked or not is_price_called):
                try:
                    llm_response = llm_module.generate_llm_response(
                        user_message=user_msg,
                        context_chunks=chunks,
                        conversation_history=history
                    )
                    if llm_response:
                        parts.append(llm_response)
                except Exception as e:
                    logger.info(f"LLM generation failed: {e}. Using extractive fallback.")
                    parts.append(make_extractive_fallback(chunks, user_msg, language=read_ctx.language))

            if tools_called:
                for tr in tools_called:
                    tool_name = tr.get("tool")
                    res = tr.get("result", {})
                    if tool_name == "get_price":
                        if read_ctx and read_ctx.resolved_qty and read_ctx.resolved_qty > 1:
                            continue
                        if res.get("status") == "success":
                            old_str = f" (Original: ~{res['formatted_old_price']}~)" if res.get("formatted_old_price") else ""
                            stale_str = f"\n⚠️ {res['stale_note']}" if res.get("stale_note") else ""
                            est_str = f"\nℹ️ {res['estimate_note']}" if res.get("estimate_note") else ""
                            if read_ctx and read_ctx.language == "ar":
                                parts.append(
                                    f"السعر التجاري المعتمد لـ **{res['name']}** (رمز: {res['sku']}) هو "
                                    f"**{res['formatted_price']}**{old_str}.\n"
                                    f"• الضريبة: خاضعة لنسبة 5% ضريبة القيمة المضافة في الإمارات.\n"
                                    f"• ملاحظة: السعر خاضع للتأكيد النهائي من مكتب المبيعات.{est_str}{stale_str}\n"
                                    f"• التوفر: {'متوفرة في مستودع دبي' if res['in_stock'] else 'متوفرة بالطلب'}."
                                )
                            else:
                                parts.append(
                                    f"The official price for the **{res['name']}** (SKU: {res['sku']}) is "
                                    f"**{res['formatted_price']}**{old_str}.\n"
                                    f"• VAT: Prices are subject to 5% UAE VAT.\n"
                                    f"• Note: Price subject to confirmation by our sales desk.{est_str}{stale_str}\n"
                                    f"• Availability: {'In Stock (Dubai warehouse)' if res['in_stock'] else 'Available on order'}."
                                )
                        elif res.get("status") == "quote_required":
                            parts.append(res["message"])
                        elif res.get("status") == "not_listed":
                            parts.append(res["message"])
                        elif res.get("handoff"):
                            ho = handoff_to_human(reason=res.get("message"), summary=user_msg, phone=phone, sender_id=sender_id)
                            tools_called.append({"tool": "handoff_to_human", "result": ho})
                            parts.append(f"{res.get('message')}\n\n{ho['customer_message']}")
                        else:
                            parts.append(res.get("message", "Price unavailable."))
                    elif tool_name == "get_product_link":
                        if res.get("status") == "success":
                            parts.append(f"You can view and order the *{res['name']}* here:\n🔗 {res['url']}")
                        else:
                            parts.append(res.get("message", "Link unavailable."))
                    elif tool_name == "create_quote":
                        if res.get("status") == "success":
                            parts.append(res["text_summary"])
                        else:
                            parts.append(res.get("message", "Could not generate quote."))

            if not parts:
                chunks = retrieve(user_msg, top_k=4, category=sales_state.category, model=sales_state.current_model)
                if not chunks:
                    comp_chunks = retrieve_company(user_msg, top_k=2)
                    all_chunks = [c for c in comp_chunks if c.get("text")]
                else:
                    all_chunks = chunks
                if all_chunks:
                    try:
                        llm_response = llm_module.generate_llm_response(
                            user_message=user_msg,
                            context_chunks=all_chunks,
                            conversation_history=history
                        )
                        if llm_response and "NO_ANSWER" not in llm_response:
                            parts.append(llm_response)
                        else:
                            parts.append(make_extractive_fallback(all_chunks, user_msg, language=read_ctx.language))
                    except Exception as e:
                        logger.info(f"LLM generation failed: {e}. Using extractive fallback.")
                        parts.append(make_extractive_fallback(all_chunks, user_msg, language=read_ctx.language))

            if parts:
                reply = "\n\n".join(parts)
            else:
                if any(rej in msg_lower for rej in ["dont this", "don't this", "dont want this", "don't want this", "not this one", "not this printer", "something else", "different one", "different model"]):
                    reply = (
                        "Understood! Could you let me know what specific printing requirements or applications you are looking for "
                        "(e.g., photo booth events, office business documents, wide-format CAD/posters, or high-volume kiosk)? "
                        "Kepler Tech carries a comprehensive range of Citizen and Epson printing systems, and I would be delighted to recommend the perfect model for your needs."
                    )
                else:
                    ho = handoff_to_human(reason="Query outside documented Citizen CX-02 specifications", summary=user_msg, phone=phone, sender_id=sender_id)
                    tools_called.append({"tool": "handoff_to_human", "result": ho})
                    reply = (
                        "I want to make sure I give you accurate and verified information for your requirements. "
                        f"Our Kepler Tech commercial printing specialists in Dubai will be happy to assist you directly:\n\n{ho['customer_message']}"
                    )

        # 5. Post-Guardrails Verification
        post_ok, post_err = check_post_guardrails(reply)
        if not post_ok:
            logger.warning(f"Post-guardrail breach: {post_err}")
            ho = handoff_to_human(reason=f"Post-guardrail violation: {post_err}", summary=user_msg, phone=phone, sender_id=sender_id)
            tools_called.append({"tool": "handoff_to_human", "result": ho})
            reply = ho["customer_message"]

        # Prepend self-correction acknowledgment if relevant
        if correction_prefix and not reply.startswith("Understood"):
            reply = f"{correction_prefix}{reply}"

        # Track model recommended in reply
        reply_lower = reply.lower()
        if "citizen cy-02" in reply_lower or "cy-02 photo printer" in reply_lower:
            sales_state.update_model("CY-02", brand="Citizen", category="photo")
        elif "citizen cz-01" in reply_lower or "cz-01 photo printer" in reply_lower:
            sales_state.update_model("CZ-01", brand="Citizen", category="photo")
        elif "citizen cx-02w" in reply_lower or "cx-02w photo printer" in reply_lower:
            sales_state.update_model("CX-02W", brand="Citizen", category="photo")
        elif "citizen cx-02" in reply_lower or "cx-02 photo printer" in reply_lower:
            if not sales_state.current_model:
                sales_state.update_model("CX-02", brand="Citizen", category="photo")

        # Track bot question for next-turn context inheritance
        if any(w in reply_lower for w in ["prints per day", "pages per day", "print volume", "how many prints", "how many pages"]):
            sales_state.last_bot_question = "volume"
        elif any(w in reply_lower for w in ["which print size", "what size", "print format", "4x6", "a1 or a0"]) and "?" in reply:
            sales_state.last_bot_question = "paper_size"
        elif any(w in reply_lower for w in ["print, scan", "multifunction", "print-only"]) and "?" in reply:
            sales_state.last_bot_question = "function"
        else:
            sales_state.last_bot_question = None

        save_sales_state(sales_state)

        # 6. Log message to SQLite
        log_message(sender_id=sender_id, role="user", content=user_msg, message_id=message_id, channel=channel)
        log_message(sender_id=sender_id, role="assistant", content=reply, channel=channel)

        # Build matched product cards if catalog or product matched
        cards = []
        is_handoff_unknown = any(t.get("tool") == "handoff_to_human" and "unrecognized" in str(t.get("reason", "")).lower() for t in tools_called)
        if intent not in ("guardrails", "out_of_scope") and not is_handoff_unknown:
            cards = build_matched_cards(target_sku=read_ctx.resolved_sku, intent=intent, user_msg=user_msg, tools_called=tools_called)

        return {
            "reply": reply,
            "intent": intent,
            "priority": priority,
            "tools_called": tools_called,
            "chunks_retrieved": chunks,
            "cards": cards,
            "language": read_ctx.language,
            "resolved_sku": read_ctx.resolved_sku,
            "is_anaphora": read_ctx.is_anaphora,
            "understanding": understand_res.model_dump(),
            "sales_state": decision.current_state.value,
            "state_decision": decision.model_dump(),
            "prompt_version": Config.PROMPT_VERSION
        }

