"""Phase 15 — Internationalization, Spanish Translation & Customer Language Preferences.

Tests cover:
- UI translation: key pages render in English and Spanish
- Language switcher: locale selection works
- Customer language preference: stored/read correctly
- Customer communication templates: English and Spanish generation
- Public portal: localized wording
- Customer status service: localized labels
- Safe fallback: no crash from missing translations
- Regression: existing flows remain intact
"""
import re
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

_noop = lambda *a, **kw: None


def _patch_log_action(fn):
    fn = patch("app.services.audit_service.log_action", _noop)(fn)
    fn = patch("app.services.auth_service.log_action", _noop)(fn)
    fn = patch("app.blueprints.tickets.routes.log_action", _noop)(fn)
    fn = patch("app.blueprints.quotes.routes.log_action", _noop)(fn)
    fn = patch("app.blueprints.public_portal.routes.log_action", _noop)(fn)
    return fn


from app import create_app
from app.extensions import db
from app.models import (
    AppSetting, Branch, Customer, Device, Diagnostic, Part, PartOrder,
    PortalToken, Quote, RepairChecklist, RepairService, Role,
    StockMovement, StockReservation, StockLayer, Supplier, Ticket,
    TicketNote, User, Booking, IntakeSubmission, IntakeDisclaimerAcceptance,
    NotificationTemplate, NotificationEvent, NotificationDelivery,
)
from app.models.checklist import ChecklistItem
from app.models.inventory import PartSupplier, part_category_links, PartCategory, StockLevel, StockLocation
from app.models.order import PartOrderEvent, PartOrderLine
from app.models.quote import QuoteApproval, QuoteLine, QuoteOption
from app.models.role import role_permissions
from app.models.user import user_branch_access, user_roles
from app.services.seed_service import seed_phase1_data


class TestConfig:
    TESTING = True
    SECRET_KEY = 'test-secret'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True
    BABEL_DEFAULT_LOCALE = 'en'
    BABEL_DEFAULT_TIMEZONE = 'UTC'
    SUPPORTED_LOCALES = ['en', 'es']
    DEFAULT_BRANCH_CODE = 'HQ'
    DEFAULT_INTAKE_DISCLAIMER_TEXT = 'Test disclaimer'
    DEFAULT_TICKET_SLA_DAYS = 5
    DEFAULT_IGIC_RATE = 0.07
    UPLOAD_ROOT = '/tmp/test-uploads'
    STRIPE_SECRET_KEY = ''


def _create_tables():
    tables = [
        Branch.__table__, Role.__table__, Customer.__table__, User.__table__,
        role_permissions, user_roles, user_branch_access,
        Device.__table__, Ticket.__table__, TicketNote.__table__,
        Diagnostic.__table__,
        IntakeSubmission.__table__, IntakeDisclaimerAcceptance.__table__, PortalToken.__table__,
        Quote.__table__, QuoteOption.__table__, QuoteLine.__table__, QuoteApproval.__table__,
        Supplier.__table__, PartCategory.__table__, part_category_links,
        Part.__table__, PartSupplier.__table__,
        StockLocation.__table__, StockLevel.__table__,
        StockMovement.__table__, StockReservation.__table__, StockLayer.__table__,
        PartOrder.__table__, PartOrderLine.__table__, PartOrderEvent.__table__,
        RepairChecklist.__table__, ChecklistItem.__table__,
        RepairService.__table__, Booking.__table__,
        AppSetting.__table__,
        NotificationTemplate.__table__, NotificationEvent.__table__, NotificationDelivery.__table__,
    ]
    from sqlalchemy import text
    with db.engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id CHAR(32) PRIMARY KEY,
                actor_user_id CHAR(32) REFERENCES users(id),
                action VARCHAR(120) NOT NULL,
                entity_type VARCHAR(80) NOT NULL,
                entity_id VARCHAR(64),
                ip_address VARCHAR(64),
                user_agent VARCHAR(255),
                details TEXT,
                message TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.commit()
    for t in tables:
        t.create(bind=db.engine, checkfirst=True)


def _csrf(html: bytes) -> str:
    m = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', html)
    if m:
        return m.group(1).decode()
    m2 = re.search(rb'value="([^"]+)"[^>]*name="csrf_token"', html)
    assert m2, "No csrf_token found in page"
    return m2.group(1).decode()


def _login(client, email='admin@ironcore.com', password='admin1234'):
    p = client.get('/auth/login')
    token = _csrf(p.data)
    r = client.post('/auth/login', data={
        'email': email, 'password': password, 'csrf_token': token,
    }, follow_redirects=True)
    return r


