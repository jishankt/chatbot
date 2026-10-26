"""
JSON Schema definitions for cx02-sales-ai tools.
"""

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
        "required": ["phone"]
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
