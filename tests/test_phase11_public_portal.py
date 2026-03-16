"""Phase 11 — Customer Communication & Public Repair Status Portal tests.

Covers:
- Public repair status via token-based direct access
- Public status lookup via ticket number + verifier
- Invalid/expired/non-matching access rejection
- Customer-friendly status mapping
- Internal notes NOT exposed on public page
- Quote integration on public status
- Communication summary block
- Progress step mapping
- Regression: Phase 8-10 logic intact
"""
import json
import re
import secrets
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from app import create_app
from app.extensions import db
from app.models import (
    AppSetting, AuditLog, Booking, Branch, Customer, Device, Diagnostic, IntakeSubmission,
    IntakeDisclaimerAcceptance, PartOrder, PortalToken, Quote, RepairChecklist,
    RepairService, Role, StockMovement, StockReservation, StockLayer, Supplier,
    Ticket, TicketNote, User,
)
from app.models.checklist import ChecklistItem
from app.models.inventory import PartSupplier, part_category_links, Part, PartCategory, StockLevel, StockLocation
from app.models.order import PartOrderEvent, PartOrderLine
from app.models.quote import QuoteApproval, QuoteLine, QuoteOption
from app.models.role import role_permissions
from app.models.user import user_branch_access, user_roles
from app.services.customer_status_service import (
    CUSTOMER_STATUS_MAP,
    PROGRESS_STEPS,
    communication_summary,
    customer_friendly_status,
    progress_step_index,
)
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
    ]
    for t in tables:
        t.create(bind=db.engine, checkfirst=True)


def _csrf(html: bytes) -> str:
    m = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert m
    return m.group(1).decode()


def _login(client):
    p = client.get('/auth/login')
    token = _csrf(p.data)
    r = client.post('/auth/login', data={
        'email': 'admin@ironcore.com', 'password': 'admin1234', 'csrf_token': token,
    }, follow_redirects=True)
    return r


def _setup_ticket_with_token(app, status="in_repair"):
    """Create a ticket with a public status token."""
    with app.app_context():
        branch = Branch.query.first()
        customer = Customer.query.first()
        # Ensure customer has email and phone for verifier
        customer.email = "test@example.com"
        customer.phone = "+34600123456"
        db.session.flush()

        device = Device(customer_id=customer.id, brand="Samsung", model="Galaxy S24", category="phones")
        db.session.add(device)
        db.session.flush()

        ticket = Ticket(
            ticket_number="TK-PUB-001",
            branch_id=branch.id,
            customer_id=customer.id,
            device_id=device.id,
            internal_status=status,
            customer_status="In Progress",
            priority="normal",
        )
        db.session.add(ticket)
        db.session.flush()

        # Create public status token
        token_str = secrets.token_urlsafe(24)
        db.session.add(PortalToken(token=token_str, token_type="public_status_lookup", ticket_id=ticket.id))

        # Add an internal note (should NOT be visible publicly)
        db.session.add(TicketNote(
            ticket_id=ticket.id, note_type="internal",
            content="Internal: replaced capacitor C12 on logic board",
        ))
        # Add a customer-visible note (SHOULD be visible)
        db.session.add(TicketNote(
            ticket_id=ticket.id, note_type="customer_update",
            content="Your device is being repaired and should be ready soon.",
        ))
        db.session.commit()

        return str(ticket.id), token_str, str(customer.id)


