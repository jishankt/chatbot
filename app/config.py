import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Config:
    PORT = int(os.getenv("PORT", "5000"))
    DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1")
    SECRET_KEY = os.getenv("SECRET_KEY", "cx02-sales-secret-key-default")

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

    # LLM & Ollama Configuration (Default qwen2.5:7b, nomic-embed-text)
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    OLLAMA_CHAT_MODEL = os.getenv("OLLAMA_CHAT_MODEL", "qwen2.5:7b")
    OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
    FORCE_EXTRACTIVE_MODE = os.getenv("FORCE_EXTRACTIVE_MODE", "false").lower() in ("true", "1")

    # Environment & Auth
    ENV = os.getenv("ENV", "development").lower()
    ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "kepler_admin_secret_key_2026")
    DATA_RETENTION_DAYS = int(os.getenv("DATA_RETENTION_DAYS", "90"))

    # WhatsApp Cloud API Webhook & Outbound
    WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
    WHATSAPP_API_TOKEN = os.getenv("WHATSAPP_API_TOKEN", os.getenv("WHATSAPP_TOKEN", ""))
    WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "cx02_sales_verify_token")
    WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "")
    WHATSAPP_DEV_OVERRIDE = os.getenv("WHATSAPP_DEV_OVERRIDE", "false").lower() in ("true", "1")

    # Kepler Tech LLC Contact Info
    KEPLER_PHONE = os.getenv("KEPLER_PHONE", "00971 4 323 1008")
    KEPLER_WHATSAPP = os.getenv("KEPLER_WHATSAPP", "+971 50 890 1641")
    KEPLER_ADDRESS = os.getenv("KEPLER_ADDRESS", "D79 Khalid Bin Waleed Road, Dubai")
    KEPLER_HOURS = "Mon-Fri 8:30-17:30, Sat 8:30-13:00"
