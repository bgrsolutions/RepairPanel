"""Phase 17 tests: Warranty, branded communications, customer aftercare."""

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
    StockMovement, StockReservation, Supplier, Ticket, TicketNote,
    TicketWarranty, User, AppSetting, IntakeSubmission,
    IntakeDisclaimerAcceptance, PortalToken,
)
from app.models.role import role_permissions
from app.models.user import user_roles, user_branch_access
from app.models.inventory import part_category_links
from app.services.warranty_service import (
    check_device_under_warranty,
    create_warranty,
    evaluate_warranty,
    expire_warranties,
    get_active_warranties,
    get_customer_warranties,
    get_device_warranty_history,
    get_ticket_parts_summary,
    record_claim,
    void_warranty,
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
    MAIL_TRANSPORT = "log"


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
        TicketWarranty.__table__,
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

        company = Company(legal_name="Test Corp", trading_name="TestCorp",
                          email="info@test.com", phone="555-9999",
                          default_warranty_days=90, default_warranty_terms="Standard 90-day warranty")
        db.session.add(company)
        role = Role(name=role_name)
        db.session.add(role)
        branch = Branch(code="HQ", name="Headquarters", is_active=True)
        db.session.add(branch)
        db.session.flush()
        user = User(full_name="Test Admin", email="admin@test.com", is_active=True, default_branch_id=branch.id)
        user.password_hash = "pbkdf2:sha256:600000$test$test"
        user.roles.append(role)
        db.session.add(user)
        customer = Customer(full_name="John Doe", phone="555-0001", email="john@test.com",
                            preferred_language="en", primary_branch_id=branch.id)
        db.session.add(customer)
        db.session.flush()
        device = Device(customer_id=customer.id, category="phones", brand="Apple", model="iPhone 14",
                        serial_number="SN123456")
        db.session.add(device)
        db.session.flush()

        ticket = Ticket(
            ticket_number="TK-0001", branch_id=branch.id,
            customer_id=customer.id, device_id=device.id,
            internal_status="completed",
        )
        db.session.add(ticket)
        db.session.flush()

        ids = {
            "branch_id": branch.id,
            "user_id": str(user.id),
            "customer_id": customer.id,
            "device_id": device.id,
            "ticket_id": ticket.id,
            "company_id": company.id,
        }
        db.session.commit()

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = ids["user_id"]

    return app, client, ids


def _create_ticket(app, ids, status="completed", ticket_number=None):
    """Helper to create an additional ticket."""
    with app.app_context():
        t = Ticket(
            ticket_number=ticket_number or f"TK-{uuid.uuid4().hex[:6]}",
            branch_id=ids["branch_id"],
            customer_id=ids["customer_id"],
            device_id=ids["device_id"],
            internal_status=status,
        )
        db.session.add(t)
        db.session.commit()
        return str(t.id)


# ═══════════════════════════════════════════════════════════════
# 17A: Warranty Model Tests
# ═══════════════════════════════════════════════════════════════

def test_warranty_model_fields(monkeypatch):
    """TicketWarranty model should have all required fields."""
    app, _, ids = _setup(monkeypatch)
    with app.app_context():
        assert hasattr(TicketWarranty, 'warranty_type')
        assert hasattr(TicketWarranty, 'warranty_days')
        assert hasattr(TicketWarranty, 'starts_at')
        assert hasattr(TicketWarranty, 'expires_at')
        assert hasattr(TicketWarranty, 'covers_labour')
        assert hasattr(TicketWarranty, 'covers_parts')
        assert hasattr(TicketWarranty, 'terms')
        assert hasattr(TicketWarranty, 'repair_summary')
        assert hasattr(TicketWarranty, 'parts_used')
        assert hasattr(TicketWarranty, 'status')
        assert hasattr(TicketWarranty, 'claim_count')
        assert hasattr(TicketWarranty, 'email_sent')


def test_warranty_type_constants(monkeypatch):
    """TicketWarranty should define valid type constants."""
    assert TicketWarranty.TYPE_NO_WARRANTY == "no_warranty"
    assert TicketWarranty.TYPE_STANDARD == "standard"
    assert TicketWarranty.TYPE_CUSTOM == "custom"
    assert TicketWarranty.VALID_TYPES == {"no_warranty", "standard", "custom"}


def test_warranty_status_constants(monkeypatch):
    """TicketWarranty should define valid status constants."""
    assert TicketWarranty.STATUS_ACTIVE == "active"
    assert TicketWarranty.STATUS_EXPIRED == "expired"
    assert TicketWarranty.STATUS_CLAIMED == "claimed"
    assert TicketWarranty.STATUS_VOIDED == "voided"


def test_warranty_persistence(monkeypatch):
    """Warranty should be saved and retrievable."""
    app, _, ids = _setup(monkeypatch)
    with app.app_context():
        ticket = db.session.get(Ticket, ids["ticket_id"])
        now = datetime.utcnow()
        w = TicketWarranty(
            ticket_id=ticket.id, customer_id=ids["customer_id"],
            device_id=ids["device_id"], branch_id=ids["branch_id"],
            warranty_type="standard", warranty_days=90,
            starts_at=now, expires_at=now + timedelta(days=90),
            covers_labour=True, covers_parts=True,
            terms="Standard warranty terms",
        )
        db.session.add(w)
        db.session.commit()

        fetched = TicketWarranty.query.filter_by(ticket_id=ticket.id).first()
        assert fetched is not None
        assert fetched.warranty_type == "standard"
        assert fetched.warranty_days == 90
        assert fetched.covers_labour is True
        assert fetched.covers_parts is True
        assert fetched.terms == "Standard warranty terms"


def test_warranty_date_calculation(monkeypatch):
    """Warranty end date should be start + days."""
    app, _, ids = _setup(monkeypatch)
    with app.app_context():
        ticket = db.session.get(Ticket, ids["ticket_id"])
        w = create_warranty(ticket=ticket, warranty_days=30)
        db.session.commit()
        delta = (w.expires_at - w.starts_at).days
        assert delta == 30


def test_warranty_is_active(monkeypatch):
    """Active warranty should report is_active=True."""
    app, _, ids = _setup(monkeypatch)
    with app.app_context():
        ticket = db.session.get(Ticket, ids["ticket_id"])
        w = create_warranty(ticket=ticket, warranty_days=90)
        db.session.commit()
        assert w.is_active is True
        assert w.is_expired is False
        assert w.days_remaining > 0


def test_warranty_expired(monkeypatch):
    """Expired warranty should report correctly."""
    app, _, ids = _setup(monkeypatch)
    with app.app_context():
        ticket = db.session.get(Ticket, ids["ticket_id"])
        now = datetime.utcnow()
        w = TicketWarranty(
            ticket_id=ticket.id, customer_id=ids["customer_id"],
            device_id=ids["device_id"], branch_id=ids["branch_id"],
            warranty_type="standard", warranty_days=30,
            starts_at=now - timedelta(days=60), expires_at=now - timedelta(days=30),
        )
        db.session.add(w)
        db.session.commit()
        assert w.is_active is False
        assert w.is_expired is True
        assert w.days_remaining == 0


def test_no_warranty_type(monkeypatch):
    """No-warranty type should not be active."""
    app, _, ids = _setup(monkeypatch)
    with app.app_context():
        ticket = db.session.get(Ticket, ids["ticket_id"])
        w = create_warranty(ticket=ticket, warranty_type="no_warranty")
        db.session.commit()
        assert w.warranty_type == "no_warranty"
        assert w.is_active is False
        assert w.warranty_days == 0
        assert w.covers_labour is False
        assert w.covers_parts is False


def test_warranty_coverage_description(monkeypatch):
    """Coverage description should reflect covers flags."""
    app, _, ids = _setup(monkeypatch)
    with app.app_context():
        ticket = db.session.get(Ticket, ids["ticket_id"])
        w = create_warranty(ticket=ticket, covers_labour=True, covers_parts=False)
        db.session.commit()
        assert "Labour" in w.coverage_description
        assert "Parts" not in w.coverage_description


def test_warranty_type_label(monkeypatch):
    """Type label should return human-readable text."""
    app, _, ids = _setup(monkeypatch)
    with app.app_context():
        ticket = db.session.get(Ticket, ids["ticket_id"])
        now = datetime.utcnow()
        w = TicketWarranty(
            ticket_id=ticket.id, customer_id=ids["customer_id"],
            device_id=ids["device_id"], branch_id=ids["branch_id"],
            warranty_type="standard", warranty_days=90,
            starts_at=now, expires_at=now + timedelta(days=90),
        )
        assert w.type_label == "Standard"
        w.warranty_type = "custom"
        assert w.type_label == "Custom"
        w.warranty_type = "no_warranty"
        assert w.type_label == "No Warranty"


# ═══════════════════════════════════════════════════════════════
# 17B: Warranty Service Tests
# ═══════════════════════════════════════════════════════════════

def test_create_warranty_service(monkeypatch):
    """create_warranty should create and return a warranty."""
    app, _, ids = _setup(monkeypatch)
    with app.app_context():
        ticket = db.session.get(Ticket, ids["ticket_id"])
        w = create_warranty(ticket=ticket, warranty_days=60, terms="Test terms")
        db.session.commit()
        assert w.id is not None
        assert w.warranty_days == 60
        assert w.terms == "Test terms"


def test_create_warranty_idempotent(monkeypatch):
    """Creating warranty twice for same ticket returns the existing one."""
    app, _, ids = _setup(monkeypatch)
    with app.app_context():
        ticket = db.session.get(Ticket, ids["ticket_id"])
        w1 = create_warranty(ticket=ticket, warranty_days=30)
        w2 = create_warranty(ticket=ticket, warranty_days=90)
        db.session.commit()
        assert str(w1.id) == str(w2.id)


def test_evaluate_warranty_no_warranty(monkeypatch):
    """evaluate_warranty on ticket without warranty."""
    app, _, ids = _setup(monkeypatch)
    with app.app_context():
        ticket = db.session.get(Ticket, ids["ticket_id"])
        result = evaluate_warranty(ticket)
        assert result["has_warranty"] is False
        assert result["warranty"] is None
        assert result["is_active"] is False


def test_evaluate_warranty_with_warranty(monkeypatch):
    """evaluate_warranty on ticket with warranty."""
    app, _, ids = _setup(monkeypatch)
    with app.app_context():
        ticket = db.session.get(Ticket, ids["ticket_id"])
        create_warranty(ticket=ticket, warranty_days=90)
        db.session.commit()
        result = evaluate_warranty(ticket)
        assert result["has_warranty"] is True
        assert result["is_active"] is True
        assert result["days_remaining"] > 0


def test_evaluate_warranty_prior_repairs(monkeypatch):
    """evaluate_warranty should include prior device warranties."""
    app, _, ids = _setup(monkeypatch)
    with app.app_context():
        # Create two tickets for same device
        ticket1 = db.session.get(Ticket, ids["ticket_id"])
        create_warranty(ticket=ticket1, warranty_days=30)
        db.session.commit()

        ticket2_id = _create_ticket(app, ids, ticket_number="TK-0002")
        ticket2 = db.session.get(Ticket, uuid.UUID(ticket2_id))
        result = evaluate_warranty(ticket2)
        assert len(result["prior_repairs"]) == 1


def test_get_device_warranty_history(monkeypatch):
    """Should return all warranties for a device."""
    app, _, ids = _setup(monkeypatch)
    with app.app_context():
        ticket = db.session.get(Ticket, ids["ticket_id"])
        create_warranty(ticket=ticket)
        db.session.commit()
        history = get_device_warranty_history(str(ids["device_id"]))
        assert len(history) == 1


def test_get_customer_warranties(monkeypatch):
    """Should return all warranties for a customer."""
    app, _, ids = _setup(monkeypatch)
    with app.app_context():
        ticket = db.session.get(Ticket, ids["ticket_id"])
        create_warranty(ticket=ticket)
        db.session.commit()
        warranties = get_customer_warranties(str(ids["customer_id"]))
        assert len(warranties) == 1


def test_get_active_warranties(monkeypatch):
    """Should return active warranties."""
    app, _, ids = _setup(monkeypatch)
    with app.app_context():
        ticket = db.session.get(Ticket, ids["ticket_id"])
        create_warranty(ticket=ticket, warranty_days=90)
        db.session.commit()
        active = get_active_warranties()
        assert len(active) == 1
        active_branch = get_active_warranties(branch_id=str(ids["branch_id"]))
        assert len(active_branch) == 1


def test_record_claim(monkeypatch):
    """Should record a warranty claim."""
    app, _, ids = _setup(monkeypatch)
    with app.app_context():
        ticket = db.session.get(Ticket, ids["ticket_id"])
        w = create_warranty(ticket=ticket)
        db.session.commit()
        record_claim(w, notes="Screen issue recurred")
        db.session.commit()
        assert w.claim_count == 1
        assert w.status == "claimed"
        assert "Screen issue" in w.claim_notes


def test_void_warranty(monkeypatch):
    """Should void a warranty with reason."""
    app, _, ids = _setup(monkeypatch)
    with app.app_context():
        ticket = db.session.get(Ticket, ids["ticket_id"])
        w = create_warranty(ticket=ticket)
        db.session.commit()
        void_warranty(w, reason="Customer damage", voided_by_id=ids["user_id"])
        db.session.commit()
        assert w.status == "voided"
        assert w.voided_reason == "Customer damage"
        assert w.voided_at is not None


def test_check_device_under_warranty(monkeypatch):
    """Should find active warranty for a device."""
    app, _, ids = _setup(monkeypatch)
    with app.app_context():
        ticket = db.session.get(Ticket, ids["ticket_id"])
        create_warranty(ticket=ticket, warranty_days=90)
        db.session.commit()
        active = check_device_under_warranty(str(ids["device_id"]))
        assert active is not None


def test_check_device_no_warranty(monkeypatch):
    """Should return None when device has no active warranty."""
    app, _, ids = _setup(monkeypatch)
    with app.app_context():
        result = check_device_under_warranty(str(ids["device_id"]))
        assert result is None


def test_expire_warranties(monkeypatch):
    """Should batch-expire warranties past their date."""
    app, _, ids = _setup(monkeypatch)
    with app.app_context():
        ticket = db.session.get(Ticket, ids["ticket_id"])
        now = datetime.utcnow()
        w = TicketWarranty(
            ticket_id=ticket.id, customer_id=ids["customer_id"],
            device_id=ids["device_id"], branch_id=ids["branch_id"],
            warranty_type="standard", warranty_days=30,
            starts_at=now - timedelta(days=60), expires_at=now - timedelta(days=30),
            status="active",
        )
        db.session.add(w)
        db.session.commit()
        count = expire_warranties()
        db.session.commit()
        assert count == 1
        assert w.status == "expired"


# ═══════════════════════════════════════════════════════════════
# 17C: Warranty Route Tests
# ═══════════════════════════════════════════════════════════════

def test_create_warranty_route(monkeypatch):
    """POST warranty creation should succeed for completed ticket."""
    app, client, ids = _setup(monkeypatch)
    with app.app_context():
        resp = client.post(f"/tickets/{ids['ticket_id']}/warranty", data={
            "warranty_type": "standard",
            "warranty_days": 90,
            "covers_labour": "y",
            "covers_parts": "y",
            "terms": "Standard 90 day warranty",
            "repair_summary": "Screen replaced",
        }, follow_redirects=True)
        assert resp.status_code == 200
        w = TicketWarranty.query.filter_by(ticket_id=ids["ticket_id"]).first()
        assert w is not None
        assert w.warranty_type == "standard"


def test_create_no_warranty_route(monkeypatch):
    """POST with no_warranty type should work."""
    app, client, ids = _setup(monkeypatch)
    with app.app_context():
        resp = client.post(f"/tickets/{ids['ticket_id']}/warranty", data={
            "warranty_type": "no_warranty",
            "warranty_days": 0,
        }, follow_redirects=True)
        assert resp.status_code == 200
        w = TicketWarranty.query.filter_by(ticket_id=ids["ticket_id"]).first()
        assert w is not None
        assert w.warranty_type == "no_warranty"


def test_warranty_claim_route(monkeypatch):
    """POST warranty claim should record it."""
    app, client, ids = _setup(monkeypatch)
    with app.app_context():
        ticket = db.session.get(Ticket, ids["ticket_id"])
        create_warranty(ticket=ticket)
        db.session.commit()

    resp = client.post(f"/tickets/{ids['ticket_id']}/warranty/claim", data={
        "claim_notes": "Battery draining again",
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        w = TicketWarranty.query.filter_by(ticket_id=ids["ticket_id"]).first()
        assert w.claim_count == 1
        assert w.status == "claimed"


def test_warranty_void_route(monkeypatch):
    """POST warranty void should void it."""
    app, client, ids = _setup(monkeypatch)
    with app.app_context():
        ticket = db.session.get(Ticket, ids["ticket_id"])
        create_warranty(ticket=ticket)
        db.session.commit()

    resp = client.post(f"/tickets/{ids['ticket_id']}/warranty/void", data={
        "voided_reason": "Physical damage by customer",
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        w = TicketWarranty.query.filter_by(ticket_id=ids["ticket_id"]).first()
        assert w.status == "voided"


def test_warranty_email_route(monkeypatch):
    """POST warranty email should log the email."""
    app, client, ids = _setup(monkeypatch)
    with app.app_context():
        ticket = db.session.get(Ticket, ids["ticket_id"])
        create_warranty(ticket=ticket)
        db.session.commit()

    resp = client.post(f"/tickets/{ids['ticket_id']}/warranty/send-email",
                       follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        w = TicketWarranty.query.filter_by(ticket_id=ids["ticket_id"]).first()
        assert w.email_sent is True


# ═══════════════════════════════════════════════════════════════
# 17D: Ticket Detail Warranty Rendering Tests
# ═══════════════════════════════════════════════════════════════

def test_ticket_detail_shows_warranty_section(monkeypatch):
    """Ticket detail page should contain warranty section."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get(f"/tickets/{ids['ticket_id']}")
    assert resp.status_code == 200
    assert b"warranty" in resp.data.lower() or b"Warranty" in resp.data


def test_ticket_detail_shows_warranty_form_for_completed(monkeypatch):
    """Completed ticket should show warranty capture form."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get(f"/tickets/{ids['ticket_id']}")
    assert resp.status_code == 200
    assert b"Save Warranty" in resp.data or b"warranty_type" in resp.data


def test_ticket_detail_shows_existing_warranty(monkeypatch):
    """Ticket with warranty should show warranty details."""
    app, client, ids = _setup(monkeypatch)
    with app.app_context():
        ticket = db.session.get(Ticket, ids["ticket_id"])
        create_warranty(ticket=ticket, warranty_days=90, terms="Test warranty terms displayed")
        db.session.commit()
    resp = client.get(f"/tickets/{ids['ticket_id']}")
    assert resp.status_code == 200
    assert b"Test warranty terms displayed" in resp.data


# ═══════════════════════════════════════════════════════════════
# 17E: Customer Detail Warranty Tests
# ═══════════════════════════════════════════════════════════════

def test_customer_detail_shows_warranty_column(monkeypatch):
    """Customer detail repair history should show warranty column."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get(f"/customers/{ids['customer_id']}")
    assert resp.status_code == 200
    # Should have the Warranty column header
    assert b"Warranty" in resp.data


def test_customer_detail_warranty_badge(monkeypatch):
    """Customer detail should show warranty badge for tickets with warranty."""
    app, client, ids = _setup(monkeypatch)
    with app.app_context():
        ticket = db.session.get(Ticket, ids["ticket_id"])
        create_warranty(ticket=ticket, warranty_days=90)
        db.session.commit()
    resp = client.get(f"/customers/{ids['customer_id']}")
    assert resp.status_code == 200
    assert b"Active" in resp.data


# ═══════════════════════════════════════════════════════════════
# 17F: Branded Email Service Tests
# ═══════════════════════════════════════════════════════════════

def test_branded_email_log_transport(monkeypatch):
    """Branded email with log transport should succeed."""
    app, _, ids = _setup(monkeypatch)
    with app.test_request_context():
        from app.services.branded_email_service import send_branded_email
        result = send_branded_email(
            to_email="test@example.com",
            to_name="Test User",
            subject="Test Subject",
            template_name="warranty_confirmation.html",
            template_context={
                "warranty": type('W', (), {
                    'type_label': 'Standard', 'coverage_description': 'Labour + Parts',
                    'warranty_days': 90, 'starts_at': datetime.utcnow(),
                    'expires_at': datetime.utcnow() + timedelta(days=90),
                    'terms': 'Test terms', 'repair_summary': 'Test repair',
                })(),
                "ticket": type('T', (), {'ticket_number': 'TK-0001'})(),
                "device": type('D', (), {'brand': 'Apple', 'model': 'iPhone 14', 'serial_number': 'SN123'})(),
                "customer": type('C', (), {'full_name': 'Test User'})(),
            },
        )
        assert result.success is True


def test_branded_email_no_recipient(monkeypatch):
    """Branded email without recipient should fail gracefully."""
    app, _, ids = _setup(monkeypatch)
    with app.test_request_context():
        from app.services.branded_email_service import send_branded_email
        result = send_branded_email(
            to_email="",
            subject="Test",
            template_name="warranty_confirmation.html",
        )
        assert result.success is False


def test_branded_email_missing_template(monkeypatch):
    """Branded email with nonexistent template should fail gracefully."""
    app, _, ids = _setup(monkeypatch)
    with app.test_request_context():
        from app.services.branded_email_service import send_branded_email
        result = send_branded_email(
            to_email="test@example.com",
            subject="Test",
            template_name="nonexistent_template.html",
        )
        assert result.success is False


def test_warranty_confirmation_email(monkeypatch):
    """Warranty confirmation email should succeed and mark email_sent."""
    app, _, ids = _setup(monkeypatch)
    with app.test_request_context():
        ticket = db.session.get(Ticket, ids["ticket_id"])
        w = create_warranty(ticket=ticket, warranty_days=90)
        db.session.commit()

        from app.services.branded_email_service import send_warranty_confirmation_email
        result = send_warranty_confirmation_email(w)
        db.session.commit()
        assert result.success is True
        assert w.email_sent is True


def test_aftercare_email(monkeypatch):
    """Aftercare email should succeed."""
    app, _, ids = _setup(monkeypatch)
    with app.test_request_context():
        ticket = db.session.get(Ticket, ids["ticket_id"])
        customer = db.session.get(Customer, ids["customer_id"])

        from app.services.branded_email_service import send_aftercare_email
        result = send_aftercare_email(
            customer=customer, ticket=ticket,
            message="How is your device working?",
        )
        assert result.success is True


def test_aftercare_email_no_email(monkeypatch):
    """Aftercare email should fail if customer has no email."""
    app, _, ids = _setup(monkeypatch)
    with app.test_request_context():
        customer = db.session.get(Customer, ids["customer_id"])
        customer.email = None
        db.session.commit()

        ticket = db.session.get(Ticket, ids["ticket_id"])
        from app.services.branded_email_service import send_aftercare_email
        result = send_aftercare_email(customer=customer, ticket=ticket, message="Test")
        assert result.success is False


def test_branded_email_spanish_template(monkeypatch):
    """Spanish branded email should render the ES template."""
    app, _, ids = _setup(monkeypatch)
    with app.test_request_context():
        ticket = db.session.get(Ticket, ids["ticket_id"])
        w = create_warranty(ticket=ticket, warranty_days=90)
        db.session.commit()

        from app.services.branded_email_service import send_warranty_confirmation_email
        result = send_warranty_confirmation_email(w, language="es")
        assert result.success is True


# ═══════════════════════════════════════════════════════════════
# 17G: Branded Email Route Tests
# ═══════════════════════════════════════════════════════════════

def test_send_branded_update_email_route(monkeypatch):
    """POST branded email route should succeed."""
    app, client, ids = _setup(monkeypatch)
    resp = client.post(f"/tickets/{ids['ticket_id']}/send-branded-email", data={
        "content": "Your repair is complete. Please collect your device.",
    }, follow_redirects=True)
    assert resp.status_code == 200


def test_send_branded_email_no_content(monkeypatch):
    """POST branded email without content should fail."""
    app, client, ids = _setup(monkeypatch)
    resp = client.post(f"/tickets/{ids['ticket_id']}/send-branded-email", data={
        "content": "",
    }, follow_redirects=True)
    assert resp.status_code == 200  # Redirects with flash


# ═══════════════════════════════════════════════════════════════
# 17H: Permission Tests
# ═══════════════════════════════════════════════════════════════

def test_warranty_permission_admin(monkeypatch):
    """Admin should have warranty management permission."""
    from app.services.permission_service import can_manage_warranty
    app, _, ids = _setup(monkeypatch, role_name="Admin")
    with app.app_context():
        user = db.session.get(User, uuid.UUID(ids["user_id"]))
        assert can_manage_warranty(user) is True


def test_warranty_permission_technician(monkeypatch):
    """Technician should have warranty management permission."""
    from app.services.permission_service import can_manage_warranty
    app, _, ids = _setup(monkeypatch, role_name="Technician")
    with app.app_context():
        user = db.session.get(User, uuid.UUID(ids["user_id"]))
        assert can_manage_warranty(user) is True


def test_warranty_permission_readonly_denied(monkeypatch):
    """Read Only should NOT have warranty management permission."""
    from app.services.permission_service import can_manage_warranty
    app, _, ids = _setup(monkeypatch, role_name="Read Only")
    with app.app_context():
        user = db.session.get(User, uuid.UUID(ids["user_id"]))
        assert can_manage_warranty(user) is False


def test_branded_email_permission(monkeypatch):
    """can_send_branded_email should work for workshop roles."""
    from app.services.permission_service import can_send_branded_email
    app, _, ids = _setup(monkeypatch, role_name="Manager")
    with app.app_context():
        user = db.session.get(User, uuid.UUID(ids["user_id"]))
        assert can_send_branded_email(user) is True


def test_warranty_route_permission_denied(monkeypatch):
    """Read Only user should get 403 on warranty create."""
    app, client, ids = _setup(monkeypatch, role_name="Read Only")
    resp = client.post(f"/tickets/{ids['ticket_id']}/warranty", data={
        "warranty_type": "standard",
        "warranty_days": 90,
    })
    assert resp.status_code == 403


def test_branded_email_route_permission_denied(monkeypatch):
    """Read Only user should get 403 on branded email."""
    app, client, ids = _setup(monkeypatch, role_name="Read Only")
    resp = client.post(f"/tickets/{ids['ticket_id']}/send-branded-email", data={
        "content": "Test",
    })
    assert resp.status_code == 403


# ═══════════════════════════════════════════════════════════════
# 17I: Communication Log Tests
# ═══════════════════════════════════════════════════════════════

def test_warranty_creates_note(monkeypatch):
    """Creating warranty should add a ticket note."""
    app, client, ids = _setup(monkeypatch)
    with app.app_context():
        resp = client.post(f"/tickets/{ids['ticket_id']}/warranty", data={
            "warranty_type": "standard",
            "warranty_days": 90,
            "covers_labour": "y",
            "covers_parts": "y",
        }, follow_redirects=True)
        assert resp.status_code == 200
        note = TicketNote.query.filter_by(ticket_id=ids["ticket_id"]).first()
        assert note is not None
        assert "Warranty recorded" in note.content


def test_warranty_email_creates_comm_note(monkeypatch):
    """Sending warranty email should create a communication note."""
    app, client, ids = _setup(monkeypatch)
    with app.app_context():
        ticket = db.session.get(Ticket, ids["ticket_id"])
        create_warranty(ticket=ticket)
        db.session.commit()

    client.post(f"/tickets/{ids['ticket_id']}/warranty/send-email", follow_redirects=True)
    with app.app_context():
        comm_notes = TicketNote.query.filter_by(
            ticket_id=ids["ticket_id"], note_type="communication"
        ).all()
        assert len(comm_notes) > 0


# ═══════════════════════════════════════════════════════════════
# 17J: Email Template Rendering Tests
# ═══════════════════════════════════════════════════════════════

def test_warranty_email_template_en_renders(monkeypatch):
    """English warranty email template should render without errors."""
    app, _, ids = _setup(monkeypatch)
    with app.test_request_context():
        from flask import render_template
        html = render_template("emails/en/warranty_confirmation.html",
            branding={"company_name": "TestCorp", "company_email": "test@test.com",
                       "company_phone": "555", "company_website": "test.com",
                       "company_logo": None, "document_footer": "Footer"},
            recipient_name="John",
            language="en",
            year=2026,
            warranty=type('W', (), {
                'type_label': 'Standard', 'coverage_description': 'Labour + Parts',
                'warranty_days': 90, 'starts_at': datetime(2026, 1, 1),
                'expires_at': datetime(2026, 4, 1),
                'terms': 'Test terms', 'repair_summary': 'Screen replaced',
            })(),
            ticket=type('T', (), {'ticket_number': 'TK-0001'})(),
            device=type('D', (), {'brand': 'Apple', 'model': 'iPhone 14', 'serial_number': 'SN123'})(),
            customer=type('C', (), {'full_name': 'John Doe'})(),
        )
        assert "Warranty Confirmation" in html
        assert "TestCorp" in html
        assert "TK-0001" in html


def test_warranty_email_template_es_renders(monkeypatch):
    """Spanish warranty email template should render without errors."""
    app, _, ids = _setup(monkeypatch)
    with app.test_request_context():
        from flask import render_template
        html = render_template("emails/es/warranty_confirmation.html",
            branding={"company_name": "TestCorp", "company_email": "test@test.com",
                       "company_phone": "555", "company_website": "test.com",
                       "company_logo": None, "document_footer": "Footer"},
            recipient_name="Juan",
            language="es",
            year=2026,
            warranty=type('W', (), {
                'type_label': 'Estándar', 'coverage_description': 'Mano de obra + Piezas',
                'warranty_days': 90, 'starts_at': datetime(2026, 1, 1),
                'expires_at': datetime(2026, 4, 1),
                'terms': 'Condiciones', 'repair_summary': 'Pantalla reemplazada',
            })(),
            ticket=type('T', (), {'ticket_number': 'TK-0001'})(),
            device=type('D', (), {'brand': 'Apple', 'model': 'iPhone 14', 'serial_number': 'SN123'})(),
            customer=type('C', (), {'full_name': 'Juan García'})(),
        )
        assert "Confirmación de Garantía" in html
        assert "TestCorp" in html


def test_aftercare_email_template_renders(monkeypatch):
    """Aftercare email template should render."""
    app, _, ids = _setup(monkeypatch)
    with app.test_request_context():
        from flask import render_template
        html = render_template("emails/en/aftercare_followup.html",
            branding={"company_name": "TestCorp", "company_email": "test@test.com",
                       "company_phone": "555", "company_website": "test.com",
                       "company_logo": None, "document_footer": "Footer"},
            recipient_name="John",
            language="en",
            year=2026,
            ticket=type('T', (), {
                'ticket_number': 'TK-0001',
                'device': type('D', (), {'brand': 'Apple', 'model': 'iPhone 14'})(),
            })(),
            customer=type('C', (), {'full_name': 'John Doe'})(),
            message="How is your device working?",
        )
        assert "Follow-up" in html
        assert "How is your device working?" in html


def test_ticket_update_email_template_renders(monkeypatch):
    """Ticket update email template should render."""
    app, _, ids = _setup(monkeypatch)
    with app.test_request_context():
        from flask import render_template
        html = render_template("emails/en/ticket_update.html",
            branding={"company_name": "TestCorp", "company_email": "test@test.com",
                       "company_phone": "555", "company_website": "test.com",
                       "company_logo": None, "document_footer": "Footer"},
            recipient_name="John",
            language="en",
            year=2026,
            ticket=type('T', (), {
                'ticket_number': 'TK-0001',
                'device': type('D', (), {'brand': 'Apple', 'model': 'iPhone 14'})(),
            })(),
            customer=type('C', (), {'full_name': 'John Doe'})(),
            message="Your repair is in progress.",
            status_text="In Repair",
        )
        assert "Update on Your Repair" in html
        assert "In Repair" in html


# ═══════════════════════════════════════════════════════════════
# 17K: Parts History Awareness Tests
# ═══════════════════════════════════════════════════════════════

def test_parts_summary_no_parts(monkeypatch):
    """Parts summary for ticket with no reservations should be empty."""
    app, _, ids = _setup(monkeypatch)
    with app.app_context():
        ticket = db.session.get(Ticket, ids["ticket_id"])
        summary = get_ticket_parts_summary(ticket)
        assert summary == ""


def test_parts_summary_with_reservation(monkeypatch):
    """Parts summary should include reserved parts."""
    app, _, ids = _setup(monkeypatch)
    with app.app_context():
        # Create a part, stock location, and reservation
        cat = PartCategory(name="Screens")
        db.session.add(cat)
        db.session.flush()
        part = Part(name="iPhone 14 Screen", sku="SCR-IP14", is_active=True,
                    cost_price=50.0, sale_price=100.0)
        db.session.add(part)
        loc = StockLocation(code="SHELF-A", name="Shelf A", branch_id=ids["branch_id"], location_type="shelf")
        db.session.add(loc)
        db.session.flush()
        reservation = StockReservation(
            ticket_id=ids["ticket_id"], part_id=part.id,
            branch_id=ids["branch_id"], location_id=loc.id,
            quantity=1, status="consumed",
        )
        db.session.add(reservation)
        db.session.commit()

        ticket = db.session.get(Ticket, ids["ticket_id"])
        summary = get_ticket_parts_summary(ticket)
        assert "iPhone 14 Screen" in summary
        assert "installed" in summary


# ═══════════════════════════════════════════════════════════════
# 17L: Translation Tests
# ═══════════════════════════════════════════════════════════════

def test_warranty_flash_messages_translatable(monkeypatch):
    """Warranty flash messages should be properly marked for translation."""
    # This tests that the flash messages use _() correctly.
    # We just verify the route doesn't crash with es locale.
    app, client, ids = _setup(monkeypatch)
    with client.session_transaction() as sess:
        sess['locale'] = 'es'
    resp = client.post(f"/tickets/{ids['ticket_id']}/warranty", data={
        "warranty_type": "standard",
        "warranty_days": 90,
        "covers_labour": "y",
        "covers_parts": "y",
    }, follow_redirects=True)
    assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════
# 17M: Edge Case Tests
# ═══════════════════════════════════════════════════════════════

def test_warranty_on_nonexistent_ticket(monkeypatch):
    """Warranty creation on nonexistent ticket should 302 redirect."""
    app, client, ids = _setup(monkeypatch)
    fake_id = uuid.uuid4()
    resp = client.post(f"/tickets/{fake_id}/warranty", data={
        "warranty_type": "standard", "warranty_days": 90,
    })
    assert resp.status_code == 302


def test_warranty_claim_without_warranty(monkeypatch):
    """Claiming on ticket without warranty should flash error."""
    app, client, ids = _setup(monkeypatch)
    resp = client.post(f"/tickets/{ids['ticket_id']}/warranty/claim", data={
        "claim_notes": "Test",
    }, follow_redirects=True)
    assert resp.status_code == 200


def test_warranty_void_without_warranty(monkeypatch):
    """Voiding on ticket without warranty should flash error."""
    app, client, ids = _setup(monkeypatch)
    resp = client.post(f"/tickets/{ids['ticket_id']}/warranty/void", data={
        "voided_reason": "Test",
    }, follow_redirects=True)
    assert resp.status_code == 200


def test_warranty_email_without_warranty(monkeypatch):
    """Sending warranty email without warranty should flash error."""
    app, client, ids = _setup(monkeypatch)
    resp = client.post(f"/tickets/{ids['ticket_id']}/warranty/send-email",
                       follow_redirects=True)
    assert resp.status_code == 200


def test_email_result_bool(monkeypatch):
    """EmailResult should be truthy on success and falsy on failure."""
    from app.services.branded_email_service import EmailResult
    assert bool(EmailResult(True, "ok")) is True
    assert bool(EmailResult(False, "fail")) is False


def test_company_warranty_defaults(monkeypatch):
    """Company model should have warranty default fields."""
    app, _, ids = _setup(monkeypatch)
    with app.app_context():
        company = Company.query.filter_by(is_active=True).first()
        assert company.default_warranty_days == 90
        assert company.default_warranty_terms == "Standard 90-day warranty"
