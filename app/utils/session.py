from typing import Optional
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from app.config import Config


def _get_serializer() -> URLSafeTimedSerializer:
    secret = Config.SECRET_KEY or Config.ADMIN_API_KEY or "cx02-sales-secret-key-default"
    return URLSafeTimedSerializer(secret, salt="web-session-cookie")


def sign_session_id(session_id: str) -> str:
    """Signs a session ID using itsdangerous."""
    s = _get_serializer()
    return s.dumps(session_id)


def verify_session_id(signed_cookie: Optional[str], max_age: int = 86400 * 30) -> Optional[str]:
    """
    Verifies and extracts session_id from a signed cookie.
    Returns None if signature is invalid, expired, or missing.
    """
    if not signed_cookie:
        return None
    s = _get_serializer()
    try:
        return s.loads(signed_cookie, max_age=max_age)
    except (BadSignature, SignatureExpired, Exception):
        return None
