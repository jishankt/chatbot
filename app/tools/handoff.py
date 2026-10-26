from typing import Dict, Any, Optional
from app.config import Config
from app.storage.handoffs import save_handoff, get_latest_handoff_by_sender
from app.storage.leads import save_lead, get_latest_lead_by_sender


def handoff_to_human(
    reason: str,
    summary: Optional[str] = None,
    phone: Optional[str] = None,
    sender_id: Optional[str] = None
) -> Dict[str, Any]:
    # Idempotent deduplication: if exact handoff reason was already created for sender, reuse it
    if sender_id:
        latest = get_latest_handoff_by_sender(sender_id)
        if latest and latest.get("reason") == reason:
            customer_msg = (
                f"I have routed your inquiry to our specialized sales and technical team at Kepler Tech LLC (Dubai).\n\n"
                f"📍 Office: {Config.KEPLER_ADDRESS}\n"
                f"📞 Phone: {Config.KEPLER_PHONE}\n"
                f"💬 WhatsApp: {Config.KEPLER_WHATSAPP}\n"
                f"🕒 Hours: {Config.KEPLER_HOURS}\n\n"
                f"A representative will assist you promptly."
            )
            return {
                "status": "handoff_initiated",
                "reason": reason,
                "summary": summary,
                "phone": phone,
                "customer_message": customer_msg,
                "idempotent": True
            }

    save_handoff(
        reason=reason,
        summary=summary,
        phone=phone,
        sender_id=sender_id,
        status="pending"
    )

    customer_msg = (
        f"I have routed your inquiry to our specialized sales and technical team at Kepler Tech LLC (Dubai).\n\n"
        f"📍 Office: {Config.KEPLER_ADDRESS}\n"
        f"📞 Phone: {Config.KEPLER_PHONE}\n"
        f"💬 WhatsApp: {Config.KEPLER_WHATSAPP}\n"
        f"🕒 Hours: {Config.KEPLER_HOURS}\n\n"
        f"A representative will assist you promptly."
    )

    return {
        "status": "handoff_initiated",
        "reason": reason,
        "summary": summary,
        "phone": phone,
        "customer_message": customer_msg
    }


def create_lead(
    name: Optional[str] = None,
    phone: Optional[str] = None,
    notes: Optional[str] = None,
    sender_id: Optional[str] = None
) -> Dict[str, Any]:
    # Idempotent lead capture: if same phone registered for sender, avoid duplicate lead insert
    if sender_id and phone:
        latest = get_latest_lead_by_sender(sender_id)
        if latest and latest.get("phone") == phone:
            return {
                "status": "success",
                "lead_id": latest["id"],
                "name": name,
                "phone": phone,
                "message": "Thank you! Your contact details have been registered with Kepler Tech LLC.",
                "idempotent": True
            }

    lead_id = save_lead(
        sender_id=sender_id,
        name=name,
        phone=phone,
        notes=notes,
        status="new"
    )

    return {
        "status": "success",
        "lead_id": lead_id,
        "name": name,
        "phone": phone,
        "message": "Thank you! Your contact details have been registered with Kepler Tech LLC."
    }
