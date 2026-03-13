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
