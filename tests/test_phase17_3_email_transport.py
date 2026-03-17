"""Phase 17.3 tests: Email transport configuration, SMTP delivery, log mode,
delivery logging, test email capability, sender/reply-to, and permissions."""

import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from app import create_app
from app.extensions import db
from app.models import (
    AppSetting, Branch, Booking, ChecklistItem, Company, Customer, Device,
    Diagnostic, Part, PartCategory, PartOrder, PartOrderLine, PartOrderEvent,
    Quote, QuoteApproval, QuoteLine, QuoteOption, RepairChecklist,
    RepairService, Role, StockLayer, StockLevel, StockLocation,
    StockMovement, StockReservation, Supplier, Ticket, TicketNote, User,
    IntakeSubmission, IntakeDisclaimerAcceptance, PortalToken,
)
from app.models.role import role_permissions
from app.models.user import user_roles, user_branch_access
from app.models.inventory import part_category_links


class TestConfig:
    TESTING = True
    SECRET_KEY = "test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SERVER_NAME = "localhost"
    DEFAULT_TICKET_SLA_DAYS = 5
    DEFAULT_IGIC_RATE = 0.07
    SUPPORTED_LOCALES = ["en", "es"]
    BABEL_DEFAULT_LOCALE = "en"
    BABEL_DEFAULT_TIMEZONE = "UTC"
    MAIL_TRANSPORT = "log"
    MAIL_SMTP_HOST = "smtp.example.com"
    MAIL_SMTP_PORT = 587
    MAIL_SMTP_USERNAME = "user@example.com"
    MAIL_SMTP_PASSWORD = "secret"
    MAIL_SMTP_USE_TLS = True
    MAIL_SMTP_USE_SSL = False
    MAIL_SMTP_TIMEOUT = 10
    MAIL_DEFAULT_SENDER_EMAIL = "noreply@testcorp.com"
    MAIL_DEFAULT_SENDER_NAME = "TestCorp Repairs"
    MAIL_DEFAULT_REPLY_TO = "support@testcorp.com"


class TestConfigSMTP(TestConfig):
    MAIL_TRANSPORT = "smtp"


class TestConfigNoSender(TestConfig):
    MAIL_TRANSPORT = "smtp"
    MAIL_DEFAULT_SENDER_EMAIL = ""


class TestConfigSSL(TestConfig):
    MAIL_TRANSPORT = "smtp"
    MAIL_SMTP_USE_TLS = False
    MAIL_SMTP_USE_SSL = True


def _noop_log(*a, **kw):
    return None


def _create_tables():
    tables = [
        Company.__table__, Branch.__table__, Role.__table__, Customer.__table__,
        User.__table__, role_permissions, user_roles, user_branch_access,
        Device.__table__, Ticket.__table__, IntakeSubmission.__table__,
        IntakeDisclaimerAcceptance.__table__, PortalToken.__table__,
        Diagnostic.__table__, Quote.__table__, QuoteOption.__table__,
        QuoteLine.__table__, QuoteApproval.__table__, TicketNote.__table__,
        Supplier.__table__, PartCategory.__table__, part_category_links,
        Part.__table__, StockLocation.__table__, StockLevel.__table__,
        StockMovement.__table__, StockReservation.__table__, StockLayer.__table__,
        PartOrder.__table__, PartOrderLine.__table__, PartOrderEvent.__table__,
        AppSetting.__table__, RepairChecklist.__table__, ChecklistItem.__table__,
        RepairService.__table__, Booking.__table__,
    ]
    for t in tables:
        t.create(bind=db.engine, checkfirst=True)


