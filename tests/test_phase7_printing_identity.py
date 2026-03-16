"""Phase 7 tests: Customer business identity, printable documents, labels, QR codes."""

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

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


class TestConfig:
    TESTING = True
    SECRET_KEY = "test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SERVER_NAME = "localhost"
    DEFAULT_TICKET_SLA_DAYS = 5
    DEFAULT_IGIC_RATE = 0.07
    SUPPORTED_LOCALES = ["en"]
    BABEL_DEFAULT_LOCALE = "en"
    BABEL_DEFAULT_TIMEZONE = "UTC"


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


def _setup(monkeypatch, business_customer=False):
    monkeypatch.setattr('app.services.auth_service.log_action', _noop_log)
    monkeypatch.setattr('app.services.audit_service.log_action', _noop_log)
    monkeypatch.setattr('app.blueprints.intake.routes.log_action', _noop_log)
    monkeypatch.setattr('app.blueprints.tickets.routes.log_action', _noop_log)

    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()

        company = Company(legal_name='IRONCore Repairs SL', trading_name='IRONCore',
                          cif_nif='B12345678', tax_mode='IGIC', phone='+34 922 000 000',
                          email='info@ironcore.es', default_quote_terms='Valid 30 days.',
                          default_repair_terms='Max liability limited.', document_footer='IRONCore Repairs SL · CIF B12345678')
        db.session.add(company)
        db.session.flush()

        role = Role(name="Admin")
        db.session.add(role)
        branch = Branch(code="TF", name="Tenerife Store", is_active=True, company_id=company.id,
                        address_line_1="Calle Example 1", city="Santa Cruz", postcode="38001",
                        country="Spain", phone="+34 922 111 222", email="tf@ironcore.es",
                        ticket_prefix="TF-", quote_prefix="QTF-")
        db.session.add(branch)
        db.session.flush()

        user = User(full_name="Test Admin", email="admin@test.com", is_active=True, default_branch_id=branch.id)
        user.password_hash = "pbkdf2:sha256:600000$test$test"
        user.roles.append(role)
        db.session.add(user)

        if business_customer:
            customer = Customer(
                full_name="Juan Garcia", phone="555-0001", primary_branch_id=branch.id,
                customer_type="business", company_name="Acme Corp SL", cif_vat="B87654321",
                billing_address_line_1="Av. Business 42", billing_city="Las Palmas",
                billing_postcode="35001", billing_country="Spain",
                billing_email="billing@acme.es", billing_phone="+34 928 000 000",
            )
        else:
            customer = Customer(full_name="John Doe", phone="555-0001", primary_branch_id=branch.id)
        db.session.add(customer)
        db.session.flush()

        device = Device(customer_id=customer.id, category="phones", brand="Apple", model="iPhone 14",
                        serial_number="SN12345", imei="351234567890123")
        db.session.add(device)
        db.session.flush()

        ticket = Ticket(
            ticket_number="TF-0001", branch_id=branch.id, customer_id=customer.id,
            device_id=device.id, internal_status="in_repair", customer_status="In Progress",
            priority="normal", issue_summary="Screen cracked",
            sla_target_at=datetime.utcnow() + timedelta(days=5),
        )
        db.session.add(ticket)
        db.session.flush()

        # Add intake note with accessories
        db.session.add(TicketNote(ticket_id=ticket.id, author_user_id=user.id,
                                  note_type="internal", content="Issue: Screen cracked\nAccessories: Charger, Case"))

        # Create a quote
        quote = Quote(ticket_id=ticket.id, version=1, status="draft", currency="EUR",
                      language="en", terms_snapshot="Valid 30 days.")
        db.session.add(quote)
        db.session.flush()

        option = QuoteOption(quote_id=quote.id, name="Screen Repair", position=1)
        db.session.add(option)
        db.session.flush()

        db.session.add(QuoteLine(option_id=option.id, line_type="part", description="iPhone 14 Screen",
                                 quantity=1, unit_price=89.00))
        db.session.add(QuoteLine(option_id=option.id, line_type="labour", description="Installation",
                                 quantity=1, unit_price=35.00))

        approval = QuoteApproval(quote_id=quote.id, status="pending", language="en")
        db.session.add(approval)

        # Diagnosis
        db.session.add(Diagnostic(ticket_id=ticket.id, version=1,
                                  customer_reported_fault="Screen broken",
                                  technician_diagnosis="LCD + digitizer damaged",
                                  recommended_repair="Full screen replacement"))

        # Checklist
        checklist = RepairChecklist(ticket_id=ticket.id, checklist_type="pre_repair")
        db.session.add(checklist)
        db.session.flush()
        db.session.add(ChecklistItem(checklist_id=checklist.id, label="Powers on", is_checked=True))
        db.session.add(ChecklistItem(checklist_id=checklist.id, label="Screen condition", is_checked=False, notes="Cracked"))

        ids = {
            "branch_id": branch.id,
            "user_id": str(user.id),
            "customer_id": customer.id,
            "device_id": device.id,
            "ticket_id": ticket.id,
            "quote_id": quote.id,
            "company_id": company.id,
        }
        db.session.commit()

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = ids["user_id"]

    return app, client, ids


