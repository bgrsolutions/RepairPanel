"""Phase 6 tests: Business identity, service catalogue, bookings, smart check-in."""

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
    ]
    for t in tables:
        t.create(bind=db.engine, checkfirst=True)


def _setup(monkeypatch):
    monkeypatch.setattr('app.services.auth_service.log_action', _noop_log)
    monkeypatch.setattr('app.services.audit_service.log_action', _noop_log)
    monkeypatch.setattr('app.blueprints.intake.routes.log_action', _noop_log)
    monkeypatch.setattr('app.blueprints.tickets.routes.log_action', _noop_log)

    app = create_app(TestConfig)
    with app.app_context():
        _create_tables()

        role = Role(name="Admin")
        db.session.add(role)
        branch = Branch(code="HQ", name="Headquarters", is_active=True)
        db.session.add(branch)
        db.session.flush()
        user = User(full_name="Test Admin", email="admin@test.com", is_active=True, default_branch_id=branch.id)
        user.password_hash = "pbkdf2:sha256:600000$test$test"
        user.roles.append(role)
        db.session.add(user)
        customer = Customer(full_name="John Doe", phone="555-0001", primary_branch_id=branch.id)
        db.session.add(customer)
        db.session.flush()
        device = Device(customer_id=customer.id, category="phones", brand="Apple", model="iPhone 14")
        db.session.add(device)
        part = Part(name="iPhone 14 Screen", sku="IPH14-SCR", is_active=True)
        db.session.add(part)
        db.session.flush()
        stock_loc = StockLocation(name="Main Shelf", code="SHELF-01", branch_id=branch.id, location_type="shelf")
        db.session.add(stock_loc)
        db.session.flush()

        ids = {
            "branch_id": branch.id,
            "user_id": str(user.id),
            "customer_id": customer.id,
            "device_id": device.id,
            "part_id": part.id,
            "stock_location_id": stock_loc.id,
        }
        db.session.commit()

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = ids["user_id"]

    return app, client, ids


# ── 6A: Company Management ──

