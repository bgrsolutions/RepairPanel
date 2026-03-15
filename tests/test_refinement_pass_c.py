import re

from app import create_app
from app.extensions import db
from app.models import (
    Branch, Customer, Device, Diagnostic, IntakeDisclaimerAcceptance, IntakeSubmission, Part, PartCategory, PartOrder, PartOrderEvent, PartOrderLine,
    PortalToken,
    Quote, QuoteApproval, QuoteLine, QuoteOption, Role, StockLayer, StockLevel, StockLocation, StockMovement, StockReservation,
    Supplier, Ticket, TicketNote, User, AppSetting,
)
from app.models.role import role_permissions
from app.models.user import user_branch_access, user_roles
from app.models.inventory import part_category_links
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
        QuoteLine.__table__, QuoteApproval.__table__, TicketNote.__table__, Supplier.__table__, PartCategory.__table__, part_category_links, Part.__table__, StockLocation.__table__,
        StockLevel.__table__, StockMovement.__table__, StockReservation.__table__, StockLayer.__table__, PartOrder.__table__, PartOrderLine.__table__, PartOrderEvent.__table__, AppSetting.__table__,
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


def test_pass_c1_order_blank_lines_and_ticket_detail_compact(monkeypatch):
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        branch = Branch.query.filter_by(code='HQ').first()
        customer = Customer(full_name='Order Person', phone='+34999999', email='order.person@example.com', preferred_language='en', primary_branch=branch)
        db.session.add(customer); db.session.flush()
        device = Device(customer=customer, category='phones', brand='Google', model='Pixel', serial_number='PX-1', imei='IMEI-PX')
        db.session.add(device); db.session.flush()
        ticket = Ticket(ticket_number='HQ-20260313-5555', branch_id=branch.id, customer_id=customer.id, device_id=device.id, internal_status='awaiting_parts', customer_status='Waiting parts', priority='normal')
        supplier = Supplier(name='Dynamic Supplier', is_active=True)
        part = Part(sku='BAT-900', name='Battery Pack', is_active=True, supplier_sku='SUP-BAT-900')
        db.session.add_all([ticket, supplier, part])
        db.session.commit()

    monkeypatch.setattr('app.services.auth_service.log_action', lambda *args, **kwargs: None)
    client = app.test_client()
    _login(client)

    # ticket lookup includes customer email search
    ticket_search_resp = client.get('/orders/ticket-search?q=order.person@example.com')
    assert ticket_search_resp.status_code == 200
    assert any('5555' in item['label'] for item in ticket_search_resp.get_json()['items'])

    # create order with one valid line and one blank line (blank should be ignored)
    order_page = client.get('/orders/new')
    token = _csrf(order_page.data)
    with app.app_context():
        supplier = Supplier.query.filter_by(name='Dynamic Supplier').first()
        branch = Branch.query.filter_by(code='HQ').first()
        part = Part.query.filter_by(sku='BAT-900').first()
        ticket = Ticket.query.filter_by(ticket_number='HQ-20260313-5555').first()

    post = client.post('/orders/new', data={
        'csrf_token': token,
        'ticket_id': str(ticket.id),
        'supplier_id': str(supplier.id),
        'branch_id': str(branch.id),
        'status': 'ordered',
        'reference': 'PO-DYN-1',
        'lines-0-part_id': str(part.id),
        'lines-0-quantity': '2',
        'lines-0-unit_cost': '15',
        'lines-1-part_id': '',
        'lines-1-quantity': '',
        'lines-1-unit_cost': '',
    }, follow_redirects=False)
    assert post.status_code == 302

    with app.app_context():
        order = PartOrder.query.filter_by(reference='PO-DYN-1').first()
        assert order is not None
        assert len(order.lines) == 1
        assert float(order.lines[0].quantity) == 2.0

        ticket = Ticket.query.filter_by(ticket_number='HQ-20260313-5555').first()

    detail = client.get(f'/tickets/{ticket.id}')
    assert detail.status_code == 200
    html = detail.data.decode()
    assert 'Actions' in html
    assert 'Search by part name, SKU, barcode, supplier SKU' in html


def test_pass_c_categories_route_loads_without_nameerror(monkeypatch):
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()

    monkeypatch.setattr('app.services.auth_service.log_action', lambda *args, **kwargs: None)
    client = app.test_client()
    _login(client)

    resp = client.get('/inventory/categories', follow_redirects=False)
    assert resp.status_code == 200
    assert 'Part Categories' in resp.data.decode()


