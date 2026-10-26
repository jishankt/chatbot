import time
import logging
import requests
from typing import Dict, Any, Optional
from app.config import Config
from app.utils.phone import mask_phone_number

logger = logging.getLogger(__name__)

GRAPH_API_VERSION = "v19.0"


def send_whatsapp_message(
    to: str,
    text: str,
    phone_number_id: Optional[str] = None,
    api_token: Optional[str] = None,
    max_retries: int = 3,
    backoff_factor: float = 0.5
) -> Dict[str, Any]:
    """
    Sends an outbound WhatsApp text message via Meta Graph API with exponential backoff.
    """
    token = api_token or Config.WHATSAPP_API_TOKEN
    number_id = phone_number_id or Config.WHATSAPP_PHONE_NUMBER_ID
    masked_to = mask_phone_number(to)

    if not token or not number_id:
        logger.info(f"[OUTBOUND MOCK] WhatsApp message to {masked_to} (credentials unconfigured): {text[:60]}...")
        return {
            "status": "mock_sent",
            "to": masked_to,
            "message_snippet": text[:100],
            "note": "Meta Graph API token or phone number ID not configured; mocked successfully."
        }

    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{number_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"preview_url": False, "body": text}
    }

    last_error = None
    for attempt in range(max_retries):
        try:
            logger.info(f"Attempt {attempt + 1}/{max_retries}: sending outbound WhatsApp to {masked_to}")
            resp = requests.post(url, headers=headers, json=payload, timeout=10)
            if resp.status_code in (200, 201):
                res_json = resp.json()
                logger.info(f"Successfully sent WhatsApp message to {masked_to}")
                return {
                    "status": "sent",
                    "to": masked_to,
                    "meta_response": res_json
                }
            else:
                last_error = f"HTTP {resp.status_code}: {resp.text}"
                logger.warning(f"Meta Graph API error (attempt {attempt + 1}): {last_error}")
        except Exception as e:
            last_error = str(e)
            logger.warning(f"Network error sending WhatsApp to {masked_to} (attempt {attempt + 1}): {e}")

        if attempt < max_retries - 1:
            sleep_duration = backoff_factor * (2 ** attempt)
            time.sleep(sleep_duration)

    logger.error(f"Failed to send outbound WhatsApp message to {masked_to} after {max_retries} attempts. Error: {last_error}")
    return {
        "status": "failed",
        "to": masked_to,
        "error": last_error
    }
