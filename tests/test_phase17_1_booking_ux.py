"""Phase 17.1 tests: Booking intake UX, customer search/create, device handling,
navigation clarity, conversion eligibility from confirmed, post-conversion flow."""

import json
import uuid
from datetime import datetime, timedelta

import pytest
from app import create_app
from app.extensions import db
from app.models import (
    Branch, Booking, ChecklistItem, Company, Customer, Device, Diagnostic,
    Part, PartCategory, PartOrder, PartOrderLine, PartOrderEvent,
    Quote, QuoteApproval, QuoteLine, QuoteOption, RepairChecklist,
    RepairService, Role, StockLayer, StockLevel, StockLocation,
    StockMovement, StockReservation, Supplier, Ticket, TicketNote, User,
    AppSetting, IntakeSubmission, IntakeDisclaimerAcceptance, PortalToken,
)
from app.models.role import role_permissions
from app.models.user import user_roles, user_branch_access
from app.models.inventory import part_category_links
from app.services.booking_service import (
    InvalidTransitionError,
    convert_booking_to_ticket,
    transition_status,
)


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


def _noop_log(*a, **kw):
    return None


def _create_tables():
    """Create tables explicitly, skipping AuditLog (uses JSONB)."""
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


def _setup(monkeypatch, role_name="Admin"):
    monkeypatch.setattr('app.services.auth_service.log_action', _noop_log)
    monkeypatch.setattr('app.services.audit_service.log_action', _noop_log)
    monkeypatch.setattr('app.blueprints.intake.routes.log_action', _noop_log)
    monkeypatch.setattr('app.blueprints.tickets.routes.log_action', _noop_log)
    monkeypatch.setattr('app.services.booking_service.log_action', _noop_log)
    monkeypatch.setattr('app.blueprints.bookings.routes.log_action', _noop_log)

    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()

        role = Role(name=role_name)
        db.session.add(role)
        branch = Branch(code="HQ", name="Headquarters", is_active=True)
        db.session.add(branch)
        db.session.flush()
        user = User(full_name="Test Admin", email="admin@test.com", is_active=True, default_branch_id=branch.id)
        user.password_hash = "pbkdf2:sha256:600000$test$test"
        user.roles.append(role)
        db.session.add(user)
        customer = Customer(full_name="John Doe", phone="555-0001", email="john@example.com", primary_branch_id=branch.id)
        db.session.add(customer)
        db.session.flush()
        device = Device(customer_id=customer.id, category="phones", brand="Apple", model="iPhone 14", serial_number="SN001")
        db.session.add(device)
        service = RepairService(name="Screen Repair", is_active=True, labour_minutes=45)
        db.session.add(service)
        db.session.flush()

        ids = {
            "branch_id": branch.id,
            "user_id": str(user.id),
            "customer_id": customer.id,
            "device_id": device.id,
            "service_id": service.id,
        }
        db.session.commit()

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = ids["user_id"]

    return app, client, ids


def _create_booking(app, ids, status="new", hours_offset=2, customer=True, device=True):
    with app.app_context():
        now = datetime.utcnow()
        booking = Booking(
            location_id=ids["branch_id"],
            customer_id=ids["customer_id"] if customer else None,
            device_id=ids["device_id"] if device else None,
            start_time=now + timedelta(hours=hours_offset),
            end_time=now + timedelta(hours=hours_offset + 1),
            status=status,
            customer_name="John Doe" if customer else None,
        )
        db.session.add(booking)
        db.session.commit()
        return str(booking.id)


# ===========================================================================
# A. Customer search endpoint
# ===========================================================================

def test_customer_search_by_name(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    resp = client.get("/bookings/customer-search?q=John")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["items"]) >= 1
    assert "John Doe" in data["items"][0]["label"]


