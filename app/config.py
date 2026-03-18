import os


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "postgresql+psycopg2://ironcore:ironcore@localhost:5432/ironcore"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    BABEL_DEFAULT_LOCALE = os.getenv("BABEL_DEFAULT_LOCALE", "en")
    BABEL_DEFAULT_TIMEZONE = os.getenv("BABEL_DEFAULT_TIMEZONE", "UTC")
    SUPPORTED_LOCALES = [x.strip() for x in os.getenv("SUPPORTED_LOCALES", "en,es").split(",") if x.strip()]

    DEFAULT_BRANCH_CODE = os.getenv("DEFAULT_BRANCH_CODE", "HQ")
    UPLOAD_ROOT = os.getenv("UPLOAD_ROOT", "uploads")
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", str(10 * 1024 * 1024)))

    DEFAULT_INTAKE_DISCLAIMER_TEXT = os.getenv(
        "DEFAULT_INTAKE_DISCLAIMER_TEXT",
        "I confirm the provided details are accurate and accept the intake terms.",
    )

    DEFAULT_TICKET_SLA_DAYS = int(os.getenv("DEFAULT_TICKET_SLA_DAYS", "5"))
    DEFAULT_IGIC_RATE = float(os.getenv("DEFAULT_IGIC_RATE", "0.07"))

    # Email transport configuration
    MAIL_TRANSPORT = os.getenv("MAIL_TRANSPORT", "log")  # "log" or "smtp"
    MAIL_SMTP_HOST = os.getenv("MAIL_SMTP_HOST", "localhost")
    MAIL_SMTP_PORT = int(os.getenv("MAIL_SMTP_PORT", "587"))
    MAIL_SMTP_USERNAME = os.getenv("MAIL_SMTP_USERNAME", "")
    MAIL_SMTP_PASSWORD = os.getenv("MAIL_SMTP_PASSWORD", "")
    MAIL_SMTP_USE_TLS = os.getenv("MAIL_SMTP_USE_TLS", "true").lower() in ("true", "1", "yes")
    MAIL_SMTP_USE_SSL = os.getenv("MAIL_SMTP_USE_SSL", "false").lower() in ("true", "1", "yes")
    MAIL_SMTP_TIMEOUT = int(os.getenv("MAIL_SMTP_TIMEOUT", "10"))
    MAIL_DEFAULT_SENDER_EMAIL = os.getenv("MAIL_DEFAULT_SENDER_EMAIL", "")
    MAIL_DEFAULT_SENDER_NAME = os.getenv("MAIL_DEFAULT_SENDER_NAME", "")
    MAIL_DEFAULT_REPLY_TO = os.getenv("MAIL_DEFAULT_REPLY_TO", "")

    # IMEIcheck.net integration (optional)
    IMEICHECK_API_KEY = os.getenv("IMEICHECK_API_KEY", "")
    IMEICHECK_API_URL = os.getenv("IMEICHECK_API_URL", "https://api.imeicheck.net")
    IMEICHECK_TIMEOUT = int(os.getenv("IMEICHECK_TIMEOUT", "10"))
