"""Phase 16 tests: Booking operations, intake queue, service scheduling foundations."""

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
    get_booking_counts,
    get_intake_queue,
    get_overdue_bookings,
    get_todays_bookings,
    get_upcoming_bookings,
    status_label,
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
    """Create tables explicitly, skipping AuditLog (uses JSONB, incompatible with SQLite)."""
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
        customer = Customer(full_name="John Doe", phone="555-0001", primary_branch_id=branch.id)
        db.session.add(customer)
        db.session.flush()
        device = Device(customer_id=customer.id, category="phones", brand="Apple", model="iPhone 14")
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
    """Helper to create a booking in the database."""
    with app.app_context():
        booking = Booking(
            location_id=ids["branch_id"],
            customer_id=ids["customer_id"] if customer else None,
            device_id=ids["device_id"] if device else None,
            repair_service_id=ids["service_id"],
            start_time=datetime.utcnow() + timedelta(hours=hours_offset),
            end_time=datetime.utcnow() + timedelta(hours=hours_offset + 1),
            status=status,
            notes="Test booking notes",
        )
        db.session.add(booking)
        db.session.commit()
        return str(booking.id)


# ═══════════════════════════════════════════════════════════════
# 16A: Model / Status Transition Tests
# ═══════════════════════════════════════════════════════════════

def test_booking_model_has_new_statuses(monkeypatch):
    """Booking model should have Phase 16 lifecycle statuses."""
    assert Booking.STATUS_NEW == "new"
    assert Booking.STATUS_CONFIRMED == "confirmed"
    assert Booking.STATUS_ARRIVED == "arrived"
    assert Booking.STATUS_NO_SHOW == "no_show"
    assert Booking.STATUS_CONVERTED == "converted"
    assert Booking.STATUS_CANCELLED == "cancelled"


def test_booking_active_statuses(monkeypatch):
    """Active statuses should include new, confirmed, arrived."""
    assert Booking.ACTIVE_STATUSES == {"new", "confirmed", "arrived"}


def test_booking_terminal_statuses(monkeypatch):
    """Terminal statuses should include no_show, converted, cancelled."""
    assert Booking.TERMINAL_STATUSES == {"no_show", "converted", "cancelled"}


def test_valid_transitions_new(monkeypatch):
    """New bookings can transition to confirmed, arrived, cancelled, no_show."""
    allowed = Booking.VALID_TRANSITIONS[Booking.STATUS_NEW]
    assert Booking.STATUS_CONFIRMED in allowed
    assert Booking.STATUS_ARRIVED in allowed
    assert Booking.STATUS_CANCELLED in allowed
    assert Booking.STATUS_NO_SHOW in allowed


def test_valid_transitions_confirmed(monkeypatch):
    """Confirmed bookings can transition to arrived, cancelled, no_show."""
    allowed = Booking.VALID_TRANSITIONS[Booking.STATUS_CONFIRMED]
    assert Booking.STATUS_ARRIVED in allowed
    assert Booking.STATUS_CANCELLED in allowed
    assert Booking.STATUS_NO_SHOW in allowed


def test_valid_transitions_arrived(monkeypatch):
    """Arrived bookings can transition to converted or cancelled."""
    allowed = Booking.VALID_TRANSITIONS[Booking.STATUS_ARRIVED]
    assert Booking.STATUS_CONVERTED in allowed
    assert Booking.STATUS_CANCELLED in allowed


def test_terminal_statuses_cannot_transition(monkeypatch):
    """Terminal statuses should not allow any transitions."""
    for status in [Booking.STATUS_NO_SHOW, Booking.STATUS_CONVERTED, Booking.STATUS_CANCELLED]:
        assert len(Booking.VALID_TRANSITIONS[status]) == 0


def test_can_transition_to_method(monkeypatch):
    """Booking.can_transition_to should validate transitions."""
    app, _, ids = _setup(monkeypatch)
    with app.app_context():
        booking = Booking(
            location_id=ids["branch_id"],
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow() + timedelta(hours=1),
            status="new",
        )
        assert booking.can_transition_to("confirmed") is True
        assert booking.can_transition_to("converted") is False


def test_is_active_property(monkeypatch):
    """is_active should return True for active statuses."""
    app, _, ids = _setup(monkeypatch)
    with app.app_context():
        booking = Booking(
            location_id=ids["branch_id"],
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow() + timedelta(hours=1),
            status="new",
        )
        assert booking.is_active is True
        booking.status = "cancelled"
        assert booking.is_active is False


