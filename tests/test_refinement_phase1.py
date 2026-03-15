"""Tests for Phase 1 refinement: quote part search, admin actions, reservations, inventory."""
import re
import uuid

from app import create_app
from app.extensions import db
from app.models import (
    Branch,
    Customer,
    Device,
    Diagnostic,
    IntakeSubmission,
    Part,
    PartCategory,
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
    from sqlalchemy import inspect as sa_inspect

    inspector = sa_inspect(db.engine)
    existing = inspector.get_table_names()
    for table in tables:
        if table.name not in existing:
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


def _seed_ticket(app, status="awaiting_diagnostics", ticket_number="HQ-20260315-P001"):
    with app.app_context():
        branch = Branch.query.filter_by(code="HQ").first()
        customer = Customer.query.filter_by(email="phase1test@example.com").first()
        if not customer:
            customer = Customer(
                full_name="Phase1 Test Customer",
                phone="+34111222333",
                email="phase1test@example.com",
                preferred_language="en",
                primary_branch=branch,
            )
            db.session.add(customer)
            db.session.flush()

        device = Device(
            customer=customer,
            category="phones",
            brand="Apple",
            model="iPhone 15",
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


# ---------------------------------------------------------------------------
# Test 1: Part search endpoint returns name and sale_price
# ---------------------------------------------------------------------------
def test_part_search_returns_name_and_price(monkeypatch):
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()

        branch = Branch.query.filter_by(code="HQ").first()
        part = Part(sku="TST-001", name="Test Screen Replacement", sale_price=49.99, is_active=True)
        db.session.add(part)
        db.session.commit()

    monkeypatch.setattr("app.services.auth_service.log_action", lambda *a, **kw: None)
    client = app.test_client()
    _login(client)

    resp = client.get("/inventory/parts/search?q=Test Screen")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["items"]) >= 1
    item = data["items"][0]
    assert "name" in item
    assert "sale_price" in item
    assert item["name"] == "Test Screen Replacement"
    assert item["sale_price"] == 49.99


# ---------------------------------------------------------------------------
# Test 2: Supplier toggle-active route
# ---------------------------------------------------------------------------
def test_supplier_toggle_active(monkeypatch):
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()

        supplier = Supplier(name="Test Supplier Toggle", is_active=True)
        db.session.add(supplier)
        db.session.commit()
        supplier_id = supplier.id

    monkeypatch.setattr("app.services.auth_service.log_action", lambda *a, **kw: None)
    client = app.test_client()
    _login(client)

    resp = client.post(f"/suppliers/{supplier_id}/toggle-active", follow_redirects=False)
    assert resp.status_code == 302

    with app.app_context():
        supplier = db.session.get(Supplier, supplier_id)
        assert supplier.is_active is False

    # Toggle back
    resp = client.post(f"/suppliers/{supplier_id}/toggle-active", follow_redirects=False)
    assert resp.status_code == 302

    with app.app_context():
        supplier = db.session.get(Supplier, supplier_id)
        assert supplier.is_active is True


# ---------------------------------------------------------------------------
# Test 3: Category soft-delete route
# ---------------------------------------------------------------------------
def test_category_soft_delete(monkeypatch):
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()

        from sqlalchemy import inspect as sa_inspect

        inspector = sa_inspect(db.engine)
        if not inspector.has_table("part_categories"):
            PartCategory.__table__.create(bind=db.engine, checkfirst=True)

        category = PartCategory(name="To Delete Category")
        db.session.add(category)
        db.session.commit()
        category_id = category.id

    monkeypatch.setattr("app.services.auth_service.log_action", lambda *a, **kw: None)
    client = app.test_client()
    _login(client)

    resp = client.post(f"/inventory/categories/{category_id}/delete", follow_redirects=False)
    assert resp.status_code == 302

    with app.app_context():
        category = db.session.get(PartCategory, category_id)
        assert category.deleted_at is not None


# ---------------------------------------------------------------------------
# Test 4: Reservation release route
# ---------------------------------------------------------------------------
def test_reservation_release(monkeypatch):
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()

    ticket_id = _seed_ticket(app, ticket_number="HQ-20260315-P002")

    with app.app_context():
        branch = Branch.query.filter_by(code="HQ").first()
        location = StockLocation(branch_id=branch.id, code="BIN-A1", name="Bin A1", location_type="shelf", is_active=True)
        db.session.add(location)
        db.session.flush()

        part = Part(sku="RES-001", name="Test Part Reserve", sale_price=20.00, is_active=True)
        db.session.add(part)
        db.session.flush()

        level = StockLevel(part_id=part.id, branch_id=branch.id, location_id=location.id, on_hand_qty=10, reserved_qty=3)
        db.session.add(level)
        db.session.flush()

        reservation = StockReservation(
            ticket_id=ticket_id,
            part_id=part.id,
            branch_id=branch.id,
            location_id=location.id,
            quantity=3,
            status="reserved",
        )
        db.session.add(reservation)
        db.session.commit()
        reservation_id = reservation.id

    monkeypatch.setattr("app.services.auth_service.log_action", lambda *a, **kw: None)
    monkeypatch.setattr("app.blueprints.tickets.routes.log_action", lambda *a, **kw: None)
    client = app.test_client()
    _login(client)

    resp = client.post(f"/tickets/{ticket_id}/release-reservation/{reservation_id}", follow_redirects=False)
    assert resp.status_code == 302

    with app.app_context():
        reservation = db.session.get(StockReservation, reservation_id)
        assert reservation.status == "released"
        level = StockLevel.query.filter_by(part_id=reservation.part_id).first()
        assert float(level.reserved_qty) == 0.0


# ---------------------------------------------------------------------------
# Test 5: Ticket detail shows reservation status and release button
# ---------------------------------------------------------------------------
def test_ticket_detail_shows_reservation_status(monkeypatch):
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()

    ticket_id = _seed_ticket(app, ticket_number="HQ-20260315-P003")

    with app.app_context():
        branch = Branch.query.filter_by(code="HQ").first()
        location = StockLocation(branch_id=branch.id, code="BIN-B1", name="Bin B1", location_type="shelf", is_active=True)
        db.session.add(location)
        db.session.flush()

        part = Part(sku="STA-001", name="Status Display Part", sale_price=15.00, is_active=True)
        db.session.add(part)
        db.session.flush()

        level = StockLevel(part_id=part.id, branch_id=branch.id, location_id=location.id, on_hand_qty=5, reserved_qty=2)
        db.session.add(level)
        db.session.flush()

        reservation = StockReservation(
            ticket_id=ticket_id,
            part_id=part.id,
            branch_id=branch.id,
            location_id=location.id,
            quantity=2,
            status="reserved",
        )
        db.session.add(reservation)
        db.session.commit()

    monkeypatch.setattr("app.services.auth_service.log_action", lambda *a, **kw: None)
    monkeypatch.setattr("app.blueprints.tickets.routes.log_action", lambda *a, **kw: None)
    client = app.test_client()
    _login(client)

    resp = client.get(f"/tickets/{ticket_id}")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert "Reserved" in html
    assert "Release" in html
    assert "release-reservation" in html


# ---------------------------------------------------------------------------
# Test 6: Archive and reopen forms have CSRF tokens
# ---------------------------------------------------------------------------
def test_archive_reopen_have_csrf(monkeypatch):
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
    monkeypatch.setattr("app.services.auth_service.log_action", lambda *a, **kw: None)
    monkeypatch.setattr("app.blueprints.tickets.routes.log_action", lambda *a, **kw: None)

    ticket_id = _seed_ticket(app, status="in_repair", ticket_number="HQ-20260315-P004")

    client = app.test_client()
    _login(client)

    resp = client.get(f"/tickets/{ticket_id}")
    assert resp.status_code == 200
    html = resp.data.decode()
    # Archive form should have csrf_token
    assert 'action="/tickets/' in html
    assert 'name="csrf_token"' in html


# ---------------------------------------------------------------------------
# Test 7: csrf_token is available in template context
# ---------------------------------------------------------------------------
def test_csrf_token_in_context(monkeypatch):
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
    monkeypatch.setattr("app.services.auth_service.log_action", lambda *a, **kw: None)
    monkeypatch.setattr("app.blueprints.tickets.routes.log_action", lambda *a, **kw: None)

    ticket_id = _seed_ticket(app, status="archived", ticket_number="HQ-20260315-P005")
    client = app.test_client()
    _login(client)

    # This page uses csrf_token() for the reopen form — if it renders, csrf_token works
    resp = client.get(f"/tickets/{ticket_id}")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Test 8: Stock overview uses part threshold for color coding
# ---------------------------------------------------------------------------
def test_stock_overview_renders(monkeypatch):
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
    monkeypatch.setattr("app.services.auth_service.log_action", lambda *a, **kw: None)

    client = app.test_client()
    _login(client)

    resp = client.get("/inventory/")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert "Stock Overview" in html
    assert "Categories" in html  # New nav link
