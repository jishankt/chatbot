import logging
from typing import List, Dict, Any, Optional

from app.config import Config
from app.cognitive.reader import ReadContext
from app.cognitive.understander import UnderstandResult
from app.cognitive.state_machine import StateMachineDecision
from app.agent.validator import validate_output, make_extractive_fallback
from app.agent.llm import generate_llm_response

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Deterministic Route Templates
# ---------------------------------------------------------------------------

class Templates:
    @staticmethod
    def guardrails(fixed_response: str, handoff_message: str) -> str:
        return f"{fixed_response}\n\n{handoff_message}"

    @staticmethod
    def small_talk() -> str:
        return (
            "Hello! Welcome to Kepler Tech LLC. I am your specialized sales assistant for the "
            "*Citizen CX-02 photo printer* in Dubai. How can I help you today with pricing, technical specifications, "
            "or consumable media?"
        )

    @staticmethod
    def human_demo(customer_message: str) -> str:
        return customer_message

    @staticmethod
    def out_of_scope(fixed_response: str, handoff_message: str) -> str:
        return f"{fixed_response}\n\n{handoff_message}"

    @staticmethod
    def policy(message: str, handoff_message: Optional[str] = None) -> str:
        if handoff_message:
            return f"{message}\n\n{handoff_message}"
        return message

    @staticmethod
    def discount(handoff_message: str) -> str:
        return (
            "Kepler Tech LLC offers commercial tier pricing for bulk media orders and multi-unit printer deployments. "
            "Discounts and commercial terms must be approved directly by our sales management.\n\n"
            f"{handoff_message}"
        )

    @staticmethod
    def stock(name: str, stock_status: str) -> str:
        return f"📦 *Stock Status for {name}*:\n{stock_status}."

    @staticmethod
    def price(
        name: str,
        sku: str,
        formatted_price: str,
        in_stock: bool,
        formatted_old_price: Optional[str] = None,
        stale_note: Optional[str] = None,
        estimate_note: Optional[str] = None,
        to_confirm_note: Optional[str] = None
    ) -> str:
        old_str = f" (Original: ~{formatted_old_price}~)" if formatted_old_price else ""
        stale_str = f"\n⚠️ {stale_note}" if stale_note else ""
        est_str = f"\nℹ️ {estimate_note}" if estimate_note else ""
        confirm_str = f"\nℹ️ Note: {to_confirm_note}" if to_confirm_note else ""
        availability = "In Stock (Dubai)" if in_stock else "Pre-order"

        return (
            f"The official price for the *{name}* (SKU: {sku}) is "
            f"*{formatted_price}*{old_str}.{est_str}{confirm_str}{stale_str}\n"
            f"Availability: {availability}."
        )

    @staticmethod
    def product_link(name: str, url: str) -> str:
        return f"You can view and order the *{name}* here:\n🔗 {url}"

    @staticmethod
    def media_yield_cost(
        size: str,
        media_name: str,
        media_sku: str,
        box_price: float,
        prints_per_box: Any,
        formatted_cost: str,
        estimate_note: Optional[str] = None,
        spec_header: str = ""
    ) -> str:
        est = f" {estimate_note}" if estimate_note else ""
        roll_info = ""
        if "4x6" in size:
            roll_info = " (400 prints per roll, 2 rolls per box)"
        elif "5x7" in size:
            roll_info = " (230 prints per roll, 2 rolls per box)"
        elif "6x8" in size:
            roll_info = " (200 prints per roll, 2 rolls per box)"
        return (
            f"{spec_header}"
            f"📊 *Running Cost Calculation ({size})*:\n"
            f"• Media SKU: {media_name} ({media_sku})\n"
            f"• Box Price: {box_price:,.2f} AED\n"
            f"• Yield: {prints_per_box} prints/box{roll_info}{est}\n"
            f"• *Cost per Print: {formatted_cost}*"
        )

    @staticmethod
    def catalog(products_lines: List[str], stale_note: Optional[str] = None) -> str:
        catalog_text = "\n".join(products_lines)
        stale_warning = f"\n\n⚠️ {stale_note}" if stale_note else ""
        return (
            f"📋 *Kepler Tech LLC — Official Citizen CX-02 Catalog*:\n\n"
            f"{catalog_text}{stale_warning}\n\n"
            f"All products are available from our Dubai distribution center."
        )


# ---------------------------------------------------------------------------
# Composite Response Composer (Cognitive Step 5: RESPOND)
# ---------------------------------------------------------------------------

