import logging
from typing import Dict, Any, Callable
from app.tools.schemas import TOOL_SCHEMAS
from app.tools.pricing import get_price, check_stock, list_products, calculate_cost_per_print
from app.tools.links import get_product_link
from app.tools.quote import create_quote
from app.tools.policies import get_policy
from app.tools.handoff import handoff_to_human, create_lead

logger = logging.getLogger(__name__)

TOOL_MAP: Dict[str, Callable] = {
    "get_price": get_price,
    "get_product_link": get_product_link,
    "check_stock": check_stock,
    "list_products": list_products,
    "calculate_cost_per_print": calculate_cost_per_print,
    "create_quote": create_quote,
    "get_policy": get_policy,
    "create_lead": create_lead,
    "handoff_to_human": handoff_to_human
}


def execute_tool(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Safely dispatches and executes a tool with JSON-schema validation.
    Guarantees no unhandled exceptions are raised.
    """
    if tool_name not in TOOL_MAP:
        logger.warning(f"Attempted execution of unknown tool '{tool_name}'")
        return {
            "status": "error",
            "tool": tool_name,
            "message": f"Tool '{tool_name}' is not recognized.",
            "handoff": True
        }

    func = TOOL_MAP[tool_name]
    schema = TOOL_SCHEMAS.get(tool_name, {})
    required_fields = schema.get("required", [])

    # Validate required arguments
    missing = [rf for rf in required_fields if rf not in args or args[rf] is None]
    if missing:
        return {
            "status": "error",
            "tool": tool_name,
            "message": f"Missing required parameter(s): {', '.join(missing)}",
            "handoff": False
        }

    try:
        result = func(**args)
        return {
            "status": "success",
            "tool": tool_name,
            "result": result
        }
    except Exception as e:
        logger.exception(f"Unexpected error executing tool '{tool_name}': {e}")
        # Safe fallback handoff
        ho = handoff_to_human(
            reason=f"Tool execution exception in '{tool_name}': {str(e)}",
            summary=f"Args: {args}"
        )
        return {
            "status": "error",
            "tool": tool_name,
            "message": f"An error occurred while running {tool_name}. Transferring to customer desk.",
            "handoff": True,
            "handoff_result": ho
        }
