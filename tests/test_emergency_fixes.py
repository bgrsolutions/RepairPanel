"""Emergency Fixes — tests for migration, quote approval, dashboard visibility, staff badge.

Covers:
- A. Migration partial-failure resilience and UUID type detection
- B/C. Ticket list and detail pages render without errors
- D. Public quote approval creates notification events
- E. Dashboard shows recently approved quotes card
- F. Staff update badge count appears in header
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


def _create_user_with_role(role_name, email, password='test1234'):
    role = Role.query.filter_by(name=role_name).first()
    if not role:
        role = Role(name=role_name, description=role_name)
        db.session.add(role)
        db.session.flush()
    user = User(
        email=email,
        full_name=f"Test {role_name}",
        is_active=True,
    )
    user.set_password(password)
    user.roles.append(role)
    db.session.add(user)
    db.session.commit()
    return user


def _setup_app_and_data():
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        branch = Branch.query.first()
        customer = Customer.query.first()
        if not customer:
            customer = Customer(full_name="Test Customer", email="cust@test.com")
            db.session.add(customer)
            db.session.flush()
        device = Device.query.first()
        if not device:
            device = Device(customer_id=customer.id, brand="Apple", model="iPhone 14", category="smartphone")
            db.session.add(device)
            db.session.flush()

        now = datetime.utcnow()
        ticket = Ticket(
            ticket_number="HQ-0001",
            branch_id=branch.id,
            customer_id=customer.id,
            device_id=device.id,
            priority="normal",
            internal_status="awaiting_quote_approval",
            customer_status="In Progress",
        )
        db.session.add(ticket)
        db.session.flush()

        # Create a quote with approval token
        quote = Quote(
            ticket_id=ticket.id,
            customer_id=customer.id,
            version=1,
            status="sent",
            currency="EUR",
            language="en",
            sent_at=now - timedelta(hours=1),
        )
        db.session.add(quote)
        db.session.flush()

        option = QuoteOption(quote_id=quote.id, name="Default", position=1)
        db.session.add(option)
        db.session.flush()

        line = QuoteLine(option_id=option.id, line_type="labour", description="Screen repair", quantity=1, unit_price=150.0)
        db.session.add(line)
        db.session.flush()

        import secrets
        approval_token = secrets.token_urlsafe(24)
        approval = QuoteApproval(
            quote_id=quote.id,
            token=approval_token,
            status="pending",
            expires_at=now + timedelta(days=7),
        )
        db.session.add(approval)

        # Portal token for the ticket
        portal_token = PortalToken(
            token=secrets.token_urlsafe(24),
            token_type="public_status_lookup",
            ticket_id=ticket.id,
        )
        db.session.add(portal_token)

        # A notification template for quote_approved (needed for notification service)
        nt = NotificationTemplate(
            key="quote_approved",
            channel="email",
            language="en",
            subject_template="Quote approved",
            body_template="Your quote has been approved.",
            is_active=True,
        )
        db.session.add(nt)

        db.session.commit()
    return app


# ---------------------------------------------------------------------------
# A. Migration Tests
# ---------------------------------------------------------------------------

class TestMigrationFix:
    """Test that the migration file handles partial-failure and dialect detection."""

    def test_migration_uses_uuid_detection_logic(self):
        """Verify migration file contains dialect-aware type selection."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "migration_d8e0f2a4b6c8",
            "migrations/versions/d8e0f2a4b6c8_phase11_portal_token_ticket_id.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        import inspect
        source = inspect.getsource(mod.upgrade)
        assert "dialect" in source, "Migration should detect database dialect"
        assert "postgresql" in source, "Migration should handle PostgreSQL UUID type"
        assert "existing_cols" in source or "insp" in source, "Migration should guard against re-runs"

    def test_migration_has_partial_failure_guards(self):
        """Verify migration checks for existing columns/indexes before creating."""
        with open("migrations/versions/d8e0f2a4b6c8_phase11_portal_token_ticket_id.py") as f:
            content = f.read()
        assert "ticket_id" in content
        assert "get_columns" in content, "Should introspect existing columns"
        assert "get_indexes" in content, "Should introspect existing indexes"
        assert "get_foreign_keys" in content, "Should introspect existing FKs"


