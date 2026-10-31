import re
import ssl
import smtplib
import logging
from email.message import EmailMessage
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from app.config import Config
from app.storage.handoffs import update_handoff_notification
from app.utils.phone import mask_phone_number

logger = logging.getLogger(__name__)


def _send_smtp_email(
    subject: str,
    body: str,
    to_email: str
) -> Dict[str, Any]:
    """
    Dispatches a TLS-encrypted plain-text email with sanitized headers and verified TLS context.
    """
    if not Config.SMTP_HOST or not to_email:
        return {"status": "skipped_unconfigured", "note": "SMTP host or recipient not configured"}

    # Header sanitization to prevent CRLF injection
    clean_subject = re.sub(r"[\r\n]+", " ", subject).strip()
    clean_to = re.sub(r"[\r\n]+", "", to_email).strip()
    clean_from = re.sub(r"[\r\n]+", "", Config.SMTP_FROM_EMAIL).strip()

    msg = EmailMessage()
    msg["Subject"] = clean_subject
    msg["From"] = clean_from
    msg["To"] = clean_to
    msg.set_content(body)

    try:
        smtp_port = Config.SMTP_PORT or 587
        server = smtplib.SMTP(Config.SMTP_HOST, smtp_port, timeout=10)
        try:
            if getattr(Config, "SMTP_USE_TLS", True):
                tls_context = ssl.create_default_context()
                try:
                    server.starttls(context=tls_context)
                except TypeError:
                    server.starttls()
            if Config.SMTP_USER and Config.SMTP_PASSWORD:
                server.login(Config.SMTP_USER, Config.SMTP_PASSWORD)
            server.send_message(msg)
            return {"status": "sent"}
        finally:
            try:
                server.quit()
            except Exception:
                pass
    except Exception as e:
        logger.error(f"SMTP dispatch error: {e}")
        return {"status": "failed", "error": str(e)}


def notify_salesperson_of_handoff(
    handoff_id: int,
    reason: str,
    summary: Optional[str] = None,
    phone: Optional[str] = None,
    sender_id: Optional[str] = None,
    priority: str = "medium"
) -> Dict[str, Any]:
    """
    Delivers an immediate handoff alert to the Kepler Tech sales desk.
    Primary channel: SMTP Email (TLS, sanitized headers, plain-text body, truncated user text).
    Secondary channel: WhatsApp (if configured).
    Records per-channel status and alerts if no channel succeeded.
    """
    masked_customer = mask_phone_number(phone or sender_id or "unknown")
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Header sanitization
    clean_reason = re.sub(r"[\r\n]+", " ", reason).strip()
    # Truncate user-controlled summary to prevent log/email amplification
    clean_summary = (summary or "Customer requested specialist assistance")[:500]

    email_subject = f"🔔 SALES HANDOFF ALERT (#{handoff_id}) - Priority: {priority.upper()}"
    email_body = (
        f"NEW SALES HANDOFF ALERT - Kepler Tech Sales AI\n"
        f"--------------------------------------------------\n"
        f"Priority: {priority.upper()}\n"
        f"Handoff ID: #{handoff_id}\n"
        f"Customer Identifier: {phone or sender_id or 'Unknown'}\n"
        f"Reason: {clean_reason}\n"
        f"Context Summary (Truncated): {clean_summary}\n"
        f"Timestamp: {timestamp}\n"
        f"--------------------------------------------------\n"
        f"Action: Review client inquiry and respond via corporate console.\n"
    )

    channel_results = {}

    # 1. Primary Channel: SMTP Email
    email_res = _send_smtp_email(
        subject=email_subject,
        body=email_body,
        to_email=Config.SALESPERSON_EMAIL
    )
    channel_results["email"] = email_res.get("status", "unknown")

    # 2. Secondary Channel: WhatsApp (if configured)
    whatsapp_res = {"status": "skipped_unconfigured"}
    if Config.WHATSAPP_API_TOKEN and Config.WHATSAPP_PHONE_NUMBER_ID:
        try:
            from app.whatsapp.client import send_whatsapp_message
            whatsapp_res = send_whatsapp_message(
                to=Config.SALESPERSON_PHONE,
                text=email_body
            )
        except Exception as we:
            whatsapp_res = {"status": "failed", "error": str(we)}
    channel_results["whatsapp"] = whatsapp_res.get("status", "skipped_unconfigured")

    # Construct combined status string: e.g. "email:sent|whatsapp:skipped_unconfigured"
    status_str = f"email:{channel_results['email']}|whatsapp:{channel_results['whatsapp']}"
    any_success = channel_results["email"] == "sent" or channel_results["whatsapp"] == "sent"

    if any_success:
        update_handoff_notification(handoff_id, status=status_str)
        logger.info(f"Dispatched handoff #{handoff_id} alert ({status_str}) for {masked_customer}")
    else:
        # Alert when handoff has no successful channel!
        error_detail = f"Email: {email_res.get('error', 'unconfigured')}; WhatsApp: {whatsapp_res.get('error', 'unconfigured')}"
        logger.critical(f"CRITICAL: Handoff #{handoff_id} has NO successful notification channel! Customer: {masked_customer}. Error: {error_detail}")
        update_handoff_notification(handoff_id, status=status_str, error=error_detail)

    return {
        "status": "success" if any_success else "no_successful_channel",
        "channels": channel_results,
        "combined_status": status_str
    }


