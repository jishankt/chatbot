import re
import uuid
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from app.config import Config
from app.tools.pricing import load_catalog, normalize_sku, is_price_stale
from app.storage.db import get_db_connection
from app.storage.quotes import save_quote, get_latest_quote_by_sender
from app.utils.quantity import parse_quantity, get_large_quantity_threshold


def validate_customer_name(name: str) -> bool:
    """Validate customer name against strict allowlist allowing letters, numbers, spaces, and corporate symbols (&, ())."""
    if not name or len(name) > getattr(Config, "MAX_CUSTOMER_NAME_LENGTH", 100):
        return False
    # Reject control chars and newlines
    if re.search(r"[\x00-\x1f\x7f-\x9f\r\n]", name):
        return False
    # Reject URLs
    if re.search(r"https?://|www\.|\.[a-z]{2,6}(/|\b)", name, re.IGNORECASE):
        return False
    # Allowlist: Latin & Arabic characters, digits, spaces, dots, hyphens, apostrophes, ampersand, parentheses
    if not re.match(r"^[\w\s\.\'\-\&\(\)]+$", name, re.UNICODE):
        return False
    return True


def create_quote(
    items: List[Dict[str, Any]],
    customer_name: str = "Valued Customer",
    phone: Optional[str] = None,
    sender_id: Optional[str] = None,
    idempotency_key: Optional[str] = None
) -> Dict[str, Any]:
    # Validate customer_name allowlist
    if not validate_customer_name(customer_name):
        return {
            "status": "error",
            "message": "Invalid customer_name. Must be 1 to 100 characters using valid letters, numbers, spaces, and allowed business characters (&, (), ., -, '). URLs and control characters are prohibited.",
            "handoff": False
        }

    catalog = load_catalog()
    as_of = catalog.get("as_of", "")
    if is_price_stale(as_of):
        return {
            "status": "error",
            "message": (
                f"Quotation pricing is stale (catalog date {as_of}, older than {Config.PRICE_MAX_AGE_DAYS} days). "
                f"To confirm current commercial rates and receive an official quotation, please speak directly with "
                f"our sales specialists at Kepler Tech LLC (Dubai) on {Config.KEPLER_PHONE} or WhatsApp {Config.KEPLER_WHATSAPP}."
            ),
            "handoff": True
        }

    products = catalog.get("products", {})
    large_qty_threshold = get_large_quantity_threshold()

    if not items:
        return {
            "status": "error",
            "message": "Cannot create quotation: No items were provided.",
            "handoff": False
        }

    # Session & global rate limits
    if sender_id:
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM quotes WHERE sender_id = ? AND created_at > datetime('now', '-1 hour')",
                (sender_id,)
            )
            session_quotes = cur.fetchone()[0]
            if session_quotes >= getattr(Config, "MAX_QUOTES_PER_SESSION_HOUR", 15):
                conn.close()
                return {
                    "status": "error",
                    "message": "Quotation limit reached for this session. Please speak directly with our corporate sales desk.",
                    "handoff": True
                }
            cur.execute("SELECT COUNT(*) FROM quotes WHERE created_at > datetime('now', '-1 hour')")
            global_quotes = cur.fetchone()[0]
            conn.close()
            if global_quotes >= getattr(Config, "MAX_QUOTES_GLOBAL_HOUR", 500):
                return {
                    "status": "error",
                    "message": "Quotation capacity temporarily reached. Please contact our corporate sales desk.",
                    "handoff": True
                }
        except Exception:
            pass

    # Idempotent replay: if the sender generated an identical quote recently, reuse it
    # ONLY if prices in the catalog have not changed and the quote has not expired
    if sender_id:
        latest = get_latest_quote_by_sender(sender_id)
        if latest:
            expired = False
            if latest.get("expires_at"):
                try:
                    exp_str = str(latest["expires_at"]).replace("Z", "+00:00")
                    exp_dt = datetime.fromisoformat(exp_str)
                    if exp_dt.tzinfo is None:
                        exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                    if exp_dt < datetime.now(timezone.utc):
                        expired = True
                except Exception:
                    pass

            latest_items = [{
                "sku": i.get("sku"),
                "qty": i.get("qty"),
                "unit_price": Decimal(str(i.get("unit_price", 0)))
            } for i in latest.get("items", [])]
            incoming_items = [{
                "sku": normalize_sku(i.get("sku", "")),
                "qty": parse_quantity(i.get("qty", 1))
            } for i in items]

            price_changed = False
            if not expired and len(latest_items) == len(incoming_items):
                items_match = True
                for incoming, recorded in zip(incoming_items, latest_items):
                    if incoming["sku"] != recorded["sku"] or incoming["qty"] != recorded["qty"]:
                        items_match = False
                        break
                    curr_prod = products.get(incoming["sku"])
                    if curr_prod:
                        curr_price = Decimal(str(curr_prod.get("price", 0)))
                        if curr_price != recorded["unit_price"]:
                            price_changed = True
                            break
                    else:
                        price_changed = True
                        break

                if items_match and not price_changed:
                    vat_line = f"VAT ({int(Config.VAT_RATE * 100)}%): {latest['vat_amount']:,.2f} AED" if latest.get("vat_amount") else "VAT: Consult sales desk for applicable tax treatment"
                    line_strings = [
                        f"• {l['qty']}x {l['name']} (SKU: {l['sku']})\n   @ {l['unit_price']:,.2f} AED = {l['line_total']:,.2f} AED"
                        for l in latest.get("items", [])
                    ]
                    text_summary = (
                        f"📄 *Official Quotation ({latest['quote_id']})*\n"
                        f"Customer: {latest['customer_name']}\n"
                        f"Supplier: Kepler Tech LLC (Dubai)\n"
                        f"----------------------------------------\n"
                        f"{chr(10).join(line_strings)}\n"
                        f"----------------------------------------\n"
                        f"Subtotal: {latest['subtotal']:,.2f} AED\n"
                        f"{vat_line}\n"
                        f"*Total: {latest['total']:,.2f} AED*\n\n"
                        f"To confirm this order, contact our specialized sales team at Kepler Tech LLC:\n"
                        f"📞 Phone: {Config.KEPLER_PHONE} | 💬 WhatsApp: {Config.KEPLER_WHATSAPP}"
                    )
                    return {
                        "status": "success",
                        "quote_id": latest["quote_id"],
                        "customer_name": latest["customer_name"],
                        "phone": latest["phone"],
                        "lines": latest["items"],
                        "subtotal": latest["subtotal"],
                        "vat_amount": latest.get("vat_amount"),
                        "total": latest["total"],
                        "text_summary": text_summary,
                        "idempotent": True
                    }

    validated_lines = []
    subtotal_dec = Decimal("0.00")
    FILS_PER_AED = Decimal("100")

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

        parsed_qty = parse_quantity(item.get("qty", 1))
        if parsed_qty is None:
            return {
                "status": "error",
                "message": f"Invalid quantity for SKU '{raw_sku}'. Quantity must be a valid number.",
                "handoff": False
            }

        qty = parsed_qty
        if qty < 1 or qty > 1000:
            return {
                "status": "error",
                "message": f"Quantity for {products[norm_sku]['name']} must be between 1 and 1,000 units. For larger commercial orders, please speak with our corporate sales desk.",
                "handoff": True
            }

        # Check configurable large-quantity handoff threshold for printers (>= 10)
        if norm_sku == "CX-02" and qty >= large_qty_threshold:
            return {
                "status": "error",
                "message": (
                    f"Quantity of {qty} units for {products[norm_sku]['name']} qualifies for commercial tier pricing. "
                    f"Orders of {large_qty_threshold} or more printers require sales desk assistance. "
                    f"Please contact our Dubai corporate desk at {Config.KEPLER_PHONE} or WhatsApp {Config.KEPLER_WHATSAPP}."
                ),
                "handoff": True,
                "large_quantity": True
            }

        unit_price_dec = Decimal(str(products[norm_sku]["price"])).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        qty_dec = Decimal(str(qty))
        line_total_dec = (unit_price_dec * qty_dec).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        subtotal_dec += line_total_dec

        validated_lines.append({
            "sku": norm_sku,
            "name": products[norm_sku]["name"],
            "unit_price": float(unit_price_dec),
            "qty": qty,
            "line_total": float(line_total_dec)
        })

    subtotal_dec = subtotal_dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    subtotal = float(subtotal_dec)
    subtotal_fils = int((subtotal_dec * FILS_PER_AED).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    # VAT Calculation: only if VAT_RATE and PRICES_INCLUDE_VAT are configured
    vat_amount = None
    vat_fils = None

    if Config.VAT_RATE is not None and Config.PRICES_INCLUDE_VAT is not None:
        vat_rate_dec = Decimal(str(Config.VAT_RATE))
        if Config.PRICES_INCLUDE_VAT is False:
            vat_dec = (subtotal_dec * vat_rate_dec).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            total_dec = (subtotal_dec + vat_dec).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            vat_amount = float(vat_dec)
            total = float(total_dec)
            vat_line = f"VAT ({int(Config.VAT_RATE * 100)}%): {vat_amount:,.2f} AED"
        else:
            one_plus_vat = Decimal("1.0") + vat_rate_dec
            net_dec = (subtotal_dec / one_plus_vat).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            vat_dec = (subtotal_dec - net_dec).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            total_dec = subtotal_dec
            vat_amount = float(vat_dec)
            total = float(total_dec)
            vat_line = f"Includes {int(Config.VAT_RATE * 100)}% VAT ({vat_amount:,.2f} AED)"
        vat_fils = int((vat_dec * FILS_PER_AED).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    else:
        total_dec = subtotal_dec
        total = float(total_dec)
        vat_line = "VAT: Consult sales desk for applicable tax treatment"

    total_fils = int((total_dec * FILS_PER_AED).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    catalog_version = catalog.get("catalog_version", "2026.1")
    expires_at = (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()

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
        f"To confirm this order, contact our specialized sales team at Kepler Tech LLC:\n"
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
        phone=phone,
        subtotal_fils=subtotal_fils,
        vat_fils=vat_fils,
        total_fils=total_fils,
        catalog_version=catalog_version,
        expires_at=expires_at
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