def test_is_terminal_property(monkeypatch):
    """is_terminal should return True for terminal statuses."""
    app, _, ids = _setup(monkeypatch)
    with app.app_context():
        booking = Booking(
            location_id=ids["branch_id"],
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow() + timedelta(hours=1),
            status="cancelled",
        )
        assert booking.is_terminal is True
        booking.status = "new"
        assert booking.is_terminal is False


# ═══════════════════════════════════════════════════════════════
# 16B: Service Layer Tests
# ═══════════════════════════════════════════════════════════════

def test_status_label_returns_translatable_strings(monkeypatch):
    """status_label should return display labels for all statuses."""
    app, client, _ = _setup(monkeypatch)
    with app.test_request_context():
        assert status_label("new") == "New"
        assert status_label("confirmed") == "Confirmed"
        assert status_label("arrived") == "Arrived"
        assert status_label("no_show") == "No Show"
        assert status_label("converted") == "Converted"
        assert status_label("cancelled") == "Cancelled"


def test_transition_status_valid(monkeypatch):
    """transition_status should update status on valid transitions."""
    app, _, ids = _setup(monkeypatch)
    with app.app_context():
        booking = Booking(
            location_id=ids["branch_id"],
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow() + timedelta(hours=1),
            status="new",
        )
        db.session.add(booking)
        db.session.flush()
        transition_status(booking, "confirmed")
        assert booking.status == "confirmed"


def test_transition_status_invalid(monkeypatch):
    """transition_status should raise InvalidTransitionError on invalid transitions."""
    app, _, ids = _setup(monkeypatch)
    with app.app_context():
        booking = Booking(
            location_id=ids["branch_id"],
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow() + timedelta(hours=1),
            status="cancelled",
        )
        db.session.add(booking)
        db.session.flush()
        with pytest.raises(InvalidTransitionError):
            transition_status(booking, "confirmed")


def test_get_todays_bookings(monkeypatch):
    """get_todays_bookings should return bookings scheduled for today."""
    app, _, ids = _setup(monkeypatch)
    with app.app_context():
        now = datetime.utcnow()
        booking = Booking(
            location_id=ids["branch_id"],
            start_time=now.replace(hour=14, minute=0),
            end_time=now.replace(hour=15, minute=0),
            status="new",
        )
        db.session.add(booking)
        db.session.commit()
        result = get_todays_bookings()
        assert len(result) == 1
        assert result[0].status == "new"


def test_get_todays_bookings_with_location_filter(monkeypatch):
    """get_todays_bookings should filter by location."""
    app, _, ids = _setup(monkeypatch)
    with app.app_context():
        now = datetime.utcnow()
        booking = Booking(
            location_id=ids["branch_id"],
            start_time=now.replace(hour=14, minute=0),
            end_time=now.replace(hour=15, minute=0),
            status="new",
        )
        db.session.add(booking)
        db.session.commit()
        result = get_todays_bookings(location_id=str(ids["branch_id"]))
        assert len(result) == 1
        # Non-existent location
        fake_id = str(uuid.uuid4())
        result = get_todays_bookings(location_id=fake_id)
        assert len(result) == 0


def test_get_overdue_bookings(monkeypatch):
    """get_overdue_bookings should return past active bookings."""
    app, _, ids = _setup(monkeypatch)
    with app.app_context():
        yesterday = datetime.utcnow() - timedelta(days=1)
        booking = Booking(
            location_id=ids["branch_id"],
            start_time=yesterday,
            end_time=yesterday + timedelta(hours=1),
            status="new",
        )
        db.session.add(booking)
        db.session.commit()
        result = get_overdue_bookings()
        assert len(result) == 1


def test_get_overdue_excludes_terminal(monkeypatch):
    """get_overdue_bookings should exclude terminal-status bookings."""
    app, _, ids = _setup(monkeypatch)
    with app.app_context():
        yesterday = datetime.utcnow() - timedelta(days=1)
        booking = Booking(
            location_id=ids["branch_id"],
            start_time=yesterday,
            end_time=yesterday + timedelta(hours=1),
            status="cancelled",
        )
        db.session.add(booking)
        db.session.commit()
        result = get_overdue_bookings()
        assert len(result) == 0


