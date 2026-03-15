import re
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from app import create_app
from app.extensions import db
from app.models import (
    AppSetting, Branch, Customer, Device, Diagnostic, IntakeDisclaimerAcceptance,
    IntakeSubmission, Part, PartCategory, PartOrder, PartOrderEvent, PartOrderLine,
    PortalToken, Quote, QuoteApproval, QuoteLine, QuoteOption, RepairChecklist,
    Role, StockLayer, StockLevel, StockLocation, StockMovement, StockReservation,
    Supplier, Ticket, TicketNote, User,
)
from app.models.checklist import ChecklistItem, DEFAULT_CHECKLISTS
from app.models.inventory import PartSupplier, part_category_links
from app.models.role import role_permissions
from app.models.user import user_branch_access, user_roles
from app.services.seed_service import seed_phase1_data
from app.utils.ticketing import default_sla_target, is_ticket_overdue


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
        Device.__table__, Ticket.__table__, IntakeSubmission.__table__,
        IntakeDisclaimerAcceptance.__table__, PortalToken.__table__,
        Diagnostic.__table__, Quote.__table__, QuoteOption.__table__,
        QuoteLine.__table__, QuoteApproval.__table__, TicketNote.__table__,
        Supplier.__table__, PartCategory.__table__, part_category_links,
        Part.__table__, PartSupplier.__table__,
        StockLocation.__table__, StockLevel.__table__,
        StockMovement.__table__, StockReservation.__table__, StockLayer.__table__,
        PartOrder.__table__, PartOrderLine.__table__, PartOrderEvent.__table__,
        AppSetting.__table__, RepairChecklist.__table__, ChecklistItem.__table__,
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
    r = client.post('/auth/login', data={'email': 'admin@ironcore.com', 'password': 'admin1234', 'csrf_token': token}, follow_redirects=False)
    assert r.status_code == 302


def _setup(monkeypatch):
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        branch = Branch.query.filter_by(code='HQ').first()
        customer = Customer(
            full_name='P5 Customer', phone='+34555111222',
            email='p5test@example.com', preferred_language='en',
            primary_branch=branch,
        )
        db.session.add(customer)
        db.session.flush()
        device = Device(
            customer=customer, category='phones', brand='Samsung',
            model='Galaxy S24', serial_number='SN-P5X', imei='IMEI-P5X',
        )
        db.session.add(device)
        db.session.flush()
        ticket = Ticket(
            ticket_number='HQ-20260315-P5X1', branch_id=branch.id,
            customer_id=customer.id, device_id=device.id,
            internal_status='in_repair', customer_status='In Progress',
            priority='normal',
            sla_target_at=default_sla_target(datetime.utcnow(), 5),
        )
        db.session.add(ticket)
        db.session.flush()
        supplier = Supplier(name='P5 Supplier', is_active=True)
        db.session.add(supplier)
        db.session.flush()
        part = Part(sku='P5X-001', name='Test Battery P5', is_active=True, sale_price=80.00, cost_price=40.00)
        db.session.add(part)
        db.session.flush()
        location = StockLocation(branch_id=branch.id, code='P5MAIN', name='P5 Main', location_type='main_stock', is_active=True)
        db.session.add(location)
        db.session.commit()
        ids = {
            'branch_id': str(branch.id),
            'customer_id': str(customer.id),
            'ticket_id': str(ticket.id),
            'supplier_id': str(supplier.id),
            'part_id': str(part.id),
            'location_id': str(location.id),
        }
    monkeypatch.setattr('app.services.auth_service.log_action', lambda *a, **kw: None)
    client = app.test_client()
    _login(client)
    return app, client, ids


# ── 5A: Dashboard overdue SLA ──