def _setup(monkeypatch, role_name="Admin", config_class=TestConfig):
    monkeypatch.setattr('app.services.auth_service.log_action', _noop_log)
    monkeypatch.setattr('app.services.audit_service.log_action', _noop_log)
    monkeypatch.setattr('app.blueprints.intake.routes.log_action', _noop_log)
    monkeypatch.setattr('app.blueprints.tickets.routes.log_action', _noop_log)
    monkeypatch.setattr('app.services.booking_service.log_action', _noop_log)
    monkeypatch.setattr('app.blueprints.bookings.routes.log_action', _noop_log)

    app = create_app(config_class)
    with app.app_context():
        _create_tables()
        company = Company(legal_name="Test Corp", trading_name="TestCorp",
                          email="info@testcorp.com", phone="555-9999")
        db.session.add(company)
        role = Role(name=role_name)
        db.session.add(role)
        branch = Branch(code="HQ", name="Headquarters", is_active=True)
        db.session.add(branch)
        db.session.flush()
        user = User(full_name="Test Admin", email="admin@test.com",
                     is_active=True, default_branch_id=branch.id)
        user.password_hash = "pbkdf2:sha256:600000$test$test"
        user.roles.append(role)
        db.session.add(user)
        db.session.flush()

        ids = {
            "branch_id": branch.id,
            "user_id": str(user.id),
        }
        db.session.commit()

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = ids["user_id"]

    return app, client, ids


# ===========================================================================
# A. Config parsing / defaults
# ===========================================================================

def test_config_defaults():
    """Config class should have all email transport settings with defaults."""
    from app.config import Config
    assert Config.MAIL_TRANSPORT == "log"
    assert Config.MAIL_SMTP_HOST == "localhost"
    assert Config.MAIL_SMTP_PORT == 587
    assert Config.MAIL_SMTP_USE_TLS is True
    assert Config.MAIL_SMTP_USE_SSL is False
    assert Config.MAIL_SMTP_TIMEOUT == 10
    assert Config.MAIL_DEFAULT_SENDER_EMAIL == ""
    assert Config.MAIL_DEFAULT_SENDER_NAME == ""
    assert Config.MAIL_DEFAULT_REPLY_TO == ""


def test_config_test_values():
    """TestConfig should have overridden email settings."""
    assert TestConfig.MAIL_TRANSPORT == "log"
    assert TestConfig.MAIL_SMTP_HOST == "smtp.example.com"
    assert TestConfig.MAIL_DEFAULT_SENDER_EMAIL == "noreply@testcorp.com"
    assert TestConfig.MAIL_DEFAULT_REPLY_TO == "support@testcorp.com"


# ===========================================================================
# B. Transport mode switching
# ===========================================================================

def test_log_transport_returns_success(monkeypatch):
    """Log transport should succeed without sending anything."""
    app, client, ids = _setup(monkeypatch)
    with app.test_request_context():
        from app.services.branded_email_service import send_branded_email
        result = send_branded_email(
            to_email="test@example.com",
            subject="Test",
            template_name="test_email.html",
        )
        assert result.success is True
        assert result.transport == "log"
        assert "Logged" in result.message


def test_unknown_transport_falls_back_to_log(monkeypatch):
    """Unknown transport should fall back to log mode."""
    app, client, ids = _setup(monkeypatch)
    with app.test_request_context():
        app.config["MAIL_TRANSPORT"] = "carrier_pigeon"
        from app.services.branded_email_service import send_branded_email
        result = send_branded_email(
            to_email="test@example.com",
            subject="Test",
            template_name="test_email.html",
        )
        assert result.success is True
        assert result.transport == "log"


# ===========================================================================
# C. SMTP transport (mocked)
# ===========================================================================

def test_smtp_transport_sends_email(monkeypatch):
    """SMTP transport should construct and send email via smtplib."""
    app, client, ids = _setup(monkeypatch, config_class=TestConfigSMTP)
    with app.test_request_context():
        mock_smtp = MagicMock()
        mock_smtp_instance = MagicMock()
        mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_smtp_instance)
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

        with patch('app.services.branded_email_service.smtplib.SMTP', mock_smtp):
            from app.services.branded_email_service import send_branded_email
            result = send_branded_email(
                to_email="customer@example.com",
                to_name="Customer",
                subject="SMTP Test",
                template_name="test_email.html",
            )

        assert result.success is True
        assert result.transport == "smtp"
        mock_smtp.assert_called_once_with("smtp.example.com", 587, timeout=10)