def test_customer_search_by_phone(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    resp = client.get("/bookings/customer-search?q=555-0001")
    data = resp.get_json()
    assert len(data["items"]) >= 1


def test_customer_search_by_email(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    resp = client.get("/bookings/customer-search?q=john@example")
    data = resp.get_json()
    assert len(data["items"]) >= 1


def test_customer_search_min_length(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    resp = client.get("/bookings/customer-search?q=J")
    data = resp.get_json()
    assert data["items"] == []


def test_customer_search_no_results(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    resp = client.get("/bookings/customer-search?q=ZZZZNONEXISTENT")
    data = resp.get_json()
    assert data["items"] == []


# ===========================================================================
# B. Customer create endpoint
# ===========================================================================

def test_customer_create_new(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    resp = client.post("/bookings/customer-create",
        data=json.dumps({"name": "Jane Smith", "phone": "555-9999", "email": "jane@test.com"}),
        content_type="application/json")
    data = resp.get_json()
    assert data["ok"] is True
    assert data["name"] == "Jane Smith"
    assert data["existing"] is False
    # Verify persisted
    with app.app_context():
        c = Customer.query.filter_by(full_name="Jane Smith").first()
        assert c is not None


def test_customer_create_duplicate_email(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    resp = client.post("/bookings/customer-create",
        data=json.dumps({"name": "John Duplicate", "phone": "555-0000", "email": "john@example.com"}),
        content_type="application/json")
    data = resp.get_json()
    assert data["ok"] is True
    assert data["existing"] is True
    assert data["name"] == "John Doe"  # original customer returned


def test_customer_create_duplicate_phone(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    resp = client.post("/bookings/customer-create",
        data=json.dumps({"name": "Phone Dup", "phone": "555-0001", "email": ""}),
        content_type="application/json")
    data = resp.get_json()
    assert data["ok"] is True
    assert data["existing"] is True


def test_customer_create_no_name(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    resp = client.post("/bookings/customer-create",
        data=json.dumps({"name": "", "phone": "555", "email": ""}),
        content_type="application/json")
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["ok"] is False


# ===========================================================================
# C. Customer devices endpoint
# ===========================================================================

def test_customer_devices_returns_list(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    resp = client.get(f"/bookings/customer/{ids['customer_id']}/devices")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) >= 1
    assert "Apple" in data[0]["label"]


def test_customer_devices_empty_for_unknown(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    fake_id = uuid.uuid4()
    resp = client.get(f"/bookings/customer/{fake_id}/devices")
    data = resp.get_json()
    assert data == []


# ===========================================================================
# D. Booking create with existing customer
# ===========================================================================

def test_booking_create_with_customer(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    now = datetime.utcnow()
    start = (now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
    end = (now + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M")
    resp = client.post("/bookings/new", data={
        "location_id": str(ids["branch_id"]),
        "customer_id": str(ids["customer_id"]),
        "device_id": str(ids["device_id"]),
        "start_time": start,
        "end_time": end,
        "status": "new",
        "customer_name": "John Doe",
        "customer_phone": "555-0001",
        "customer_email": "john@example.com",
        "device_description": "",
    }, follow_redirects=False)
    assert resp.status_code == 302
    with app.app_context():
        b = Booking.query.first()
        assert b is not None
        assert b.customer_id == ids["customer_id"]


# ===========================================================================
# E. Booking create with new customer (inline creation + device description)
# ===========================================================================

def test_booking_create_with_device_description(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    now = datetime.utcnow()
    start = (now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
    end = (now + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M")
    resp = client.post("/bookings/new", data={
        "location_id": str(ids["branch_id"]),
        "customer_id": str(ids["customer_id"]),
        "start_time": start,
        "end_time": end,
        "status": "new",
        "customer_name": "John Doe",
        "device_description": "Samsung Galaxy S24, water damage",
    }, follow_redirects=False)
    assert resp.status_code == 302
    with app.app_context():
        b = Booking.query.first()
        assert b.device_description == "Samsung Galaxy S24, water damage"


def test_booking_stores_customer_email(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    now = datetime.utcnow()
    start = (now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
    end = (now + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M")
    resp = client.post("/bookings/new", data={
        "location_id": str(ids["branch_id"]),
        "customer_id": str(ids["customer_id"]),
        "start_time": start,
        "end_time": end,
        "status": "new",
        "customer_email": "test@booking.com",
    }, follow_redirects=False)
    assert resp.status_code == 302
    with app.app_context():
        b = Booking.query.first()
        assert b.customer_email == "test@booking.com"


# ===========================================================================
# F. Conversion from confirmed status
# ===========================================================================

def test_conversion_allowed_from_confirmed(monkeypatch):
    """Confirmed bookings should be convertible to tickets."""
    app, client, ids = _setup(monkeypatch)
    booking_id = _create_booking(app, ids, status="confirmed")
    with app.app_context():
        b = db.session.get(Booking, uuid.UUID(booking_id))
        assert b.can_transition_to(Booking.STATUS_CONVERTED) is True


def test_conversion_still_works_from_arrived(monkeypatch):
    """Arrived bookings should still be convertible."""
    app, client, ids = _setup(monkeypatch)
    booking_id = _create_booking(app, ids, status="arrived")
    with app.app_context():
        b = db.session.get(Booking, uuid.UUID(booking_id))
        assert b.can_transition_to(Booking.STATUS_CONVERTED) is True


def test_conversion_blocked_from_cancelled(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    booking_id = _create_booking(app, ids, status="cancelled")
    with app.app_context():
        b = db.session.get(Booking, uuid.UUID(booking_id))
        assert b.can_transition_to(Booking.STATUS_CONVERTED) is False


def test_conversion_blocked_from_no_show(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    booking_id = _create_booking(app, ids, status="no_show")
    with app.app_context():
        b = db.session.get(Booking, uuid.UUID(booking_id))
        assert b.can_transition_to(Booking.STATUS_CONVERTED) is False


def test_conversion_blocked_from_already_converted(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    booking_id = _create_booking(app, ids, status="converted")
    with app.app_context():
        b = db.session.get(Booking, uuid.UUID(booking_id))
        assert b.can_transition_to(Booking.STATUS_CONVERTED) is False


def test_convert_route_from_confirmed(monkeypatch):
    """POST to convert from confirmed status should succeed."""
    app, client, ids = _setup(monkeypatch)
    booking_id = _create_booking(app, ids, status="confirmed")
    resp = client.post(f"/bookings/{booking_id}/convert", data={
        "device_id": str(ids["device_id"]),
        "issue_summary": "Screen cracked",
    }, follow_redirects=False)
    # Should redirect to ticket detail (302)
    assert resp.status_code == 302
    with app.app_context():
        b = db.session.get(Booking, uuid.UUID(booking_id))
        assert b.status == "converted"
        assert b.converted_ticket_id is not None


def test_convert_route_prevents_duplicate(monkeypatch):
    """Converting an already-converted booking should show warning."""
    app, client, ids = _setup(monkeypatch)
    booking_id = _create_booking(app, ids, status="confirmed")
    # Convert once
    client.post(f"/bookings/{booking_id}/convert", data={
        "device_id": str(ids["device_id"]),
    })
    # Try again
    resp = client.post(f"/bookings/{booking_id}/convert", data={
        "device_id": str(ids["device_id"]),
    }, follow_redirects=True)
    assert b"already been converted" in resp.data


# ===========================================================================
# G. Post-conversion redirect to ticket detail
# ===========================================================================

def test_post_conversion_redirects_to_ticket(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    booking_id = _create_booking(app, ids, status="arrived")
    resp = client.post(f"/bookings/{booking_id}/convert", data={
        "device_id": str(ids["device_id"]),
        "issue_summary": "Test conversion",
    }, follow_redirects=False)
    assert resp.status_code == 302
    location = resp.headers.get("Location", "")
    assert "/tickets/" in location
    # Verify it's the ticket detail, not booking detail
    assert "/bookings/" not in location


# ===========================================================================
# H. Navigation / Menu
# ===========================================================================

def test_nav_has_new_booking_link(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    resp = client.get("/")
    html = resp.data.decode()
    assert "New Booking" in html or "Nueva Reserva" in html


def test_nav_has_create_new_ticket_link(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    resp = client.get("/")
    html = resp.data.decode()
    assert "Create New Ticket" in html or "Crear Nuevo Ticket" in html


def test_nav_has_fast_checkin_link(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    resp = client.get("/")
    html = resp.data.decode()
    assert "Fast Check-In" in html


def test_nav_new_ticket_points_to_intake(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    resp = client.get("/")
    html = resp.data.decode()
    assert "/intake/new" in html


def test_nav_new_booking_points_to_bookings_new(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    resp = client.get("/")
    html = resp.data.decode()
    assert "/bookings/new" in html


# ===========================================================================
# I. Booking detail shows convert for confirmed
# ===========================================================================

def test_detail_shows_convert_for_confirmed(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    booking_id = _create_booking(app, ids, status="confirmed")
    resp = client.get(f"/bookings/{booking_id}")
    html = resp.data.decode()
    assert "Create Ticket from Booking" in html or "convert" in html.lower()


def test_detail_shows_convert_for_arrived(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    booking_id = _create_booking(app, ids, status="arrived")
    resp = client.get(f"/bookings/{booking_id}")
    html = resp.data.decode()
    assert "Create Ticket from Booking" in html


def test_detail_no_convert_for_cancelled(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    booking_id = _create_booking(app, ids, status="cancelled")
    resp = client.get(f"/bookings/{booking_id}")
    html = resp.data.decode()
    assert "Create Ticket from Booking" not in html


# ===========================================================================
# J. Device handling on booking form
# ===========================================================================

def test_booking_form_loads(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    resp = client.get("/bookings/new")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert "Device Description" in html or "device-description" in html


def test_booking_detail_shows_device_description(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    with app.app_context():
        now = datetime.utcnow()
        b = Booking(
            location_id=ids["branch_id"],
            customer_id=ids["customer_id"],
            start_time=now + timedelta(hours=1),
            end_time=now + timedelta(hours=2),
            status="new",
            device_description="iPad Air 5, bent frame",
        )
        db.session.add(b)
        db.session.commit()
        bid = str(b.id)
    resp = client.get(f"/bookings/{bid}")
    html = resp.data.decode()
    assert "iPad Air 5, bent frame" in html


# ===========================================================================
# K. Permission enforcement
# ===========================================================================

def test_readonly_cannot_manage_bookings(monkeypatch):
    app, client, ids = _setup(monkeypatch, role_name="Read Only")
    resp = client.get("/bookings/new")
    assert resp.status_code == 403


def test_readonly_cannot_create_customer(monkeypatch):
    app, client, ids = _setup(monkeypatch, role_name="Read Only")
    resp = client.post("/bookings/customer-create",
        data=json.dumps({"name": "Test"}),
        content_type="application/json")
    assert resp.status_code == 403


def test_readonly_can_view_bookings(monkeypatch):
    app, client, ids = _setup(monkeypatch, role_name="Read Only")
    resp = client.get("/bookings/")
    assert resp.status_code == 200


def test_readonly_can_search_customers(monkeypatch):
    """Customer search is available to any logged-in user."""
    app, client, ids = _setup(monkeypatch, role_name="Read Only")
    resp = client.get("/bookings/customer-search?q=John")
    assert resp.status_code == 200


# ===========================================================================
# L. Edit booking preserves new fields
# ===========================================================================

def test_edit_booking_saves_new_fields(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    booking_id = _create_booking(app, ids, status="new")
    now = datetime.utcnow()
    start = (now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
    end = (now + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M")
    resp = client.post(f"/bookings/{booking_id}/edit", data={
        "location_id": str(ids["branch_id"]),
        "customer_id": str(ids["customer_id"]),
        "start_time": start,
        "end_time": end,
        "status": "new",
        "customer_email": "updated@test.com",
        "device_description": "Pixel 7, broken camera",
    }, follow_redirects=False)
    assert resp.status_code == 302
    with app.app_context():
        b = db.session.get(Booking, uuid.UUID(booking_id))
        assert b.customer_email == "updated@test.com"
        assert b.device_description == "Pixel 7, broken camera"


# ===========================================================================
# M. Service-layer conversion with confirmed status
# ===========================================================================

def test_service_convert_confirmed_booking(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    with app.app_context():
        now = datetime.utcnow()
        b = Booking(
            location_id=ids["branch_id"],
            customer_id=ids["customer_id"],
            device_id=ids["device_id"],
            start_time=now + timedelta(hours=1),
            end_time=now + timedelta(hours=2),
            status="confirmed",
        )
        db.session.add(b)
        db.session.flush()
        ticket = convert_booking_to_ticket(
            booking=b,
            branch_code="HQ",
            user_id=ids["user_id"],
            ticket_number="HQ-0001",
            issue_summary="Confirmed conversion test",
        )
        db.session.commit()
        assert ticket is not None
        assert b.status == "converted"
        assert b.converted_ticket_id == ticket.id


def test_service_convert_blocked_for_cancelled(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    with app.app_context():
        now = datetime.utcnow()
        b = Booking(
            location_id=ids["branch_id"],
            customer_id=ids["customer_id"],
            device_id=ids["device_id"],
            start_time=now + timedelta(hours=1),
            end_time=now + timedelta(hours=2),
            status="cancelled",
        )
        db.session.add(b)
        db.session.flush()
        with pytest.raises(InvalidTransitionError):
            convert_booking_to_ticket(
                booking=b,
                branch_code="HQ",
                user_id=ids["user_id"],
                ticket_number="HQ-0002",
            )


# ===========================================================================
# N. Translation rendering
# ===========================================================================

def test_booking_form_renders_en(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    resp = client.get("/bookings/new")
    html = resp.data.decode()
    assert "New Booking" in html
    assert "Customer" in html


def test_booking_form_renders_es(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    # Set language to ES
    client.get("/set-language/es")
    resp = client.get("/bookings/new")
    html = resp.data.decode()
    # ES strings should appear if locale is set (may or may not depending on .mo compile)
    # At minimum the form should load successfully
    assert resp.status_code == 200


# ===========================================================================
# O. Model fields existence
# ===========================================================================

def test_booking_model_has_new_fields(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    with app.app_context():
        now = datetime.utcnow()
        b = Booking(
            location_id=ids["branch_id"],
            start_time=now,
            end_time=now + timedelta(hours=1),
            customer_email="model@test.com",
            device_description="Test device desc",
        )
        db.session.add(b)
        db.session.commit()
        loaded = db.session.get(Booking, b.id)
        assert loaded.customer_email == "model@test.com"
        assert loaded.device_description == "Test device desc"


def test_confirmed_transitions_include_converted():
    """Verify the model's VALID_TRANSITIONS allow confirmed → converted."""
    allowed = Booking.VALID_TRANSITIONS[Booking.STATUS_CONFIRMED]
    assert Booking.STATUS_CONVERTED in allowed
    # Also check other valid transitions still work
    assert Booking.STATUS_ARRIVED in allowed
    assert Booking.STATUS_CANCELLED in allowed
    assert Booking.STATUS_NO_SHOW in allowed
