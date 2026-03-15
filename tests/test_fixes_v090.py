"""Tests for v0.9.0 fixes: archive/reopen, staff approval, duplicate removal, send update."""
import re

from app import create_app
from app.extensions import db
from app.models import (
    Branch,
    Customer,
    Device,
    Diagnostic,
    IntakeSubmission,
    Part,
    PartOrder,
    PartOrderEvent,
    PartOrderLine,
    Quote,
    QuoteApproval,
    QuoteLine,
    QuoteOption,
    Role,
    StockLevel,
    StockLocation,
    StockMovement,
    StockReservation,
    Supplier,
    Ticket,
    TicketNote,
    User,
)
from app.models.role import role_permissions
from app.models.user import user_branch_access, user_roles
from app.services.seed_service import seed_phase1_data


class TestConfig:
    TESTING = True
    SECRET_KEY = "test-secret"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True
    BABEL_DEFAULT_LOCALE = "en"
    BABEL_DEFAULT_TIMEZONE = "UTC"
    SUPPORTED_LOCALES = ["en", "es"]
    DEFAULT_BRANCH_CODE = "HQ"


def _create_tables():
    tables = [
        Branch.__table__,
        Role.__table__,
        Customer.__table__,
        User.__table__,
        role_permissions,
        user_roles,
        user_branch_access,
        Device.__table__,
        Ticket.__table__,
        IntakeSubmission.__table__,
        Diagnostic.__table__,
        Quote.__table__,
        QuoteOption.__table__,
        QuoteLine.__table__,
        QuoteApproval.__table__,
        TicketNote.__table__,
        Supplier.__table__,
        Part.__table__,
        StockLocation.__table__,
        StockLevel.__table__,
        StockMovement.__table__,
        StockReservation.__table__,
        PartOrder.__table__,
        PartOrderLine.__table__,
        PartOrderEvent.__table__,
    ]
    for table in tables:
        table.create(bind=db.engine, checkfirst=True)


def _extract_csrf_token(html: bytes) -> str:
    match = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert match is not None
    return match.group(1).decode("utf-8")


def _login(client):
    page = client.get("/auth/login")
    token = _extract_csrf_token(page.data)
    resp = client.post(
        "/auth/login",
        data={"email": "admin@ironcore.com", "password": "admin1234", "csrf_token": token},
        follow_redirects=False,
    )
    assert resp.status_code == 302


def _seed_ticket(app, status="awaiting_diagnostics", ticket_number="HQ-20260315-0001"):
    with app.app_context():
        branch = Branch.query.filter_by(code="HQ").first()
        customer = Customer.query.filter_by(email="test.fix@example.com").first()
        if not customer:
            customer = Customer(
                full_name="Fix Test Customer",
                phone="+34999888777",
                email="test.fix@example.com",
                preferred_language="en",
                primary_branch=branch,
            )
            db.session.add(customer)
            db.session.flush()

        device = Device(
            customer=customer,
            category="phones",
            brand="Samsung",
            model="Galaxy S24",
            serial_number=f"SN-{ticket_number}",
        )
        db.session.add(device)
        db.session.flush()

        ticket = Ticket(
            ticket_number=ticket_number,
            branch_id=branch.id,
            customer_id=customer.id,
            device_id=device.id,
            internal_status=status,
            customer_status="Received",
            priority="normal",
        )
        db.session.add(ticket)
        db.session.commit()
        return ticket.id


def _seed_quote(app, ticket_id):
    with app.app_context():
        quote = Quote(ticket_id=ticket_id, version=1, status="draft", currency="EUR", language="en")
        db.session.add(quote)
        db.session.flush()
        option = QuoteOption(quote_id=quote.id, name="Standard Repair", position=1)
        db.session.add(option)
        db.session.flush()
        line = QuoteLine(option_id=option.id, line_type="labour", description="Test labour", quantity=1, unit_price=50)
        db.session.add(line)
        approval = QuoteApproval(quote_id=quote.id, status="pending", language="en")
        db.session.add(approval)
        db.session.commit()
        return quote.id


# ---------------------------------------------------------------------------
# Test 1: Ticket detail page does NOT show duplicate technician/workflow forms
# ---------------------------------------------------------------------------
def test_ticket_detail_no_duplicate_controls(monkeypatch):
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
    monkeypatch.setattr("app.services.auth_service.log_action", lambda *a, **kw: None)
    monkeypatch.setattr("app.blueprints.tickets.routes.log_action", lambda *a, **kw: None)

    ticket_id = _seed_ticket(app)
    client = app.test_client()
    _login(client)

    resp = client.get(f"/tickets/{ticket_id}")
    assert resp.status_code == 200
    html = resp.data.decode()
    # The right sidebar should have the technician form, but the top panel should NOT
    # Count occurrences of the assign form action
    assign_count = html.count(f"/tickets/{ticket_id}/assign")
    assert assign_count == 1, f"Expected 1 assign form, found {assign_count}"
    status_count = html.count(f"/tickets/{ticket_id}/status")
    assert status_count == 1, f"Expected 1 status form, found {status_count}"