# ── 7A: Customer Business Identity ──

def test_customer_model_has_business_fields(monkeypatch):
    """Customer model should have business identity fields."""
    app, _, ids = _setup(monkeypatch, business_customer=True)
    with app.app_context():
        c = db.session.get(Customer, ids["customer_id"])
        assert c.customer_type == "business"
        assert c.company_name == "Acme Corp SL"
        assert c.cif_vat == "B87654321"
        assert c.is_business is True
        assert "Acme Corp SL" in c.display_name
        assert c.billing_address


def test_customer_individual_defaults(monkeypatch):
    """Individual customer should have sensible defaults."""
    app, _, ids = _setup(monkeypatch)
    with app.app_context():
        c = db.session.get(Customer, ids["customer_id"])
        assert c.customer_type == "individual"
        assert c.is_business is False
        assert c.display_name == "John Doe"
        assert c.short_name == "Doe"


def test_customer_edit_page(monkeypatch):
    """Customer edit page should load with business fields."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get(f'/customers/{str(ids["customer_id"])}/edit')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'Customer Type' in html
    assert 'Company Name' in html
    assert 'CIF / VAT' in html


def test_customer_edit_to_business(monkeypatch):
    """Should be able to convert individual to business customer."""
    app, client, ids = _setup(monkeypatch)
    resp = client.post(f'/customers/{str(ids["customer_id"])}/edit', data={
        'full_name': 'John Doe',
        'phone': '555-0001',
        'customer_type': 'business',
        'company_name': 'Test Business SL',
        'cif_vat': 'B99999999',
        'preferred_language': 'en',
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        c = db.session.get(Customer, ids["customer_id"])
        assert c.customer_type == "business"
        assert c.company_name == "Test Business SL"


def test_customer_detail_shows_business_badge(monkeypatch):
    """Business customer detail page should show BIZ badge."""
    app, client, ids = _setup(monkeypatch, business_customer=True)
    resp = client.get(f'/customers/{str(ids["customer_id"])}')
    assert resp.status_code == 200
    assert b'Business' in resp.data or b'BIZ' in resp.data


def test_customer_list_shows_business_badge(monkeypatch):
    """Customer list should show BIZ badge for business customers."""
    app, client, ids = _setup(monkeypatch, business_customer=True)
    resp = client.get('/customers/')
    assert resp.status_code == 200
    assert b'BIZ' in resp.data


# ── 7B: Company-Aware Ticket/Quote Context ──

def test_ticket_detail_shows_business_customer(monkeypatch):
    """Ticket detail should show business customer name and badge."""
    app, client, ids = _setup(monkeypatch, business_customer=True)
    resp = client.get(f'/tickets/{str(ids["ticket_id"])}')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'Acme Corp SL' in html
    assert 'BIZ' in html


def test_ticket_detail_individual_no_badge(monkeypatch):
    """Ticket detail for individual should not show BIZ badge."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get(f'/tickets/{str(ids["ticket_id"])}')
    assert resp.status_code == 200
    assert b'BIZ' not in resp.data


