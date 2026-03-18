"""Startup configuration validation.

Checks that required environment variables are present and that
optional integrations have their dependencies configured.  Logs
warnings but never crashes the app — a missing optional key should
not prevent the application from starting.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def validate_config(app) -> list[str]:
    """Validate application configuration and return a list of warnings.

    Called once during ``create_app()``.  Warnings are logged at
    WARNING level; critical issues at ERROR level.  The application
    is never stopped — all checks are advisory.
    """
    warnings: list[str] = []
    cfg = app.config

    # --- Required keys --------------------------------------------------------
    if not cfg.get("SQLALCHEMY_DATABASE_URI"):
        msg = "DATABASE_URL is not set — the application will not be able to connect to the database."
        logger.error(msg)
        warnings.append(msg)

    secret = cfg.get("SECRET_KEY", "")
    if not secret or secret == "dev-secret":
        msg = "SECRET_KEY is using the default value — set a strong random key for production."
        logger.warning(msg)
        warnings.append(msg)

    # --- Email / SMTP ---------------------------------------------------------
    mail_enabled = cfg.get("MAIL_ENABLED", False)
    mail_transport = cfg.get("MAIL_TRANSPORT", "log")

    if mail_enabled or mail_transport == "smtp":
        smtp_host = cfg.get("MAIL_SERVER") or cfg.get("MAIL_SMTP_HOST")
        smtp_user = cfg.get("MAIL_USERNAME") or cfg.get("MAIL_SMTP_USERNAME")
        smtp_pass = cfg.get("MAIL_PASSWORD") or cfg.get("MAIL_SMTP_PASSWORD")
        sender = cfg.get("MAIL_DEFAULT_SENDER") or cfg.get("MAIL_DEFAULT_SENDER_EMAIL")

        if not smtp_host or smtp_host == "localhost":
            msg = "MAIL_ENABLED is true but MAIL_SERVER is not configured."
            logger.warning(msg)
            warnings.append(msg)

        if not smtp_user:
            msg = "MAIL_ENABLED is true but MAIL_USERNAME is empty."
            logger.warning(msg)
            warnings.append(msg)

        if not smtp_pass:
            msg = "MAIL_ENABLED is true but MAIL_PASSWORD is empty."
            logger.warning(msg)
            warnings.append(msg)

        if not sender:
            msg = "MAIL_ENABLED is true but MAIL_DEFAULT_SENDER is empty."
            logger.warning(msg)
            warnings.append(msg)

    # --- IMEICheck API --------------------------------------------------------
    imei_enabled = cfg.get("IMEICHECK_ENABLED", False)
    imei_key = cfg.get("IMEICHECK_API_KEY", "")

    if imei_enabled and not imei_key:
        msg = "IMEICHECK_ENABLED is true but IMEICHECK_API_KEY is not set — IMEI lookups will fail."
        logger.warning(msg)
        warnings.append(msg)

    if imei_enabled and imei_key:
        service_id = cfg.get("IMEICHECK_SERVICE_ID", 12)
        logger.info(
            "IMEIcheck.net configured: url=%s service_id=%s",
            cfg.get("IMEICHECK_API_URL", "https://api.imeicheck.net"),
            service_id,
        )

    # Also warn if an API key is set but enabled flag is off (likely oversight)
    if imei_key and not imei_enabled:
        msg = "IMEICHECK_API_KEY is set but IMEICHECK_ENABLED is false — set IMEICHECK_ENABLED=true to activate."
        logger.info(msg)

    # --- Summary --------------------------------------------------------------
    if warnings:
        logger.warning("Configuration check completed with %d warning(s).", len(warnings))
    else:
        logger.info("Configuration check passed — all settings OK.")

    return warnings