def test_pass_c_quote_detail_igic_decimal_safe(monkeypatch):
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        branch = Branch.query.filter_by(code='HQ').first()
        customer = Customer(full_name='Quote Decimal', phone='+3477777', email='quote.decimal@example.com', preferred_language='en', primary_branch=branch)
        db.session.add(customer)
        db.session.flush()
        device = Device(customer=customer, category='phones', brand='Nokia', model='3310', serial_number='QUOTE-DEV', imei='Q-IMEI')
        db.session.add(device)
        db.session.flush()
        ticket = Ticket(ticket_number='HQ-20260313-8888', branch_id=branch.id, customer_id=customer.id, device_id=device.id, internal_status='awaiting_diagnostics', customer_status='Received', priority='normal')
        db.session.add(ticket)
        db.session.flush()
        quote = Quote(ticket_id=ticket.id, version=1, status='draft')
        db.session.add(quote)
        db.session.flush()
        option = QuoteOption(quote_id=quote.id, name='Standard', position=1)
        db.session.add(option)
        db.session.flush()
        db.session.add(QuoteLine(option_id=option.id, line_type='part', description='Screen', quantity=2, unit_price=50))
        db.session.commit()
        quote_id = quote.id

    monkeypatch.setattr('app.services.auth_service.log_action', lambda *args, **kwargs: None)
    client = app.test_client()
    _login(client)

    resp = client.get(f'/quotes/{quote_id}')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'IGIC (7%)' in html
    assert '107.00' in html


def test_pass_e1_bench_board_tabs_visible(monkeypatch):
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()

    monkeypatch.setattr('app.services.auth_service.log_action', lambda *args, **kwargs: None)
    client = app.test_client()
    _login(client)

    resp = client.get('/tickets/board')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'Repair Bench Board' in html
    assert 'Awaiting Parts' in html
    assert 'data-tab="0"' in html


def test_pass_e1_supplier_detail_update(monkeypatch):
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        supplier = Supplier(name='Edit Me', is_active=True)
        db.session.add(supplier)
        db.session.commit()
        supplier_id = supplier.id

    monkeypatch.setattr('app.services.auth_service.log_action', lambda *args, **kwargs: None)
    client = app.test_client()
    _login(client)

    page = client.get(f'/suppliers/{supplier_id}')
    assert page.status_code == 200
    token = _csrf(page.data)
    post = client.post(f'/suppliers/{supplier_id}/update', data={
        'csrf_token': token,
        'name': 'Edited Supplier',
        'contact_name': 'Ops',
        'email': 'ops@example.com',
        'phone': '1234',
        'website': '',
        'account_reference': 'AC-1',
        'default_lead_time_days': '5',
        'notes': 'Updated',
        'is_active': 'y',
    }, follow_redirects=False)
    assert post.status_code == 302

    with app.app_context():
        updated = db.session.get(Supplier, supplier_id)
        assert updated.name == 'Edited Supplier'
        assert updated.default_lead_time_days == 5


def test_pass_f_quote_public_payment_choice_and_customer_update(monkeypatch):
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        branch = Branch.query.filter_by(code='HQ').first()
        customer = Customer(full_name='Portal Customer', phone='+34911111', email='portal.customer@example.com', preferred_language='en', primary_branch=branch)
        db.session.add(customer); db.session.flush()
        device = Device(customer=customer, category='phones', brand='Apple', model='iPhone', serial_number='PORTAL-1', imei='IM-1')
        db.session.add(device); db.session.flush()
        ticket = Ticket(ticket_number='HQ-20260313-9900', branch_id=branch.id, customer_id=customer.id, device_id=device.id, internal_status='awaiting_quote_approval', customer_status='Waiting quote', priority='normal')
        db.session.add(ticket); db.session.flush()
        quote = Quote(ticket_id=ticket.id, version=1, status='sent')
        db.session.add(quote); db.session.flush()
        option = QuoteOption(quote_id=quote.id, name='Standard', position=1)
        db.session.add(option); db.session.flush()
        db.session.add(QuoteLine(option_id=option.id, line_type='part', description='Battery', quantity=1, unit_price=99))
        approval = QuoteApproval(quote_id=quote.id, status='pending')
        db.session.add(approval)
        db.session.add(TicketNote(ticket_id=ticket.id, note_type='internal', content='Internal only note'))
        db.session.add(TicketNote(ticket_id=ticket.id, note_type='customer_update', content='Your part arrived'))
        db.session.commit()
        token = approval.token

    monkeypatch.setattr('app.services.audit_service.log_action', lambda *args, **kwargs: None)
    client = app.test_client()

    page = client.get(f'/public/quote/{token}')
    csrf = _csrf(page.data)
    post = client.post(f'/public/quote/{token}', data={
        'csrf_token': csrf,
        'actor_name': 'Portal Customer',
        'actor_contact': 'portal.customer@example.com',
        'language': 'en',
        'decision': 'approved',
        'payment_choice': 'pay_in_store',
        'declined_reason': '',
    }, follow_redirects=False)
    assert post.status_code == 302

    status_page = client.post('/public/status', data={'ticket_number': 'HQ-20260313-9900', 'verifier': 'portal.customer@example.com', 'csrf_token': _csrf(client.get('/public/status').data)}, follow_redirects=True)
    html = status_page.data.decode()
    assert 'Your part arrived' in html
    assert 'Internal only note' not in html


