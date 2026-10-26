import uuid
from typing import List, Dict, Any, Optional
from app.config import Config
from app.tools.pricing import load_catalog, normalize_sku
from app.storage.quotes import save_quote


def create_quote(
    items: List[Dict[str, Any]],
    customer_name: str = "Valued Customer",
    phone: Optional[str] = None,
    sender_id: Optional[str] = None
) -> Dict[str, Any]:
    catalog = load_catalog()
    products = catalog.get("products", {})

    if not items:
        return {
            "status": "error",
            "message": "Cannot create quotation: No items were provided.",
            "handoff": False
        }

    validated_lines = []
    subtotal = 0.0

    for item in items:
        raw_sku = item.get("sku", "")
        norm_sku = normalize_sku(raw_sku)

        if norm_sku not in products:
            if "6x9" in raw_sku.lower():
                return {
                    "status": "error",
                    "message": "6x9\" media is not currently sold by Kepler Tech LLC. Quote cannot be finalized.",
                    "handoff": True
                }
            return {
                "status": "error",
                "message": f"SKU '{raw_sku}' is not available in our Citizen CX-02 catalog.",
                "handoff": True
            }

        try:
            qty = int(item.get("qty", 1))
        except (ValueError, TypeError):
            return {
                "status": "error",
                "message": f"Invalid quantity for SKU '{raw_sku}'. Quantity must be an integer.",
                "handoff": False
            }

        if qty < 1 or qty > 1000:
            return {
                "status": "error",
                "message": f"Quantity for {products[norm_sku]['name']} must be between 1 and 1,000 units. For larger commercial orders, please speak with our corporate sales desk.",
                "handoff": True
            }

        unit_price = products[norm_sku]["price"]
        line_total = round(unit_price * qty, 2)
        subtotal += line_total

        validated_lines.append({
            "sku": norm_sku,
            "name": products[norm_sku]["name"],
            "unit_price": unit_price,
            "qty": qty,
            "line_total": line_total
        })

    subtotal = round(subtotal, 2)

    # VAT Calculation: only if VAT_RATE and PRICES_INCLUDE_VAT are configured
    vat_amount = None
    if Config.VAT_RATE is not None and Config.PRICES_INCLUDE_VAT is not None:
        if Config.PRICES_INCLUDE_VAT is False:
            vat_amount = round(subtotal * Config.VAT_RATE, 2)
            total = round(subtotal + vat_amount, 2)
            vat_line = f"VAT ({int(Config.VAT_RATE * 100)}%): {vat_amount:,.2f} AED"
        else:
            vat_amount = round(subtotal - (subtotal / (1.0 + Config.VAT_RATE)), 2)
            total = subtotal
            vat_line = f"Includes {int(Config.VAT_RATE * 100)}% VAT ({vat_amount:,.2f} AED)"
    else:
        total = subtotal
        vat_line = "VAT: Consult sales desk for applicable tax treatment"

    quote_id = f"Q-{uuid.uuid4().hex[:8].upper()}"

    # Render fixed deterministic template
    line_strings = []
    for line in validated_lines:
        line_strings.append(
            f"• {line['qty']}x {line['name']} (SKU: {line['sku']})\n"
            f"   @ {line['unit_price']:,.2f} AED = {line['line_total']:,.2f} AED"
        )
    items_block = "\n".join(line_strings)

    text_summary = (
        f"📄 *Official Quotation ({quote_id})*\n"
        f"Customer: {customer_name}\n"
        f"Supplier: Kepler Tech LLC (Dubai)\n"
        f"----------------------------------------\n"
        f"{items_block}\n"
        f"----------------------------------------\n"
        f"Subtotal: {subtotal:,.2f} AED\n"
        f"{vat_line}\n"
        f"*Total: {total:,.2f} AED*\n\n"
        f"To confirm this order, contact Kepler Tech LLC:\n"
        f"📞 Phone: {Config.KEPLER_PHONE} | 💬 WhatsApp: {Config.KEPLER_WHATSAPP}"
    )

    # Persist in SQLite
    save_quote(
        quote_id=quote_id,
        items=validated_lines,
        subtotal=subtotal,
        total=total,
        vat_amount=vat_amount,
        sender_id=sender_id,
        customer_name=customer_name,
        phone=phone
    )

    return {
        "status": "success",
        "quote_id": quote_id,
        "customer_name": customer_name,
        "phone": phone,
        "lines": validated_lines,
        "subtotal": subtotal,
        "vat_amount": vat_amount,
        "total": total,
        "text_summary": text_summary
    }
