import re
import logging
from typing import Dict, Any, List, Optional
from app.config import Config
from app.agent.router import classify_intent, PRICE_KEYWORDS, DATASHEET_KEYWORDS
from app.agent.guardrails import check_pre_guardrails, check_post_guardrails
from app.agent.llm import generate_llm_response
from app.agent.validator import make_extractive_fallback
from app.rag.retriever import retrieve
from app.tools.pricing import get_price, check_stock, list_products, calculate_cost_per_print
from app.tools.links import get_product_link
from app.tools.quote import create_quote
from app.tools.policies import get_policy
from app.tools.handoff import handoff_to_human, create_lead
from app.storage.messages import log_message, get_conversation_history
from app.storage.leads import set_pending_lead, get_pending_lead, clear_pending_lead

from app.utils.quantity import parse_quantity
from app.cognitive.reader import read_message, ReadContext
from app.cognitive.understander import understand_message, UnderstandResult
from app.cognitive.state_machine import load_sales_state, transition_sales_state, SalesState

logger = logging.getLogger(__name__)


def determine_target_sku(text: str, read_ctx: Optional[ReadContext] = None) -> Optional[str]:
    # 0. If read_ctx already resolved a specific SKU, honor it
    if read_ctx and read_ctx.resolved_sku:
        return read_ctx.resolved_sku

    raw_lower = text.lower()
    t = raw_lower.replace(" ", "").replace("-", "").replace(".", "").replace("\"", "").replace("×", "x").replace("*", "x")

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

    # 2. Unsupported accessories / items
    unsupported_items = ["tripod", "cable", "adapter", "battery", "scanner", "stand", "bluetooth", "wireless", "xyz"]
    if any(u in raw_lower for u in unsupported_items):
        return None

    # 3. Media without specific size defaults to standard 4x6 media
    if any(m in raw_lower for m in ["media", "paper", "consumable", "rolls"]):
        return "CX2-MS46-2PC"

    # 4. Printer or general product inquiry ("CX-02", "printer", "machine", "unit", "it")
    if any(p in raw_lower for p in ["cx-02", "cx02", "printer", "machine", "unit", "it", "device"]):
        return "CX-02"

    # 5. General pricing / purchase inquiry
    if any(q in raw_lower for q in ["price", "cost", "how much", "rate", "quote", "buy", "order", "link", "url"]):
        return "CX-02"

    return None


