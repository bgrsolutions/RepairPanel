import os
import re
import uuid
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
from app.models.checklist import ChecklistItem
from app.models.inventory import PartSupplier, part_category_links
from app.models.role import role_permissions
from app.models.user import user_branch_access, user_roles
from app.services.seed_service import seed_phase1_data
from app.services.inventory_service import apply_stock_movement
from app.services.order_service import append_order_event, line_remaining_qty


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


def test_part_creation_stock_and_reservation(monkeypatch):
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        branch = Branch.query.filter_by(code='HQ').first()
        customer = Customer(full_name='Inv Cust', phone='+34000', email='inv@example.com', preferred_language='en', primary_branch=branch)
        db.session.add(customer); db.session.flush()
        device = Device(customer=customer, category='phones', brand='Nokia', model='N1', serial_number='INV1', imei='123')
        db.session.add(device); db.session.flush()
        ticket = Ticket(ticket_number='HQ-20260312-4000', branch_id=branch.id, customer_id=customer.id, device_id=device.id, internal_status='in_repair', customer_status='In progress', priority='normal')
        db.session.add(ticket); db.session.commit()
        ticket_id = ticket.id

    monkeypatch.setattr('app.services.auth_service.log_action', lambda *args, **kwargs: None)
    client = app.test_client()
    _login(client)

    part_new = client.get('/inventory/parts/new')
    token = _csrf(part_new.data)
    part_resp = client.post('/inventory/parts/new', data={'csrf_token': token, 'sku': 'BAT-001', 'barcode': 'BATBAR', 'name': 'Battery Pack', 'category': 'Battery', 'supplier_sku': 'SUP-BAT', 'cost_price': '10', 'sale_price': '25', 'serial_tracking': '', 'is_active': 'y', 'notes': 'test'}, follow_redirects=False)
    assert part_resp.status_code == 302

    loc_new = client.get('/inventory/locations/new')
    token2 = _csrf(loc_new.data)
    with app.app_context():
        branch = Branch.query.filter_by(code='HQ').first()
    loc_resp = client.post('/inventory/locations/new', data={'csrf_token': token2, 'branch_id': str(branch.id), 'code': 'MAIN', 'name': 'Main Stock', 'location_type': 'main_stock'}, follow_redirects=False)
    assert loc_resp.status_code == 302

    move_new = client.get('/inventory/movements/new')
    token3 = _csrf(move_new.data)
    with app.app_context():
        part = Part.query.filter_by(sku='BAT-001').first()
        loc = StockLocation.query.filter_by(code='MAIN').first()
        branch = Branch.query.filter_by(code='HQ').first()
    move_resp = client.post('/inventory/movements/new', data={'csrf_token': token3, 'part_id': str(part.id), 'branch_id': str(branch.id), 'location_id': str(loc.id), 'movement_type': 'inbound', 'quantity': '5', 'notes': 'initial stock'}, follow_redirects=False)
    assert move_resp.status_code == 302

    detail = client.get(f'/tickets/{ticket_id}')
    token4 = _csrf(detail.data)
    reserve_resp = client.post(f'/tickets/{ticket_id}/reserve', data={'csrf_token': token4, 'part_id': str(part.id), 'location_id': str(loc.id), 'quantity': '2'}, follow_redirects=False)
    assert reserve_resp.status_code == 302

    with app.app_context():
        level = StockLevel.query.filter_by(part_id=part.id, location_id=loc.id).first()
        assert float(level.on_hand_qty) == 5.0
        assert float(level.reserved_qty) == 2.0
        res = StockReservation.query.filter_by(ticket_id=ticket_id).first()
        assert res is not None


# ── Phase 4: helpers ──

def _setup_p4(monkeypatch):
    """Reusable setup for Phase 4 tests."""
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        branch = Branch.query.filter_by(code='HQ').first()
        customer = Customer(
            full_name='P4 Customer', phone='+34999111222',
            email='p4test@example.com', preferred_language='en',
            primary_branch=branch,
        )
        db.session.add(customer)
        db.session.flush()
        device = Device(
            customer=customer, category='phones', brand='Apple',
            model='iPhone 15', serial_number='SN-P4X', imei='IMEI-P4X',
        )
        db.session.add(device)
        db.session.flush()
        ticket = Ticket(
            ticket_number='HQ-20260315-P4X1', branch_id=branch.id,
            customer_id=customer.id, device_id=device.id,
            internal_status='in_repair', customer_status='In Progress',
            priority='normal',
        )
        db.session.add(ticket)
        db.session.flush()
        supplier = Supplier(name='P4 Supplier', is_active=True)
        db.session.add(supplier)
        db.session.flush()
        part = Part(sku='P4X-001', name='Test Screen P4', is_active=True, sale_price=120.00, cost_price=60.00)
        db.session.add(part)
        db.session.flush()
        location = StockLocation(branch_id=branch.id, code='P4MAIN', name='P4 Main', location_type='main_stock', is_active=True)
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


# ── 4A: Quote total calculation ──

def test_quote_builder_has_change_event(monkeypatch):
    """Quote builder JS should bind change events for broad browser compat."""
    app, client, ids = _setup_p4(monkeypatch)
    resp = client.get(f'/quotes/ticket/{ids["ticket_id"]}/new')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'updateLineTotal' in html
    assert "addEventListener('change'" in html or 'addEventListener("change"' in html