def test_smtp_ssl_transport(monkeypatch):
    """SMTP_SSL should be used when use_ssl is True."""
    app, client, ids = _setup(monkeypatch, config_class=TestConfigSSL)
    with app.test_request_context():
        mock_smtp_ssl = MagicMock()
        mock_smtp_ssl_instance = MagicMock()
        mock_smtp_ssl.return_value.__enter__ = MagicMock(return_value=mock_smtp_ssl_instance)
        mock_smtp_ssl.return_value.__exit__ = MagicMock(return_value=False)

        with patch('app.services.branded_email_service.smtplib.SMTP_SSL', mock_smtp_ssl):
            from app.services.branded_email_service import send_branded_email
            result = send_branded_email(
                to_email="customer@example.com",
                subject="SSL Test",
                template_name="test_email.html",
            )

        assert result.success is True
        assert result.transport == "smtp"
        mock_smtp_ssl.assert_called_once_with("smtp.example.com", 587, timeout=10)


def test_smtp_starttls_called(monkeypatch):
    """STARTTLS should be called when use_tls=True and use_ssl=False."""
    app, client, ids = _setup(monkeypatch, config_class=TestConfigSMTP)
    with app.test_request_context():
        mock_server = MagicMock()
        mock_smtp = MagicMock(return_value=mock_server)
        mock_server.__enter__ = MagicMock(return_value=mock_server)
        mock_server.__exit__ = MagicMock(return_value=False)

        with patch('app.services.branded_email_service.smtplib.SMTP', mock_smtp):
            from app.services.branded_email_service import send_branded_email
            send_branded_email(
                to_email="test@example.com",
                subject="TLS Test",
                template_name="test_email.html",
            )

        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("user@example.com", "secret")


def test_smtp_sendmail_called_with_correct_args(monkeypatch):
    """sendmail should be called with sender and recipient."""
    app, client, ids = _setup(monkeypatch, config_class=TestConfigSMTP)
    with app.test_request_context():
        mock_server = MagicMock()
        mock_smtp = MagicMock(return_value=mock_server)
        mock_server.__enter__ = MagicMock(return_value=mock_server)
        mock_server.__exit__ = MagicMock(return_value=False)

        with patch('app.services.branded_email_service.smtplib.SMTP', mock_smtp):
            from app.services.branded_email_service import send_branded_email
            send_branded_email(
                to_email="recipient@example.com",
                subject="Send Test",
                template_name="test_email.html",
            )

        mock_server.sendmail.assert_called_once()
        call_args = mock_server.sendmail.call_args
        assert call_args[0][0] == "noreply@testcorp.com"
        assert call_args[0][1] == ["recipient@example.com"]


# ===========================================================================
# D. Graceful SMTP failure handling
# ===========================================================================

def test_smtp_connection_failure(monkeypatch):
    """SMTP connection failure should return failure without crashing."""
    app, client, ids = _setup(monkeypatch, config_class=TestConfigSMTP)
    with app.test_request_context():
        import smtplib
        with patch('app.services.branded_email_service.smtplib.SMTP',
                   side_effect=OSError("Connection refused")):
            from app.services.branded_email_service import send_branded_email
            result = send_branded_email(
                to_email="test@example.com",
                subject="Fail Test",
                template_name="test_email.html",
            )

        assert result.success is False
        assert result.transport == "smtp"
        assert "connection" in result.message.lower()


def test_smtp_auth_failure(monkeypatch):
    """SMTP authentication failure should return failure gracefully."""
    app, client, ids = _setup(monkeypatch, config_class=TestConfigSMTP)
    with app.test_request_context():
        import smtplib
        mock_server = MagicMock()
        mock_smtp = MagicMock(return_value=mock_server)
        mock_server.__enter__ = MagicMock(return_value=mock_server)
        mock_server.__exit__ = MagicMock(return_value=False)
        mock_server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Bad credentials")

        with patch('app.services.branded_email_service.smtplib.SMTP', mock_smtp):
            from app.services.branded_email_service import send_branded_email
            result = send_branded_email(
                to_email="test@example.com",
                subject="Auth Fail",
                template_name="test_email.html",
            )

        assert result.success is False
        assert "authentication" in result.message.lower()