def extract_phone_and_name(text: str) -> Dict[str, Optional[str]]:
    phone_match = re.search(r"(\+?\d[\d\s-]{7,15}\d)", text)
    phone = phone_match.group(1).replace(" ", "").replace("-", "") if phone_match else None

    name_match = re.search(r"(?:my name is|i am|this is)\s+([a-zA-Z\s]+)", text, re.IGNORECASE)
    name = name_match.group(1).strip() if name_match else None

    return {"phone": phone, "name": name}


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
        # 1. Fetch conversation history (last 8 turns)
        history = get_conversation_history(sender_id, limit=8)

        # 2. Cognitive Step 1: READ (Normalization, Language, Anaphora, Quantity)
        read_ctx = read_message(user_message, history=history)
        user_msg = read_ctx.normalized_text
        msg_lower = user_msg.lower()
        tools_called = []
        chunks = []

        # 3. Cognitive Step 2: UNDERSTAND (Structured NLU, Entities, Risk Flags)
        understand_res = understand_message(read_ctx)

        # 4. Cognitive Step 3: THINK (Deterministic Sales Policy State Machine)
        sales_state = load_sales_state(sender_id)
        decision = transition_sales_state(
            state=sales_state,
            understand_res=understand_res,
            read_ctx=read_ctx,
            phone=phone
        )

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

        # Branch 1: Guardrails
        if intent == "guardrails":
            fixed_resp = routing.get("fixed_response", "This query violates CX-02 operational guidelines.")
            ho = handoff_to_human(reason=routing.get("reason", "Guardrail breach"), summary=user_msg, phone=phone, sender_id=sender_id)
            tools_called.append({"tool": "handoff_to_human", "result": ho})
            reply = f"{fixed_resp}\n\n{ho['customer_message']}"

        # Branch 2: Small Talk
        elif intent == "small_talk":
            reply = (
                "Hello! Welcome to Kepler Tech LLC. I am your specialized sales assistant for the "
                "*Citizen CX-02 photo printer* in Dubai. How can I help you today with pricing, technical specifications, "
                "or consumable media?"
            )

        # Branch 3: Human / Demo / Reserve
        elif intent == "human_demo_reserve":
            effective_phone = phone or (pending.get("temp_phone") if pending else None)
            if not effective_phone and channel != "whatsapp":
                set_pending_lead(sender_id, stage="awaiting_contact", last_intent="demo_or_human")
                reply = (
                    "I would be glad to connect you with our sales team or arrange a demonstration at our Dubai showroom! "
                    "Could you please share your name and mobile/WhatsApp number?"
                )
            else:
                ho = handoff_to_human(reason=routing.get("reason"), summary=user_msg, phone=effective_phone, sender_id=sender_id)
                tools_called.append({"tool": "handoff_to_human", "result": ho})
                reply = ho["customer_message"]

        # Branch 4: Out of Scope
        elif intent == "out_of_scope":
            fixed_resp = routing.get("fixed_response", "This query is outside the scope of Citizen CX-02.")
            ho = handoff_to_human(reason=routing.get("reason", "Out of scope"), summary=user_msg, phone=phone, sender_id=sender_id)
            tools_called.append({"tool": "handoff_to_human", "result": ho})
            reply = f"{fixed_resp}\n\n{ho['customer_message']}"

        # Branch 6: Policies (Delivery charges, payment methods, returns)
        elif intent == "policies":
            pol_key = routing.get("policy_name", "warranty")
            pol_res = get_policy(pol_key)
            tools_called.append({"tool": "get_policy", "args": {"policy_name": pol_key}, "result": pol_res})
            if pol_res.get("handoff"):
                ho = handoff_to_human(reason=f"Policy inquiry for '{pol_key}' (unconfirmed in policies.json)", summary=user_msg, phone=phone, sender_id=sender_id)
                tools_called.append({"tool": "handoff_to_human", "result": ho})
                reply = pol_res["message"]
            else:
                reply = pol_res.get("message", str(pol_res.get("details")))

        # Branch 7: Discount / Negotiation -> Handoff
        elif intent == "discount_negotiation":
            ho = handoff_to_human(reason="Customer requested commercial discount / negotiation", summary=user_msg, phone=phone, sender_id=sender_id)
            tools_called.append({"tool": "handoff_to_human", "result": ho})
            reply = (
                "Kepler Tech LLC offers commercial tier pricing for bulk media orders and multi-unit printer deployments. "
                "Discounts and commercial terms must be approved directly by our sales management.\n\n"
                f"{ho['customer_message']}"
            )

        # Branch 9: Stock Availability
        elif intent == "stock":
            target_sku = determine_target_sku(user_msg, read_ctx=read_ctx)
            if target_sku is None:
                ho = handoff_to_human(
                    reason=f"Stock inquiry for unrecognized item: {user_msg}",
                    summary=user_msg,
                    phone=phone,
                    sender_id=sender_id
                )
                tools_called.append({"tool": "handoff_to_human", "result": ho})
                reply = (
                    "I specialize exclusively in the *Citizen CX-02 photo printer* and its official accessories "
                    "(4x6\", 5x7\", and 6x8\" media sets, protective carry bag, and printhead cleaning pen). "
                    f"Our sales desk can check stock for other products.\n\n{ho['customer_message']}"
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
                spec_header = ""
                if chunks:
                    spec_header = f"According to the official Citizen CX-02 specifications ({chunks[0]['section']}):\n\n"
                reply = (
                    f"{spec_header}"
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

        # Branch 11: Bundle / Catalog
        elif intent == "bundle_catalog":
            cat_res = list_products()
            tools_called.append({"tool": "list_products", "result": cat_res})
            lines = [f"• *{p['name']}* ({p['sku']}): *{p['formatted_price']}*" for p in cat_res.get("products", [])]
            catalog_text = "\n".join(lines)
            stale_warning = f"\n\n⚠️ {cat_res['stale_note']}" if cat_res.get("stale_note") else ""
            reply = (
                f"📋 *Kepler Tech LLC — Official Citizen CX-02 Catalog*:\n\n"
                f"{catalog_text}{stale_warning}\n\n"
                f"All products are available from our Dubai distribution center."
            )

        # General Multi-intent / Hybrid Handling (Pricing, Quotes, Links, and Knowledge RAG)
        else:
            is_6x9_inquiry = "6x9" in msg_lower and any(w in msg_lower for w in ["sell", "have", "buy", "media", "paper", "order", "roll", "stock", "get", "cost", "price"])
            has_price_terms = is_6x9_inquiry or any(p in msg_lower for p in [
                "price", "how much", "cost", "rate", "aed", "dirham", "dirhams", "quote", "quotation", "link", "url", "where can i buy", "where to buy", "website"
            ])
            has_knowledge_terms = any(k in msg_lower for k in [
                "spec", "dpi", "resolution", "weight", "dimension", "dimensions", "size", "sizes", "speed", "fast",
                "seconds", "ribbon", "paper", "media", "roll", "prints", "overcoat", "glossy",
                "matte", "luster", "warranty", "mac", "windows", "cups", "driver", "drivers", "usb",
                "photobooth", "rewind", "cleaning", "pen", "bag", "power", "watt", "wattage", "sleep"
            ])

            parts = []

            # 1. Execute tool if pricing or quote or link is asked
            if intent in ("price", "quote", "link") or has_price_terms:
                target_sku = determine_target_sku(user_msg, read_ctx=read_ctx)

                if target_sku is None:
                    ho = handoff_to_human(
                        reason=f"Unrecognized or ambiguous product inquiry: {user_msg}",
                        summary=user_msg,
                        phone=phone,
                        sender_id=sender_id
                    )
                    tools_called.append({"tool": "handoff_to_human", "result": ho})
                    parts.append(
                        "I specialize exclusively in the *Citizen CX-02 photo printer* and its official accessories "
                        "(4x6\", 5x7\", and 6x8\" media sets, protective carry bag, and printhead cleaning pen). "
                        "I could not identify the specific product you are asking about. "
                        f"Our sales desk can confirm availability for you.\n\n{ho['customer_message']}"
                    )
                elif "quote" in msg_lower or "quotation" in msg_lower or (read_ctx and read_ctx.resolved_qty and read_ctx.resolved_qty > 1 and read_ctx.is_anaphora):
                    qty = (read_ctx.resolved_qty if read_ctx else None) or parse_quantity(user_msg) or 1

                    # Check if multi-item quote (e.g. printer AND media)
                    if ("printer" in msg_lower or "unit" in msg_lower) and any(m in msg_lower for m in ["4x6", "5x7", "6x8", "paper", "media", "bag", "pen"]):
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
                chunks = retrieve(user_msg, top_k=2)

            # 3. Synthesize response combining RAG and Tool results
            if chunks:
                top_chunk = chunks[0]
                section = top_chunk["section"]
                text = top_chunk["text"]
                lines = [l.strip() for l in text.splitlines() if l.strip() and not l.startswith("#")]
                key_details = "\n".join(lines[:5])
                parts.append(f"Here are the official specifications for the *Citizen CX-02* ({section}):\n\n{key_details}")

            if tools_called:
                for tr in tools_called:
                    tool_name = tr.get("tool")
                    res = tr.get("result", {})
                    if tool_name == "get_price":
                        if res.get("status") == "success":
                            old_str = f" (Original: ~{res['formatted_old_price']}~)" if res.get("formatted_old_price") else ""
                            stale_str = f"\n⚠️ {res['stale_note']}" if res.get("stale_note") else ""
                            est_str = f"\nℹ️ {res['estimate_note']}" if res.get("estimate_note") else ""
                            confirm_str = f"\nℹ️ Note: {res['to_confirm_note']}" if res.get("to_confirm_note") else ""
                            parts.append(
                                f"The official price for the *{res['name']}* (SKU: {res['sku']}) is "
                                f"*{res['formatted_price']}*{old_str}.{est_str}{confirm_str}{stale_str}\n"
                                f"Availability: {'In Stock (Dubai)' if res['in_stock'] else 'Pre-order'}."
                            )
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

            if parts:
                reply = "\n\n".join(parts)
            else:
                ho = handoff_to_human(reason="Query outside documented Citizen CX-02 specifications", summary=user_msg, phone=phone, sender_id=sender_id)
                tools_called.append({"tool": "handoff_to_human", "result": ho})
                reply = ho["customer_message"]

        # 5. Post-Guardrails Verification
        post_ok, post_err = check_post_guardrails(reply)
        if not post_ok:
            logger.warning(f"Post-guardrail breach: {post_err}")
            ho = handoff_to_human(reason=f"Post-guardrail violation: {post_err}", summary=user_msg, phone=phone, sender_id=sender_id)
            tools_called.append({"tool": "handoff_to_human", "result": ho})
            reply = ho["customer_message"]

        # 6. Log message to SQLite
        log_message(sender_id=sender_id, role="user", content=user_msg, message_id=message_id, channel=channel)
        log_message(sender_id=sender_id, role="assistant", content=reply, channel=channel)

        return {
            "reply": reply,
            "intent": intent,
            "priority": priority,
            "tools_called": tools_called,
            "chunks_retrieved": chunks,
            "language": read_ctx.language,
            "resolved_sku": read_ctx.resolved_sku,
            "is_anaphora": read_ctx.is_anaphora,
            "understanding": understand_res.model_dump(),
            "sales_state": decision.current_state.value,
            "state_decision": decision.model_dump()
        }