# ---------------------------------------------------------------------------
# B/C. Ticket Page Tests
# ---------------------------------------------------------------------------

class TestTicketPages:
    """Test that ticket list and detail pages render without errors."""

    @_patch_log_action
    def test_ticket_list_renders(self):
        app = _setup_app_and_data()
        with app.test_client() as client:
            with app.app_context():
                _login(client)
                resp = client.get('/tickets/')
                assert resp.status_code == 200
                assert b"Ticket Operations" in resp.data

    @_patch_log_action
    def test_ticket_detail_renders(self):
        app = _setup_app_and_data()
        with app.test_client() as client:
            with app.app_context():
                _login(client)
                ticket = Ticket.query.first()
                resp = client.get(f'/tickets/{ticket.id}')
                assert resp.status_code == 200
                assert ticket.ticket_number.encode() in resp.data

    @_patch_log_action
    def test_ticket_detail_shows_portal_token(self):
        app = _setup_app_and_data()
        with app.test_client() as client:
            with app.app_context():
                _login(client)
                ticket = Ticket.query.first()
                resp = client.get(f'/tickets/{ticket.id}')
                assert resp.status_code == 200
                assert b"public-status-url" in resp.data or b"Portal link" in resp.data

    @_patch_log_action
    def test_ticket_detail_shows_quote_section(self):
        app = _setup_app_and_data()
        with app.test_client() as client:
            with app.app_context():
                _login(client)
                ticket = Ticket.query.first()
                resp = client.get(f'/tickets/{ticket.id}')
                assert resp.status_code == 200
                assert b"Quotes" in resp.data


# ---------------------------------------------------------------------------
# D. Public Quote Approval Tests
# ---------------------------------------------------------------------------

class TestPublicQuoteApproval:
    """Test public portal quote approval updates system correctly."""

    @_patch_log_action
    def test_quote_approval_sets_status_approved(self):
        app = _setup_app_and_data()
        with app.test_client() as client:
            with app.app_context():
                approval = QuoteApproval.query.first()
                quote = approval.quote
                assert quote.status == "sent"

                # POST approval (public form has csrf=False)
                resp = client.post(f'/public/quote/{approval.token}', data={
                    'decision': 'approved',
                    'actor_name': 'John Doe',
                    'actor_contact': 'john@test.com',
                    'payment_choice': 'pay_in_store',
                    'language': 'en',
                    'submit': 'Submit Decision',
                }, follow_redirects=True)
                assert resp.status_code == 200

                # Verify state changed
                db.session.refresh(quote)
                assert quote.status == "approved"
                if quote.ticket:
                    db.session.refresh(quote.ticket)
                    assert quote.ticket.internal_status == "in_repair"

    @_patch_log_action
    def test_quote_approval_creates_notification_event(self):
        app = _setup_app_and_data()
        with app.test_client() as client:
            with app.app_context():
                approval = QuoteApproval.query.first()

                client.post(f'/public/quote/{approval.token}', data={
                    'decision': 'approved',
                    'actor_name': 'Jane Doe',
                    'actor_contact': 'jane@test.com',
                    'payment_choice': 'pay_in_store',
                    'language': 'en',
                    'submit': 'Submit Decision',
                }, follow_redirects=True)

                events = NotificationEvent.query.filter_by(event_type="quote_approved").all()
                assert len(events) >= 1, "Should create a quote_approved notification event"

    @_patch_log_action
    def test_quote_decline_sets_status(self):
        app = _setup_app_and_data()
        with app.test_client() as client:
            with app.app_context():
                approval = QuoteApproval.query.first()

                client.post(f'/public/quote/{approval.token}', data={
                    'decision': 'declined',
                    'actor_name': 'Jane',
                    'actor_contact': 'jane@test.com',
                    'declined_reason': 'Too expensive',
                    'language': 'en',
                    'submit': 'Submit Decision',
                }, follow_redirects=True)

                db.session.refresh(approval.quote)
                assert approval.quote.status == "declined"