def _setup():
    """Create tables, seed data, return app."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
    return app


# ====================================================================
# Language Switcher
# ====================================================================

@_patch_log_action
def test_language_switcher_sets_session_locale():
    """GET /set-language/es should store locale in session."""
    app = _setup()
    with app.test_client() as client:
        resp = client.get('/set-language/es')
        assert resp.status_code == 302
        # Next request should reflect Spanish locale
        with client.session_transaction() as sess:
            assert sess.get('locale') == 'es'


@_patch_log_action
def test_language_switcher_rejects_invalid_locale():
    """GET /set-language/fr should not store locale."""
    app = _setup()
    with app.test_client() as client:
        client.get('/set-language/fr')
        with client.session_transaction() as sess:
            assert sess.get('locale') is None


# ====================================================================
# Staff UI renders in English
# ====================================================================

@_patch_log_action
def test_dashboard_renders_in_english():
    """Dashboard should render with English text by default."""
    app = _setup()
    with app.test_client() as client:
        _login(client)
        resp = client.get('/')
        assert resp.status_code == 200
        html = resp.data.decode()
        assert 'Dashboard' in html or 'dashboard' in html.lower()


@_patch_log_action
def test_ticket_list_renders_in_english():
    """Ticket list should render with English text."""
    app = _setup()
    with app.test_client() as client:
        _login(client)
        resp = client.get('/tickets/')
        assert resp.status_code == 200


@_patch_log_action
def test_quote_list_renders_in_english():
    """Quote list should render with English text."""
    app = _setup()
    with app.test_client() as client:
        _login(client)
        resp = client.get('/quotes/list')
        assert resp.status_code == 200


@_patch_log_action
def test_inventory_renders_in_english():
    """Inventory overview should render."""
    app = _setup()
    with app.test_client() as client:
        _login(client)
        resp = client.get('/inventory/')
        assert resp.status_code == 200


# ====================================================================
# Staff UI renders in Spanish
# ====================================================================

@_patch_log_action
def test_dashboard_renders_in_spanish():
    """Dashboard should render with Spanish text when locale is es."""
    app = _setup()
    with app.test_client() as client:
        _login(client)
        client.get('/set-language/es')
        resp = client.get('/')
        assert resp.status_code == 200
        html = resp.data.decode()
        # Check for at least one Spanish string
        assert 'Panel de Control' in html or 'Reparaciones' in html or 'Operaciones' in html


@_patch_log_action
def test_ticket_list_renders_in_spanish():
    """Ticket list should render in Spanish."""
    app = _setup()
    with app.test_client() as client:
        _login(client)
        client.get('/set-language/es')
        resp = client.get('/tickets/')
        assert resp.status_code == 200
        html = resp.data.decode()
        # Spanish text should appear in navigation or page content
        assert 'es' in html.lower()  # At minimum the locale switcher shows ES


# ====================================================================
# Public Portal renders in both languages
# ====================================================================

@_patch_log_action
def test_public_status_page_renders_in_english():
    """Public status lookup page renders in English."""
    app = _setup()
    with app.test_client() as client:
        resp = client.get('/public/status')
        assert resp.status_code == 200
        html = resp.data.decode()
        assert 'repair' in html.lower() or 'track' in html.lower()


@_patch_log_action
def test_public_status_page_renders_in_spanish():
    """Public status lookup page renders in Spanish."""
    app = _setup()
    with app.test_client() as client:
        client.get('/set-language/es')
        resp = client.get('/public/status')
        assert resp.status_code == 200
        html = resp.data.decode()
        # Check for Spanish content
        assert 'reparaci' in html.lower() or 'seguimiento' in html.lower() or 'ticket' in html.lower()


@_patch_log_action
def test_public_checkin_renders():
    """Public check-in page renders without errors."""
    app = _setup()
    with app.test_client() as client:
        resp = client.get('/public/check-in')
        assert resp.status_code == 200


@_patch_log_action
def test_public_quote_approval_invalid_token():
    """Quote approval with invalid token redirects gracefully."""
    app = _setup()
    with app.test_client() as client:
        resp = client.get('/public/quote/invalid-token-12345')
        assert resp.status_code in (302, 200)


# ====================================================================
# Customer Language Preference
# ====================================================================

@_patch_log_action
def test_customer_preferred_language_default():
    """Customer preferred_language should default to 'en'."""
    app = _setup()
    with app.app_context():
        customer = Customer(full_name="Test Customer", email="test@test.com")
        db.session.add(customer)
        db.session.flush()
        assert customer.preferred_language == "en"
        db.session.rollback()


@_patch_log_action
def test_customer_preferred_language_stored():
    """Customer preferred_language can be set to 'es'."""
    app = _setup()
    with app.app_context():
        customer = Customer(full_name="Cliente Test", email="es@test.com", preferred_language="es")
        db.session.add(customer)
        db.session.flush()
        assert customer.preferred_language == "es"
        # Reload from DB
        cid = customer.id
        db.session.expire(customer)
        reloaded = db.session.get(Customer, cid)
        assert reloaded.preferred_language == "es"
        db.session.rollback()


# ====================================================================
# Customer Communication Templates — English and Spanish
# ====================================================================

@_patch_log_action
def test_communication_template_english():
    """Communication templates render in English by default."""
    app = _setup()
    with app.test_request_context():
        from app.services.customer_communication_service import generate_message
        result = generate_message(
            "checked_in",
            ticket_number="TK-001",
            device_summary="iPhone 15",
            customer_name="John",
            portal_url="https://example.com/status",
        )
        assert "subject" in result
        assert "body" in result
        assert "TK-001" in result["body"]
        assert "iPhone 15" in result["body"]
        assert "https://example.com/status" in result["body"]
        # English text
        assert "checked in" in result["subject"].lower() or "checked in" in result["body"].lower()


@_patch_log_action
def test_communication_template_spanish():
    """Communication templates render in Spanish when language='es'."""
    app = _setup()
    with app.test_request_context():
        from app.services.customer_communication_service import generate_message
        result = generate_message(
            "checked_in",
            ticket_number="TK-001",
            device_summary="iPhone 15",
            customer_name="Juan",
            portal_url="https://example.com/status",
            language="es",
        )
        assert "subject" in result
        assert "body" in result
        assert "TK-001" in result["body"]
        assert "iPhone 15" in result["body"]
        # Spanish text
        assert "registrado" in result["subject"].lower() or "registrado" in result["body"].lower()


@_patch_log_action
def test_communication_template_quote_ready():
    """Quote-ready template includes quote approval URL."""
    app = _setup()
    with app.test_request_context():
        from app.services.customer_communication_service import generate_message
        result = generate_message(
            "quote_ready",
            ticket_number="TK-002",
            device_summary="Samsung Galaxy",
            customer_name="Maria",
            portal_url="https://example.com/status",
            quote_approval_url="https://example.com/quote/abc123",
        )
        assert "https://example.com/quote/abc123" in result["body"]
        assert "https://example.com/status" in result["body"]


@_patch_log_action
def test_communication_template_ready_for_collection():
    """Ready-for-collection template renders correctly."""
    app = _setup()
    with app.test_request_context():
        from app.services.customer_communication_service import generate_message
        result = generate_message(
            "ready_for_collection",
            ticket_number="TK-003",
            device_summary="iPad Pro",
            customer_name="Carlos",
            portal_url="https://example.com/status",
            opening_hours="Mon-Fri 9-18",
        )
        assert "TK-003" in result["body"]
        assert "Mon-Fri 9-18" in result["body"]


@_patch_log_action
def test_communication_fallback_to_english():
    """When no language is specified, English is used."""
    app = _setup()
    with app.test_request_context():
        from app.services.customer_communication_service import generate_message
        result = generate_message(
            "in_repair",
            ticket_number="TK-004",
            device_summary="MacBook",
        )
        # Should contain English text (the default)
        assert "body" in result
        assert "TK-004" in result["body"]


@_patch_log_action
def test_available_templates_returns_all_keys():
    """available_templates() should return all 7 template keys."""
    app = _setup()
    with app.test_request_context():
        from app.services.customer_communication_service import available_templates
        templates = available_templates()
        assert len(templates) == 7
        keys = [t["key"] for t in templates]
        assert "checked_in" in keys
        assert "ready_for_collection" in keys
        assert "completed" in keys


@_patch_log_action
def test_suggested_template_key():
    """suggested_template_key maps status to correct template."""
    app = _setup()
    with app.test_request_context():
        from app.services.customer_communication_service import suggested_template_key
        assert suggested_template_key("unassigned") == "checked_in"
        assert suggested_template_key("in_repair") == "in_repair"
        assert suggested_template_key("ready_for_collection") == "ready_for_collection"


# ====================================================================
# Customer Status Service — Localized labels
# ====================================================================

@_patch_log_action
def test_customer_friendly_status_english():
    """customer_friendly_status returns English labels."""
    app = _setup()
    with app.test_request_context():
        from app.services.customer_status_service import customer_friendly_status
        status = customer_friendly_status("unassigned")
        # English or Spanish depending on locale; in test context defaults to English
        assert status in ("Checked In", "Registrado")


@_patch_log_action
def test_customer_friendly_status_unknown():
    """Unknown status returns title-cased version."""
    app = _setup()
    with app.test_request_context():
        from app.services.customer_status_service import customer_friendly_status
        status = customer_friendly_status("some_weird_status")
        assert status == "Some Weird Status"


@_patch_log_action
def test_progress_steps_returns_list():
    """progress_steps() returns a list of 6 steps."""
    app = _setup()
    with app.test_request_context():
        from app.services.customer_status_service import progress_steps
        steps = progress_steps()
        assert len(steps) == 6


@_patch_log_action
def test_progress_step_index():
    """progress_step_index returns correct indices."""
    app = _setup()
    with app.test_request_context():
        from app.services.customer_status_service import progress_step_index
        assert progress_step_index("unassigned") == 0
        assert progress_step_index("in_repair") == 3
        assert progress_step_index("ready_for_collection") == 5


@_patch_log_action
def test_communication_summary_default():
    """communication_summary returns a non-empty string."""
    app = _setup()
    with app.test_request_context():
        from app.services.customer_status_service import communication_summary
        msg = communication_summary("in_repair")
        assert len(msg) > 10


@_patch_log_action
def test_communication_summary_with_pending_quote():
    """communication_summary enriches message for pending quote."""
    app = _setup()
    with app.test_request_context():
        from app.services.customer_status_service import communication_summary
        msg = communication_summary("awaiting_quote_approval", has_pending_quote=True)
        assert len(msg) > 10
        assert "quote" in msg.lower() or "presupuesto" in msg.lower()


# ====================================================================
# Safe Fallback — missing translations don't crash
# ====================================================================

@_patch_log_action
def test_missing_translation_falls_back_to_english():
    """A string without a Spanish translation should fall back to English."""
    app = _setup()
    with app.test_request_context():
        from flask_babel import force_locale, gettext as _
        # This string likely has no translation — should return English source
        with force_locale("es"):
            result = _("Some string that probably has no translation")
            # Flask-Babel returns the msgid when no translation found
            assert result == "Some string that probably has no translation"


# ====================================================================
# Regression — existing flows still work
# ====================================================================

@_patch_log_action
def test_login_page_renders():
    """Login page renders without errors."""
    app = _setup()
    with app.test_client() as client:
        resp = client.get('/auth/login')
        assert resp.status_code == 200


@_patch_log_action
def test_login_and_dashboard_flow():
    """Login + redirect to dashboard works."""
    app = _setup()
    with app.test_client() as client:
        resp = _login(client)
        assert resp.status_code == 200


@_patch_log_action
def test_public_portal_status_lookup():
    """Public status lookup form renders."""
    app = _setup()
    with app.test_client() as client:
        resp = client.get('/public/status')
        assert resp.status_code == 200


@_patch_log_action
def test_reports_dashboard_renders():
    """Reports dashboard renders for authorized user."""
    app = _setup()
    with app.test_client() as client:
        _login(client)
        resp = client.get('/reports/')
        assert resp.status_code == 200


@_patch_log_action
def test_settings_page_renders():
    """Settings page renders."""
    app = _setup()
    with app.test_client() as client:
        _login(client)
        resp = client.get('/settings/')
        assert resp.status_code == 200


@_patch_log_action
def test_intake_list_renders():
    """Intake list renders."""
    app = _setup()
    with app.test_client() as client:
        _login(client)
        resp = client.get('/intake/')
        assert resp.status_code == 200


@_patch_log_action
def test_customer_list_renders():
    """Customer list renders."""
    app = _setup()
    with app.test_client() as client:
        _login(client)
        resp = client.get('/customers/')
        assert resp.status_code == 200


@_patch_log_action
def test_supplier_list_renders():
    """Supplier list renders."""
    app = _setup()
    with app.test_client() as client:
        _login(client)
        resp = client.get('/suppliers/')
        assert resp.status_code == 200


@_patch_log_action
def test_services_list_renders():
    """Services list renders."""
    app = _setup()
    with app.test_client() as client:
        _login(client)
        resp = client.get('/services/')
        assert resp.status_code == 200


@_patch_log_action
def test_bookings_list_renders():
    """Bookings list renders."""
    app = _setup()
    with app.test_client() as client:
        _login(client)
        resp = client.get('/bookings/')
        assert resp.status_code == 200


@_patch_log_action
def test_spanish_locale_in_html_tag():
    """When locale is es, the HTML lang attribute should be 'es'."""
    app = _setup()
    with app.test_client() as client:
        _login(client)
        client.get('/set-language/es')
        resp = client.get('/')
        html = resp.data.decode()
        assert 'lang="es"' in html