def test_quote_detail_shows_business_customer(monkeypatch):
    """Quote detail should show business customer info."""
    app, client, ids = _setup(monkeypatch, business_customer=True)
    resp = client.get(f'/quotes/{str(ids["quote_id"])}')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'Acme Corp SL' in html


# ── 7D: Printable Quote ──

def test_print_quote_route(monkeypatch):
    """Printable quote route should load successfully."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get(f'/print/quote/{str(ids["quote_id"])}')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'IRONCore' in html
    assert 'iPhone 14 Screen' in html
    assert 'EUR' in html
    assert 'Print' in html


def test_print_quote_business_customer(monkeypatch):
    """Printable quote for business customer should show company details."""
    app, client, ids = _setup(monkeypatch, business_customer=True)
    resp = client.get(f'/print/quote/{str(ids["quote_id"])}')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'Acme Corp SL' in html
    assert 'B87654321' in html


def test_print_quote_has_totals(monkeypatch):
    """Printable quote should show subtotal, IGIC, and grand total."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get(f'/print/quote/{str(ids["quote_id"])}')
    html = resp.data.decode()
    assert 'Subtotal' in html
    assert 'IGIC' in html
    assert 'Total' in html


def test_print_quote_has_branch_identity(monkeypatch):
    """Printable quote should show branch/company identity."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get(f'/print/quote/{str(ids["quote_id"])}')
    html = resp.data.decode()
    assert 'B12345678' in html  # CIF
    assert 'Santa Cruz' in html or 'Calle Example' in html


# ── 7E: Printable Ticket / Intake Slip ──

def test_print_ticket_route(monkeypatch):
    """Printable ticket route should load successfully."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get(f'/print/ticket/{str(ids["ticket_id"])}')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'TF-0001' in html
    assert 'Apple' in html
    assert 'iPhone 14' in html
    assert 'Screen cracked' in html


def test_print_ticket_business_customer(monkeypatch):
    """Printable ticket for business customer shows company details."""
    app, client, ids = _setup(monkeypatch, business_customer=True)
    resp = client.get(f'/print/ticket/{str(ids["ticket_id"])}')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'Acme Corp SL' in html


def test_print_ticket_has_device_details(monkeypatch):
    """Printable ticket should show IMEI and serial."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get(f'/print/ticket/{str(ids["ticket_id"])}')
    html = resp.data.decode()
    assert 'SN12345' in html
    assert '351234567890123' in html


def test_print_ticket_has_diagnostics(monkeypatch):
    """Printable ticket should include diagnostic summary."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get(f'/print/ticket/{str(ids["ticket_id"])}')
    html = resp.data.decode()
    assert 'LCD' in html or 'Screen broken' in html


# ── 7F: Printable Checklist ──

def test_print_checklist_route(monkeypatch):
    """Printable checklist route should load."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get(f'/print/ticket/{str(ids["ticket_id"])}/checklist')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'Powers on' in html
    assert 'Screen condition' in html
    assert 'Pre Repair' in html or 'Pre-Repair' in html


# ── 7G: Device and Accessory Labels ──

def test_device_label_route(monkeypatch):
    """Device label route should load with ticket info."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get(f'/print/ticket/{str(ids["ticket_id"])}/label/device')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'TF-0001' in html
    assert 'Apple' in html or 'iPhone 14' in html


