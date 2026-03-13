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