# ---------------------------------------------------------------------------
# E. Dashboard Approved Quotes Visibility
# ---------------------------------------------------------------------------

class TestDashboardApprovedQuotes:
    """Test that recently approved quotes appear on the staff dashboard."""

    @_patch_log_action
    def test_dashboard_shows_approved_quotes_card(self):
        app = _setup_app_and_data()
        with app.test_client() as client:
            with app.app_context():
                # Approve a quote directly
                quote = Quote.query.first()
                quote.status = "approved"
                quote.updated_at = datetime.utcnow()
                db.session.commit()

                _login(client)
                resp = client.get('/')
                assert resp.status_code == 200
                assert b"Recently Approved Quotes" in resp.data
                assert b"approved-quotes-card" in resp.data

    @_patch_log_action
    def test_dashboard_hides_card_when_no_approvals(self):
        app = _setup_app_and_data()
        with app.test_client() as client:
            with app.app_context():
                # Ensure no approved quotes
                for q in Quote.query.all():
                    q.status = "draft"
                db.session.commit()

                _login(client)
                resp = client.get('/')
                assert resp.status_code == 200
                assert b"approved-quotes-card" not in resp.data


# ---------------------------------------------------------------------------
# E2. Ticket Detail Approved Quote Banner
# ---------------------------------------------------------------------------

class TestTicketDetailApprovedBanner:
    """Test approved quote banner appears on ticket detail."""

    @_patch_log_action
    def test_ticket_detail_shows_approved_banner(self):
        app = _setup_app_and_data()
        with app.test_client() as client:
            with app.app_context():
                quote = Quote.query.first()
                quote.status = "approved"
                db.session.commit()

                _login(client)
                # Use the ticket linked to the quote
                ticket = db.session.get(Ticket, quote.ticket_id)
                resp = client.get(f'/tickets/{ticket.id}')
                assert resp.status_code == 200
                assert b"approved-quote-banner" in resp.data
                assert b"Quote Approved" in resp.data

    @_patch_log_action
    def test_ticket_detail_no_banner_for_draft_quote(self):
        app = _setup_app_and_data()
        with app.test_client() as client:
            with app.app_context():
                quote = Quote.query.first()
                quote.status = "draft"
                db.session.commit()

                _login(client)
                ticket = db.session.get(Ticket, quote.ticket_id)
                resp = client.get(f'/tickets/{ticket.id}')
                assert resp.status_code == 200
                assert b"approved-quote-banner" not in resp.data


# ---------------------------------------------------------------------------
# F. Staff Update Badge
# ---------------------------------------------------------------------------

class TestStaffUpdateBadge:
    """Test staff notification badge in header."""

    @_patch_log_action
    def test_badge_shows_when_updates_exist(self):
        app = _setup_app_and_data()
        with app.test_client() as client:
            with app.app_context():
                # Approved quote = badge should show
                quote = Quote.query.first()
                quote.status = "approved"
                quote.updated_at = datetime.utcnow()
                db.session.commit()

                _login(client)
                resp = client.get('/')
                assert resp.status_code == 200
                assert b"actionable update" in resp.data

    @_patch_log_action
    def test_badge_hidden_for_unauthenticated(self):
        app = _setup_app_and_data()
        with app.test_client() as client:
            with app.app_context():
                resp = client.get('/auth/login')
                assert resp.status_code == 200
                assert b"actionable update" not in resp.data

    @_patch_log_action
    def test_badge_counts_unassigned_tickets(self):
        app = _setup_app_and_data()
        with app.test_client() as client:
            with app.app_context():
                # Ensure no approved quotes to isolate unassigned count
                for q in Quote.query.all():
                    q.status = "draft"
                db.session.commit()

                # The test ticket is unassigned — badge should reflect that
                ticket = Ticket.query.first()
                ticket.assigned_technician_id = None
                ticket.internal_status = "unassigned"
                db.session.commit()

                _login(client)
                resp = client.get('/')
                assert resp.status_code == 200
                assert b"actionable update" in resp.data