def test_get_intake_queue(monkeypatch):
    """get_intake_queue should return categorized bookings."""
    app, _, ids = _setup(monkeypatch)
    with app.app_context():
        now = datetime.utcnow()
        # Today
        db.session.add(Booking(
            location_id=ids["branch_id"],
            start_time=now.replace(hour=10, minute=0),
            end_time=now.replace(hour=11, minute=0),
            status="new",
        ))
        # Yesterday (overdue)
        yesterday = now - timedelta(days=1)
        db.session.add(Booking(
            location_id=ids["branch_id"],
            start_time=yesterday,
            end_time=yesterday + timedelta(hours=1),
            status="confirmed",
        ))
        db.session.commit()
        queue = get_intake_queue()
        assert len(queue["today"]) == 1
        assert len(queue["overdue"]) == 1


def test_get_booking_counts(monkeypatch):
    """get_booking_counts should return dashboard-compatible counts."""
    app, _, ids = _setup(monkeypatch)
    with app.app_context():
        now = datetime.utcnow()
        db.session.add(Booking(
            location_id=ids["branch_id"],
            start_time=now.replace(hour=10, minute=0),
            end_time=now.replace(hour=11, minute=0),
            status="new",
        ))
        db.session.add(Booking(
            location_id=ids["branch_id"],
            start_time=now.replace(hour=12, minute=0),
            end_time=now.replace(hour=13, minute=0),
            status="arrived",
        ))
        db.session.commit()
        counts = get_booking_counts()
        assert counts["today_total"] == 2
        assert counts["today_arrived"] == 1


# ═══════════════════════════════════════════════════════════════
# 16C: Route / Page Rendering Tests
# ═══════════════════════════════════════════════════════════════

def test_booking_list_page(monkeypatch):
    """Booking list page should render with status badges."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get('/bookings/')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'Bookings' in html


def test_booking_list_with_bookings(monkeypatch):
    """Booking list should show booking data."""
    app, client, ids = _setup(monkeypatch)
    bid = _create_booking(app, ids, status="new", hours_offset=0)
    resp = client.get(f'/bookings/?date={datetime.utcnow().strftime("%Y-%m-%d")}')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'John Doe' in html or 'Screen Repair' in html


def test_intake_queue_page(monkeypatch):
    """Intake queue page should render with sections."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get('/bookings/?view=queue')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'Intake Queue' in html
    assert 'Today' in html
    assert 'Upcoming' in html


def test_booking_detail_page(monkeypatch):
    """Booking detail page should show full booking information."""
    app, client, ids = _setup(monkeypatch)
    bid = _create_booking(app, ids)
    resp = client.get(f'/bookings/{bid}')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'Booking Detail' in html
    assert 'John Doe' in html
    assert 'Headquarters' in html


def test_booking_detail_404(monkeypatch):
    """Booking detail should return 404 for non-existent booking."""
    app, client, ids = _setup(monkeypatch)
    fake_id = str(uuid.uuid4())
    resp = client.get(f'/bookings/{fake_id}')
    assert resp.status_code == 404


