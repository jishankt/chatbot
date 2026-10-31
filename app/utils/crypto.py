import os
import base64
import hashlib
import logging
from typing import Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from app.config import Config

logger = logging.getLogger(__name__)

_KEY_CACHE: Optional[bytes] = None


def get_encryption_key() -> bytes:
    """
    Derives a 256-bit AES key from configured PII_ENCRYPTION_KEY or SECRET_KEY.
    """
    global _KEY_CACHE
    raw_key = getattr(Config, "PII_ENCRYPTION_KEY", "") or getattr(Config, "SECRET_KEY", "kepler_pii_default_secret")
    return hashlib.sha256(raw_key.encode("utf-8")).digest()


def encrypt_field(plaintext: Optional[str]) -> Optional[str]:
    """
    Encrypts a string field using AES-256-GCM.
    Returns serialized envelope: enc:v1:<nonce_b64>:<ciphertext_b64>
    Preserves None and empty strings.
    """
    if plaintext is None:
        return None
    if not isinstance(plaintext, str):
        plaintext = str(plaintext)
    if not plaintext:
        return ""
    if plaintext.startswith("enc:v1:"):
        return plaintext  # Already encrypted

    try:
        key = get_encryption_key()
        aesgcm = AESGCM(key)
        nonce = os.urandom(12)  # 96-bit nonce standard for GCM
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        nonce_b64 = base64.b64encode(nonce).decode("utf-8")
        ct_b64 = base64.b64encode(ciphertext).decode("utf-8")
        return f"enc:v1:{nonce_b64}:{ct_b64}"
    except Exception as e:
        logger.error(f"Field encryption failed: {e}")
        return plaintext


def decrypt_field(ciphertext: Optional[str]) -> Optional[str]:
    """
    Decrypts an AES-256-GCM envelope string.
    Gracefully handles unencrypted legacy fields or None.
    """
    if ciphertext is None:
        return None
    if not isinstance(ciphertext, str):
        return ciphertext
    if not ciphertext.startswith("enc:v1:"):
        return ciphertext  # Plaintext or legacy format

    parts = ciphertext.split(":", 3)
    if len(parts) != 4:
        return ciphertext

    _, version, nonce_b64, ct_b64 = parts
    try:
        nonce = base64.b64decode(nonce_b64)
        ct = base64.b64decode(ct_b64)
        key = get_encryption_key()
        aesgcm = AESGCM(key)
        plaintext_bytes = aesgcm.decrypt(nonce, ct, None)
        return plaintext_bytes.decode("utf-8")
    except Exception as e:
        logger.warning(f"Field decryption failed or invalid key: {e}")
        return ciphertext