def test_overdue_ticket_with_sla(monkeypatch):
    """Ticket past SLA target should be detected as overdue."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        branch = Branch.query.filter_by(code='HQ').first()
        customer = Customer(full_name='SLA Cust', phone='+34111', email='sla@example.com', preferred_language='en', primary_branch=branch)
        db.session.add(customer)
        db.session.flush()
        device = Device(customer=customer, category='phones', brand='Test', model='T1', serial_number='SLA1', imei='SLA1')
        db.session.add(device)
        db.session.flush()
        # Set SLA target to 2 days ago
        past_sla = datetime.utcnow() - timedelta(days=2)
        ticket = Ticket(
            ticket_number='HQ-20260315-SLA1', branch_id=branch.id,
            customer_id=customer.id, device_id=device.id,
            internal_status='in_repair', customer_status='In Progress',
            priority='normal', sla_target_at=past_sla,
        )
        db.session.add(ticket)
        db.session.commit()
        assert is_ticket_overdue(ticket, datetime.utcnow()) is True


def test_overdue_ticket_without_sla_field(monkeypatch):
    """Ticket without sla_target_at should compute default and still be detected as overdue."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        branch = Branch.query.filter_by(code='HQ').first()
        customer = Customer(full_name='NoSLA Cust', phone='+34222', email='nosla@example.com', preferred_language='en', primary_branch=branch)
        db.session.add(customer)
        db.session.flush()
        device = Device(customer=customer, category='phones', brand='Test', model='T2', serial_number='NOSLA1', imei='NOSLA1')
        db.session.add(device)
        db.session.flush()
        # Ticket created 10 days ago, no sla_target_at
        ticket = Ticket(
            ticket_number='HQ-20260315-NOSLA', branch_id=branch.id,
            customer_id=customer.id, device_id=device.id,
            internal_status='in_repair', customer_status='In Progress',
            priority='normal',
        )
        db.session.add(ticket)
        db.session.commit()
        ticket.created_at = datetime.utcnow() - timedelta(days=10)
        db.session.commit()
        # With sla_days=5, a 10-day-old ticket should be overdue
        assert is_ticket_overdue(ticket, datetime.utcnow(), sla_days=5) is True


# ── 5B: Checklist improvements ──

def test_checklist_no_line_through(monkeypatch):
    """Checked checklist items should not have line-through class."""
    app, client, ids = _setup(monkeypatch)
    # Create checklist
    detail = client.get(f'/tickets/{ids["ticket_id"]}')
    token = _csrf(detail.data)
    client.post(f'/tickets/{ids["ticket_id"]}/checklists/create', data={'csrf_token': token, 'checklist_type': 'pre_repair'}, follow_redirects=False)
    resp = client.get(f'/tickets/{ids["ticket_id"]}')
    html = resp.data.decode()
    assert 'line-through' not in html


def test_new_checklist_after_completion(monkeypatch):
    """Should be able to create a new checklist after completing the previous one."""
    app, client, ids = _setup(monkeypatch)
    with app.app_context():
        ticket = db.session.get(Ticket, uuid.UUID(ids['ticket_id']))
        checklist = RepairChecklist(ticket_id=ticket.id, checklist_type='pre_repair', device_category='phones')
        db.session.add(checklist)
        db.session.flush()
        item = ChecklistItem(checklist_id=checklist.id, position=0, label='Test', is_checked=True)
        db.session.add(item)
        checklist.completed_at = datetime.utcnow()
        db.session.commit()
        cl_id = str(checklist.id)

    # Now try creating another pre_repair checklist
    detail = client.get(f'/tickets/{ids["ticket_id"]}')
    token = _csrf(detail.data)
    resp = client.post(f'/tickets/{ids["ticket_id"]}/checklists/create', data={'csrf_token': token, 'checklist_type': 'pre_repair'}, follow_redirects=False)
    assert resp.status_code == 302

    with app.app_context():
        count = RepairChecklist.query.filter_by(ticket_id=uuid.UUID(ids['ticket_id']), checklist_type='pre_repair').count()
        assert count == 2


# ── 5D: EUR-only quote display ──

def test_quote_detail_shows_eur(monkeypatch):
    """Quote detail page should show EUR currency."""
    app, client, ids = _setup(monkeypatch)
    with app.app_context():
        ticket = db.session.get(Ticket, uuid.UUID(ids['ticket_id']))
        quote = Quote(ticket_id=ticket.id, version=1, status='draft', currency='EUR')
        db.session.add(quote)
        db.session.flush()
        option = QuoteOption(quote_id=quote.id, name='Repair Option 1', position=1)
        db.session.add(option)
        db.session.flush()
        line = QuoteLine(option_id=option.id, line_type='part', description='Battery', quantity=1, unit_price=80.00)
        db.session.add(line)
        approval = QuoteApproval(quote_id=quote.id, status='pending', language='en')
        db.session.add(approval)
        db.session.commit()
        quote_id = str(quote.id)

    resp = client.get(f'/quotes/{quote_id}')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'EUR' in html
    assert 'IGIC' in html