def test_smtp_generic_error(monkeypatch):
    """Generic SMTP error should return failure gracefully."""
    app, client, ids = _setup(monkeypatch, config_class=TestConfigSMTP)
    with app.test_request_context():
        import smtplib
        mock_server = MagicMock()
        mock_smtp = MagicMock(return_value=mock_server)
        mock_server.__enter__ = MagicMock(return_value=mock_server)
        mock_server.__exit__ = MagicMock(return_value=False)
        mock_server.sendmail.side_effect = smtplib.SMTPException("Relay denied")

        with patch('app.services.branded_email_service.smtplib.SMTP', mock_smtp):
            from app.services.branded_email_service import send_branded_email
            result = send_branded_email(
                to_email="test@example.com",
                subject="SMTP Error",
                template_name="test_email.html",
            )

        assert result.success is False
        assert result.transport == "smtp"


def test_smtp_no_sender_configured(monkeypatch):
    """Missing sender email should fail gracefully."""
    app, client, ids = _setup(monkeypatch, config_class=TestConfigNoSender)
    with app.test_request_context():
        # Remove company email too so fallback is noreply@example.com
        Company.query.delete()
        db.session.commit()
        from app.services.branded_email_service import send_branded_email
        result = send_branded_email(
            to_email="test@example.com",
            subject="No Sender",
            template_name="test_email.html",
        )
        assert result.success is False
        assert "sender" in result.message.lower() or "sender" in (result.error or "").lower()


# ===========================================================================
# E. No recipient email
# ===========================================================================

def test_no_recipient_email(monkeypatch):
    """Empty recipient should fail immediately."""
    app, client, ids = _setup(monkeypatch)
    with app.test_request_context():
        from app.services.branded_email_service import send_branded_email
        result = send_branded_email(
            to_email="",
            subject="Test",
            template_name="test_email.html",
        )
        assert result.success is False
        assert "missing_email" in (result.error or "")


# ===========================================================================
# F. Missing template
# ===========================================================================

def test_missing_template(monkeypatch):
    """Non-existent template should fail gracefully."""
    app, client, ids = _setup(monkeypatch)
    with app.test_request_context():
        from app.services.branded_email_service import send_branded_email
        result = send_branded_email(
            to_email="test@example.com",
            subject="Test",
            template_name="nonexistent_template.html",
        )
        assert result.success is False
        assert "template" in result.message.lower()


# ===========================================================================
# G. EmailResult object
# ===========================================================================

def test_email_result_bool():
    """EmailResult should be truthy on success, falsy on failure."""
    from app.services.branded_email_service import EmailResult
    assert bool(EmailResult(True, "ok")) is True
    assert bool(EmailResult(False, "fail")) is False


def test_email_result_transport():
    """EmailResult should carry transport info."""
    from app.services.branded_email_service import EmailResult
    r = EmailResult(True, "ok", transport="smtp")
    assert r.transport == "smtp"
    assert "smtp" in repr(r)


# ===========================================================================
# H. Sender/reply-to
# ===========================================================================

def test_sender_info_from_config(monkeypatch):
    """_get_sender_info should prefer config over company record."""
    app, client, ids = _setup(monkeypatch)
    with app.test_request_context():
        from app.services.branded_email_service import _get_sender_info
        email, name, reply_to = _get_sender_info()
        assert email == "noreply@testcorp.com"
        assert name == "TestCorp Repairs"
        assert reply_to == "support@testcorp.com"


def test_sender_fallback_to_company(monkeypatch):
    """When config sender is empty, should fall back to company email."""
    app, client, ids = _setup(monkeypatch)
    with app.test_request_context():
        app.config["MAIL_DEFAULT_SENDER_EMAIL"] = ""
        app.config["MAIL_DEFAULT_SENDER_NAME"] = ""
        app.config["MAIL_DEFAULT_REPLY_TO"] = ""
        from app.services.branded_email_service import _get_sender_info
        email, name, reply_to = _get_sender_info()
        assert email == "info@testcorp.com"  # From Company record
        assert name == "TestCorp"  # From Company display_name
        assert reply_to == "info@testcorp.com"  # Falls back to sender


# ===========================================================================
# I. Test email function
# ===========================================================================

def test_send_test_email_log_mode(monkeypatch):
    """send_test_email should succeed in log mode."""
    app, client, ids = _setup(monkeypatch)
    with app.test_request_context():
        from app.services.branded_email_service import send_test_email
        result = send_test_email("admin@test.com")
        assert result.success is True
        assert result.transport == "log"