# ---------------------------------------------------------------------------
# Test 2: Quote create page does NOT show duplicate terms_snapshot
# ---------------------------------------------------------------------------
def test_quote_create_no_duplicate_terms(monkeypatch):
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
    monkeypatch.setattr("app.services.auth_service.log_action", lambda *a, **kw: None)
    monkeypatch.setattr("app.blueprints.quotes.routes.log_action", lambda *a, **kw: None)

    ticket_id = _seed_ticket(app, ticket_number="HQ-20260315-0002")
    client = app.test_client()
    _login(client)

    resp = client.get(f"/quotes/ticket/{ticket_id}/new")
    assert resp.status_code == 200
    html = resp.data.decode()
    # Count occurrences of terms_snapshot field render
    terms_count = html.count("terms_snapshot")
    # Should appear once for label and once for field (name attribute) = 2 total, not 4
    assert terms_count <= 3, f"Expected at most 3 terms_snapshot occurrences (label+field+name), found {terms_count}"


# ---------------------------------------------------------------------------
# Test 3: Staff can approve/decline quotes from internal UI
# ---------------------------------------------------------------------------
def test_staff_manual_quote_approval(monkeypatch):
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
    monkeypatch.setattr("app.services.auth_service.log_action", lambda *a, **kw: None)
    monkeypatch.setattr("app.blueprints.quotes.routes.log_action", lambda *a, **kw: None)

    ticket_id = _seed_ticket(app, ticket_number="HQ-20260315-0003")
    quote_id = _seed_quote(app, ticket_id)

    client = app.test_client()
    _login(client)

    # Send quote first
    resp = client.post(f"/quotes/{quote_id}/send", follow_redirects=False)
    assert resp.status_code == 302

    # Approve via manual approval endpoint
    resp = client.post(
        f"/quotes/{quote_id}/manual-approval",
        data={"decision": "approved", "actor_name": "Staff Member", "actor_contact": "staff@ironcore.com"},
        follow_redirects=False,
    )
    assert resp.status_code == 302

    with app.app_context():
        quote = db.session.get(Quote, quote_id)
        assert quote.status == "approved"
        assert quote.ticket.internal_status == "in_repair"
        approvals = QuoteApproval.query.filter_by(quote_id=quote_id).all()
        manual = [a for a in approvals if a.method == "in_store_manual"]
        assert len(manual) == 1
        assert manual[0].status == "approved"
        assert manual[0].actor_name == "Staff Member"


def test_staff_manual_quote_decline(monkeypatch):
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
    monkeypatch.setattr("app.services.auth_service.log_action", lambda *a, **kw: None)
    monkeypatch.setattr("app.blueprints.quotes.routes.log_action", lambda *a, **kw: None)

    ticket_id = _seed_ticket(app, ticket_number="HQ-20260315-0004")
    quote_id = _seed_quote(app, ticket_id)

    client = app.test_client()
    _login(client)

    client.post(f"/quotes/{quote_id}/send", follow_redirects=False)
    resp = client.post(
        f"/quotes/{quote_id}/manual-approval",
        data={"decision": "declined", "actor_name": "Customer via phone"},
        follow_redirects=False,
    )
    assert resp.status_code == 302

    with app.app_context():
        quote = db.session.get(Quote, quote_id)
        assert quote.status == "declined"


# ---------------------------------------------------------------------------
# Test 4: Ticket archive and reopen
# ---------------------------------------------------------------------------
def test_ticket_archive_and_reopen(monkeypatch):
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
    monkeypatch.setattr("app.services.auth_service.log_action", lambda *a, **kw: None)
    monkeypatch.setattr("app.blueprints.tickets.routes.log_action", lambda *a, **kw: None)

    ticket_id = _seed_ticket(app, status="in_repair", ticket_number="HQ-20260315-0005")

    client = app.test_client()
    _login(client)

    # Archive the ticket
    resp = client.post(f"/tickets/{ticket_id}/archive", follow_redirects=False)
    assert resp.status_code == 302

    with app.app_context():
        ticket = db.session.get(Ticket, ticket_id)
        assert ticket.internal_status == "archived"
        notes = TicketNote.query.filter_by(ticket_id=ticket_id).all()
        archive_notes = [n for n in notes if "archived" in n.content.lower()]
        assert len(archive_notes) == 1

    # Reopen the ticket
    resp = client.post(f"/tickets/{ticket_id}/reopen", follow_redirects=False)
    assert resp.status_code == 302

    with app.app_context():
        ticket = db.session.get(Ticket, ticket_id)
        assert ticket.internal_status in ("unassigned", "assigned")
        notes = TicketNote.query.filter_by(ticket_id=ticket_id).all()
        reopen_notes = [n for n in notes if "reopened" in n.content.lower()]
        assert len(reopen_notes) == 1