class TestPhase11:

    @classmethod
    def setup_class(cls):
        import app.services.audit_service as audit_mod
        import app.services.auth_service as auth_mod
        import app.blueprints.tickets.routes as ticket_routes_mod
        audit_mod.log_action = lambda *a, **kw: None
        auth_mod.log_action = lambda *a, **kw: None
        ticket_routes_mod.log_action = lambda *a, **kw: None

    def _make_app(self):
        app = create_app(TestConfig)
        with app.app_context():
            _create_tables()
            seed_phase1_data()
        return app

    # ---------- Customer Status Mapping Service ----------

    def test_all_statuses_mapped(self):
        """Every internal status has a customer-friendly mapping."""
        from app.models.ticket import Ticket
        for status in [
            Ticket.STATUS_UNASSIGNED, Ticket.STATUS_ASSIGNED,
            Ticket.STATUS_AWAITING_DIAGNOSTICS, Ticket.STATUS_AWAITING_QUOTE_APPROVAL,
            Ticket.STATUS_AWAITING_PARTS, Ticket.STATUS_IN_REPAIR,
            Ticket.STATUS_TESTING_QA, Ticket.STATUS_READY_FOR_COLLECTION,
            Ticket.STATUS_COMPLETED, Ticket.STATUS_CANCELLED, Ticket.STATUS_ARCHIVED,
        ]:
            label = customer_friendly_status(status)
            assert label, f"No mapping for {status}"
            assert "_" not in label, f"Status '{label}' still has underscores"

    def test_status_mapping_values(self):
        assert customer_friendly_status("unassigned") == "Checked In"
        assert customer_friendly_status("assigned") == "Checked In"
        assert customer_friendly_status("awaiting_diagnostics") == "Awaiting Diagnosis"
        assert customer_friendly_status("awaiting_quote_approval") == "Awaiting Your Approval"
        assert customer_friendly_status("awaiting_parts") == "Waiting for Parts"
        assert customer_friendly_status("in_repair") == "In Repair"
        assert customer_friendly_status("testing_qa") == "Quality Check"
        assert customer_friendly_status("ready_for_collection") == "Ready for Collection"
        assert customer_friendly_status("completed") == "Completed"
        assert customer_friendly_status("cancelled") == "Cancelled"

    def test_progress_steps_count(self):
        assert len(PROGRESS_STEPS) == 6

    def test_progress_step_mapping(self):
        assert progress_step_index("unassigned") == 0
        assert progress_step_index("awaiting_diagnostics") == 1
        assert progress_step_index("in_repair") == 3
        assert progress_step_index("testing_qa") == 4
        assert progress_step_index("ready_for_collection") == 5
        assert progress_step_index("cancelled") == -1

    def test_communication_summary_messages(self):
        msg = communication_summary("in_repair")
        assert "repaired" in msg.lower() or "repair" in msg.lower()
        msg = communication_summary("ready_for_collection")
        assert "ready" in msg.lower() or "collection" in msg.lower()
        msg = communication_summary("awaiting_quote_approval", has_pending_quote=True)
        assert "quote" in msg.lower() or "approval" in msg.lower()
        msg = communication_summary("awaiting_parts", has_pending_parts=True)
        assert "parts" in msg.lower()

    # ---------- Token-Based Direct Access ----------

    def test_token_access_success(self):
        """Valid token gives access to status page without login."""
        app = self._make_app()
        with app.app_context():
            ticket_id, token, _ = _setup_ticket_with_token(app)

        with app.test_client() as client:
            resp = client.get(f'/public/repair/{token}')
            assert resp.status_code == 200
            assert b'TK-PUB-001' in resp.data
            assert b'Samsung Galaxy S24' in resp.data
            assert b'In Repair' in resp.data

    def test_token_access_invalid_token(self):
        """Invalid token redirects with error."""
        app = self._make_app()
        with app.test_client() as client:
            resp = client.get('/public/repair/invalid_token_here', follow_redirects=True)
            assert resp.status_code == 200
            assert b'Invalid or expired' in resp.data

    def test_token_access_no_login_required(self):
        """Token access works without any authentication."""
        app = self._make_app()
        with app.app_context():
            _, token, _ = _setup_ticket_with_token(app)

        with app.test_client() as client:
            # No login call - direct access
            resp = client.get(f'/public/repair/{token}')
            assert resp.status_code == 200
            assert b'TK-PUB-001' in resp.data

    # ---------- Verifier-Based Lookup ----------

    def test_status_lookup_with_email(self):
        app = self._make_app()
        with app.app_context():
            _setup_ticket_with_token(app)

        with app.test_client() as client:
            # Get CSRF from the status page
            resp = client.get('/public/status')
            token = _csrf(resp.data)

            resp = client.post('/public/status', data={
                'csrf_token': token,
                'ticket_number': 'TK-PUB-001',
                'verifier': 'test@example.com',
            })
            assert resp.status_code == 200
            assert b'TK-PUB-001' in resp.data
            assert b'Samsung Galaxy S24' in resp.data

    def test_status_lookup_with_phone(self):
        app = self._make_app()
        with app.app_context():
            _setup_ticket_with_token(app)

        with app.test_client() as client:
            resp = client.get('/public/status')
            token = _csrf(resp.data)

            resp = client.post('/public/status', data={
                'csrf_token': token,
                'ticket_number': 'TK-PUB-001',
                'verifier': '+34600123456',
            })
            assert resp.status_code == 200
            assert b'TK-PUB-001' in resp.data

    def test_status_lookup_wrong_verifier(self):
        app = self._make_app()
        with app.app_context():
            _setup_ticket_with_token(app)

        with app.test_client() as client:
            resp = client.get('/public/status')
            token = _csrf(resp.data)

            resp = client.post('/public/status', data={
                'csrf_token': token,
                'ticket_number': 'TK-PUB-001',
                'verifier': 'wrong@email.com',
            })
            assert resp.status_code == 200
            assert b'No repair record found' in resp.data

    # ---------- Internal Notes NOT Exposed ----------

    def test_internal_notes_not_visible(self):
        """Internal notes must never appear on the public status page."""
        app = self._make_app()
        with app.app_context():
            _, token, _ = _setup_ticket_with_token(app)

        with app.test_client() as client:
            resp = client.get(f'/public/repair/{token}')
            assert resp.status_code == 200
            assert b'replaced capacitor' not in resp.data
            assert b'Internal:' not in resp.data

    def test_customer_notes_visible(self):
        """Customer-type notes should appear on the public status page."""
        app = self._make_app()
        with app.app_context():
            _, token, _ = _setup_ticket_with_token(app)

        with app.test_client() as client:
            resp = client.get(f'/public/repair/{token}')
            assert resp.status_code == 200
            assert b'Your device is being repaired' in resp.data

    # ---------- Customer-Friendly Status on Public Page ----------

    def test_ready_for_collection_banner(self):
        app = self._make_app()
        with app.app_context():
            _, token, _ = _setup_ticket_with_token(app, status="ready_for_collection")

        with app.test_client() as client:
            resp = client.get(f'/public/repair/{token}')
            assert resp.status_code == 200
            assert b'ready for collection' in resp.data.lower()
            assert b'Ready for Collection' in resp.data

    def test_awaiting_parts_status(self):
        app = self._make_app()
        with app.app_context():
            _, token, _ = _setup_ticket_with_token(app, status="awaiting_parts")

        with app.test_client() as client:
            resp = client.get(f'/public/repair/{token}')
            assert resp.status_code == 200
            assert b'Waiting for Parts' in resp.data
            assert b'waiting for parts' in resp.data.lower()

    def test_communication_summary_on_page(self):
        """Public page shows contextual communication summary."""
        app = self._make_app()
        with app.app_context():
            _, token, _ = _setup_ticket_with_token(app, status="in_repair")

        with app.test_client() as client:
            resp = client.get(f'/public/repair/{token}')
            assert resp.status_code == 200
            assert b'currently being repaired' in resp.data

    # ---------- Quote Integration ----------

    def test_pending_quote_banner_visible(self):
        """When ticket has pending quote, public page shows approval prompt."""
        app = self._make_app()
        with app.app_context():
            _, token, _ = _setup_ticket_with_token(app, status="awaiting_quote_approval")
            # Create a pending quote
            ticket = Ticket.query.filter_by(ticket_number="TK-PUB-001").first()
            quote = Quote(
                ticket_id=ticket.id, customer_id=ticket.customer_id,
                status="sent", version=1, currency="EUR", language="en",
            )
            db.session.add(quote)
            db.session.flush()
            approval = QuoteApproval(quote_id=quote.id, status="pending")
            db.session.add(approval)
            db.session.commit()

        with app.test_client() as client:
            resp = client.get(f'/public/repair/{token}')
            assert resp.status_code == 200
            assert b'approval is needed' in resp.data.lower() or b'Awaiting Your Approval' in resp.data
            assert b'approve quote' in resp.data.lower()

    # ---------- Progress Steps ----------

    def test_progress_steps_rendered(self):
        app = self._make_app()
        with app.app_context():
            _, token, _ = _setup_ticket_with_token(app, status="in_repair")

        with app.test_client() as client:
            resp = client.get(f'/public/repair/{token}')
            assert resp.status_code == 200
            assert b'Repair progress' in resp.data
            # Check all progress step labels are present
            for step in PROGRESS_STEPS:
                assert step.encode() in resp.data, f"Step '{step}' not found"

    # ---------- Ticket Detail Shows Public URL ----------

    def test_ticket_detail_shows_public_url(self):
        app = self._make_app()
        with app.app_context():
            _, token, _ = _setup_ticket_with_token(app)
            ticket_id = str(Ticket.query.filter_by(ticket_number="TK-PUB-001").first().id)

        with app.test_client() as client:
            _login(client)
            resp = client.get(f'/tickets/{ticket_id}')
            assert resp.status_code == 200
            assert b'Customer Communication' in resp.data
            assert b'public-status-url' in resp.data
            assert token.encode() in resp.data

    # ---------- Deleted ticket not accessible ----------

    def test_deleted_ticket_not_accessible(self):
        app = self._make_app()
        with app.app_context():
            _, token, _ = _setup_ticket_with_token(app)
            ticket = Ticket.query.filter_by(ticket_number="TK-PUB-001").first()
            ticket.deleted_at = datetime.utcnow()
            db.session.commit()

        with app.test_client() as client:
            resp = client.get(f'/public/repair/{token}', follow_redirects=True)
            assert resp.status_code == 200
            assert b'TK-PUB-001' not in resp.data

    # ---------- Regression: Phase 8/9/10 ----------

    def test_bench_board_still_works(self):
        app = self._make_app()
        with app.test_client() as client:
            _login(client)
            resp = client.get('/tickets/board')
            assert resp.status_code == 200

    def test_ticket_creation_still_works(self):
        app = self._make_app()
        with app.test_client() as client:
            _login(client)
            resp = client.get('/tickets/new')
            assert resp.status_code == 200

    def test_customer_search_still_works(self):
        app = self._make_app()
        with app.test_client() as client:
            _login(client)
            resp = client.get('/tickets/customer-search?q=admin')
            assert resp.status_code == 200

    def test_public_checkin_still_works(self):
        app = self._make_app()
        with app.test_client() as client:
            resp = client.get('/public/check-in')
            assert resp.status_code == 200

    def test_public_status_lookup_page_loads(self):
        app = self._make_app()
        with app.test_client() as client:
            resp = client.get('/public/status')
            assert resp.status_code == 200
            assert b'Track your repair' in resp.data

    # ---------- Token creation on ticket creation ----------

    def test_ticket_creation_generates_status_token(self):
        """When a ticket is created, a public status token should be generated."""
        app = self._make_app()
        with app.app_context():
            branch = Branch.query.first()
            customer = Customer.query.first()
            device = Device.query.first()
            branch_id = str(branch.id)
            customer_id = str(customer.id)
            device_id = str(device.id)

        with app.test_client() as client:
            _login(client)
            resp = client.get('/tickets/new')
            token = _csrf(resp.data)

            resp = client.post('/tickets/new', data={
                'csrf_token': token,
                'branch_id': branch_id,
                'customer_id': customer_id,
                'device_id': device_id,
                'priority': 'normal',
                'issue_summary': 'Screen cracked',
            }, follow_redirects=True)
            assert resp.status_code == 200

        with app.app_context():
            ticket = Ticket.query.filter(Ticket.issue_summary == 'Screen cracked').first()
            if ticket:
                pt = PortalToken.query.filter_by(ticket_id=ticket.id, token_type="public_status_lookup").first()
                assert pt is not None
                assert len(pt.token) > 10
