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
                f"A dedicated sales specialist from our team will assist you promptly."
            )
            return {
                "status": "handoff_initiated",
                "reason": reason,
                "summary": summary,
                "phone": phone,
                "customer_message": customer_msg,
                "idempotent": True
            }

    # Rate limits: per session per day and global per hour
    if sender_id:
        try:
            from app.storage.db import get_db_connection
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM handoffs WHERE sender_id = ? AND created_at > datetime('now', '-24 hours')",
                (sender_id,)
            )
            session_daily_handoffs = cur.fetchone()[0]
            if session_daily_handoffs >= getattr(Config, "MAX_HANDOFFS_PER_SESSION_DAY", 5):
                conn.close()
                return {
                    "status": "rate_limited",
                    "capped": True,
                    "reason": "Handoff daily limit reached",
                    "customer_message": (
                        "You have reached the daily handoff inquiry limit for this session. "
                        "Our specialized team has already received your previous request and will follow up promptly.\n\n"
                        "For immediate assistance, please connect with our Dubai desk directly:\n"
                        f"📍 Office: {Config.KEPLER_ADDRESS}\n"
                        f"📞 Phone: {Config.KEPLER_PHONE}\n"
                        f"💬 WhatsApp: {Config.KEPLER_WHATSAPP}"
                    ),
                    "idempotent": True
                }
            cur.execute("SELECT COUNT(*) FROM handoffs WHERE created_at > datetime('now', '-1 hour')")
            global_hourly_handoffs = cur.fetchone()[0]
            conn.close()
            if global_hourly_handoffs >= getattr(Config, "MAX_HANDOFFS_GLOBAL_HOUR", 100):
                return {
                    "status": "rate_limited",
                    "capped": True,
                    "reason": "Global handoff capacity reached",
                    "customer_message": (
                        "Our specialized sales desk is experiencing high inquiry volume. "
                        f"Please contact us directly at {Config.KEPLER_PHONE} or WhatsApp {Config.KEPLER_WHATSAPP}."
                    ),
                    "idempotent": True
                }
        except Exception:
            pass

    handoff_id = save_handoff(
        reason=reason,
        summary=summary,
        phone=phone,
        sender_id=sender_id,
        status="pending"
    )

    # Deliver alert to sales specialist (WP10)
    try:
        from app.notifications.salesperson import notify_salesperson_of_handoff
        notify_salesperson_of_handoff(
            handoff_id=handoff_id,
            reason=reason,
            summary=summary,
            phone=phone,
            sender_id=sender_id
        )
    except Exception:
        pass

    customer_msg = (
        f"I have routed your inquiry to our specialized sales and technical team at Kepler Tech LLC (Dubai).\n\n"
        f"📍 Office: {Config.KEPLER_ADDRESS}\n"
        f"📞 Phone: {Config.KEPLER_PHONE}\n"
        f"💬 WhatsApp: {Config.KEPLER_WHATSAPP}\n"
        f"🕒 Hours: {Config.KEPLER_HOURS}\n\n"
        f"A dedicated sales specialist from our team will assist you promptly."
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