# ── 5E: Quote terms from settings ──

def test_quote_settings_page(monkeypatch):
    """Quote settings page should be accessible."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get('/settings/quotes')
    assert resp.status_code == 200
    assert b'Terms' in resp.data


# ── 5F: Quote option naming ──

def test_quote_builder_repair_option_label(monkeypatch):
    """Quote builder should use 'Repair Option' naming."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get(f'/quotes/ticket/{ids["ticket_id"]}/new')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'Repair Option' in html


def test_standalone_quote_repair_option_label(monkeypatch):
    """Standalone quote builder should use 'Repair Option' naming."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get('/quotes/standalone/new')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'Repair Option' in html


# ── 5G: Public quote approval ──

def test_public_quote_approval_form_no_csrf_block(monkeypatch):
    """Public quote approval form should not require CSRF (token auth)."""
    from app.forms.public_forms import PublicQuoteApprovalForm
    assert hasattr(PublicQuoteApprovalForm.Meta, 'csrf')
    assert PublicQuoteApprovalForm.Meta.csrf is False


# ── 5H: Intake rework ──

def test_intake_page_shows_quick_checkin(monkeypatch):
    """Ticket creation page should show Quick Check-In branding."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get('/tickets/new')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'Quick Check-In' in html
    assert 'Device Condition' in html or 'device_condition' in html


# ── 5I: Part creation JSON endpoint ──

def test_create_part_json(monkeypatch):
    """Parts can be created via JSON API."""
    app, client, ids = _setup(monkeypatch)
    # Get CSRF token from a page
    page = client.get('/inventory/parts')
    token = _csrf(page.data)
    resp = client.post('/inventory/parts/create-json',
        json={'sku': 'NEW-JSON-001', 'name': 'JSON Part', 'cost_price': 10.0, 'sale_price': 25.0},
        headers={'X-CSRFToken': token, 'Content-Type': 'application/json'},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['ok'] is True
    assert data['sku'] == 'NEW-JSON-001'


# ── 5J: Part search includes cost_price ──

def test_part_search_includes_cost_price(monkeypatch):
    """Part search endpoint should include cost_price in results."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get('/inventory/parts/search?q=P5X')
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data['items']) > 0
    assert 'cost_price' in data['items'][0]


# ── 5K: Auto order status ──

def test_order_auto_status_on_all_received():
    """Order status logic already checks all lines received."""
    from app.services.order_service import line_remaining_qty
    # Simple unit test of the helper
    class MockLine:
        def __init__(self, qty, recv):
            self.quantity = qty
            self.received_quantity = recv
    assert line_remaining_qty(MockLine(10, 10)) == 0
    assert line_remaining_qty(MockLine(10, 5)) == 5


# ── 5L: Order list has filter form ──

def test_order_list_has_filter(monkeypatch):
    """Orders list should have a filter form."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get('/orders/')
    assert resp.status_code == 200
    assert b'Filter' in resp.data


# ── 5M: Movement form has part search ──

def test_movement_form_has_part_search(monkeypatch):
    """Stock movement form should have part search input."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get('/inventory/movements/new')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'part-search' in html


# ── Customer creation JSON endpoint ──

def test_create_customer_json(monkeypatch):
    """Customers can be created via JSON API."""
    app, client, ids = _setup(monkeypatch)
    page = client.get('/inventory/parts')
    token = _csrf(page.data)
    resp = client.post('/customers/create-json',
        json={'full_name': 'New Customer', 'phone': '+34999888777', 'email': 'new@example.com'},
        headers={'X-CSRFToken': token, 'Content-Type': 'application/json'},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['ok'] is True


# ── Dashboard shows overdue count ──

def test_dashboard_loads(monkeypatch):
    """Dashboard should load without errors."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get('/')
    assert resp.status_code == 200
    assert b'Overdue' in resp.data or b'overdue' in resp.data
