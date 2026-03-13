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
    SECRET_KEY = 'test-secret'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True
    BABEL_DEFAULT_LOCALE = 'en'
    BABEL_DEFAULT_TIMEZONE = 'UTC'
    SUPPORTED_LOCALES = ['en', 'es']
    DEFAULT_BRANCH_CODE = 'HQ'


def _create_tables():
    tables = [Branch.__table__, Role.__table__, Customer.__table__, User.__table__, role_permissions, user_roles, user_branch_access,
              Device.__table__, Ticket.__table__, IntakeSubmission.__table__, Diagnostic.__table__, Quote.__table__, QuoteOption.__table__,
              QuoteLine.__table__, QuoteApproval.__table__, TicketNote.__table__, Supplier.__table__, Part.__table__, StockLocation.__table__,
              StockLevel.__table__, StockMovement.__table__, StockReservation.__table__, PartOrder.__table__, PartOrderLine.__table__, PartOrderEvent.__table__]
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


def test_order_creation_and_status_transitions(monkeypatch):
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        branch = Branch.query.filter_by(code='HQ').first()
        customer = Customer(full_name='Ord Cust', phone='+34001', email='ord@example.com', preferred_language='en', primary_branch=branch)
        db.session.add(customer); db.session.flush()
        device = Device(customer=customer, category='laptops', brand='Dell', model='XPS', serial_number='OR1', imei=None)
        db.session.add(device); db.session.flush()
        ticket = Ticket(ticket_number='HQ-20260312-5000', branch_id=branch.id, customer_id=customer.id, device_id=device.id, internal_status='awaiting_parts', customer_status='Waiting for parts', priority='high')
        db.session.add(ticket)
        supplier = Supplier(name='Supplier A', is_active=True)
        db.session.add(supplier)
        part = Part(sku='LCD-001', name='LCD Panel', is_active=True)
        db.session.add(part)
        db.session.commit()

    monkeypatch.setattr('app.services.auth_service.log_action', lambda *args, **kwargs: None)
    client = app.test_client()
    _login(client)

    new_order_page = client.get('/orders/new')
    token = _csrf(new_order_page.data)

    with app.app_context():
        supplier = Supplier.query.filter_by(name='Supplier A').first()
        branch = Branch.query.filter_by(code='HQ').first()
        part = Part.query.filter_by(sku='LCD-001').first()

    create_resp = client.post('/orders/new', data={
        'csrf_token': token,
        'supplier_id': str(supplier.id),
        'branch_id': str(branch.id),
        'reference': 'PO-001',
        'status': 'ordered',
        'supplier_reference': 'SUP-PO-001',
        'tracking_number': 'TRK-001',
        'estimated_arrival_at': '2026-12-31T10:00',
        'lines-0-part_id': str(part.id),
        'lines-0-quantity': '1',
        'lines-0-unit_cost': '80',
    }, follow_redirects=False)
    assert create_resp.status_code == 302

    with app.app_context():
        order = PartOrder.query.filter_by(reference='PO-001').first()
        assert order is not None
        assert order.status == 'ordered'

    detail_page = client.get(f'/orders/{order.id}')
    token2 = _csrf(detail_page.data)
    status_resp = client.post(f'/orders/{order.id}', data={'csrf_token': token2, 'event_type': 'received', 'notes': 'Delivery received'}, follow_redirects=False)
    assert status_resp.status_code == 302

    with app.app_context():
        refreshed = db.session.get(PartOrder, order.id)
        assert refreshed.status == 'received'
        assert PartOrderEvent.query.filter_by(order_id=order.id, event_type='received').count() == 1