def test_archived_tickets_hidden_from_list(monkeypatch):
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
    monkeypatch.setattr("app.services.auth_service.log_action", lambda *a, **kw: None)
    monkeypatch.setattr("app.blueprints.tickets.routes.log_action", lambda *a, **kw: None)

    ticket_id = _seed_ticket(app, status="archived", ticket_number="HQ-20260315-0006")

    client = app.test_client()
    _login(client)

    # Default list should not show archived ticket
    resp = client.get("/tickets/")
    assert resp.status_code == 200
    assert b"HQ-20260315-0006" not in resp.data

    # Archived filter should show it
    resp = client.get("/tickets/?status=archived")
    assert resp.status_code == 200
    assert b"HQ-20260315-0006" in resp.data


# ---------------------------------------------------------------------------
# Test 5: Quote detail page shows approve/decline button for sent quotes
# ---------------------------------------------------------------------------
def test_quote_detail_shows_staff_approval_button(monkeypatch):
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
    monkeypatch.setattr("app.services.auth_service.log_action", lambda *a, **kw: None)
    monkeypatch.setattr("app.blueprints.quotes.routes.log_action", lambda *a, **kw: None)

    ticket_id = _seed_ticket(app, ticket_number="HQ-20260315-0007")
    quote_id = _seed_quote(app, ticket_id)

    client = app.test_client()
    _login(client)

    # Send the quote
    client.post(f"/quotes/{quote_id}/send", follow_redirects=False)

    resp = client.get(f"/quotes/{quote_id}")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert "Approve / Decline" in html
    assert "staff-approval-modal" in html
    assert "Mark Expired" in html


# ---------------------------------------------------------------------------
# Test 6: Send update with optional email
# ---------------------------------------------------------------------------
def test_send_update_without_email(monkeypatch):
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
    monkeypatch.setattr("app.services.auth_service.log_action", lambda *a, **kw: None)
    monkeypatch.setattr("app.blueprints.tickets.routes.log_action", lambda *a, **kw: None)

    ticket_id = _seed_ticket(app, ticket_number="HQ-20260315-0008")

    client = app.test_client()
    _login(client)

    resp = client.post(
        f"/tickets/{ticket_id}/send-update",
        data={"content": "Your device is being repaired"},
        follow_redirects=False,
    )
    assert resp.status_code == 302

    with app.app_context():
        notes = TicketNote.query.filter_by(ticket_id=ticket_id).all()
        update_notes = [n for n in notes if n.note_type == "customer_update"]
        assert len(update_notes) == 1
        assert update_notes[0].content == "Your device is being repaired"
        # No communication note since email was not requested
        comm_notes = [n for n in notes if n.note_type == "communication"]
        assert len(comm_notes) == 0


def test_send_update_with_email(monkeypatch):
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
    monkeypatch.setattr("app.services.auth_service.log_action", lambda *a, **kw: None)
    monkeypatch.setattr("app.blueprints.tickets.routes.log_action", lambda *a, **kw: None)
    monkeypatch.setattr("app.services.communication_service.send_customer_update_email", lambda **kw: False)

    ticket_id = _seed_ticket(app, ticket_number="HQ-20260315-0009")

    client = app.test_client()
    _login(client)

    resp = client.post(
        f"/tickets/{ticket_id}/send-update",
        data={"content": "Repair complete", "send_email": "1"},
        follow_redirects=False,
    )
    assert resp.status_code == 302

    with app.app_context():
        notes = TicketNote.query.filter_by(ticket_id=ticket_id).all()
        update_notes = [n for n in notes if n.note_type == "customer_update"]
        assert len(update_notes) == 1
        comm_notes = [n for n in notes if n.note_type == "communication"]
        assert len(comm_notes) == 1
        assert "intended" in comm_notes[0].content


# ---------------------------------------------------------------------------
# Test 7: Ticket detail page shows quotes section prominently
# ---------------------------------------------------------------------------
def test_ticket_detail_shows_quotes_prominently(monkeypatch):
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
    monkeypatch.setattr("app.services.auth_service.log_action", lambda *a, **kw: None)
    monkeypatch.setattr("app.blueprints.tickets.routes.log_action", lambda *a, **kw: None)
    monkeypatch.setattr("app.blueprints.quotes.routes.log_action", lambda *a, **kw: None)

    ticket_id = _seed_ticket(app, ticket_number="HQ-20260315-0010")
    quote_id = _seed_quote(app, ticket_id)

    client = app.test_client()
    _login(client)

    resp = client.get(f"/tickets/{ticket_id}")
    assert resp.status_code == 200
    html = resp.data.decode()
    # Should show quotes section with quote details
    assert "Quotes" in html
    assert "+ New Quote" in html
    assert "View details" in html


# ---------------------------------------------------------------------------
# Test 8: Archived status in model
# ---------------------------------------------------------------------------
def test_archived_is_closed_status():
    assert "archived" in Ticket.CLOSED_STATUSES
    assert Ticket.STATUS_ARCHIVED == "archived"