def test_pass_f_reports_human_labels_and_metrics(monkeypatch):
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()

    monkeypatch.setattr('app.services.auth_service.log_action', lambda *args, **kwargs: None)
    client = app.test_client()
    _login(client)

    resp = client.get('/reports/')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'Quote Approval Rate' in html
    assert '%' in html
    assert 'Awaiting Diagnosis' in html


def test_pass_f1_waiting_parts_filter_and_queue_eta(monkeypatch):
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        branch = Branch.query.filter_by(code='HQ').first()
        tech = User.query.filter(User.is_active.is_(True)).first()
        customer = Customer(full_name='Wait Parts', phone='+34000111', email='wait.parts@example.com', preferred_language='en', primary_branch=branch)
        db.session.add(customer)
        db.session.flush()
        device = Device(customer=customer, category='phones', brand='Sony', model='X', serial_number='WAIT-1', imei='WAIT-IMEI')
        db.session.add(device)
        db.session.flush()
        ticket = Ticket(ticket_number='HQ-20260313-7777', branch_id=branch.id, customer_id=customer.id, device_id=device.id, internal_status='in_repair', customer_status='In Progress', priority='normal', assigned_technician_id=tech.id)
        db.session.add(ticket)
        db.session.flush()
        supplier = Supplier(name='ETA Supplier', is_active=True)
        db.session.add(supplier)
        db.session.flush()
        order = PartOrder(reference='PO-WAIT-1', supplier_id=supplier.id, branch_id=branch.id, ticket_id=ticket.id, status='ordered')
        order.estimated_arrival_at = ticket.created_at
        db.session.add(order)
        db.session.commit()

    monkeypatch.setattr('app.services.auth_service.log_action', lambda *args, **kwargs: None)
    client = app.test_client()
    _login(client)

    board = client.get('/tickets/board?waiting_parts=1')
    assert board.status_code == 200
    assert 'HQ-20260313-7777' in board.data.decode()

    queue = client.get('/tickets/my-queue')
    html = queue.data.decode()
    assert 'Parts ETA:' in html


def test_pass_f1_send_update_email_intent(monkeypatch):
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        branch = Branch.query.filter_by(code='HQ').first()
        customer = Customer(full_name='Mail Target', phone='+34000222', email='mail.target@example.com', preferred_language='en', primary_branch=branch)
        db.session.add(customer)
        db.session.flush()
        device = Device(customer=customer, category='phones', brand='LG', model='G', serial_number='MAIL-1', imei='MAIL-IMEI')
        db.session.add(device)
        db.session.flush()
        ticket = Ticket(ticket_number='HQ-20260313-6666', branch_id=branch.id, customer_id=customer.id, device_id=device.id, internal_status='awaiting_diagnostics', customer_status='Received', priority='normal')
        db.session.add(ticket)
        db.session.commit()
        ticket_id = ticket.id

    monkeypatch.setattr('app.services.auth_service.log_action', lambda *args, **kwargs: None)
    monkeypatch.setattr('app.blueprints.tickets.routes.log_action', lambda *args, **kwargs: None)
    monkeypatch.setattr('app.services.communication_service.send_customer_update_email', lambda **kwargs: True)
    client = app.test_client()
    _login(client)

    post = client.post(f'/tickets/{ticket_id}/send-update', data={'content': 'Ready for pickup soon', 'send_email': '1'}, follow_redirects=False)
    assert post.status_code == 302

    with app.app_context():
        notes = TicketNote.query.filter_by(ticket_id=ticket_id).order_by(TicketNote.created_at.asc()).all()
        note_types = [n.note_type for n in notes]
        assert 'customer_update' in note_types
        assert 'communication' in note_types


