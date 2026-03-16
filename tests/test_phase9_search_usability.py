"""Phase 9 — Ticket Creation, Search & Workshop Usability tests.

Covers:
- Device search AJAX endpoint
- Device creation via AJAX (inline new device)
- Customer search endpoints
- Part search endpoint
- Safe part deletion (unused part deletes, used part blocked)
- Ticket creation with existing and new devices
- Phase 8 workshop regression checks
"""
import json
import re
import uuid
from datetime import datetime, timedelta

from app import create_app
from app.extensions import db
from app.models import (
    AppSetting, Booking, Branch, Customer, Device, Diagnostic, IntakeSubmission,
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
    }, follow_redirects=False)
    assert r.status_code == 302


def _setup(monkeypatch):
    """Create app with seeded data plus test customer/device/part."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        branch = Branch.query.filter_by(code='HQ').first()
        customer = Customer(
            full_name='Search TestCustomer', phone='+34555111222',
            email='search@test.com', preferred_language='en',
            primary_branch=branch,
        )
        db.session.add(customer)
        db.session.flush()
        device = Device(
            customer_id=customer.id, category='phones',
            brand='Apple', model='iPhone 15 Pro', serial_number='SN-SEARCH-001',
            imei='123456789012345',
        )
        db.session.add(device)
        db.session.flush()
        part = Part(sku='SCR-IPH15', name='iPhone 15 Screen', is_active=True,
                    cost_price=45.00, sale_price=89.00)
        db.session.add(part)
        db.session.flush()
        unused_part = Part(sku='UNUSED-001', name='Unused Test Part', is_active=True,
                           cost_price=10.00, sale_price=20.00)
        db.session.add(unused_part)
        db.session.flush()
        ids = {
            'branch_id': branch.id,
            'customer_id': customer.id,
            'device_id': device.id,
            'part_id': part.id,
            'unused_part_id': unused_part.id,
        }
        db.session.commit()
    monkeypatch.setattr('app.services.auth_service.log_action', lambda *a, **kw: None)
    monkeypatch.setattr('app.services.audit_service.log_action', lambda *a, **kw: None)
    monkeypatch.setattr('app.blueprints.tickets.routes.log_action', lambda *a, **kw: None)
    return app, ids


# ──────────────────────────────────────────────────
# 9.1: Device Search AJAX
# ──────────────────────────────────────────────────

def test_device_search_by_model(monkeypatch):
    """Device search should find devices by model name."""
    app, ids = _setup(monkeypatch)
    client = app.test_client()
    _login(client)
    resp = client.get('/tickets/device-search?q=iPhone')
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data['items']) >= 1
    assert any('iPhone 15 Pro' in item['label'] for item in data['items'])


def test_device_search_by_serial(monkeypatch):
    """Device search should find devices by serial number."""
    app, ids = _setup(monkeypatch)
    client = app.test_client()
    _login(client)
    resp = client.get('/tickets/device-search?q=SN-SEARCH')
    data = resp.get_json()
    assert len(data['items']) >= 1


def test_device_search_by_imei(monkeypatch):
    """Device search should find devices by IMEI."""
    app, ids = _setup(monkeypatch)
    client = app.test_client()
    _login(client)
    resp = client.get('/tickets/device-search?q=123456789')
    data = resp.get_json()
    assert len(data['items']) >= 1


def test_device_search_scoped_to_customer(monkeypatch):
    """Device search with customer_id should scope results."""
    app, ids = _setup(monkeypatch)
    client = app.test_client()
    _login(client)
    resp = client.get(f'/tickets/device-search?q=iPhone&customer_id={ids["customer_id"]}')
    data = resp.get_json()
    assert len(data['items']) >= 1


def test_device_search_min_length(monkeypatch):
    """Device search with < 2 chars should return empty."""
    app, ids = _setup(monkeypatch)
    client = app.test_client()
    _login(client)
    resp = client.get('/tickets/device-search?q=i')
    data = resp.get_json()
    assert data['items'] == []


# ──────────────────────────────────────────────────
# 9.2: Device Creation via AJAX
# ──────────────────────────────────────────────────

def test_device_create_json_success(monkeypatch):
    """AJAX device creation should create a device and return its ID."""
    app, ids = _setup(monkeypatch)
    client = app.test_client()
    _login(client)
    # Get CSRF token
    page = client.get('/tickets/new')
    token = _csrf(page.data)
    resp = client.post('/tickets/device-create-json',
        data=json.dumps({
            'customer_id': str(ids['customer_id']),
            'brand': 'Samsung', 'model': 'Galaxy S24',
            'category': 'phones', 'serial_number': 'SN-NEW-001',
        }),
        content_type='application/json',
        headers={'X-CSRFToken': token},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['ok'] is True
    assert 'Samsung' in data['label']
    assert 'Galaxy S24' in data['label']
    # Verify device exists in DB
    with app.app_context():
        d = db.session.get(Device, uuid.UUID(data['id']))
        assert d is not None
        assert d.brand == 'Samsung'
        assert d.customer_id == ids['customer_id']


def test_device_create_json_missing_fields(monkeypatch):
    """AJAX device creation should fail if brand or model missing."""
    app, ids = _setup(monkeypatch)
    client = app.test_client()
    _login(client)
    page = client.get('/tickets/new')
    token = _csrf(page.data)
    resp = client.post('/tickets/device-create-json',
        data=json.dumps({'customer_id': str(ids['customer_id']), 'brand': '', 'model': ''}),
        content_type='application/json',
        headers={'X-CSRFToken': token},
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['ok'] is False


# ──────────────────────────────────────────────────
# 9.3: Customer Search
# ──────────────────────────────────────────────────

def test_customer_search_in_tickets(monkeypatch):
    """Ticket customer search should find customers by name."""
    app, ids = _setup(monkeypatch)
    client = app.test_client()
    _login(client)
    resp = client.get('/tickets/customer-search?q=Search')
    data = resp.get_json()
    assert len(data['items']) >= 1
    assert any('Search TestCustomer' in item['label'] for item in data['items'])


def test_customer_search_in_customers_bp(monkeypatch):
    """Customer blueprint search should find customers by phone."""
    app, ids = _setup(monkeypatch)
    client = app.test_client()
    _login(client)
    resp = client.get('/customers/search?q=555111')
    data = resp.get_json()
    assert len(data['items']) >= 1


def test_customer_search_min_length(monkeypatch):
    """Customer search with < 2 chars should return empty."""
    app, ids = _setup(monkeypatch)
    client = app.test_client()
    _login(client)
    resp = client.get('/tickets/customer-search?q=S')
    data = resp.get_json()
    assert data['items'] == []


def test_customer_list_page_has_search(monkeypatch):
    """Customer list page should have a search input."""
    app, ids = _setup(monkeypatch)
    client = app.test_client()
    _login(client)
    resp = client.get('/customers/')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'customer-live-search' in html


def test_customer_list_search_filters(monkeypatch):
    """Customer list page should filter by query param."""
    app, ids = _setup(monkeypatch)
    client = app.test_client()
    _login(client)
    resp = client.get('/customers/?q=Search+TestCustomer')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'Search TestCustomer' in html


# ──────────────────────────────────────────────────
# 9.4: Part Search
# ──────────────────────────────────────────────────

def test_part_search_by_name(monkeypatch):
    """Part search should find parts by name."""
    app, ids = _setup(monkeypatch)
    client = app.test_client()
    _login(client)
    resp = client.get('/inventory/parts/search?q=iPhone+15')
    data = resp.get_json()
    assert len(data['items']) >= 1
    assert any('iPhone 15 Screen' in item['label'] for item in data['items'])


def test_part_search_by_sku(monkeypatch):
    """Part search should find parts by SKU."""
    app, ids = _setup(monkeypatch)
    client = app.test_client()
    _login(client)
    resp = client.get('/inventory/parts/search?q=SCR-IPH15')
    data = resp.get_json()
    assert len(data['items']) >= 1


def test_part_search_min_length(monkeypatch):
    """Part search with < 2 chars should return empty."""
    app, ids = _setup(monkeypatch)
    client = app.test_client()
    _login(client)
    resp = client.get('/inventory/parts/search?q=S')
    data = resp.get_json()
    assert data['items'] == []


def test_parts_list_has_live_search(monkeypatch):
    """Parts list page should have live search input."""
    app, ids = _setup(monkeypatch)
    client = app.test_client()
    _login(client)
    resp = client.get('/inventory/parts')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'parts-live-search' in html


def test_parts_list_has_delete_button(monkeypatch):
    """Parts list should show delete buttons."""
    app, ids = _setup(monkeypatch)
    client = app.test_client()
    _login(client)
    resp = client.get('/inventory/parts')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'Delete' in html


# ──────────────────────────────────────────────────
# 9.5: Safe Part Deletion
# ──────────────────────────────────────────────────

def test_delete_unused_part(monkeypatch):
    """Unused part should be soft-deleted successfully."""
    app, ids = _setup(monkeypatch)
    client = app.test_client()
    _login(client)
    page = client.get('/inventory/parts')
    token = _csrf(page.data)
    resp = client.post(f'/inventory/parts/{ids["unused_part_id"]}/delete',
                       data={'csrf_token': token}, follow_redirects=True)
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'deleted' in html.lower() or 'Unused Test Part' not in html
    with app.app_context():
        part = db.session.get(Part, ids['unused_part_id'])
        assert part.deleted_at is not None
        assert part.is_active is False


def test_delete_part_with_stock_movements_blocked(monkeypatch):
    """Part with stock movements should not be deletable."""
    app, ids = _setup(monkeypatch)
    with app.app_context():
        branch = Branch.query.filter_by(code='HQ').first()
        loc = StockLocation(branch_id=branch.id, code='MAIN', name='Main Stock',
                            location_type='main_stock', is_active=True)
        db.session.add(loc)
        db.session.flush()
        mv = StockMovement(part_id=ids['part_id'], branch_id=branch.id,
                           location_id=loc.id, movement_type='inbound',
                           quantity=5, notes='Test movement')
        db.session.add(mv)
        db.session.commit()
    client = app.test_client()
    _login(client)
    page = client.get('/inventory/parts')
    token = _csrf(page.data)
    resp = client.post(f'/inventory/parts/{ids["part_id"]}/delete',
                       data={'csrf_token': token}, follow_redirects=True)
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'Cannot delete' in html or 'Deactivate' in html
    with app.app_context():
        part = db.session.get(Part, ids['part_id'])
        assert part.deleted_at is None  # Should NOT be deleted


def test_delete_part_with_order_lines_blocked(monkeypatch):
    """Part referenced by part order lines should not be deletable."""
    app, ids = _setup(monkeypatch)
    with app.app_context():
        branch = Branch.query.filter_by(code='HQ').first()
        supplier = Supplier(name='Test Supplier', email='sup@test.com', is_active=True)
        db.session.add(supplier)
        db.session.flush()
        order = PartOrder(reference='PO-TEST-001', supplier_id=supplier.id,
                          branch_id=branch.id, status='ordered')
        db.session.add(order)
        db.session.flush()
        line = PartOrderLine(order_id=order.id, part_id=ids['part_id'],
                             quantity=2, unit_cost=45.00)
        db.session.add(line)
        db.session.commit()
    client = app.test_client()
    _login(client)
    page = client.get('/inventory/parts')
    token = _csrf(page.data)
    resp = client.post(f'/inventory/parts/{ids["part_id"]}/delete',
                       data={'csrf_token': token}, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        part = db.session.get(Part, ids['part_id'])
        assert part.deleted_at is None  # Should NOT be deleted


# ──────────────────────────────────────────────────
# 9.6: Ticket Creation Flow
# ──────────────────────────────────────────────────

def test_ticket_creation_page_loads(monkeypatch):
    """Ticket creation page should load with new device form."""
    app, ids = _setup(monkeypatch)
    client = app.test_client()
    _login(client)
    resp = client.get('/tickets/new')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'new-device-btn' in html
    assert 'new-device-form' in html
    assert 'device-search' in html


def test_customer_devices_endpoint(monkeypatch):
    """Customer devices endpoint should return devices for a customer."""
    app, ids = _setup(monkeypatch)
    client = app.test_client()
    _login(client)
    resp = client.get(f'/tickets/customer/{ids["customer_id"]}/devices')
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) >= 1
    assert any('iPhone 15 Pro' in d['label'] for d in data)


def test_ticket_creation_with_existing_device(monkeypatch):
    """Creating a ticket with an existing device should work."""
    app, ids = _setup(monkeypatch)
    client = app.test_client()
    _login(client)
    page = client.get('/tickets/new')
    token = _csrf(page.data)
    resp = client.post('/tickets/new', data={
        'csrf_token': token,
        'customer_id': str(ids['customer_id']),
        'device_id': str(ids['device_id']),
        'branch_id': str(ids['branch_id']),
        'priority': 'normal',
        'issue_summary': 'Screen replacement needed',
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        ticket = Ticket.query.filter_by(issue_summary='Screen replacement needed').first()
        assert ticket is not None
        assert ticket.device_id == ids['device_id']
        assert ticket.customer_id == ids['customer_id']


# ──────────────────────────────────────────────────
# 9.7: Phase 8 Regression Checks
# ──────────────────────────────────────────────────

def test_bench_board_still_loads(monkeypatch):
    """Bench board should still load after Phase 9 changes."""
    app, ids = _setup(monkeypatch)
    client = app.test_client()
    _login(client)
    resp = client.get('/tickets/board')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'Awaiting Diagnosis' in html


def test_workflow_transitions_intact(monkeypatch):
    """Phase 8 workflow transitions should still work."""
    from app.services.workflow_service import is_valid_transition
    assert is_valid_transition('unassigned', 'assigned')
    assert not is_valid_transition('unassigned', 'completed')
    assert is_valid_transition('in_repair', 'testing_qa')


def test_dashboard_still_loads(monkeypatch):
    """Dashboard should still load with workshop metrics."""
    app, ids = _setup(monkeypatch)
    client = app.test_client()
    _login(client)
    resp = client.get('/')
    assert resp.status_code == 200
