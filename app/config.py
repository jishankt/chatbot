import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Config:
    PORT = int(os.getenv("PORT", "5000"))
    DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1")
    SECRET_KEY = os.getenv("SECRET_KEY", "cx02-sales-secret-key-default")
    AUDIT_HMAC_KEY = os.getenv("AUDIT_HMAC_KEY", "cx02-sales-audit-hmac-default")

    # Security & Size Bounds
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", str(64 * 1024)))  # 64 KB limit

    # Storage paths
    DATABASE_PATH = Path(os.getenv("DATABASE_PATH", str(BASE_DIR / "data" / "sales_ai.db")))
    AUDIT_LOG_PATH = BASE_DIR / "data" / "audit.jsonl"
    PRODUCTS_PATH = BASE_DIR / "data" / "products.json"
    POLICIES_PATH = BASE_DIR / "data" / "policies.json"
    KB_DIR = BASE_DIR / "data" / "kb"

    # Pricing & Freshness Rules
    PRICE_MAX_AGE_DAYS = int(os.getenv("PRICE_MAX_AGE_DAYS", "14"))

    # VAT Treatment: Default to None (Unknown) unless explicitly set in config
    _vat_env = os.getenv("VAT_RATE", "").strip()
    VAT_RATE = float(_vat_env) if _vat_env else None

    _inc_vat_env = os.getenv("PRICES_INCLUDE_VAT", "").strip().lower()
    PRICES_INCLUDE_VAT = (_inc_vat_env in ("true", "1")) if _inc_vat_env else None

    # LLM & OpenRouter / Ollama Configuration
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openrouter" if os.getenv("OPENROUTER_API_KEY") else "ollama").lower()
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
    OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct")

    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    OLLAMA_CHAT_MODEL = os.getenv("OLLAMA_CHAT_MODEL", "qwen2.5:32b")
    OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
    FORCE_EXTRACTIVE_MODE = os.getenv("FORCE_EXTRACTIVE_MODE", "false").lower() in ("true", "1")
    MAX_CONCURRENT_GENERATIONS = int(os.getenv("MAX_CONCURRENT_GENERATIONS", "2"))
    QUEUE_WAIT_BUDGET_SECONDS = float(os.getenv("QUEUE_WAIT_BUDGET_SECONDS", "6.0"))

    # Environment & Auth
    ENV = os.getenv("APP_ENV", os.getenv("ENV", "development")).lower()
    ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "kepler_admin_secret_key_2026")
    PII_ENCRYPTION_KEY = os.getenv("PII_ENCRYPTION_KEY", "kepler_pii_aes_gcm_secret_key_2026")
    PII_ENCRYPTION_KEYS = {
        "v1": os.getenv("PII_ENCRYPTION_KEY_V1", os.getenv("PII_ENCRYPTION_KEY", "kepler_pii_aes_gcm_secret_key_2026")),
        "v2": os.getenv("PII_ENCRYPTION_KEY_V2", "")
    }
    PII_ACTIVE_KEY_VERSION = os.getenv("PII_ACTIVE_KEY_VERSION", "v1")
    DATA_RETENTION_DAYS = int(os.getenv("DATA_RETENTION_DAYS", "90"))

    # WhatsApp Cloud API Webhook & Outbound
    WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
    WHATSAPP_API_TOKEN = os.getenv("WHATSAPP_API_TOKEN", os.getenv("WHATSAPP_TOKEN", ""))
    WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "cx02_sales_verify_token")
    WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "")
    WHATSAPP_DEV_OVERRIDE = os.getenv("WHATSAPP_DEV_OVERRIDE", "false").lower() in ("true", "1")
    WHATSAPP_GRAPH_API_VERSION = os.getenv("WHATSAPP_GRAPH_API_VERSION", "v21.0")

    # Kepler Tech LLC Contact Info
    KEPLER_PHONE = os.getenv("KEPLER_PHONE", "00971 4 323 1008")
    KEPLER_WHATSAPP = os.getenv("KEPLER_WHATSAPP", "+971 50 890 1641")
    KEPLER_EMAIL = os.getenv("KEPLER_EMAIL", "sales@keplertechllc.com")
    KEPLER_ADDRESS = os.getenv("KEPLER_ADDRESS", "D79 Khalid Bin Waleed Road, Dubai")
    KEPLER_HOURS = "Mon-Fri 8:30-17:30, Sat 8:30-13:00"

    # Salesperson notification target
    SALESPERSON_PHONE = os.getenv("SALESPERSON_PHONE", "+971508901641")
    SALESPERSON_EMAIL = os.getenv("SALESPERSON_EMAIL", "sales@keplertechllc.com")
    MAX_HANDOFF_RETRY_ATTEMPTS = int(os.getenv("MAX_HANDOFF_RETRY_ATTEMPTS", "3"))

    # SMTP Email Configuration for Handoff Alerts
    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() in ("true", "1")
    SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", "sales-ai@keplertechllc.com")

    # Rate Limiting & Input Validation Bounds
    MAX_MESSAGE_LENGTH = int(os.getenv("MAX_MESSAGE_LENGTH", "1000"))
    MAX_CUSTOMER_NAME_LENGTH = 100
    MAX_QUOTES_PER_SESSION_HOUR = int(os.getenv("MAX_QUOTES_PER_SESSION_HOUR", "15"))
    MAX_HANDOFFS_PER_SESSION_HOUR = int(os.getenv("MAX_HANDOFFS_PER_SESSION_HOUR", "10"))
    MAX_HANDOFFS_PER_SESSION_DAY = int(os.getenv("MAX_HANDOFFS_PER_SESSION_DAY", "5"))
    MAX_QUOTES_GLOBAL_HOUR = int(os.getenv("MAX_QUOTES_GLOBAL_HOUR", "500"))
    MAX_HANDOFFS_GLOBAL_HOUR = int(os.getenv("MAX_HANDOFFS_GLOBAL_HOUR", "100"))

    # Prompt / Engine Version
    PROMPT_VERSION = "2.0.0"


REQUIRED_IN_PROD = [
    "ADMIN_API_KEY",
    "PII_ENCRYPTION_KEY",
    "SECRET_KEY"
]

KNOWN_INSECURE_DEFAULTS = {
    "kepler_admin_secret_key_2026",
    "kepler_pii_aes_gcm_secret_key_2026",
    "cx02-sales-secret-key-default"
}


def validate_config():
    """
    Validates configuration settings, enforcing fail-closed security in production.
    Raises ValueError if mock mode is active, or if critical secrets are missing / left as known defaults.
    """
    env = os.getenv("APP_ENV", os.getenv("ENV", Config.ENV)).lower()
    whatsapp_dev_override = os.getenv("WHATSAPP_DEV_OVERRIDE", str(Config.WHATSAPP_DEV_OVERRIDE)).lower() in ("true", "1")

    if env == "production":
        if whatsapp_dev_override:
            raise ValueError("Mock mode (WHATSAPP_DEV_OVERRIDE) is strictly forbidden in production!")

        missing = [k for k in REQUIRED_IN_PROD if not os.getenv(k, getattr(Config, k, None))]
        insecure = [k for k in REQUIRED_IN_PROD if os.getenv(k, getattr(Config, k, None)) in KNOWN_INSECURE_DEFAULTS]
        if missing or insecure:
            raise RuntimeError(
                f"FATAL: Production configuration validation failed!\n"
                f"Missing variables: {missing}\n"
                f"Known insecure default secrets detected in production: {insecure}"
            )