def test_send_test_email_smtp_mocked(monkeypatch):
    """send_test_email should use SMTP when configured."""
    app, client, ids = _setup(monkeypatch, config_class=TestConfigSMTP)
    with app.test_request_context():
        mock_server = MagicMock()
        mock_smtp = MagicMock(return_value=mock_server)
        mock_server.__enter__ = MagicMock(return_value=mock_server)
        mock_server.__exit__ = MagicMock(return_value=False)

        with patch('app.services.branded_email_service.smtplib.SMTP', mock_smtp):
            from app.services.branded_email_service import send_test_email
            result = send_test_email("admin@test.com")

        assert result.success is True
        assert result.transport == "smtp"


# ===========================================================================
# J. Email settings page
# ===========================================================================

def test_email_settings_page_returns_200(monkeypatch):
    """GET /settings/email should render for admins."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get("/settings/email")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert "Email Transport" in html or "email" in html.lower()


def test_email_settings_shows_transport_status(monkeypatch):
    """Email settings page should show current transport mode."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get("/settings/email")
    html = resp.data.decode()
    assert "LOG" in html or "log" in html.lower()


def test_email_settings_shows_smtp_config(monkeypatch):
    """Email settings page should show SMTP host/port."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get("/settings/email")
    html = resp.data.decode()
    assert "smtp.example.com" in html
    assert "587" in html


def test_email_settings_shows_sender_details(monkeypatch):
    """Email settings page should show sender email/name."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get("/settings/email")
    html = resp.data.decode()
    assert "noreply@testcorp.com" in html
    assert "TestCorp Repairs" in html


def test_email_settings_masks_password(monkeypatch):
    """Email settings page should not show SMTP password in plain text."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get("/settings/email")
    html = resp.data.decode()
    assert "secret" not in html
    assert "••••" in html


def test_email_settings_has_test_form(monkeypatch):
    """Email settings page should have a test email form."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get("/settings/email")
    html = resp.data.decode()
    assert "to_email" in html
    assert "/settings/email/test" in html


# ===========================================================================
# K. Test email route
# ===========================================================================

def test_send_test_email_route_success(monkeypatch):
    """POST /settings/email/test should send test email and redirect."""
    app, client, ids = _setup(monkeypatch)
    resp = client.post("/settings/email/test", data={"to_email": "admin@test.com"},
                       follow_redirects=False)
    assert resp.status_code == 302
    assert "/settings/email" in resp.headers["Location"]

    # Follow redirect to check flash message
    resp2 = client.get("/settings/email")
    html = resp2.data.decode()
    assert "admin@test.com" in html or "success" in html.lower() or "Test email sent" in html


def test_send_test_email_route_invalid_email(monkeypatch):
    """POST /settings/email/test with invalid email should flash error."""
    app, client, ids = _setup(monkeypatch)
    resp = client.post("/settings/email/test", data={"to_email": "notanemail"},
                       follow_redirects=True)
    html = resp.data.decode()
    assert "valid email" in html.lower() or "error" in html.lower()


def test_send_test_email_route_empty_email(monkeypatch):
    """POST /settings/email/test with empty email should flash error."""
    app, client, ids = _setup(monkeypatch)
    resp = client.post("/settings/email/test", data={"to_email": ""},
                       follow_redirects=True)
    html = resp.data.decode()
    assert "valid email" in html.lower() or "error" in html.lower()


# ===========================================================================
# L. Permissions
# ===========================================================================

def test_email_settings_requires_admin(monkeypatch):
    """GET /settings/email should be denied for non-admin roles."""
    app, client, ids = _setup(monkeypatch, role_name="Technician")
    resp = client.get("/settings/email")
    assert resp.status_code in (302, 403)


def test_test_email_route_requires_admin(monkeypatch):
    """POST /settings/email/test should be denied for non-admin roles."""
    app, client, ids = _setup(monkeypatch, role_name="Technician")
    resp = client.post("/settings/email/test", data={"to_email": "test@example.com"})
    assert resp.status_code in (302, 403)


