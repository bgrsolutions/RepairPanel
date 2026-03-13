import re

from app import create_app
from app.extensions import db
from app.models import (
    Branch, Customer, Device, Diagnostic, IntakeSubmission, Part, PartOrder, PartOrderEvent, PartOrderLine,
    Quote, QuoteApproval, QuoteLine, QuoteOption, Role, StockLevel, StockLocation, StockMovement, StockReservation,
    Supplier, Ticket, TicketNote, User,
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
        Branch.__table__, Role.__table__, Customer.__table__, User.__table__, role_permissions, user_roles, user_branch_access,
        Device.__table__, Ticket.__table__, IntakeSubmission.__table__, Diagnostic.__table__, Quote.__table__, QuoteOption.__table__,
        QuoteLine.__table__, QuoteApproval.__table__, TicketNote.__table__, Supplier.__table__, Part.__table__, StockLocation.__table__,
        StockLevel.__table__, StockMovement.__table__, StockReservation.__table__, PartOrder.__table__, PartOrderLine.__table__, PartOrderEvent.__table__,
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


def test_refinement_pass_b_plus_core(monkeypatch):
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        branch = Branch.query.filter_by(code='HQ').first()

        tech_role = Role.query.filter_by(name='Technician').first()
        tech = User(full_name='B+ Tech', email='bp-tech@example.com', preferred_language='en', is_active=True, default_branch=branch)
        tech.set_password('admin1234')
        tech.roles.append(tech_role)
        tech.branches.append(branch)
        db.session.add(tech)

        supplier_a = Supplier(name='Supplier A', is_active=True)
        supplier_b = Supplier(name='Supplier B', is_active=True)
        db.session.add_all([supplier_a, supplier_b])

        part_a = Part(sku='P-A', name='Part A', is_active=True)
        part_b = Part(sku='P-B', name='Part B', is_active=True)
        db.session.add_all([part_a, part_b])

        customer = Customer(full_name='B Plus Customer', phone='+34002', email='bplus@example.com', preferred_language='en', primary_branch=branch)
        db.session.add(customer)
        db.session.flush()
        device = Device(customer=customer, category='phones', brand='Google', model='Pixel', serial_number='BP-1', imei='999')
        db.session.add(device)

        location = StockLocation(branch_id=branch.id, code='MAIN', name='Main', location_type='main_stock', is_active=True)
        db.session.add(location)
        db.session.commit()

    monkeypatch.setattr('app.services.auth_service.log_action', lambda *args, **kwargs: None)
    monkeypatch.setattr('app.blueprints.tickets.routes.log_action', lambda *args, **kwargs: None)
    monkeypatch.setattr('app.blueprints.quotes.routes.log_action', lambda *args, **kwargs: None)
    client = app.test_client()
    _login(client)

    # ticket create with technician assignment and promised ETA
    new_page = client.get('/tickets/new')
    token = _csrf(new_page.data)
    with app.app_context():
        branch = Branch.query.filter_by(code='HQ').first()
        customer = Customer.query.filter_by(email='bplus@example.com').first()
        device = Device.query.filter_by(serial_number='BP-1').first()
        tech = User.query.filter_by(email='bp-tech@example.com').first()
    resp = client.post('/tickets/new', data={
        'csrf_token': token,
        'branch_id': str(branch.id),
        'customer_id': str(customer.id),
        'device_id': str(device.id),
        'assigned_technician_id': str(tech.id),
        'internal_status': '',
        'priority': 'normal',
        'issue_summary': 'Screen issue',
        'quoted_completion_at': '2026-12-31T15:00',
    }, follow_redirects=False)
    assert resp.status_code == 302

    with app.app_context():
        ticket = Ticket.query.filter_by(issue_summary='Screen issue').first()
        assert ticket is not None
        assert ticket.internal_status == 'assigned'
        assert str(ticket.assigned_technician_id) == str(tech.id)
        assert ticket.quoted_completion_at is not None
        ticket_id = ticket.id

    # quote with multiple lines
    q_page = client.get(f'/quotes/ticket/{ticket_id}/new')
    q_token = _csrf(q_page.data)
    with app.app_context():
        part_a = Part.query.filter_by(sku='P-A').first()
    q_resp = client.post(f'/quotes/ticket/{ticket_id}/create', data={
        'csrf_token': q_token,
        'currency': 'EUR',
        'language': 'en',
        'options-0-name': 'Repair Option',
        'options-0-lines-0-line_type': 'labour',
        'options-0-lines-0-linked_part_id': '',
        'options-0-lines-0-description': 'Labour',
        'options-0-lines-0-quantity': '1',
        'options-0-lines-0-unit_price': '50',
        'options-0-lines-1-line_type': 'part',
        'options-0-lines-1-linked_part_id': str(part_a.id),
        'options-0-lines-1-description': 'Part A',
        'options-0-lines-1-quantity': '2',
        'options-0-lines-1-unit_price': '10',
    }, follow_redirects=False)
    assert q_resp.status_code == 302

    # create stock order without ticket and receive stock
    o_page = client.get('/orders/new')
    o_token = _csrf(o_page.data)
    with app.app_context():
        supplier_a = Supplier.query.filter_by(name='Supplier A').first()
        branch = Branch.query.filter_by(code='HQ').first()
        part_b = Part.query.filter_by(sku='P-B').first()
        location = StockLocation.query.filter_by(code='MAIN').first()
    o_resp = client.post('/orders/new', data={
        'csrf_token': o_token,
        'ticket_id': '',
        'supplier_id': str(supplier_a.id),
        'branch_id': str(branch.id),
        'status': 'ordered',
        'reference': 'SOCK-1',
        'supplier_reference': 'PO-SOCK-1',
        'tracking_number': 'TRK-2',
        'ordered_at': '2026-12-01T10:00',
        'estimated_arrival_at': '2026-12-03T10:00',
        'lines-0-part_id': str(part_b.id),
        'lines-0-description_override': 'Stock line',
        'lines-0-supplier_sku': 'SUP-P-B',
        'lines-0-quantity': '5',
        'lines-0-unit_cost': '7.5',
    }, follow_redirects=False)
    assert o_resp.status_code == 302

    with app.app_context():
        order = PartOrder.query.filter_by(reference='SOCK-1').first()
        assert order is not None
        assert order.ticket_id is None
        assert order.order_type == 'stock'
        line = order.lines[0]

    d_page = client.get(f'/orders/{order.id}')
    d_token = _csrf(d_page.data)
    r_resp = client.post(f'/orders/{order.id}/receive', data={
        'csrf_token': d_token,
        'line_id': str(line.id),
        'location_id': str(location.id),
        'quantity': '3',
        'received_note': 'partial',
    }, follow_redirects=False)
    assert r_resp.status_code == 302

    with app.app_context():
        refreshed_order = db.session.get(PartOrder, order.id)
        assert refreshed_order.status == 'partially_received'
        refreshed_line = db.session.get(PartOrderLine, line.id)
        assert float(refreshed_line.received_quantity) == 3.0
        level = StockLevel.query.filter_by(part_id=part_b.id, branch_id=branch.id, location_id=location.id).first()
        assert level is not None
        assert float(level.on_hand_qty) == 3.0