def test_device_label_has_qr(monkeypatch):
    """Device label should include QR code."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get(f'/print/ticket/{str(ids["ticket_id"])}/label/device')
    html = resp.data.decode()
    assert 'data:image/png;base64,' in html


def test_accessory_label_route(monkeypatch):
    """Accessory label route should load."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get(f'/print/ticket/{str(ids["ticket_id"])}/label/accessory')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'TF-0001' in html
    assert 'Charger' in html
    assert 'Case' in html


# ── 7H: Document Service ──

def test_resolve_branch_identity(monkeypatch):
    """Document service should resolve full branch + company identity."""
    app, _, ids = _setup(monkeypatch)
    from app.services.document_service import resolve_branch_identity
    with app.app_context():
        branch = db.session.get(Branch, ids["branch_id"])
        identity = resolve_branch_identity(branch)
        assert identity["company_name"] == "IRONCore"
        assert identity["cif_nif"] == "B12345678"
        assert identity["branch_name"] == "Tenerife Store"
        assert "Santa Cruz" in identity["address"]
        assert identity["quote_terms"] == "Valid 30 days."


def test_customer_block_individual(monkeypatch):
    """Customer block for individual should have basic info."""
    app, _, ids = _setup(monkeypatch)
    from app.services.document_service import customer_block
    with app.app_context():
        c = db.session.get(Customer, ids["customer_id"])
        block = customer_block(c)
        assert block["is_business"] is False
        assert block["display_name"] == "John Doe"


def test_customer_block_business(monkeypatch):
    """Customer block for business should include company details."""
    app, _, ids = _setup(monkeypatch, business_customer=True)
    from app.services.document_service import customer_block
    with app.app_context():
        c = db.session.get(Customer, ids["customer_id"])
        block = customer_block(c)
        assert block["is_business"] is True
        assert block["company_name"] == "Acme Corp SL"
        assert block["cif_vat"] == "B87654321"


# ── 7I: QR Code ──

def test_qr_code_generation():
    """QR code generator should produce a data URI."""
    from app.services.document_service import generate_qr_data_uri
    uri = generate_qr_data_uri("TF-0001")
    assert uri is not None
    assert uri.startswith("data:image/png;base64,")


# ── 7J: Navigation / Actions ──

def test_ticket_detail_has_print_buttons(monkeypatch):
    """Ticket detail should have print action buttons."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get(f'/tickets/{str(ids["ticket_id"])}')
    html = resp.data.decode()
    assert 'Ticket Slip' in html
    assert 'Checklist' in html
    assert 'Device Label' in html
    assert 'Accessory Label' in html


def test_quote_detail_has_print_button(monkeypatch):
    """Quote detail should have a Print Quote button."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get(f'/quotes/{str(ids["quote_id"])}')
    html = resp.data.decode()
    assert 'Print Quote' in html


# ── 7K: Migration Validation ──

def test_migration_covers_customer_fields(monkeypatch):
    """Phase 7 migration should include customer business fields."""
    import os
    migrations_dir = os.path.join(os.path.dirname(__file__), '..', 'migrations', 'versions')
    content = ''
    for fname in os.listdir(migrations_dir):
        if 'phase7' in fname.lower() or 'customer_business' in fname.lower():
            with open(os.path.join(migrations_dir, fname)) as f:
                content += f.read()
    assert 'customer_type' in content
    assert 'company_name' in content
    assert 'cif_vat' in content
    assert 'billing_address_line_1' in content


def test_migration_has_downgrade(monkeypatch):
    """Phase 7 migration must have working downgrade."""
    import os
    migrations_dir = os.path.join(os.path.dirname(__file__), '..', 'migrations', 'versions')
    for fname in os.listdir(migrations_dir):
        if 'phase7' in fname.lower() or 'customer_business' in fname.lower():
            with open(os.path.join(migrations_dir, fname)) as f:
                content = f.read()
            assert 'def downgrade' in content
            assert 'drop_column' in content