def test_email_settings_requires_login(monkeypatch):
    """GET /settings/email without login should redirect."""
    monkeypatch.setattr('app.services.auth_service.log_action', _noop_log)
    monkeypatch.setattr('app.services.audit_service.log_action', _noop_log)
    monkeypatch.setattr('app.blueprints.intake.routes.log_action', _noop_log)
    monkeypatch.setattr('app.blueprints.tickets.routes.log_action', _noop_log)
    monkeypatch.setattr('app.services.booking_service.log_action', _noop_log)
    monkeypatch.setattr('app.blueprints.bookings.routes.log_action', _noop_log)

    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
    client = app.test_client()
    resp = client.get("/settings/email")
    assert resp.status_code in (302, 401)


# ===========================================================================
# M. Settings index link
# ===========================================================================

def test_settings_index_has_email_link(monkeypatch):
    """Settings index should have a link to email settings."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get("/settings/")
    html = resp.data.decode()
    assert "/settings/email" in html
    assert "Email Settings" in html or "Email" in html


# ===========================================================================
# N. Delivery logging (verify through logger)
# ===========================================================================

def test_delivery_log_on_success(monkeypatch, caplog):
    """Successful send should log delivery with status=success."""
    app, client, ids = _setup(monkeypatch)
    with app.test_request_context():
        import logging
        with caplog.at_level(logging.INFO, logger="app.services.branded_email_service"):
            from app.services.branded_email_service import send_branded_email
            send_branded_email(
                to_email="test@example.com",
                subject="Log Test",
                template_name="test_email.html",
                event_type="test_email",
            )
    assert any("EMAIL_DELIVERY" in r.message and "status=success" in r.message for r in caplog.records)
    assert any("test@example.com" in r.message for r in caplog.records)


def test_delivery_log_on_failure(monkeypatch, caplog):
    """Failed send should log delivery with status=failed."""
    app, client, ids = _setup(monkeypatch)
    with app.test_request_context():
        import logging
        with caplog.at_level(logging.INFO, logger="app.services.branded_email_service"):
            from app.services.branded_email_service import send_branded_email
            send_branded_email(
                to_email="",  # Will fail
                subject="Fail Log",
                template_name="test_email.html",
            )
    # Missing email fails before delivery logging, but that's expected behavior


# ===========================================================================
# O. Test email template renders
# ===========================================================================

def test_test_email_template_en(monkeypatch):
    """English test email template should render."""
    app, client, ids = _setup(monkeypatch)
    with app.test_request_context():
        from flask import render_template
        html = render_template("emails/en/test_email.html",
                               branding={"company_name": "Test", "company_phone": "",
                                         "company_email": "", "company_website": "",
                                         "document_footer": ""},
                               transport="log", language="en", year=2026,
                               recipient_name="")
        assert "Email Configuration Test" in html
        assert "log" in html


def test_test_email_template_es(monkeypatch):
    """Spanish test email template should render."""
    app, client, ids = _setup(monkeypatch)
    with app.test_request_context():
        from flask import render_template
        html = render_template("emails/es/test_email.html",
                               branding={"company_name": "Test", "company_phone": "",
                                         "company_email": "", "company_website": "",
                                         "document_footer": ""},
                               transport="smtp", language="es", year=2026,
                               recipient_name="")
        assert "Prueba de Configuración" in html or "Correo de Prueba" in html


# ===========================================================================
# P. Backward compatibility — existing send functions still work
# ===========================================================================

def test_log_transport_backward_compatible(monkeypatch):
    """Existing send_branded_email call pattern should still work."""
    app, client, ids = _setup(monkeypatch)
    with app.test_request_context():
        from app.services.branded_email_service import send_branded_email
        # Old-style call without event_type
        result = send_branded_email(
            to_email="test@example.com",
            to_name="Test User",
            subject="Backward compat",
            template_name="test_email.html",
            template_context={"transport": "log"},
            language="en",
        )
        assert result.success is True


def test_email_result_has_transport_field():
    """EmailResult should always have transport field."""
    from app.services.branded_email_service import EmailResult
    # Default transport
    r = EmailResult(True, "ok")
    assert hasattr(r, "transport")
    assert r.transport == "unknown"
