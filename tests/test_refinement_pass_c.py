import re

from app import create_app
from app.extensions import db
from app.models import (
    Branch, Customer, Device, Diagnostic, IntakeDisclaimerAcceptance, IntakeSubmission, Part, PartOrder, PartOrderEvent, PartOrderLine,
    PortalToken,
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
    DEFAULT_INTAKE_DISCLAIMER_TEXT = "Test disclaimer"


def _create_tables():
    tables = [
        Branch.__table__, Role.__table__, Customer.__table__, User.__table__, role_permissions, user_roles, user_branch_access,
        Device.__table__, Ticket.__table__, IntakeSubmission.__table__, IntakeDisclaimerAcceptance.__table__, PortalToken.__table__, Diagnostic.__table__, Quote.__table__, QuoteOption.__table__,
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


def test_pass_c_search_and_device_transfer(monkeypatch):
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        branch = Branch.query.filter_by(code='HQ').first()
        c1 = Customer(full_name='Alice One', phone='+341111111', email='alice@example.com', preferred_language='en', primary_branch=branch)
        c2 = Customer(full_name='Bob Two', phone='+342222222', email='bob@example.com', preferred_language='en', primary_branch=branch)
        db.session.add_all([c1, c2]); db.session.flush()
        d1 = Device(customer=c1, category='phones', brand='Apple', model='iPhone', serial_number='DV-1', imei='111')
        db.session.add(d1)
        db.session.flush()
        t1 = Ticket(ticket_number='HQ-20260313-0001', branch_id=branch.id, customer_id=c1.id, device_id=d1.id, internal_status='in_repair', customer_status='In Progress', priority='normal')
        db.session.add(t1)
        db.session.commit()
        d1_id = d1.id

    monkeypatch.setattr('app.services.auth_service.log_action', lambda *args, **kwargs: None)
    client = app.test_client()
    _login(client)

    # internal intake customer search endpoint
    resp = client.get('/intake/customer-search?q=alice')
    assert resp.status_code == 200
    assert any('alice' in i['label'].lower() for i in resp.get_json()['items'])

    # ticket customer search endpoint
    resp2 = client.get('/tickets/customer-search?q=alice')
    assert resp2.status_code == 200
    assert len(resp2.get_json()['items']) >= 1

    # orders ticket search endpoint
    resp3 = client.get('/orders/ticket-search?q=0001')
    assert resp3.status_code == 200
    items = resp3.get_json()['items']
    assert any(i['id'] == str(t1.id) for i in items)

    # public intake exact-match association by email (safe, no public customer reveal)
    checkin = client.get('/public/check-in')
    token = _csrf(checkin.data)
    with app.app_context():
        branch = Branch.query.filter_by(code='HQ').first()
    post = client.post('/public/check-in', data={
        'csrf_token': token,
        'branch_id': str(branch.id),
        'category': 'phones',
        'customer_name': 'Alice One',
        'customer_phone': '+341111111',
        'customer_email': 'alice@example.com',
        'preferred_language': 'en',
        'preferred_contact_method': 'phone',
        'device_brand': 'Apple',
        'device_model': 'iPhone 14',
        'serial_number': 'DV-NEW',
        'imei': '222',
        'reported_fault': 'Screen issue',
        'accepted_disclaimer': 'y',
    }, follow_redirects=False)
    assert post.status_code == 302

    with app.app_context():
        intake = IntakeSubmission.query.filter_by(serial_number='DV-NEW').first()
        assert intake is not None
        assert intake.customer.email == 'alice@example.com'

    # device transfer then unlink
    with app.app_context():
        c2 = Customer.query.filter_by(email='bob@example.com').first()
        c1 = Customer.query.filter_by(email='alice@example.com').first()
    tr = client.post(f'/customers/devices/{d1_id}/transfer', data={'target_customer_id': str(c2.id), 'redirect_customer_id': str(c1.id)}, follow_redirects=False)
    assert tr.status_code == 302

    with app.app_context():
        device = db.session.get(Device, d1_id)
        assert str(device.customer_id) == str(c2.id)

    un = client.post(f'/customers/devices/{d1_id}/unlink', data={'redirect_customer_id': str(c2.id)}, follow_redirects=False)
    assert un.status_code == 302
    with app.app_context():
        device = db.session.get(Device, d1_id)
        assert device.customer_id is None
