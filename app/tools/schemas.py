"""
JSON Schema and Pydantic definitions for cx02-sales-ai tools.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Pydantic Schemas for Tool Arguments
# ---------------------------------------------------------------------------

class GetPriceArgs(BaseModel):
    sku: str = Field(..., description="Product SKU or alias, e.g. CX-02, CX2-MS46-2PC")


class GetProductLinkArgs(BaseModel):
    sku: str = Field(..., description="Product SKU to fetch official product URL")


class CheckStockArgs(BaseModel):
    sku: str = Field(..., description="Product SKU to check stock availability")


class ListProductsArgs(BaseModel):
    pass


class CalculateCostArgs(BaseModel):
    size: str = Field("4x6", description="Print size: 4x6, 5x7, 6x8, 6x9")
    volume: Optional[int] = Field(None, ge=1, description="Total number of prints to estimate cost for")


class QuoteItem(BaseModel):
    sku: str = Field(..., description="Product SKU")
    qty: int = Field(1, ge=1, le=1000, description="Quantity (1-1,000)")


class CreateQuoteArgs(BaseModel):
    items: List[QuoteItem] = Field(..., min_length=1, description="List of quote items")
    customer_name: str = Field("Valued Customer", description="Customer name")
    phone: Optional[str] = Field(None, description="Customer contact phone")
    sender_id: Optional[str] = Field(None, description="Sender channel ID")
    idempotency_key: Optional[str] = Field(None, description="Idempotency key")


class GetPolicyArgs(BaseModel):
    policy_name: str = Field(..., description="Policy key: warranty, delivery_time, delivery_charges, etc.")


class CreateLeadArgs(BaseModel):
    phone: Optional[str] = Field(None, description="Customer contact phone")
    name: Optional[str] = Field("Valued Customer", description="Customer full name")
    notes: Optional[str] = Field(None, description="Internal notes")
    sender_id: Optional[str] = Field(None, description="Sender ID")


class HandoffArgs(BaseModel):
    reason: str = Field(..., description="Reason for handoff")
    summary: Optional[str] = Field(None, description="Inquiry summary")
    phone: Optional[str] = Field(None, description="Customer phone number")
    sender_id: Optional[str] = Field(None, description="Sender ID")


TOOL_ARG_MODELS: Dict[str, Any] = {
    "get_price": GetPriceArgs,
    "get_product_link": GetProductLinkArgs,
    "check_stock": CheckStockArgs,
    "list_products": ListProductsArgs,
    "calculate_cost_per_print": CalculateCostArgs,
    "create_quote": CreateQuoteArgs,
    "get_policy": GetPolicyArgs,
    "create_lead": CreateLeadArgs,
    "handoff_to_human": HandoffArgs
}


# ---------------------------------------------------------------------------
# Backward-Compatible JSON Schemas
# ---------------------------------------------------------------------------

TOOL_SCHEMAS = {
    "get_price": {
        "type": "object",
        "properties": {
            "sku": {
                "type": "string",
                "description": "Product SKU, e.g. CX-02, CX2-MS46-2PC, CX2-MS57-2PC, CX2-MS68-2PC, CX-02-BAG, CITIZEN-PEN"
            }
        },
        "required": ["sku"]
    },
    "get_product_link": {
        "type": "object",
        "properties": {
            "sku": {
                "type": "string",
                "description": "Product SKU to fetch official product URL"
            }
        },
        "required": ["sku"]
    },
    "check_stock": {
        "type": "object",
        "properties": {
            "sku": {
                "type": "string",
                "description": "Product SKU to check stock availability"
            }
        },
        "required": ["sku"]
    },
    "list_products": {
        "type": "object",
        "properties": {},
        "required": []
    },
    "calculate_cost_per_print": {
        "type": "object",
        "properties": {
            "size": {
                "type": "string",
                "enum": ["4x6", "5x7", "6x8", "6x9"],
                "description": "Print size to calculate running cost for"
            },
            "volume": {
                "type": "integer",
                "minimum": 1,
                "description": "Total number of prints to estimate total cost for"
            }
        },
        "required": []
    },
    "create_quote": {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "sku": {"type": "string"},
                        "qty": {"type": "integer", "minimum": 1, "maximum": 1000}
                    },
                    "required": ["sku", "qty"]
                },
                "minItems": 1
            },
            "customer_name": {"type": "string"},
            "phone": {"type": "string"}
        },
        "required": ["items"]
    },
    "get_policy": {
        "type": "object",
        "properties": {
            "policy_name": {
                "type": "string",
                "description": "Name of policy: warranty, delivery_time, delivery_charges, payment_methods, return_policy, installation, support_terms, vat_treatment"
            }
        },
        "required": ["policy_name"]
    },
    "create_lead": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "phone": {"type": "string"},
            "notes": {"type": "string"}
        },
        "required": []
    },
    "handoff_to_human": {
        "type": "object",
        "properties": {
            "reason": {"type": "string"},
            "summary": {"type": "string"},
            "phone": {"type": "string"}
        },
        "required": ["reason"]
    }
}
