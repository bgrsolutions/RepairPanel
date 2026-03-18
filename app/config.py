import os


def _bool(key: str, default: str = "false") -> bool:
    """Parse an environment variable as a boolean."""
    return os.getenv(key, default).lower() in ("true", "1", "yes")


class Config:
    # --- Core -----------------------------------------------------------------
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "postgresql+psycopg2://ironcore:ironcore@localhost:5432/ironcore"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- Locale & Timezone ----------------------------------------------------
    BABEL_DEFAULT_LOCALE = os.getenv("BABEL_DEFAULT_LOCALE", "en")
    BABEL_DEFAULT_TIMEZONE = os.getenv("BABEL_DEFAULT_TIMEZONE", "UTC")
    SUPPORTED_LOCALES = [x.strip() for x in os.getenv("SUPPORTED_LOCALES", "en,es").split(",") if x.strip()]
    DEFAULT_LOCALE = os.getenv("DEFAULT_LOCALE", os.getenv("BABEL_DEFAULT_LOCALE", "en"))
    TIMEZONE = os.getenv("TIMEZONE", os.getenv("BABEL_DEFAULT_TIMEZONE", "UTC"))

    # --- Branch / Upload ------------------------------------------------------
    DEFAULT_BRANCH_CODE = os.getenv("DEFAULT_BRANCH_CODE", "HQ")
    UPLOAD_ROOT = os.getenv("UPLOAD_ROOT", "uploads")
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", str(10 * 1024 * 1024)))

    # --- Intake ---------------------------------------------------------------
    DEFAULT_INTAKE_DISCLAIMER_TEXT = os.getenv(
        "DEFAULT_INTAKE_DISCLAIMER_TEXT",
        "I confirm the provided details are accurate and accept the intake terms.",
    )

    # --- SLA & Tax ------------------------------------------------------------
    DEFAULT_TICKET_SLA_DAYS = int(os.getenv("DEFAULT_TICKET_SLA_DAYS", "5"))
    DEFAULT_IGIC_RATE = float(os.getenv("DEFAULT_IGIC_RATE", "0.07"))

    # --- Email (SMTP) ---------------------------------------------------------
    MAIL_TRANSPORT = os.getenv("MAIL_TRANSPORT", "log")  # "log" or "smtp"
    MAIL_ENABLED = _bool("MAIL_ENABLED", "false")
    MAIL_SERVER = os.getenv("MAIL_SERVER", os.getenv("MAIL_SMTP_HOST", "localhost"))
    MAIL_PORT = int(os.getenv("MAIL_PORT", os.getenv("MAIL_SMTP_PORT", "587")))
    MAIL_USE_TLS = _bool("MAIL_USE_TLS", os.getenv("MAIL_SMTP_USE_TLS", "true"))
    MAIL_USE_SSL = _bool("MAIL_USE_SSL", os.getenv("MAIL_SMTP_USE_SSL", "false"))
    MAIL_USERNAME = os.getenv("MAIL_USERNAME", os.getenv("MAIL_SMTP_USERNAME", ""))
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", os.getenv("MAIL_SMTP_PASSWORD", ""))
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", os.getenv("MAIL_DEFAULT_SENDER_EMAIL", ""))
    MAIL_DEFAULT_SENDER_NAME = os.getenv("MAIL_DEFAULT_SENDER_NAME", "")
    MAIL_DEFAULT_REPLY_TO = os.getenv("MAIL_DEFAULT_REPLY_TO", "")
    MAIL_SMTP_TIMEOUT = int(os.getenv("MAIL_SMTP_TIMEOUT", "10"))

    # Backwards-compat aliases (used by branded_email_service)
    MAIL_SMTP_HOST = os.getenv("MAIL_SMTP_HOST", os.getenv("MAIL_SERVER", "localhost"))
    MAIL_SMTP_PORT = int(os.getenv("MAIL_SMTP_PORT", os.getenv("MAIL_PORT", "587")))
    MAIL_SMTP_USERNAME = os.getenv("MAIL_SMTP_USERNAME", os.getenv("MAIL_USERNAME", ""))
    MAIL_SMTP_PASSWORD = os.getenv("MAIL_SMTP_PASSWORD", os.getenv("MAIL_PASSWORD", ""))
    MAIL_SMTP_USE_TLS = _bool("MAIL_SMTP_USE_TLS", os.getenv("MAIL_USE_TLS", "true"))
    MAIL_SMTP_USE_SSL = _bool("MAIL_SMTP_USE_SSL", os.getenv("MAIL_USE_SSL", "false"))
    MAIL_DEFAULT_SENDER_EMAIL = os.getenv("MAIL_DEFAULT_SENDER_EMAIL", os.getenv("MAIL_DEFAULT_SENDER", ""))

    # --- IMEICheck API --------------------------------------------------------
    IMEICHECK_ENABLED = _bool("IMEICHECK_ENABLED", "false")
    IMEICHECK_API_KEY = os.getenv("IMEICHECK_API_KEY", "")
    IMEICHECK_API_URL = os.getenv("IMEICHECK_API_URL", "https://api.imeicheck.net")
    IMEICHECK_BASE_URL = os.getenv("IMEICHECK_BASE_URL", "https://imeicheck.net/api")
    IMEICHECK_SERVICE_ID = int(os.getenv("IMEICHECK_SERVICE_ID", "12"))
    IMEICHECK_TIMEOUT = int(os.getenv("IMEICHECK_TIMEOUT", "10"))

    # Brand-aware service mapping (JSON): {"apple": 12, "samsung": 3, ...}
    # If a brand matches a key, that service ID is used instead of the default.
    # Keys are matched case-insensitively. Use "*" or "default" for fallback.
    @staticmethod
    def _parse_service_map():
        raw = os.getenv("IMEICHECK_SERVICE_MAP", "")
        if not raw:
            return {}
        try:
            import json
            return {k.lower(): int(v) for k, v in json.loads(raw).items()}
        except Exception:
            return {}

    IMEICHECK_SERVICE_MAP = _parse_service_map()

    # --- Device Security ------------------------------------------------------
    DEVICE_UNLOCK_KEY = os.getenv("DEVICE_UNLOCK_KEY", "")

    # --- Optional / Future (Redis + Celery) -----------------------------------
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", os.getenv("REDIS_URL", "redis://localhost:6379/0"))