def dispatch_secondary_emergency_alert(handoff_id: int, reason: str, customer: str):
    """
    Dispatches a critical escalation alert to a secondary channel when all primary
    channels have exhausted their max retry attempts.
    """
    clean_cust = mask_phone_number(customer or "unknown")
    logger.critical(
        f"🚨 SECONDARY CHANNEL EMERGENCY ALERT: Handoff #{handoff_id} has PERMANENTLY FAILED "
        f"all notification channels. Customer: {clean_cust}. Reason: {reason}"
    )
    secondary_recipient = getattr(Config, "EMERGENCY_ESCALATION_EMAIL", "ops-emergency@keplertechllc.com")
    try:
        _send_smtp_email(
            subject=f"🚨 EMERGENCY: Permanent Notification Failure for Handoff #{handoff_id}",
            body=(
                f"ATTENTION: Sales Lead Notification Failure\n"
                f"Handoff ID: #{handoff_id}\n"
                f"Customer: {clean_cust}\n"
                f"Reason: {reason}\n"
                f"Status: PERMANENT FAILURE (Exhausted max retries)\n"
                f"Immediate manual review required on corporate desk.\n"
            ),
            to_email=secondary_recipient
        )
    except Exception as e:
        logger.error(f"Failed to deliver secondary emergency alert: {e}")


def retry_failed_handoffs_sweep(limit: int = 50) -> Dict[str, Any]:
    """
    Sweeps for handoffs with no successful channel or failed status and retries alert dispatch.
    Limits retries to MAX_HANDOFF_RETRY_ATTEMPTS (default 3).
    When max attempts are reached, marks status as 'permanent_failure' and emits a critical alert.
    """
    from app.storage.db import get_db_connection
    conn = get_db_connection()
    retried = 0
    succeeded = 0
    permanent_failures = 0
    max_attempts = getattr(Config, "MAX_HANDOFF_RETRY_ATTEMPTS", 3)

    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, reason, summary, phone, sender_id, COALESCE(retry_count, 0) as retry_count, status
            FROM handoffs
            WHERE status NOT IN ('permanent_failure', 'alert_abandoned', 'resolved', 'sent', 'archived_test')
              AND (
                  notification_status LIKE '%failed%'
                  OR notification_status LIKE '%no_successful_channel%'
                  OR status = 'failed_all_channels'
                  OR notification_status = 'pending'
              )
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,)
        )
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    for row in rows:
        hid = row["id"]
        current_retries = row["retry_count"]
        new_retries = current_retries + 1
        retried += 1

        res = notify_salesperson_of_handoff(
            handoff_id=hid,
            reason=row["reason"],
            summary=row["summary"],
            phone=row["phone"],
            sender_id=row["sender_id"]
        )

        update_conn = get_db_connection()
        try:
            ucur = update_conn.cursor()
            if res.get("status") == "success":
                succeeded += 1
                ucur.execute(
                    "UPDATE handoffs SET retry_count = ?, status = 'sent' WHERE id = ?",
                    (new_retries, hid)
                )
            else:
                if new_retries >= max_attempts:
                    permanent_failures += 1
                    ucur.execute(
                        """
                        UPDATE handoffs 
                        SET retry_count = ?, status = 'permanent_failure', notification_status = 'failed_max_attempts'
                        WHERE id = ?
                        """,
                        (new_retries, hid)
                    )
                    logger.critical(
                        f"CRITICAL FINAL ALERT: Handoff #{hid} reached max retries ({new_retries}/{max_attempts}). "
                        f"Marked as permanent_failure. Customer: {mask_phone_number(row.get('phone') or row.get('sender_id') or 'unknown')}"
                    )
                    # Dispatch to secondary escalation channel
                    dispatch_secondary_emergency_alert(
                        handoff_id=hid,
                        reason=row["reason"],
                        customer=row.get("phone") or row.get("sender_id") or "unknown"
                    )
                else:
                    ucur.execute(
                        "UPDATE handoffs SET retry_count = ? WHERE id = ?",
                        (new_retries, hid)
                    )
            update_conn.commit()
        finally:
            update_conn.close()

    return {
        "swept_count": retried,
        "retried": retried,
        "succeeded": succeeded,
        "permanent_failures": permanent_failures
    }