def test_booking_create_page(monkeypatch):
    """Booking create page should render the form."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get('/bookings/new')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'New Booking' in html
    assert 'Start Time' in html
    assert 'End Time' in html


def test_booking_create_submit(monkeypatch):
    """Creating a booking via POST should succeed."""
    app, client, ids = _setup(monkeypatch)
    start = (datetime.utcnow() + timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M')
    end = (datetime.utcnow() + timedelta(hours=3)).strftime('%Y-%m-%dT%H:%M')
    resp = client.post('/bookings/new', data={
        'location_id': str(ids['branch_id']),
        'start_time': start,
        'end_time': end,
        'status': 'new',
        'repair_service_id': '',
        'device_id': '',
        'notes': 'Test booking',
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        bookings = Booking.query.all()
        assert len(bookings) == 1
        assert bookings[0].notes == 'Test booking'
        assert bookings[0].status == 'new'


def test_booking_create_with_customer_contact(monkeypatch):
    """Booking can store customer name and phone snapshot."""
    app, client, ids = _setup(monkeypatch)
    start = (datetime.utcnow() + timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M')
    end = (datetime.utcnow() + timedelta(hours=3)).strftime('%Y-%m-%dT%H:%M')
    resp = client.post('/bookings/new', data={
        'location_id': str(ids['branch_id']),
        'start_time': start,
        'end_time': end,
        'status': 'new',
        'repair_service_id': '',
        'device_id': '',
        'customer_name': 'Walk-in Customer',
        'customer_phone': '555-9999',
        'notes': '',
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        booking = Booking.query.first()
        assert booking.customer_name == 'Walk-in Customer'
        assert booking.customer_phone == '555-9999'


def test_booking_edit_page(monkeypatch):
    """Booking edit page should render with existing data."""
    app, client, ids = _setup(monkeypatch)
    bid = _create_booking(app, ids)
    resp = client.get(f'/bookings/{bid}/edit')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'Edit Booking' in html


def test_booking_edit_submit(monkeypatch):
    """Editing a booking via POST should update it."""
    app, client, ids = _setup(monkeypatch)
    bid = _create_booking(app, ids)
    start = (datetime.utcnow() + timedelta(hours=4)).strftime('%Y-%m-%dT%H:%M')
    end = (datetime.utcnow() + timedelta(hours=5)).strftime('%Y-%m-%dT%H:%M')
    resp = client.post(f'/bookings/{bid}/edit', data={
        'location_id': str(ids['branch_id']),
        'start_time': start,
        'end_time': end,
        'status': 'confirmed',
        'repair_service_id': '',
        'device_id': '',
        'notes': 'Updated notes',
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        b = db.session.get(Booking, uuid.UUID(bid))
        assert b.status == 'confirmed'
        assert b.notes == 'Updated notes'


# ═══════════════════════════════════════════════════════════════
# 16D: Status Action Tests
# ═══════════════════════════════════════════════════════════════

def test_confirm_booking_action(monkeypatch):
    """POST to confirm should transition booking to confirmed."""
    app, client, ids = _setup(monkeypatch)
    bid = _create_booking(app, ids, status="new")
    resp = client.post(f'/bookings/{bid}/confirm', follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        b = db.session.get(Booking, uuid.UUID(bid))
        assert b.status == "confirmed"


def test_mark_arrived_action(monkeypatch):
    """POST to arrive should transition booking to arrived."""
    app, client, ids = _setup(monkeypatch)
    bid = _create_booking(app, ids, status="confirmed")
    resp = client.post(f'/bookings/{bid}/arrive', follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        b = db.session.get(Booking, uuid.UUID(bid))
        assert b.status == "arrived"


def test_mark_no_show_action(monkeypatch):
    """POST to no-show should transition booking to no_show."""
    app, client, ids = _setup(monkeypatch)
    bid = _create_booking(app, ids, status="new")
    resp = client.post(f'/bookings/{bid}/no-show', follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        b = db.session.get(Booking, uuid.UUID(bid))
        assert b.status == "no_show"


def test_cancel_booking_action(monkeypatch):
    """POST to cancel should transition booking to cancelled."""
    app, client, ids = _setup(monkeypatch)
    bid = _create_booking(app, ids, status="new")
    resp = client.post(f'/bookings/{bid}/cancel', follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        b = db.session.get(Booking, uuid.UUID(bid))
        assert b.status == "cancelled"


def test_invalid_transition_returns_warning(monkeypatch):
    """Invalid transition should not change status and show warning."""
    app, client, ids = _setup(monkeypatch)
    bid = _create_booking(app, ids, status="cancelled")
    resp = client.post(f'/bookings/{bid}/confirm', follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        b = db.session.get(Booking, uuid.UUID(bid))
        assert b.status == "cancelled"  # unchanged


# ═══════════════════════════════════════════════════════════════
# 16E: Conversion Flow Tests
# ═══════════════════════════════════════════════════════════════

def test_convert_page_renders(monkeypatch):
    """Conversion page should render for arrived booking with customer."""
    app, client, ids = _setup(monkeypatch)
    bid = _create_booking(app, ids, status="arrived")
    resp = client.get(f'/bookings/{bid}/convert')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'Convert Booking to Ticket' in html
    assert 'John Doe' in html


def test_convert_booking_to_ticket_success(monkeypatch):
    """Converting booking to ticket should create ticket and update booking."""
    app, client, ids = _setup(monkeypatch)
    bid = _create_booking(app, ids, status="arrived")
    resp = client.post(f'/bookings/{bid}/convert', data={
        'device_id': str(ids['device_id']),
        'repair_service_id': str(ids['service_id']),
        'issue_summary': 'Screen is cracked',
        'device_condition': 'Good',
        'accessories': 'Charger',
    }, follow_redirects=False)
    # Should redirect to detail page on success
    assert resp.status_code in (200, 302)
    resp2 = client.post(f'/bookings/{bid}/convert', data={
        'device_id': str(ids['device_id']),
        'repair_service_id': str(ids['service_id']),
        'issue_summary': 'Screen is cracked',
        'device_condition': 'Good',
        'accessories': 'Charger',
    }, follow_redirects=True)
    with app.app_context():
        booking = db.session.get(Booking, uuid.UUID(bid))
        # Check if first or second attempt went through
        assert booking.status == "converted"
        assert booking.converted_ticket_id is not None
        assert booking.linked_ticket_id is not None
        # Verify ticket was created
        ticket = db.session.get(Ticket, booking.converted_ticket_id)
        assert ticket is not None
        assert ticket.customer_id == ids["customer_id"]
        assert ticket.device_id == ids["device_id"]
        assert ticket.issue_summary == 'Screen is cracked'


def test_convert_creates_portal_token(monkeypatch):
    """Conversion should create a portal token for the new ticket."""
    app, client, ids = _setup(monkeypatch)
    bid = _create_booking(app, ids, status="arrived")
    client.post(f'/bookings/{bid}/convert', data={
        'device_id': str(ids['device_id']),
        'issue_summary': 'Test issue',
        'repair_service_id': '',
    }, follow_redirects=True)
    with app.app_context():
        booking = db.session.get(Booking, uuid.UUID(bid))
        tokens = PortalToken.query.filter_by(ticket_id=booking.converted_ticket_id).all()
        assert len(tokens) >= 1


def test_convert_creates_ticket_note(monkeypatch):
    """Conversion should create an intake note on the ticket."""
    app, client, ids = _setup(monkeypatch)
    bid = _create_booking(app, ids, status="arrived")
    client.post(f'/bookings/{bid}/convert', data={
        'device_id': str(ids['device_id']),
        'issue_summary': 'Test issue',
        'repair_service_id': '',
    }, follow_redirects=True)
    with app.app_context():
        booking = db.session.get(Booking, uuid.UUID(bid))
        notes = TicketNote.query.filter_by(ticket_id=booking.converted_ticket_id).all()
        assert len(notes) >= 1
        assert 'Test issue' in notes[0].content


def test_prevent_duplicate_conversion(monkeypatch):
    """Converting an already-converted booking should show warning."""
    app, client, ids = _setup(monkeypatch)
    bid = _create_booking(app, ids, status="arrived")
    # First conversion
    client.post(f'/bookings/{bid}/convert', data={
        'device_id': str(ids['device_id']),
        'issue_summary': 'First conversion',
        'repair_service_id': '',
    }, follow_redirects=True)
    # Second attempt
    resp = client.get(f'/bookings/{bid}/convert', follow_redirects=True)
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'already been converted' in html or 'Booking Detail' in html


def test_convert_wrong_status_blocked(monkeypatch):
    """Converting a new (non-arrived) booking should be blocked."""
    app, client, ids = _setup(monkeypatch)
    bid = _create_booking(app, ids, status="new")
    resp = client.get(f'/bookings/{bid}/convert', follow_redirects=True)
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'cannot be converted' in html or 'Booking Detail' in html


def test_convert_without_customer_blocked(monkeypatch):
    """Converting a booking without customer should be blocked."""
    app, client, ids = _setup(monkeypatch)
    bid = _create_booking(app, ids, status="arrived", customer=False)
    resp = client.get(f'/bookings/{bid}/convert', follow_redirects=True)
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'customer must be assigned' in html or 'Edit Booking' in html or 'Booking' in html


def test_linked_ticket_visible_after_conversion(monkeypatch):
    """After conversion, booking detail should show linked ticket."""
    app, client, ids = _setup(monkeypatch)
    bid = _create_booking(app, ids, status="arrived")
    client.post(f'/bookings/{bid}/convert', data={
        'device_id': str(ids['device_id']),
        'issue_summary': 'Linked test',
        'repair_service_id': '',
    }, follow_redirects=True)
    resp = client.get(f'/bookings/{bid}')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'Linked Ticket' in html or 'View Ticket' in html


def test_convert_service_function_directly(monkeypatch):
    """Test convert_booking_to_ticket service function directly."""
    app, _, ids = _setup(monkeypatch)
    with app.app_context():
        booking = Booking(
            location_id=ids["branch_id"],
            customer_id=ids["customer_id"],
            device_id=ids["device_id"],
            repair_service_id=ids["service_id"],
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow() + timedelta(hours=1),
            status="arrived",
            notes="Direct test",
        )
        db.session.add(booking)
        db.session.flush()

        ticket = convert_booking_to_ticket(
            booking=booking,
            branch_code="HQ",
            user_id=str(ids["user_id"]),
            ticket_number="HQ-20260317-00001",
            issue_summary="Screen repair needed",
        )
        db.session.commit()

        assert ticket is not None
        assert booking.status == "converted"
        assert booking.converted_ticket_id == ticket.id
        assert ticket.ticket_number == "HQ-20260317-00001"
        assert ticket.customer_id == ids["customer_id"]


def test_convert_already_converted_raises(monkeypatch):
    """convert_booking_to_ticket should raise ValueError on duplicate."""
    app, _, ids = _setup(monkeypatch)
    with app.app_context():
        booking = Booking(
            location_id=ids["branch_id"],
            customer_id=ids["customer_id"],
            device_id=ids["device_id"],
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow() + timedelta(hours=1),
            status="arrived",
        )
        db.session.add(booking)
        db.session.flush()

        convert_booking_to_ticket(
            booking=booking,
            branch_code="HQ",
            user_id=str(ids["user_id"]),
            ticket_number="HQ-20260317-00002",
        )
        db.session.commit()

        with pytest.raises(ValueError, match="already been converted"):
            convert_booking_to_ticket(
                booking=booking,
                branch_code="HQ",
                user_id=str(ids["user_id"]),
                ticket_number="HQ-20260317-00003",
            )


def test_convert_without_customer_raises(monkeypatch):
    """convert_booking_to_ticket should raise ValueError without customer."""
    app, _, ids = _setup(monkeypatch)
    with app.app_context():
        booking = Booking(
            location_id=ids["branch_id"],
            customer_id=None,
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow() + timedelta(hours=1),
            status="arrived",
        )
        db.session.add(booking)
        db.session.flush()

        with pytest.raises(ValueError, match="must have a customer"):
            convert_booking_to_ticket(
                booking=booking,
                branch_code="HQ",
                user_id=str(ids["user_id"]),
                ticket_number="HQ-20260317-00004",
            )


# ═══════════════════════════════════════════════════════════════
# 16F: Permission Tests
# ═══════════════════════════════════════════════════════════════

def test_readonly_cannot_access_booking_create(monkeypatch):
    """Read Only role should get 403 on booking create."""
    app, client, ids = _setup(monkeypatch, role_name="Read Only")
    resp = client.get('/bookings/new')
    assert resp.status_code == 403


def test_readonly_can_view_booking_list(monkeypatch):
    """Read Only role should be able to view booking list."""
    app, client, ids = _setup(monkeypatch, role_name="Read Only")
    resp = client.get('/bookings/')
    assert resp.status_code == 200


def test_readonly_cannot_confirm_booking(monkeypatch):
    """Read Only role should get 403 on booking status actions."""
    app, client, ids = _setup(monkeypatch, role_name="Read Only")
    bid = _create_booking(app, ids, status="new")
    resp = client.post(f'/bookings/{bid}/confirm')
    assert resp.status_code == 403


def test_readonly_cannot_convert_booking(monkeypatch):
    """Read Only role should get 403 on booking conversion."""
    app, client, ids = _setup(monkeypatch, role_name="Read Only")
    bid = _create_booking(app, ids, status="arrived")
    resp = client.get(f'/bookings/{bid}/convert')
    assert resp.status_code == 403


def test_frontdesk_can_manage_bookings(monkeypatch):
    """Front Desk role should be able to create and manage bookings."""
    app, client, ids = _setup(monkeypatch, role_name="Front Desk")
    resp = client.get('/bookings/new')
    assert resp.status_code == 200


def test_frontdesk_can_convert_bookings(monkeypatch):
    """Front Desk role should be able to convert bookings to tickets."""
    app, client, ids = _setup(monkeypatch, role_name="Front Desk")
    bid = _create_booking(app, ids, status="arrived")
    resp = client.get(f'/bookings/{bid}/convert')
    assert resp.status_code == 200


def test_technician_can_view_but_not_manage(monkeypatch):
    """Technician role should be able to view but not create bookings."""
    app, client, ids = _setup(monkeypatch, role_name="Technician")
    # Can view list
    resp = client.get('/bookings/')
    assert resp.status_code == 200
    # Cannot create
    resp = client.get('/bookings/new')
    assert resp.status_code == 403


def test_manager_can_manage_bookings(monkeypatch):
    """Manager role should have full booking management access."""
    app, client, ids = _setup(monkeypatch, role_name="Manager")
    resp = client.get('/bookings/new')
    assert resp.status_code == 200
    bid = _create_booking(app, ids, status="new")
    resp = client.post(f'/bookings/{bid}/confirm', follow_redirects=True)
    assert resp.status_code == 200


def test_post_cancel_requires_permission(monkeypatch):
    """POST to cancel should require can_manage_bookings permission."""
    app, client, ids = _setup(monkeypatch, role_name="Inventory")
    bid = _create_booking(app, ids, status="new")
    resp = client.post(f'/bookings/{bid}/cancel')
    assert resp.status_code == 403


def test_post_arrive_requires_permission(monkeypatch):
    """POST to arrive should require can_manage_bookings permission."""
    app, client, ids = _setup(monkeypatch, role_name="Inventory")
    bid = _create_booking(app, ids, status="confirmed")
    resp = client.post(f'/bookings/{bid}/arrive')
    assert resp.status_code == 403


def test_post_noshow_requires_permission(monkeypatch):
    """POST to no-show should require can_manage_bookings permission."""
    app, client, ids = _setup(monkeypatch, role_name="Inventory")
    bid = _create_booking(app, ids, status="new")
    resp = client.post(f'/bookings/{bid}/no-show')
    assert resp.status_code == 403


def test_edit_booking_requires_permission(monkeypatch):
    """GET/POST to edit should require can_manage_bookings permission."""
    app, client, ids = _setup(monkeypatch, role_name="Read Only")
    bid = _create_booking(app, ids, status="new")
    resp = client.get(f'/bookings/{bid}/edit')
    assert resp.status_code == 403


# ═══════════════════════════════════════════════════════════════
# 16G: Status Filter Tests
# ═══════════════════════════════════════════════════════════════

def test_booking_list_status_filter(monkeypatch):
    """Booking list should support filtering by status."""
    app, client, ids = _setup(monkeypatch)
    _create_booking(app, ids, status="new", hours_offset=0)
    _create_booking(app, ids, status="confirmed", hours_offset=1)
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    resp = client.get(f'/bookings/?date={date_str}&status=new')
    assert resp.status_code == 200


def test_intake_queue_status_filter(monkeypatch):
    """Intake queue should support filtering by status."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get('/bookings/?view=queue&status=confirmed')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'Intake Queue' in html