def test_company_list_page(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    resp = client.get('/admin/companies/')
    assert resp.status_code == 200
    assert b'Companies' in resp.data


def test_company_create_form(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    resp = client.get('/admin/companies/new')
    assert resp.status_code == 200
    assert b'Legal Name' in resp.data
    assert b'CIF / NIF' in resp.data
    assert b'Tax Mode' in resp.data


def test_company_create_submit(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    resp = client.post('/admin/companies/new', data={
        'legal_name': 'IRONCore Repairs SL',
        'trading_name': 'IRONCore',
        'cif_nif': 'B12345678',
        'tax_mode': 'IGIC',
        'phone': '+34 922 123 456',
        'email': 'info@ironcore.es',
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        companies = Company.query.all()
        assert len(companies) == 1
        assert companies[0].legal_name == 'IRONCore Repairs SL'
        assert companies[0].cif_nif == 'B12345678'


def test_company_edit(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    with app.app_context():
        company = Company(legal_name='Old Name', tax_mode='IGIC')
        db.session.add(company)
        db.session.commit()
        cid = str(company.id)
    resp = client.post(f'/admin/companies/{cid}/edit', data={
        'legal_name': 'New Name',
        'tax_mode': 'VAT',
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        c = db.session.get(Company, uuid.UUID(cid))
        assert c.legal_name == 'New Name'
        assert c.tax_mode == 'VAT'


# ── 6B: Branch / Store Extension ──

def test_branch_edit_page(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    resp = client.get(f'/settings/branches/{str(ids["branch_id"])}/edit')
    assert resp.status_code == 200
    assert b'Address Line 1' in resp.data
    assert b'Opening Hours' in resp.data
    assert b'Ticket Prefix' in resp.data


def test_branch_edit_submit(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    resp = client.post(f'/settings/branches/{str(ids["branch_id"])}/edit', data={
        'code': 'HQ',
        'name': 'Headquarters Store',
        'address_line_1': '123 Main Street',
        'city': 'Santa Cruz de Tenerife',
        'postcode': '38001',
        'island_or_region': 'Tenerife',
        'country': 'Spain',
        'phone': '+34 922 000 000',
        'ticket_prefix': 'TF-',
        'company_id': '',
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        branch = db.session.get(Branch, ids["branch_id"])
        assert branch.address_line_1 == '123 Main Street'
        assert branch.city == 'Santa Cruz de Tenerife'
        assert branch.ticket_prefix == 'TF-'


def test_branch_company_link(monkeypatch):
    """Branch can be linked to a company."""
    app, client, ids = _setup(monkeypatch)
    with app.app_context():
        company = Company(legal_name='Test Co', tax_mode='IGIC')
        db.session.add(company)
        db.session.commit()
        cid = str(company.id)
    resp = client.post(f'/settings/branches/{str(ids["branch_id"])}/edit', data={
        'code': 'HQ', 'name': 'HQ Store', 'company_id': cid,
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        branch = db.session.get(Branch, ids["branch_id"])
        assert str(branch.company_id) == cid
        assert branch.company.legal_name == 'Test Co'


# ── 6C: Service Catalogue ──

def test_service_list_page(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    resp = client.get('/services/')
    assert resp.status_code == 200
    assert b'Service Catalogue' in resp.data


def test_service_create(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    resp = client.post('/services/new', data={
        'name': 'iPhone 14 Screen Repair',
        'device_category': 'phones',
        'default_part_id': str(ids['part_id']),
        'labour_minutes': '45',
        'suggested_sale_price': '89.00',
        'is_active': 'y',
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        services = RepairService.query.all()
        assert len(services) == 1
        assert services[0].name == 'iPhone 14 Screen Repair'
        assert services[0].labour_minutes == 45
        assert services[0].default_part_id == ids['part_id']


def test_service_edit(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    with app.app_context():
        svc = RepairService(name='Old Service', is_active=True)
        db.session.add(svc)
        db.session.commit()
        sid = str(svc.id)
    resp = client.post(f'/services/{sid}/edit', data={
        'name': 'Updated Service',
        'device_category': 'laptops',
        'default_part_id': '',
        'labour_minutes': '60',
        'suggested_sale_price': '120.00',
        'is_active': 'y',
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        s = db.session.get(RepairService, uuid.UUID(sid))
        assert s.name == 'Updated Service'
        assert s.labour_minutes == 60


# ── 6D: Smart Check-In with Service Selector ──

def test_fast_checkin_has_service_field(monkeypatch):
    """Fast Check-In page should show repair service selector."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get('/tickets/new')
    html = resp.data.decode()
    assert 'repair_service_id' in html or 'Service' in html
    assert 'Part Availability' in html


def test_fast_checkin_has_eta_suggestion(monkeypatch):
    """Fast Check-In should have ETA suggestion UI elements."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get('/tickets/new')
    html = resp.data.decode()
    assert 'eta-suggestion' in html
    assert 'Suggested' in html


# ── 6E: Part Availability API ──

def test_service_availability_endpoint(monkeypatch):
    """Service availability endpoint returns stock data for a service."""
    app, client, ids = _setup(monkeypatch)
    with app.app_context():
        svc = RepairService(
            name='Screen Repair', device_category='phones',
            default_part_id=ids['part_id'], labour_minutes=30,
            is_active=True,
        )
        db.session.add(svc)
        db.session.commit()
        sid = str(svc.id)

    resp = client.get(f'/tickets/service-availability?service_id={sid}&branch_id={str(ids["branch_id"])}')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['service_name'] == 'Screen Repair'
    assert data['labour_minutes'] == 30
    assert 'part_name' in data
    assert 'stock_this_store' in data
    assert 'suggested_eta' in data


def test_service_availability_with_stock(monkeypatch):
    """When stock is available, availability endpoint reports correctly."""
    app, client, ids = _setup(monkeypatch)
    with app.app_context():
        svc = RepairService(
            name='Screen Fix', default_part_id=ids['part_id'],
            labour_minutes=45, is_active=True,
        )
        db.session.add(svc)
        db.session.flush()
        stock = StockLevel(
            part_id=ids['part_id'], branch_id=ids['branch_id'],
            location_id=ids['stock_location_id'],
            on_hand_qty=5, reserved_qty=1,
        )
        db.session.add(stock)
        db.session.commit()
        sid = str(svc.id)

    resp = client.get(f'/tickets/service-availability?service_id={sid}&branch_id={str(ids["branch_id"])}')
    data = resp.get_json()
    assert data['part_in_stock'] is True
    assert float(data['stock_this_store']) == 4


def test_service_availability_no_stock(monkeypatch):
    """When no stock, reports needs_ordering."""
    app, client, ids = _setup(monkeypatch)
    with app.app_context():
        svc = RepairService(
            name='Battery Replace', default_part_id=ids['part_id'],
            labour_minutes=20, is_active=True,
        )
        db.session.add(svc)
        db.session.commit()
        sid = str(svc.id)

    resp = client.get(f'/tickets/service-availability?service_id={sid}&branch_id={str(ids["branch_id"])}')
    data = resp.get_json()
    assert data['part_in_stock'] is False
    assert data['needs_ordering'] is True


# ── 6F: ETA Suggestion ──

def test_eta_suggestion_in_availability(monkeypatch):
    """Service availability response should include suggested ETA."""
    app, client, ids = _setup(monkeypatch)
    with app.app_context():
        svc = RepairService(
            name='Quick Fix', default_part_id=ids['part_id'],
            labour_minutes=15, is_active=True,
        )
        db.session.add(svc)
        db.session.flush()
        stock = StockLevel(part_id=ids['part_id'], branch_id=ids['branch_id'], location_id=ids['stock_location_id'], on_hand_qty=10)
        db.session.add(stock)
        db.session.commit()
        sid = str(svc.id)

    resp = client.get(f'/tickets/service-availability?service_id={sid}&branch_id={str(ids["branch_id"])}')
    data = resp.get_json()
    assert 'suggested_eta' in data
    eta = datetime.strptime(data['suggested_eta'], '%Y-%m-%dT%H:%M')
    assert eta > datetime.utcnow()


# ── 6G: Booking Foundation ──

def test_booking_list_page(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    resp = client.get('/bookings/')
    assert resp.status_code == 200
    assert b'Bookings' in resp.data


def test_booking_create(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    start = (datetime.utcnow() + timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M')
    end = (datetime.utcnow() + timedelta(hours=3)).strftime('%Y-%m-%dT%H:%M')
    resp = client.post('/bookings/new', data={
        'location_id': str(ids['branch_id']),
        'start_time': start,
        'end_time': end,
        'status': 'scheduled',
        'repair_service_id': '',
        'notes': 'Test booking',
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        bookings = Booking.query.all()
        assert len(bookings) == 1
        assert bookings[0].notes == 'Test booking'
        assert bookings[0].status == 'scheduled'


def test_booking_edit(monkeypatch):
    app, client, ids = _setup(monkeypatch)
    with app.app_context():
        booking = Booking(
            location_id=ids['branch_id'],  # already UUID object
            start_time=datetime.utcnow() + timedelta(hours=1),
            end_time=datetime.utcnow() + timedelta(hours=2),
            status='scheduled',
        )
        db.session.add(booking)
        db.session.commit()
        bid = str(booking.id)
    start = (datetime.utcnow() + timedelta(hours=4)).strftime('%Y-%m-%dT%H:%M')
    end = (datetime.utcnow() + timedelta(hours=5)).strftime('%Y-%m-%dT%H:%M')
    resp = client.post(f'/bookings/{bid}/edit', data={
        'location_id': str(ids['branch_id']),
        'start_time': start,
        'end_time': end,
        'status': 'confirmed',
        'repair_service_id': '',
        'notes': 'Updated',
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        b = db.session.get(Booking, uuid.UUID(bid))
        assert b.status == 'confirmed'
        assert b.notes == 'Updated'


# ── 6H: Dashboard Bookings Widget ──

def test_dashboard_has_bookings_section(monkeypatch):
    """Dashboard should include today's bookings widget."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get('/')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert "Today's Bookings" in html or "No bookings today" in html


# ── 6I: Document Identity ──

def test_branch_full_address_property(monkeypatch):
    """Branch.full_address should build a comma-separated address."""
    app, _, ids = _setup(monkeypatch)
    with app.app_context():
        branch = db.session.get(Branch, ids['branch_id'])
        branch.address_line_1 = '123 Main St'
        branch.city = 'Santa Cruz'
        branch.postcode = '38001'
        db.session.commit()
        assert '123 Main St' in branch.full_address
        assert 'Santa Cruz' in branch.full_address
        assert '38001' in branch.full_address


def test_company_display_name(monkeypatch):
    """Company.display_name should prefer trading_name over legal_name."""
    app, _, ids = _setup(monkeypatch)
    with app.app_context():
        c1 = Company(legal_name='Legal Corp SL', trading_name='TradeName', tax_mode='IGIC')
        c2 = Company(legal_name='Only Legal SL', tax_mode='IGIC')
        db.session.add_all([c1, c2])
        db.session.commit()
        assert c1.display_name == 'TradeName'
        assert c2.display_name == 'Only Legal SL'


# ── 6K: Migration Validation ──

def test_migration_covers_new_tables(monkeypatch):
    """Phase 6 migration should include companies, repair_services, bookings tables."""
    import os
    migrations_dir = os.path.join(os.path.dirname(__file__), '..', 'migrations', 'versions')
    migration_content = ''
    for fname in os.listdir(migrations_dir):
        if 'phase6' in fname.lower() or 'business_identity' in fname.lower():
            with open(os.path.join(migrations_dir, fname)) as f:
                migration_content += f.read()

    assert 'companies' in migration_content
    assert 'repair_services' in migration_content
    assert 'bookings' in migration_content
    assert 'company_id' in migration_content


def test_migration_has_downgrade(monkeypatch):
    """Phase 6 migration must have working downgrade."""
    import os
    migrations_dir = os.path.join(os.path.dirname(__file__), '..', 'migrations', 'versions')
    for fname in os.listdir(migrations_dir):
        if 'phase6' in fname.lower() or ('business_identity' in fname.lower() and 'phase7' not in fname.lower()):
            with open(os.path.join(migrations_dir, fname)) as f:
                content = f.read()
            assert 'def downgrade' in content
            assert 'drop_table' in content


# ── Navigation ──

def test_nav_has_bookings_and_services(monkeypatch):
    """Navigation should include Bookings and Services links."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get('/')
    html = resp.data.decode()
    assert 'Bookings' in html
    assert 'Services' in html


def test_settings_has_companies_link(monkeypatch):
    """Settings page should link to company management."""
    app, client, ids = _setup(monkeypatch)
    resp = client.get('/settings/')
    html = resp.data.decode()
    assert 'Companies' in html
    assert 'Service Catalogue' in html
