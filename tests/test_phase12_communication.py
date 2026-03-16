"""Phase 12 — Notifications, Portal Delivery & Customer Communication Actions tests.

Covers:
- Staff communication panel on ticket detail
- Communication event logging
- Customer message template generation
- Portal token regeneration and revocation
- Ready-for-collection communication shortcut
- Quote approval communication shortcut
- Communication history block
- Portal security hardening
- Regression: Phase 8-11 behavior intact
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
    AppSetting, AuditLog, Booking, Branch, Customer, Device, Diagnostic,
    IntakeSubmission, IntakeDisclaimerAcceptance, PartOrder, PortalToken,
    Quote, RepairChecklist, RepairService, Role, StockMovement,
    StockReservation, StockLayer, Supplier, Ticket, TicketNote, User,
)
from app.models.checklist import ChecklistItem
from app.models.inventory import PartSupplier, part_category_links, Part, PartCategory, StockLevel, StockLocation
from app.models.order import PartOrderEvent, PartOrderLine
from app.models.quote import QuoteApproval, QuoteLine, QuoteOption
from app.models.role import role_permissions
from app.models.user import user_branch_access, user_roles
from app.services.customer_communication_service import (
    available_templates,
    generate_message,
    get_portal_token,
    regenerate_portal_token,
    revoke_portal_token,
    suggested_template_key,
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
    """Create a ticket with a public status token and return (ticket_id, token, customer_id)."""
    with app.app_context():
        branch = Branch.query.first()
        customer = Customer.query.first()
        customer.email = "test@example.com"
        customer.phone = "+34600123456"
        db.session.flush()

        device = Device(customer_id=customer.id, brand="Samsung", model="Galaxy S24", category="phones")
        db.session.add(device)
        db.session.flush()

        ticket = Ticket(
            ticket_number="TK-P12-001",
            branch_id=branch.id,
            customer_id=customer.id,
            device_id=device.id,
            internal_status=status,
            customer_status="In Progress",
            priority="normal",
        )
        db.session.add(ticket)
        db.session.flush()

        token_str = secrets.token_urlsafe(24)
        db.session.add(PortalToken(token=token_str, token_type="public_status_lookup", ticket_id=ticket.id))

        # Internal note (should NOT be visible publicly)
        db.session.add(TicketNote(
            ticket_id=ticket.id, note_type="internal",
            content="Internal: replaced capacitor C12",
        ))
        # Customer-visible note
        db.session.add(TicketNote(
            ticket_id=ticket.id, note_type="customer_update",
            content="Your device is being repaired.",
        ))
        db.session.commit()

        return str(ticket.id), token_str, str(customer.id)


class TestPhase12:

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

    # ===== Feature 1: Staff Communication Actions =====

    def test_ticket_detail_shows_communication_panel(self):
        """Ticket detail has the Customer Communication panel."""
        app = self._make_app()
        with app.app_context():
            ticket_id, token, _ = _setup_ticket_with_token(app)

        with app.test_client() as client:
            _login(client)
            resp = client.get(f'/tickets/{ticket_id}')
            assert resp.status_code == 200
            assert b'Customer Communication' in resp.data
            assert b'customer-communication-panel' in resp.data

    def test_portal_link_shown_in_communication_panel(self):
        """Portal link is visible in the communication panel."""
        app = self._make_app()
        with app.app_context():
            ticket_id, token, _ = _setup_ticket_with_token(app)

        with app.test_client() as client:
            _login(client)
            resp = client.get(f'/tickets/{ticket_id}')
            assert resp.status_code == 200
            assert b'public-status-url' in resp.data
            assert token.encode() in resp.data

    def test_quote_approval_link_shown_when_pending_quote(self):
        """Quote approval link appears when a pending quote exists."""
        app = self._make_app()
        with app.app_context():
            ticket_id, token, _ = _setup_ticket_with_token(app, status="awaiting_quote_approval")
            ticket = Ticket.query.filter_by(ticket_number="TK-P12-001").first()
            quote = Quote(ticket_id=ticket.id, customer_id=ticket.customer_id,
                          status="sent", version=1, currency="EUR", language="en")
            db.session.add(quote)
            db.session.flush()
            approval = QuoteApproval(quote_id=quote.id, status="pending")
            db.session.add(approval)
            db.session.commit()
            approval_token = approval.token

        with app.test_client() as client:
            _login(client)
            resp = client.get(f'/tickets/{ticket_id}')
            assert resp.status_code == 200
            assert b'quote-approval-url' in resp.data
            assert approval_token.encode() in resp.data

    def test_quote_link_hidden_when_no_pending_quote(self):
        """Quote approval link is not shown when there is no pending quote."""
        app = self._make_app()
        with app.app_context():
            ticket_id, _, _ = _setup_ticket_with_token(app)

        with app.test_client() as client:
            _login(client)
            resp = client.get(f'/tickets/{ticket_id}')
            assert resp.status_code == 200
            assert b'quote-approval-url' not in resp.data

    def test_ready_notification_button_shown_when_ready(self):
        """Ready Notification button appears when ticket is ready for collection."""
        app = self._make_app()
        with app.app_context():
            ticket_id, _, _ = _setup_ticket_with_token(app, status="ready_for_collection")

        with app.test_client() as client:
            _login(client)
            resp = client.get(f'/tickets/{ticket_id}')
            assert resp.status_code == 200
            assert b'Ready Notification' in resp.data

    def test_ready_notification_button_hidden_when_not_ready(self):
        """Ready Notification button hidden when ticket is not ready."""
        app = self._make_app()
        with app.app_context():
            ticket_id, _, _ = _setup_ticket_with_token(app, status="in_repair")

        with app.test_client() as client:
            _login(client)
            resp = client.get(f'/tickets/{ticket_id}')
            assert resp.status_code == 200
            assert b'Ready Notification' not in resp.data

    def test_message_builder_button_present(self):
        """Message Builder button is present in communication panel."""
        app = self._make_app()
        with app.app_context():
            ticket_id, _, _ = _setup_ticket_with_token(app)

        with app.test_client() as client:
            _login(client)
            resp = client.get(f'/tickets/{ticket_id}')
            assert resp.status_code == 200
            assert b'Message Builder' in resp.data
            assert b'message-builder-modal' in resp.data

    # ===== Feature 2: Communication Event Logging =====

    def test_log_communication_action(self):
        """POST to log-communication creates a communication note."""
        app = self._make_app()
        with app.app_context():
            ticket_id, _, _ = _setup_ticket_with_token(app)

        with app.test_client() as client:
            _login(client)
            page = client.get(f'/tickets/{ticket_id}')
            csrf = _csrf(page.data)
            resp = client.post(f'/tickets/{ticket_id}/log-communication',
                               json={"action_type": "portal_link_copied"},
                               headers={"X-CSRFToken": csrf})
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["ok"] is True

        with app.app_context():
            ticket = Ticket.query.filter_by(ticket_number="TK-P12-001").first()
            comm_notes = TicketNote.query.filter_by(
                ticket_id=ticket.id, note_type="communication"
            ).all()
            assert any("Portal status link copied" in n.content for n in comm_notes)

    def test_log_communication_quote_link_copied(self):
        """Logging quote_link_copied action creates correct note."""
        app = self._make_app()
        with app.app_context():
            ticket_id, _, _ = _setup_ticket_with_token(app)

        with app.test_client() as client:
            _login(client)
            page = client.get(f'/tickets/{ticket_id}')
            csrf = _csrf(page.data)
            resp = client.post(f'/tickets/{ticket_id}/log-communication',
                               json={"action_type": "quote_link_copied"},
                               headers={"X-CSRFToken": csrf})
            assert resp.status_code == 200

        with app.app_context():
            ticket = Ticket.query.filter_by(ticket_number="TK-P12-001").first()
            comm_notes = TicketNote.query.filter_by(
                ticket_id=ticket.id, note_type="communication"
            ).all()
            assert any("Quote approval link copied" in n.content for n in comm_notes)

    # ===== Feature 3: Message Template Generation =====

    def test_generate_message_contains_ticket_context(self):
        """Generated messages contain ticket number and device summary."""
        msg = generate_message(
            "checked_in",
            ticket_number="TK-001",
            device_summary="Samsung Galaxy S24",
            customer_name="John",
            portal_url="https://example.com/public/repair/abc123",
        )
        assert "TK-001" in msg["body"]
        assert "Samsung Galaxy S24" in msg["body"]
        assert "John" in msg["body"]
        assert "https://example.com/public/repair/abc123" in msg["body"]
        assert msg["subject"]

    def test_generate_message_includes_portal_url(self):
        """Portal URL is included in generated message."""
        msg = generate_message(
            "in_repair",
            ticket_number="TK-002",
            device_summary="iPhone 15",
            portal_url="https://example.com/repair/token123",
        )
        assert "https://example.com/repair/token123" in msg["body"]

    def test_generate_message_includes_quote_url(self):
        """Quote approval URL is included when template is quote_ready."""
        msg = generate_message(
            "quote_ready",
            ticket_number="TK-003",
            device_summary="MacBook Pro",
            portal_url="https://example.com/repair/abc",
            quote_approval_url="https://example.com/public/quote/xyz",
        )
        assert "https://example.com/public/quote/xyz" in msg["body"]

    def test_generate_message_ready_for_collection(self):
        """Ready for collection message uses customer-friendly wording."""
        msg = generate_message(
            "ready_for_collection",
            ticket_number="TK-004",
            device_summary="iPad Air",
            customer_name="Maria",
            portal_url="https://example.com/repair/def",
        )
        assert "ready" in msg["body"].lower()
        assert "collection" in msg["body"].lower()
        assert "Maria" in msg["body"]
        assert "iPad Air" in msg["body"]

    def test_generate_message_wording_is_customer_safe(self):
        """Messages don't contain technical jargon."""
        for key in ["checked_in", "awaiting_diagnosis", "in_repair", "ready_for_collection", "completed"]:
            msg = generate_message(
                key, ticket_number="TK-X", device_summary="Phone",
                portal_url="https://x.com/r/t",
            )
            body_lower = msg["body"].lower()
            # Should not contain internal status names
            assert "unassigned" not in body_lower
            assert "awaiting_diagnostics" not in body_lower
            assert "testing_qa" not in body_lower

    def test_available_templates_returns_all(self):
        """All expected templates are available."""
        templates = available_templates()
        keys = [t["key"] for t in templates]
        assert "checked_in" in keys
        assert "ready_for_collection" in keys
        assert "quote_ready" in keys
        assert len(templates) >= 7

    def test_suggested_template_key(self):
        """Suggested template matches internal status."""
        assert suggested_template_key("in_repair") == "in_repair"
        assert suggested_template_key("ready_for_collection") == "ready_for_collection"
        assert suggested_template_key("awaiting_quote_approval") == "quote_ready"
        assert suggested_template_key("unassigned") == "checked_in"
        assert suggested_template_key("assigned") == "checked_in"

    def test_generate_message_api_endpoint(self):
        """POST /tickets/<id>/generate-message returns JSON with message."""
        app = self._make_app()
        with app.app_context():
            ticket_id, _, _ = _setup_ticket_with_token(app)

        with app.test_client() as client:
            _login(client)
            page = client.get(f'/tickets/{ticket_id}')
            csrf = _csrf(page.data)
            resp = client.post(f'/tickets/{ticket_id}/generate-message',
                               json={"template_key": "in_repair"},
                               headers={"X-CSRFToken": csrf})
            assert resp.status_code == 200
            data = resp.get_json()
            assert "subject" in data
            assert "body" in data
            assert "TK-P12-001" in data["body"]
            assert "Samsung Galaxy S24" in data["body"]

    def test_generate_message_includes_opening_hours(self):
        """Ready-for-collection message includes opening hours when available."""
        msg = generate_message(
            "ready_for_collection",
            ticket_number="TK-005",
            device_summary="Phone",
            portal_url="https://x.com/r/t",
            opening_hours="Mon-Fri 9:00-18:00",
        )
        assert "Mon-Fri 9:00-18:00" in msg["body"]

    # ===== Feature 4: Portal Token Regenerate / Revoke =====

    def test_regenerate_portal_token_invalidates_old(self):
        """After regeneration, old token no longer works."""
        app = self._make_app()
        with app.app_context():
            ticket_id, old_token, _ = _setup_ticket_with_token(app)

        with app.test_client() as client:
            _login(client)
            page = client.get(f'/tickets/{ticket_id}')
            csrf = _csrf(page.data)
            resp = client.post(f'/tickets/{ticket_id}/regenerate-portal-token',
                               data={"csrf_token": csrf}, follow_redirects=True)
            assert resp.status_code == 200
            assert b'Portal link regenerated' in resp.data

        # Old token should fail
        with app.test_client() as client:
            resp = client.get(f'/public/repair/{old_token}', follow_redirects=True)
            assert b'Invalid or expired' in resp.data

    def test_regenerate_creates_new_working_token(self):
        """After regeneration, a new token is created and works."""
        app = self._make_app()
        with app.app_context():
            ticket_id, old_token, _ = _setup_ticket_with_token(app)

        with app.test_client() as client:
            _login(client)
            page = client.get(f'/tickets/{ticket_id}')
            csrf = _csrf(page.data)
            client.post(f'/tickets/{ticket_id}/regenerate-portal-token',
                        data={"csrf_token": csrf}, follow_redirects=True)

        # Get the new token
        with app.app_context():
            ticket = Ticket.query.filter_by(ticket_number="TK-P12-001").first()
            new_pt = PortalToken.query.filter_by(
                ticket_id=ticket.id, token_type="public_status_lookup"
            ).first()
            assert new_pt is not None
            assert new_pt.token != old_token
            new_token = new_pt.token

        # New token should work
        with app.test_client() as client:
            resp = client.get(f'/public/repair/{new_token}')
            assert resp.status_code == 200
            assert b'TK-P12-001' in resp.data

    def test_revoke_portal_token_disables_access(self):
        """After revocation, token no longer works."""
        app = self._make_app()
        with app.app_context():
            ticket_id, token, _ = _setup_ticket_with_token(app)

        with app.test_client() as client:
            _login(client)
            page = client.get(f'/tickets/{ticket_id}')
            csrf = _csrf(page.data)
            resp = client.post(f'/tickets/{ticket_id}/revoke-portal-token',
                               data={"csrf_token": csrf}, follow_redirects=True)
            assert resp.status_code == 200
            assert b'Portal link revoked' in resp.data

        # Token should fail
        with app.test_client() as client:
            resp = client.get(f'/public/repair/{token}', follow_redirects=True)
            assert b'Invalid or expired' in resp.data

    def test_regeneration_creates_communication_note(self):
        """Token regeneration creates a communication note in history."""
        app = self._make_app()
        with app.app_context():
            ticket_id, _, _ = _setup_ticket_with_token(app)

        with app.test_client() as client:
            _login(client)
            page = client.get(f'/tickets/{ticket_id}')
            csrf = _csrf(page.data)
            client.post(f'/tickets/{ticket_id}/regenerate-portal-token',
                        data={"csrf_token": csrf}, follow_redirects=True)

        with app.app_context():
            ticket = Ticket.query.filter_by(ticket_number="TK-P12-001").first()
            comm_notes = TicketNote.query.filter_by(
                ticket_id=ticket.id, note_type="communication"
            ).all()
            assert any("regenerated" in n.content.lower() for n in comm_notes)

    def test_revocation_creates_communication_note(self):
        """Token revocation creates a communication note in history."""
        app = self._make_app()
        with app.app_context():
            ticket_id, _, _ = _setup_ticket_with_token(app)

        with app.test_client() as client:
            _login(client)
            page = client.get(f'/tickets/{ticket_id}')
            csrf = _csrf(page.data)
            client.post(f'/tickets/{ticket_id}/revoke-portal-token',
                        data={"csrf_token": csrf}, follow_redirects=True)

        with app.app_context():
            ticket = Ticket.query.filter_by(ticket_number="TK-P12-001").first()
            comm_notes = TicketNote.query.filter_by(
                ticket_id=ticket.id, note_type="communication"
            ).all()
            assert any("revoked" in n.content.lower() for n in comm_notes)

    def test_unrelated_tokens_unaffected_by_regeneration(self):
        """Regenerating a status token does not affect other token types."""
        app = self._make_app()
        with app.app_context():
            ticket_id, _, _ = _setup_ticket_with_token(app)
            ticket = Ticket.query.filter_by(ticket_number="TK-P12-001").first()
            # Add an intake confirmation token (different type)
            intake_token = PortalToken(
                token=secrets.token_urlsafe(24),
                token_type="public_intake_confirmation",
                ticket_id=ticket.id,
            )
            db.session.add(intake_token)
            db.session.commit()
            intake_token_str = intake_token.token

        with app.test_client() as client:
            _login(client)
            page = client.get(f'/tickets/{ticket_id}')
            csrf = _csrf(page.data)
            client.post(f'/tickets/{ticket_id}/regenerate-portal-token',
                        data={"csrf_token": csrf}, follow_redirects=True)

        # Intake confirmation token should still exist
        with app.app_context():
            existing = PortalToken.query.filter_by(token=intake_token_str).first()
            assert existing is not None
            assert existing.token_type == "public_intake_confirmation"

    # ===== Feature 5 & 6: Communication Shortcuts =====

    def test_quote_notification_button_shown_when_pending_quote(self):
        """Quote Notification button appears when pending quote exists."""
        app = self._make_app()
        with app.app_context():
            ticket_id, _, _ = _setup_ticket_with_token(app, status="awaiting_quote_approval")
            ticket = Ticket.query.filter_by(ticket_number="TK-P12-001").first()
            quote = Quote(ticket_id=ticket.id, customer_id=ticket.customer_id,
                          status="sent", version=1, currency="EUR", language="en")
            db.session.add(quote)
            db.session.flush()
            db.session.add(QuoteApproval(quote_id=quote.id, status="pending"))
            db.session.commit()

        with app.test_client() as client:
            _login(client)
            resp = client.get(f'/tickets/{ticket_id}')
            assert resp.status_code == 200
            assert b'Quote Notification' in resp.data

    # ===== Feature 7: Communication History Block =====

    def test_communication_history_shown_on_ticket_detail(self):
        """Communication history is visible when communication notes exist."""
        app = self._make_app()
        with app.app_context():
            ticket_id, _, _ = _setup_ticket_with_token(app)
            ticket = Ticket.query.filter_by(ticket_number="TK-P12-001").first()
            db.session.add(TicketNote(
                ticket_id=ticket.id, note_type="communication",
                content="Portal status link copied to clipboard",
            ))
            db.session.commit()

        with app.test_client() as client:
            _login(client)
            resp = client.get(f'/tickets/{ticket_id}')
            assert resp.status_code == 200
            assert b'Communication History' in resp.data
            assert b'communication-history' in resp.data
            assert b'Portal status link copied' in resp.data

    def test_communication_history_hidden_when_empty(self):
        """Communication history block is not shown when there are no communication notes."""
        app = self._make_app()
        with app.app_context():
            ticket_id, _, _ = _setup_ticket_with_token(app)

        with app.test_client() as client:
            _login(client)
            resp = client.get(f'/tickets/{ticket_id}')
            assert resp.status_code == 200
            # No communication notes exist, so the block should not appear
            assert b'communication-history' not in resp.data

    def test_communication_history_not_on_public_page(self):
        """Public status page never shows communication history block."""
        app = self._make_app()
        with app.app_context():
            ticket_id, token, _ = _setup_ticket_with_token(app)
            ticket = Ticket.query.filter_by(ticket_number="TK-P12-001").first()
            db.session.add(TicketNote(
                ticket_id=ticket.id, note_type="communication",
                content="Portal link copied to clipboard",
            ))
            db.session.commit()

        with app.test_client() as client:
            resp = client.get(f'/public/repair/{token}')
            assert resp.status_code == 200
            assert b'Communication History' not in resp.data
            assert b'communication-history' not in resp.data

    # ===== Feature 8: Portal Security Hardening =====

    def test_short_token_rejected(self):
        """Tokens shorter than 20 chars are rejected immediately."""
        app = self._make_app()
        with app.test_client() as client:
            resp = client.get('/public/repair/short', follow_redirects=True)
            assert resp.status_code == 200
            assert b'Invalid or expired' in resp.data

    def test_very_long_token_rejected(self):
        """Tokens longer than 50 chars are rejected immediately."""
        app = self._make_app()
        long_token = "a" * 60
        with app.test_client() as client:
            resp = client.get(f'/public/repair/{long_token}', follow_redirects=True)
            assert resp.status_code == 200
            assert b'Invalid or expired' in resp.data

    def test_revoked_token_fails(self):
        """A revoked (deleted) token fails to resolve."""
        app = self._make_app()
        with app.app_context():
            ticket_id, token, _ = _setup_ticket_with_token(app)
            # Revoke directly
            revoke_portal_token(Ticket.query.filter_by(ticket_number="TK-P12-001").first().id)
            db.session.commit()

        with app.test_client() as client:
            resp = client.get(f'/public/repair/{token}', follow_redirects=True)
            assert b'Invalid or expired' in resp.data

    def test_valid_token_still_works(self):
        """A valid token still provides access after Phase 12 hardening."""
        app = self._make_app()
        with app.app_context():
            _, token, _ = _setup_ticket_with_token(app)

        with app.test_client() as client:
            resp = client.get(f'/public/repair/{token}')
            assert resp.status_code == 200
            assert b'TK-P12-001' in resp.data

    def test_internal_notes_still_hidden_publicly(self):
        """Internal notes remain hidden on the public page."""
        app = self._make_app()
        with app.app_context():
            _, token, _ = _setup_ticket_with_token(app)

        with app.test_client() as client:
            resp = client.get(f'/public/repair/{token}')
            assert resp.status_code == 200
            assert b'replaced capacitor' not in resp.data

    # ===== Regression: Phase 8-11 behavior =====

    def test_regression_bench_board(self):
        app = self._make_app()
        with app.test_client() as client:
            _login(client)
            resp = client.get('/tickets/board')
            assert resp.status_code == 200

    def test_regression_ticket_creation(self):
        app = self._make_app()
        with app.test_client() as client:
            _login(client)
            resp = client.get('/tickets/new')
            assert resp.status_code == 200

    def test_regression_customer_search(self):
        app = self._make_app()
        with app.test_client() as client:
            _login(client)
            resp = client.get('/tickets/customer-search?q=admin')
            assert resp.status_code == 200

    def test_regression_public_checkin(self):
        app = self._make_app()
        with app.test_client() as client:
            resp = client.get('/public/check-in')
            assert resp.status_code == 200

    def test_regression_public_status_lookup(self):
        app = self._make_app()
        with app.test_client() as client:
            resp = client.get('/public/status')
            assert resp.status_code == 200
            assert b'Track your repair' in resp.data

    def test_regression_phase11_token_access_works(self):
        """Phase 11 token access still works correctly."""
        app = self._make_app()
        with app.app_context():
            _, token, _ = _setup_ticket_with_token(app)

        with app.test_client() as client:
            resp = client.get(f'/public/repair/{token}')
            assert resp.status_code == 200
            assert b'Samsung Galaxy S24' in resp.data

    def test_regression_quote_approval_integration(self):
        """Quote approval flow from public portal still works."""
        app = self._make_app()
        with app.app_context():
            _, token, _ = _setup_ticket_with_token(app, status="awaiting_quote_approval")
            ticket = Ticket.query.filter_by(ticket_number="TK-P12-001").first()
            quote = Quote(ticket_id=ticket.id, customer_id=ticket.customer_id,
                          status="sent", version=1, currency="EUR", language="en")
            db.session.add(quote)
            db.session.flush()
            approval = QuoteApproval(quote_id=quote.id, status="pending")
            db.session.add(approval)
            db.session.commit()
            approval_token = approval.token

        with app.test_client() as client:
            resp = client.get(f'/public/quote/{approval_token}')
            assert resp.status_code == 200