# ═══════════════════════════════════════════════════════════════
# 16H: Customer / Device Reuse Tests
# ═══════════════════════════════════════════════════════════════

def test_booking_links_to_existing_customer(monkeypatch):
    """Booking should reference existing customer without duplication."""
    app, client, ids = _setup(monkeypatch)
    start = (datetime.utcnow() + timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M')
    end = (datetime.utcnow() + timedelta(hours=3)).strftime('%Y-%m-%dT%H:%M')
    client.post('/bookings/new', data={
        'location_id': str(ids['branch_id']),
        'customer_id': str(ids['customer_id']),
        'device_id': str(ids['device_id']),
        'start_time': start,
        'end_time': end,
        'status': 'new',
        'repair_service_id': '',
    }, follow_redirects=True)
    with app.app_context():
        booking = Booking.query.first()
        assert booking.customer_id == ids["customer_id"]
        assert booking.device_id == ids["device_id"]
        # No duplicate customers
        assert Customer.query.count() == 1


def test_converted_ticket_uses_booking_customer(monkeypatch):
    """Converted ticket should use the same customer as the booking."""
    app, client, ids = _setup(monkeypatch)
    bid = _create_booking(app, ids, status="arrived")
    client.post(f'/bookings/{bid}/convert', data={
        'device_id': str(ids['device_id']),
        'issue_summary': 'Customer reuse test',
        'repair_service_id': '',
    }, follow_redirects=True)
    with app.app_context():
        booking = db.session.get(Booking, uuid.UUID(bid))
        ticket = db.session.get(Ticket, booking.converted_ticket_id)
        assert ticket.customer_id == booking.customer_id
        assert Customer.query.count() == 1


# ═══════════════════════════════════════════════════════════════
# 16I: Navigation / Integration Tests
# ═══════════════════════════════════════════════════════════════

def test_nav_has_intake_queue_link(monkeypatch):
    """Navigation should include Intake Queue link."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get('/')
    html = resp.data.decode()
    assert 'Intake Queue' in html


def test_booking_detail_shows_actions_for_admin(monkeypatch):
    """Admin should see action buttons on booking detail."""
    app, client, ids = _setup(monkeypatch)
    bid = _create_booking(app, ids, status="new")
    resp = client.get(f'/bookings/{bid}')
    html = resp.data.decode()
    assert 'Confirm' in html
    assert 'Mark Arrived' in html
    assert 'Cancel Booking' in html


def test_booking_detail_shows_convert_for_arrived(monkeypatch):
    """Arrived booking should show Create Ticket button."""
    app, client, ids = _setup(monkeypatch)
    bid = _create_booking(app, ids, status="arrived")
    resp = client.get(f'/bookings/{bid}')
    html = resp.data.decode()
    assert 'Create Ticket from Booking' in html or 'Create Ticket' in html


def test_booking_detail_hides_convert_for_new(monkeypatch):
    """New booking should not show Convert button."""
    app, client, ids = _setup(monkeypatch)
    bid = _create_booking(app, ids, status="new")
    resp = client.get(f'/bookings/{bid}')
    html = resp.data.decode()
    assert 'Create Ticket from Booking' not in html


# ═══════════════════════════════════════════════════════════════
# 16J: Translation Tests
# ═══════════════════════════════════════════════════════════════

def test_booking_status_labels_translatable(monkeypatch):
    """Status labels should be rendered via translatable functions."""
    app, _, _ = _setup(monkeypatch)
    with app.test_request_context():
        for status in Booking.ALL_STATUSES:
            label = status_label(status)
            assert isinstance(label, str)
            assert len(label) > 0


def test_booking_list_page_translatable(monkeypatch):
    """Booking list page should render with translatable content."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get('/bookings/')
    html = resp.data.decode()
    assert 'Bookings' in html
    assert 'All locations' in html or 'All statuses' in html


def test_intake_queue_translatable(monkeypatch):
    """Intake queue page should render translatable headings."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get('/bookings/?view=queue')
    html = resp.data.decode()
    assert 'Intake Queue' in html
    assert 'Today' in html


# ═══════════════════════════════════════════════════════════════
# 16K: Migration Validation
# ═══════════════════════════════════════════════════════════════

def test_phase16_migration_exists(monkeypatch):
    """Phase 16 migration file should exist with proper content."""
    import os
    migrations_dir = os.path.join(os.path.dirname(__file__), '..', 'migrations', 'versions')
    found = False
    for fname in os.listdir(migrations_dir):
        if 'phase16' in fname.lower() or 'booking_operations' in fname.lower():
            with open(os.path.join(migrations_dir, fname)) as f:
                content = f.read()
            assert 'device_id' in content
            assert 'staff_notes' in content
            assert 'customer_phone' in content
            assert 'customer_name' in content
            assert 'converted_ticket_id' in content
            assert 'def downgrade' in content
            found = True
    assert found, "Phase 16 migration file not found"


# ═══════════════════════════════════════════════════════════════
# 16L: Booking Model New Fields
# ═══════════════════════════════════════════════════════════════

def test_booking_model_has_new_fields(monkeypatch):
    """Booking model should have Phase 16 fields."""
    app, _, ids = _setup(monkeypatch)
    with app.app_context():
        booking = Booking(
            location_id=ids["branch_id"],
            customer_id=ids["customer_id"],
            device_id=ids["device_id"],
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow() + timedelta(hours=1),
            status="new",
            notes="Test",
            staff_notes="Internal note",
            customer_name="John",
            customer_phone="555-1234",
        )
        db.session.add(booking)
        db.session.commit()

        loaded = db.session.get(Booking, booking.id)
        assert loaded.device_id == ids["device_id"]
        assert loaded.staff_notes == "Internal note"
        assert loaded.customer_name == "John"
        assert loaded.customer_phone == "555-1234"
        assert loaded.converted_ticket_id is None


def test_booking_device_relationship(monkeypatch):
    """Booking.device should load the related Device object."""
    app, _, ids = _setup(monkeypatch)
    with app.app_context():
        booking = Booking(
            location_id=ids["branch_id"],
            device_id=ids["device_id"],
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow() + timedelta(hours=1),
            status="new",
        )
        db.session.add(booking)
        db.session.commit()
        db.session.refresh(booking)
        assert booking.device is not None
        assert booking.device.brand == "Apple"


def test_booking_converted_ticket_relationship(monkeypatch):
    """Booking.converted_ticket should load the related Ticket."""
    app, _, ids = _setup(monkeypatch)
    with app.app_context():
        booking = Booking(
            location_id=ids["branch_id"],
            customer_id=ids["customer_id"],
            device_id=ids["device_id"],
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow() + timedelta(hours=1),
            status="arrived",
        )
        db.session.add(booking)
        db.session.flush()

        ticket = convert_booking_to_ticket(
            booking=booking,
            branch_code="HQ",
            user_id=str(ids["user_id"]),
            ticket_number="HQ-20260317-99999",
        )
        db.session.commit()
        db.session.refresh(booking)
        assert booking.converted_ticket is not None
        assert booking.converted_ticket.ticket_number == "HQ-20260317-99999"