def test_standalone_quote_has_change_event(monkeypatch):
    """Standalone quote builder also binds change events."""
    app, client, ids = _setup_p4(monkeypatch)
    resp = client.get('/quotes/standalone/new')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert "addEventListener('change'" in html or 'addEventListener("change"' in html


# ── 4C: Part creation UX ──

def test_part_new_has_numbered_sections(monkeypatch):
    """New part form should have numbered section headers and margin preview."""
    app, client, ids = _setup_p4(monkeypatch)
    resp = client.get('/inventory/parts/new')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'Identity' in html
    assert 'Pricing' in html
    assert 'Suppliers' in html
    assert 'margin-preview' in html
    assert 'updateMargin' in html


def test_part_edit_has_margin_preview(monkeypatch):
    """Edit part form should have margin preview."""
    app, client, ids = _setup_p4(monkeypatch)
    resp = client.get(f'/inventory/parts/{ids["part_id"]}/edit')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'margin-preview' in html


# ── 4D: Order line sale_price ──

def test_order_line_sale_price_column():
    """PartOrderLine model should have sale_price column."""
    from sqlalchemy import inspect as sa_inspect
    mapper = sa_inspect(PartOrderLine)
    columns = {col.key for col in mapper.columns}
    assert 'sale_price' in columns


def test_order_form_shows_sale_price(monkeypatch):
    """Order form should include sale_price input."""
    app, client, ids = _setup_p4(monkeypatch)
    resp = client.get('/orders/new')
    assert resp.status_code == 200
    assert b'Sale Price' in resp.data or b'sale_price' in resp.data


def test_order_line_sale_price_persists(monkeypatch):
    """sale_price should persist on PartOrderLine."""
    app, client, ids = _setup_p4(monkeypatch)
    with app.app_context():
        order = PartOrder(
            supplier_id=uuid.UUID(ids['supplier_id']),
            branch_id=uuid.UUID(ids['branch_id']),
            order_type='stock', status='ordered',
        )
        db.session.add(order)
        db.session.flush()
        line = PartOrderLine(
            order_id=order.id, part_id=uuid.UUID(ids['part_id']),
            quantity=5, unit_cost=55.00, sale_price=130.00, status='ordered',
        )
        db.session.add(line)
        db.session.commit()
        reloaded = db.session.get(PartOrderLine, line.id)
        assert float(reloaded.sale_price) == 130.00


# ── 4E: Bulk receive ──

def test_bulk_receive_all_lines(monkeypatch):
    """Receive All should receive every unreceived line and update stock."""
    app, client, ids = _setup_p4(monkeypatch)

    with app.app_context():
        order = PartOrder(
            supplier_id=uuid.UUID(ids['supplier_id']),
            branch_id=uuid.UUID(ids['branch_id']),
            order_type='stock', status='ordered',
        )
        db.session.add(order)
        db.session.flush()
        line = PartOrderLine(
            order_id=order.id, part_id=uuid.UUID(ids['part_id']),
            quantity=10, unit_cost=50.00, sale_price=115.00, status='ordered',
        )
        db.session.add(line)
        append_order_event(order, 'ordered', notes='Test')
        db.session.commit()
        order_id = str(order.id)

    detail = client.get(f'/orders/{order_id}')
    token = _csrf(detail.data)

    resp = client.post(
        f'/orders/{order_id}/receive-all',
        data={'location_id': ids['location_id'], 'bulk_note': 'Full batch', 'csrf_token': token},
        follow_redirects=False,
    )
    assert resp.status_code == 302

    with app.app_context():
        order = db.session.get(PartOrder, uuid.UUID(order_id))
        assert order.status == 'received'
        for line in order.lines:
            assert line.status == 'received'
            assert float(line.received_quantity) == 10.0

        part = db.session.get(Part, uuid.UUID(ids['part_id']))
        assert float(part.sale_price) == 115.00

        level = StockLevel.query.filter_by(
            part_id=uuid.UUID(ids['part_id']),
            location_id=uuid.UUID(ids['location_id']),
        ).first()
        assert level is not None
        assert float(level.on_hand_qty) == 10.0


# ── 4F: Stock overview grouping ──

def test_stock_overview_grouped_view(monkeypatch):
    """Stock overview should show grouped part rows with expandable details."""
    app, client, ids = _setup_p4(monkeypatch)

    with app.app_context():
        apply_stock_movement(
            part_id=ids['part_id'], branch_id=ids['branch_id'],
            location_id=ids['location_id'], movement_type='inbound',
            quantity=7, notes='Initial',
        )
        db.session.commit()

    resp = client.get('/inventory/')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'stock-part-row' in html
    assert 'stock-detail-row' in html
    assert 'P4X-001' in html


# ── 4G: Parts list CSRF ──

def test_parts_list_has_csrf_on_toggle(monkeypatch):
    """Parts list toggle-active form should have CSRF token."""
    app, client, ids = _setup_p4(monkeypatch)
    resp = client.get('/inventory/parts')
    assert resp.status_code == 200
    assert b'csrf_token' in resp.data


# ── 4I: Migration coverage ──

def test_migration_covers_order_line_sale_price():
    """Verify a migration adds sale_price to part_order_lines."""
    migration_dir = os.path.join(os.path.dirname(__file__), '..', 'migrations', 'versions')
    found = False
    for fname in os.listdir(migration_dir):
        if not fname.endswith('.py'):
            continue
        with open(os.path.join(migration_dir, fname)) as f:
            content = f.read()
        if 'part_order_lines' in content and 'sale_price' in content:
            found = True
            break
    assert found, "No migration found that adds sale_price to part_order_lines"