def compose_response(
    intent: str,
    tools_called: List[Dict[str, Any]],
    chunks: List[Dict[str, Any]],
    decision: StateMachineDecision,
    user_message: str,
    read_ctx: ReadContext,
    understand_res: UnderstandResult,
    conversation_history: Optional[List[Dict[str, str]]] = None
) -> str:
    """
    Assembles grounded, deterministic sales response combining:
      1. Tool outputs rendered via deterministic templates.
      2. Technical specifications from RAG (synthesized or extractive fallback).
      3. Up to 1 discovery question (if allowed by state machine).
      4. Single relevant recommendation pitch (if allowed by state machine).
      5. Strict output grounding validation (rejects ungrounded figures/claims).
    """
    parts = []

    # 1. Synthesize RAG technical knowledge if chunks are present
    if chunks:
        if Config.FORCE_EXTRACTIVE_MODE or not Config.OLLAMA_CHAT_MODEL:
            rag_text = make_extractive_fallback(chunks, user_message)
        else:
            candidate = generate_llm_response(
                user_message=user_message,
                context_chunks=chunks,
                conversation_history=conversation_history,
                timeout=15.0
            )

            # Validate only the LLM-generated portion; deterministic templates
            # are grounded by construction and must not be validated here.
            is_valid, reason = validate_output(candidate, chunks, user_message)
            if not is_valid:
                logger.warning(
                    f"LLM RAG reply failed grounding validation: {reason}. "
                    "Falling back to extractive mode."
                )
                rag_text = make_extractive_fallback(chunks, user_message)
            else:
                rag_text = candidate.strip()
                if "Citizen CX-02" not in rag_text and "citizen cx-02" not in rag_text.lower():
                    rag_text = f"Here are the official specifications for the *Citizen CX-02*:\n\n{rag_text}"
        parts.append(rag_text)

    # 2. Render tool outputs deterministically
    for tool_record in tools_called:
        t_name = tool_record.get("tool")
        res = tool_record.get("result", {})

        if t_name == "get_price":
            if res.get("status") == "success":
                parts.append(Templates.price(
                    name=res["name"],
                    sku=res["sku"],
                    formatted_price=res["formatted_price"],
                    in_stock=res.get("in_stock", True),
                    formatted_old_price=res.get("formatted_old_price"),
                    stale_note=res.get("stale_note"),
                    estimate_note=res.get("estimate_note"),
                    to_confirm_note=res.get("to_confirm_note")
                ))
            elif res.get("handoff"):
                parts.append(res.get("message", "Price unavailable."))
        elif t_name == "get_product_link":
            if res.get("status") == "success":
                parts.append(Templates.product_link(res["name"], res["url"]))
            else:
                parts.append(res.get("message", "Link unavailable."))
        elif t_name == "create_quote":
            if res.get("status") == "success":
                parts.append(res["text_summary"])
            else:
                parts.append(res.get("message", "Could not generate quotation."))
        elif t_name == "check_stock":
            if res.get("status") == "success":
                parts.append(Templates.stock(res["name"], res["stock_status"]))
            else:
                parts.append(res.get("message", "Stock status unavailable."))
        elif t_name == "calculate_cost_per_print":
            if res.get("status") == "success":
                parts.append(Templates.media_yield_cost(
                    size=res["size"],
                    media_name=res["media_name"],
                    media_sku=res["media_sku"],
                    box_price=res["media_box_price"],
                    prints_per_box=res["prints_per_box"],
                    formatted_cost=res["formatted_cost_per_print"],
                    estimate_note=res.get("estimate_note")
                ))
            else:
                parts.append(res.get("message", "Running cost unavailable."))
        elif t_name == "list_products":
            lines = [f"• *{p['name']}* ({p['sku']}): *{p['formatted_price']}*" for p in res.get("products", [])]
            parts.append(Templates.catalog(lines, res.get("stale_note")))
        elif t_name == "get_policy":
            if not res.get("handoff"):
                parts.append(res.get("message", str(res.get("details"))))

    # 3. Append state machine discovery question if permitted
    if decision.discovery_question and not decision.suppress_upsell:
        parts.append(f"💬 {decision.discovery_question}")

    # 4. Append state machine recommendation pitch if permitted
    if decision.recommendation_pitch and not decision.suppress_upsell:
        parts.append(decision.recommendation_pitch)

    composed = "\n\n".join(parts) if parts else "Thank you for contacting Kepler Tech LLC. How can I assist you with the Citizen CX-02 printer today?"

    return composed