def test_pass_f1_ticket_modal_labels_and_quote_script_present(monkeypatch):
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        branch = Branch.query.filter_by(code='HQ').first()
        customer = Customer(full_name='Modal Check', phone='+34000333', email='modal.check@example.com', preferred_language='en', primary_branch=branch)
        db.session.add(customer)
        db.session.flush()
        device = Device(customer=customer, category='phones', brand='Dell', model='D', serial_number='MODAL-1', imei='MODAL-IMEI')
        db.session.add(device)
        db.session.flush()
        ticket = Ticket(ticket_number='HQ-20260313-6655', branch_id=branch.id, customer_id=customer.id, device_id=device.id, internal_status='awaiting_diagnostics', customer_status='Received', priority='normal')
        db.session.add(ticket)
        db.session.commit()
        ticket_id = ticket.id

    monkeypatch.setattr('app.services.auth_service.log_action', lambda *args, **kwargs: None)
    client = app.test_client()
    _login(client)

    detail = client.get(f'/tickets/{ticket_id}')
    html = detail.data.decode()
    assert 'Issue summary' in html
    assert 'Send this update as an email' in html
    assert html.count('Technician &amp; Workflow') == 1

    quote_page = client.get(f'/quotes/ticket/{ticket_id}/new')
    quote_html = quote_page.data.decode()
    assert 'Repair Option 1' in quote_html
    assert 'delete el.dataset.wired' in quote_html


def test_pass_f2_ticket_quote_summary_and_diagnostics_layout(monkeypatch):
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        branch = Branch.query.filter_by(code='HQ').first()
        customer = Customer(full_name='Quote Summary', phone='+34000444', email='quote.summary@example.com', preferred_language='en', primary_branch=branch)
        db.session.add(customer); db.session.flush()
        device = Device(customer=customer, category='phones', brand='HP', model='H', serial_number='QSUM-1', imei='QSUM-IMEI')
        db.session.add(device); db.session.flush()
        ticket = Ticket(ticket_number='HQ-20260313-6644', branch_id=branch.id, customer_id=customer.id, device_id=device.id, internal_status='awaiting_quote_approval', customer_status='Waiting quote', priority='normal')
        db.session.add(ticket); db.session.flush()
        quote = Quote(ticket_id=ticket.id, version=2, status='sent', notes_snapshot='Customer approved once payment clears')
        db.session.add(quote); db.session.flush()
        option = QuoteOption(quote_id=quote.id, name='Standard', position=1)
        db.session.add(option); db.session.flush()
        db.session.add(QuoteLine(option_id=option.id, line_type='part', description='Display', quantity=1, unit_price=150))
        db.session.add(QuoteApproval(quote_id=quote.id, status='approved', payment_choice='pay_in_store', payment_status='pending'))
        db.session.commit()
        ticket_id = ticket.id

    monkeypatch.setattr('app.services.auth_service.log_action', lambda *args, **kwargs: None)
    client = app.test_client()
    _login(client)

    detail = client.get(f'/tickets/{ticket_id}')
    html = detail.data.decode()
    assert html.count('Technician &amp; Workflow') == 1
    assert 'Commercial summary and approval state' in html
    assert 'View details' in html
    assert 'max-w-5xl' in html
    assert 'md:grid-cols-2' in html


def test_pass_f2_terms_snapshot_single_field(monkeypatch):
    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()
        seed_phase1_data()
        branch = Branch.query.filter_by(code='HQ').first()
        customer = Customer(full_name='Terms Single', phone='+34000555', email='terms.single@example.com', preferred_language='en', primary_branch=branch)
        db.session.add(customer); db.session.flush()
        device = Device(customer=customer, category='phones', brand='Acer', model='A', serial_number='TERM-1', imei='TERM-IMEI')
        db.session.add(device); db.session.flush()
        ticket = Ticket(ticket_number='HQ-20260313-6633', branch_id=branch.id, customer_id=customer.id, device_id=device.id, internal_status='awaiting_diagnostics', customer_status='Received', priority='normal')
        db.session.add(ticket); db.session.commit()
        ticket_id = ticket.id

    monkeypatch.setattr('app.services.auth_service.log_action', lambda *args, **kwargs: None)
    client = app.test_client()
    _login(client)

    quote_page = client.get(f'/quotes/ticket/{ticket_id}/new')
    html = quote_page.data.decode()
    assert html.count('Terms Snapshot') == 1
