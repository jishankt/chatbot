import re

def mask_phone_number(phone: str) -> str:
    """
    Masks phone numbers in logs to protect personal privacy (e.g., '+971 50 *** 1641').
    Leaves country code and last 4 digits visible.
    """
    if not phone or len(phone) < 7:
        return "***"
    digits = re.sub(r"[^\d+]", "", phone)
    if len(digits) <= 6:
        return digits[:2] + "***" + digits[-2:]
    return digits[:6] + " *** " + digits[-4:]


mask_phone = mask_phone_number
