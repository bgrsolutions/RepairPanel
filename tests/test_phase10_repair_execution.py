"""Phase 10 — Repair Execution, Parts Usage & Technician Actions tests.

Covers:
- Consume reserved part (install) endpoint
- Technician quick actions (assign-to-me, quick status transitions)
- Quick bench note inline form
- Checklist AJAX item toggle
- Quick status transition validation
- Phase 9 regression checks
"""
import json
import re
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from app import create_app
from app.extensions import db
from app.models import (
    AppSetting, AuditLog, Booking, Branch, Customer, Device, Diagnostic, IntakeSubmission,
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
    }, follow_redirects=True)
    return r


def _setup_ticket_with_reservation(app):
    """Create a ticket with a reserved part for testing consume/release flows."""
    with app.app_context():
        branch = Branch.query.first()
        customer = Customer.query.first()
        device = Device.query.first()
        if not device:
            device = Device(customer_id=customer.id, brand="TestBrand", model="TestModel", category="phones")
            db.session.add(device)
            db.session.flush()

        ticket = Ticket(
            ticket_number="TK-TEST-001",
            branch_id=branch.id,
            customer_id=customer.id,
            device_id=device.id,
            internal_status="in_repair",
            customer_status="In Progress",
            priority="normal",
        )
        db.session.add(ticket)
        db.session.flush()

        supplier = Supplier.query.first()
        if not supplier:
            supplier = Supplier(name="Test Supplier")
            db.session.add(supplier)
            db.session.flush()

        part = Part(sku="TST-001", name="Test Screen", is_active=True, cost_price=50.0, sale_price=100.0)
        db.session.add(part)
        db.session.flush()

        location = StockLocation.query.filter_by(branch_id=branch.id).first()
        if not location:
            location = StockLocation(branch_id=branch.id, code="SHELF-A", name="Shelf A", location_type="shelf", is_active=True)
            db.session.add(location)
            db.session.flush()

        # Create stock level with stock
        level = StockLevel(part_id=part.id, branch_id=branch.id, location_id=location.id, on_hand_qty=10, reserved_qty=2)
        db.session.add(level)
        db.session.flush()

        # Create a reservation
        reservation = StockReservation(
            ticket_id=ticket.id, part_id=part.id, branch_id=branch.id,
            location_id=location.id, quantity=2, status="reserved",
        )
        db.session.add(reservation)
        db.session.commit()

        return str(ticket.id), str(reservation.id), str(part.id), str(branch.id), str(location.id)


def _setup_ticket_with_checklist(app):
    """Create a ticket with a checklist for testing toggle."""
    with app.app_context():
        branch = Branch.query.first()
        customer = Customer.query.first()
        device = Device.query.first()
        if not device:
            device = Device(customer_id=customer.id, brand="TestBrand", model="TestModel", category="phones")
            db.session.add(device)
            db.session.flush()

        ticket = Ticket(
            ticket_number="TK-TEST-CL",
            branch_id=branch.id,
            customer_id=customer.id,
            device_id=device.id,
            internal_status="in_repair",
            customer_status="In Progress",
            priority="normal",
        )
        db.session.add(ticket)
        db.session.flush()

        checklist = RepairChecklist(
            ticket_id=ticket.id,
            checklist_type="pre_repair",
            device_category="phones",
        )
        db.session.add(checklist)
        db.session.flush()

        items = []
        for i, label in enumerate(["Check screen", "Check buttons", "Check ports"]):
            item = ChecklistItem(checklist_id=checklist.id, position=i, label=label)
            db.session.add(item)
            items.append(item)
        db.session.commit()

        return str(ticket.id), str(checklist.id), [str(item.id) for item in items]


class TestPhase10:

    @classmethod
    def setup_class(cls):
        import app.services.audit_service as audit_mod
        import app.services.auth_service as auth_mod
        import app.blueprints.tickets.routes as ticket_routes_mod
        audit_mod.log_action = lambda *a, **kw: None
        auth_mod.log_action = lambda *a, **kw: None
        ticket_routes_mod.log_action = lambda *a, **kw: None

    def _make_app(self):
        app = create_app(TestConfig)
        with app.app_context():
            _create_tables()
            seed_phase1_data()
        return app

    # ---------- Consume Reserved Part ----------

    def test_consume_reservation_success(self):
        app = self._make_app()
        with app.app_context():
            ticket_id, reservation_id, part_id, branch_id, location_id = _setup_ticket_with_reservation(app)

        with app.test_client() as client:
            _login(client)
            # Get CSRF from ticket detail
            resp = client.get(f'/tickets/{ticket_id}')
            token = _csrf(resp.data)

            resp = client.post(
                f'/tickets/{ticket_id}/consume-reservation/{reservation_id}',
                data={'csrf_token': token},
                follow_redirects=True,
            )
            assert resp.status_code == 200
            assert b'Part consumed' in resp.data or b'stock updated' in resp.data

        with app.app_context():
            res = db.session.get(StockReservation, uuid.UUID(reservation_id))
            assert res.status == "consumed"
            # Check stock level: on_hand should be reduced
            level = StockLevel.query.filter_by(part_id=uuid.UUID(part_id)).first()
            assert float(level.on_hand_qty) == 8.0  # 10 - 2
            assert float(level.reserved_qty) == 0.0  # 2 - 2

    def test_consume_reservation_already_consumed(self):
        app = self._make_app()
        with app.app_context():
            ticket_id, reservation_id, _, _, _ = _setup_ticket_with_reservation(app)
            # Pre-consume
            res = db.session.get(StockReservation, uuid.UUID(reservation_id))
            res.status = "consumed"
            db.session.commit()

        with app.test_client() as client:
            _login(client)
            resp = client.get(f'/tickets/{ticket_id}')
            token = _csrf(resp.data)

            resp = client.post(
                f'/tickets/{ticket_id}/consume-reservation/{reservation_id}',
                data={'csrf_token': token},
                follow_redirects=True,
            )
            assert resp.status_code == 200
            assert b'not in reserved state' in resp.data

    def test_consume_reservation_creates_install_movement(self):
        app = self._make_app()
        with app.app_context():
            ticket_id, reservation_id, part_id, _, _ = _setup_ticket_with_reservation(app)

        with app.test_client() as client:
            _login(client)
            resp = client.get(f'/tickets/{ticket_id}')
            token = _csrf(resp.data)
            client.post(
                f'/tickets/{ticket_id}/consume-reservation/{reservation_id}',
                data={'csrf_token': token},
                follow_redirects=True,
            )

        with app.app_context():
            movements = StockMovement.query.filter_by(
                part_id=uuid.UUID(part_id), movement_type="install"
            ).all()
            assert len(movements) >= 1
            assert float(movements[0].quantity) == 2.0

    def test_consume_reservation_creates_note(self):
        app = self._make_app()
        with app.app_context():
            ticket_id, reservation_id, _, _, _ = _setup_ticket_with_reservation(app)

        with app.test_client() as client:
            _login(client)
            resp = client.get(f'/tickets/{ticket_id}')
            token = _csrf(resp.data)
            client.post(
                f'/tickets/{ticket_id}/consume-reservation/{reservation_id}',
                data={'csrf_token': token},
                follow_redirects=True,
            )

        with app.app_context():
            notes = TicketNote.query.filter_by(ticket_id=uuid.UUID(ticket_id)).all()
            install_notes = [n for n in notes if "Part installed" in (n.content or "")]
            assert len(install_notes) >= 1

    # ---------- Assign To Me ----------

    def test_assign_to_me(self):
        app = self._make_app()
        with app.app_context():
            ticket_id, _, _, _, _ = _setup_ticket_with_reservation(app)

        with app.test_client() as client:
            _login(client)
            resp = client.get(f'/tickets/{ticket_id}')
            token = _csrf(resp.data)

            resp = client.post(
                f'/tickets/{ticket_id}/assign-to-me',
                data={'csrf_token': token},
                follow_redirects=True,
            )
            assert resp.status_code == 200
            assert b'assigned to you' in resp.data

        with app.app_context():
            ticket = db.session.get(Ticket, uuid.UUID(ticket_id))
            user = User.query.filter_by(email='admin@ironcore.com').first()
            assert str(ticket.assigned_technician_id) == str(user.id)

    # ---------- Quick Status ----------

    def test_quick_status_start_repair(self):
        app = self._make_app()
        with app.app_context():
            ticket_id, _, _, _, _ = _setup_ticket_with_reservation(app)
            # Set to awaiting_parts (valid transition to in_repair)
            ticket = db.session.get(Ticket, uuid.UUID(ticket_id))
            ticket.internal_status = "awaiting_parts"
            db.session.commit()

        with app.test_client() as client:
            _login(client)
            resp = client.get(f'/tickets/{ticket_id}')
            token = _csrf(resp.data)

            resp = client.post(
                f'/tickets/{ticket_id}/quick-status',
                data={'csrf_token': token, 'action': 'start_repair'},
                follow_redirects=True,
            )
            assert resp.status_code == 200
            assert b'status updated' in resp.data

        with app.app_context():
            ticket = db.session.get(Ticket, uuid.UUID(ticket_id))
            assert ticket.internal_status == "in_repair"

    def test_quick_status_invalid_transition(self):
        app = self._make_app()
        with app.app_context():
            ticket_id, _, _, _, _ = _setup_ticket_with_reservation(app)
            # Set to unassigned — cannot go to testing_qa
            ticket = db.session.get(Ticket, uuid.UUID(ticket_id))
            ticket.internal_status = "unassigned"
            db.session.commit()

        with app.test_client() as client:
            _login(client)
            resp = client.get(f'/tickets/{ticket_id}')
            token = _csrf(resp.data)

            resp = client.post(
                f'/tickets/{ticket_id}/quick-status',
                data={'csrf_token': token, 'action': 'repair_complete'},
                follow_redirects=True,
            )
            assert resp.status_code == 200
            assert b'Invalid status transition' in resp.data

    def test_quick_status_unknown_action(self):
        app = self._make_app()
        with app.app_context():
            ticket_id, _, _, _, _ = _setup_ticket_with_reservation(app)

        with app.test_client() as client:
            _login(client)
            resp = client.get(f'/tickets/{ticket_id}')
            token = _csrf(resp.data)

            resp = client.post(
                f'/tickets/{ticket_id}/quick-status',
                data={'csrf_token': token, 'action': 'nonexistent_action'},
                follow_redirects=True,
            )
            assert resp.status_code == 200
            assert b'Unknown quick action' in resp.data

    def test_quick_status_diagnosis_complete(self):
        app = self._make_app()
        with app.app_context():
            ticket_id, _, _, _, _ = _setup_ticket_with_reservation(app)
            ticket = db.session.get(Ticket, uuid.UUID(ticket_id))
            ticket.internal_status = "awaiting_diagnostics"
            db.session.commit()

        with app.test_client() as client:
            _login(client)
            resp = client.get(f'/tickets/{ticket_id}')
            token = _csrf(resp.data)

            resp = client.post(
                f'/tickets/{ticket_id}/quick-status',
                data={'csrf_token': token, 'action': 'diagnosis_complete'},
                follow_redirects=True,
            )
            assert resp.status_code == 200

        with app.app_context():
            ticket = db.session.get(Ticket, uuid.UUID(ticket_id))
            assert ticket.internal_status == "awaiting_quote_approval"

    def test_quick_status_repair_complete(self):
        app = self._make_app()
        with app.app_context():
            ticket_id, _, _, _, _ = _setup_ticket_with_reservation(app)
            ticket = db.session.get(Ticket, uuid.UUID(ticket_id))
            ticket.internal_status = "in_repair"
            db.session.commit()

        with app.test_client() as client:
            _login(client)
            resp = client.get(f'/tickets/{ticket_id}')
            token = _csrf(resp.data)

            resp = client.post(
                f'/tickets/{ticket_id}/quick-status',
                data={'csrf_token': token, 'action': 'repair_complete'},
                follow_redirects=True,
            )
            assert resp.status_code == 200

        with app.app_context():
            ticket = db.session.get(Ticket, uuid.UUID(ticket_id))
            assert ticket.internal_status == "testing_qa"

    # ---------- Quick Bench Note ----------

    def test_quick_note(self):
        app = self._make_app()
        with app.app_context():
            ticket_id, _, _, _, _ = _setup_ticket_with_reservation(app)

        with app.test_client() as client:
            _login(client)
            resp = client.get(f'/tickets/{ticket_id}')
            token = _csrf(resp.data)

            resp = client.post(
                f'/tickets/{ticket_id}/quick-note',
                data={'csrf_token': token, 'content': 'Replaced screen module'},
                follow_redirects=True,
            )
            assert resp.status_code == 200
            assert b'Bench note added' in resp.data

        with app.app_context():
            notes = TicketNote.query.filter_by(ticket_id=uuid.UUID(ticket_id)).all()
            bench_notes = [n for n in notes if "Replaced screen module" in (n.content or "")]
            assert len(bench_notes) == 1
            assert bench_notes[0].note_type == "internal"

    def test_quick_note_empty_rejected(self):
        app = self._make_app()
        with app.app_context():
            ticket_id, _, _, _, _ = _setup_ticket_with_reservation(app)

        with app.test_client() as client:
            _login(client)
            resp = client.get(f'/tickets/{ticket_id}')
            token = _csrf(resp.data)

            resp = client.post(
                f'/tickets/{ticket_id}/quick-note',
                data={'csrf_token': token, 'content': '   '},
                follow_redirects=True,
            )
            assert resp.status_code == 200
            assert b'Note content is required' in resp.data

    # ---------- Checklist Item Toggle ----------

    def test_checklist_item_toggle(self):
        app = self._make_app()
        with app.app_context():
            ticket_id, checklist_id, item_ids = _setup_ticket_with_checklist(app)

        with app.test_client() as client:
            _login(client)
            # Get CSRF
            resp = client.get(f'/tickets/{ticket_id}')
            token = _csrf(resp.data)

            resp = client.post(
                f'/checklists/item/{item_ids[0]}/toggle',
                data=json.dumps({"is_checked": True}),
                content_type='application/json',
                headers={'X-CSRFToken': token},
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["ok"] is True
            assert data["is_checked"] is True
            assert data["checked_count"] == 1
            assert data["total_count"] == 3

    def test_checklist_item_toggle_uncheck(self):
        app = self._make_app()
        with app.app_context():
            ticket_id, checklist_id, item_ids = _setup_ticket_with_checklist(app)
            # Pre-check the item
            item = db.session.get(ChecklistItem, uuid.UUID(item_ids[0]))
            item.is_checked = True
            db.session.commit()

        with app.test_client() as client:
            _login(client)
            resp = client.get(f'/tickets/{ticket_id}')
            token = _csrf(resp.data)

            resp = client.post(
                f'/checklists/item/{item_ids[0]}/toggle',
                data=json.dumps({"is_checked": False}),
                content_type='application/json',
                headers={'X-CSRFToken': token},
            )
            data = resp.get_json()
            assert data["ok"] is True
            assert data["is_checked"] is False
            assert data["checked_count"] == 0

    def test_checklist_item_toggle_all_checked(self):
        app = self._make_app()
        with app.app_context():
            ticket_id, checklist_id, item_ids = _setup_ticket_with_checklist(app)
            # Check first two items
            for iid in item_ids[:2]:
                item = db.session.get(ChecklistItem, uuid.UUID(iid))
                item.is_checked = True
            db.session.commit()

        with app.test_client() as client:
            _login(client)
            resp = client.get(f'/tickets/{ticket_id}')
            token = _csrf(resp.data)

            # Check the last one
            resp = client.post(
                f'/checklists/item/{item_ids[2]}/toggle',
                data=json.dumps({"is_checked": True}),
                content_type='application/json',
                headers={'X-CSRFToken': token},
            )
            data = resp.get_json()
            assert data["all_checked"] is True

    def test_checklist_toggle_completed_rejected(self):
        app = self._make_app()
        with app.app_context():
            ticket_id, checklist_id, item_ids = _setup_ticket_with_checklist(app)
            # Mark checklist as complete
            checklist = db.session.get(RepairChecklist, uuid.UUID(checklist_id))
            checklist.completed_at = datetime.utcnow()
            db.session.commit()

        with app.test_client() as client:
            _login(client)
            resp = client.get(f'/tickets/{ticket_id}')
            token = _csrf(resp.data)

            resp = client.post(
                f'/checklists/item/{item_ids[0]}/toggle',
                data=json.dumps({"is_checked": True}),
                content_type='application/json',
                headers={'X-CSRFToken': token},
            )
            assert resp.status_code == 400
            data = resp.get_json()
            assert data["ok"] is False

    # ---------- Ticket Detail Shows Quick Actions & Bench Note ----------

    def test_ticket_detail_shows_quick_actions(self):
        app = self._make_app()
        with app.app_context():
            ticket_id, _, _, _, _ = _setup_ticket_with_reservation(app)

        with app.test_client() as client:
            _login(client)
            resp = client.get(f'/tickets/{ticket_id}')
            assert resp.status_code == 200
            assert b'Quick Actions' in resp.data
            assert b'assign-to-me' in resp.data
            assert b'Quick Bench Note' in resp.data
            assert b'quick-note' in resp.data

    def test_ticket_detail_shows_install_button(self):
        app = self._make_app()
        with app.app_context():
            ticket_id, reservation_id, _, _, _ = _setup_ticket_with_reservation(app)

        with app.test_client() as client:
            _login(client)
            resp = client.get(f'/tickets/{ticket_id}')
            assert resp.status_code == 200
            assert b'Install' in resp.data
            assert b'consume-reservation' in resp.data

    # ---------- Inventory Service: consume_reservation ----------

    def test_consume_reservation_service(self):
        app = self._make_app()
        with app.app_context():
            ticket_id, reservation_id, part_id, branch_id, location_id = _setup_ticket_with_reservation(app)
            from app.services.inventory_service import consume_reservation
            res = db.session.get(StockReservation, uuid.UUID(reservation_id))
            consume_reservation(res)
            db.session.commit()

            res = db.session.get(StockReservation, uuid.UUID(reservation_id))
            assert res.status == "consumed"
            level = StockLevel.query.filter_by(part_id=uuid.UUID(part_id)).first()
            assert float(level.on_hand_qty) == 8.0
            assert float(level.reserved_qty) == 0.0

    def test_consume_reservation_invalid_qty(self):
        app = self._make_app()
        with app.app_context():
            ticket_id, reservation_id, _, _, _ = _setup_ticket_with_reservation(app)
            from app.services.inventory_service import consume_reservation
            res = db.session.get(StockReservation, uuid.UUID(reservation_id))
            try:
                consume_reservation(res, quantity=0)
                assert False, "Should have raised ValueError"
            except ValueError:
                pass

    # ---------- Phase 9 Regression: search endpoints still work ----------

    def test_customer_search_still_works(self):
        app = self._make_app()
        with app.test_client() as client:
            _login(client)
            resp = client.get('/tickets/customer-search?q=admin')
            assert resp.status_code == 200
            data = resp.get_json()
            assert "items" in data

    def test_device_search_still_works(self):
        app = self._make_app()
        with app.app_context():
            _setup_ticket_with_reservation(app)
        with app.test_client() as client:
            _login(client)
            resp = client.get('/tickets/device-search?q=TestBrand')
            assert resp.status_code == 200
            data = resp.get_json()
            assert "items" in data

    # ---------- Quick status creates audit note ----------

    def test_quick_status_creates_note(self):
        app = self._make_app()
        with app.app_context():
            ticket_id, _, _, _, _ = _setup_ticket_with_reservation(app)
            ticket = db.session.get(Ticket, uuid.UUID(ticket_id))
            ticket.internal_status = "in_repair"
            db.session.commit()

        with app.test_client() as client:
            _login(client)
            resp = client.get(f'/tickets/{ticket_id}')
            token = _csrf(resp.data)
            client.post(
                f'/tickets/{ticket_id}/quick-status',
                data={'csrf_token': token, 'action': 'repair_complete'},
                follow_redirects=True,
            )

        with app.app_context():
            notes = TicketNote.query.filter_by(ticket_id=uuid.UUID(ticket_id)).all()
            status_notes = [n for n in notes if "Status changed" in (n.content or "")]
            assert len(status_notes) >= 1

    # ---------- Quick status waiting_parts ----------

    def test_quick_status_waiting_parts(self):
        app = self._make_app()
        with app.app_context():
            ticket_id, _, _, _, _ = _setup_ticket_with_reservation(app)
            ticket = db.session.get(Ticket, uuid.UUID(ticket_id))
            ticket.internal_status = "in_repair"
            db.session.commit()

        with app.test_client() as client:
            _login(client)
            resp = client.get(f'/tickets/{ticket_id}')
            token = _csrf(resp.data)
            resp = client.post(
                f'/tickets/{ticket_id}/quick-status',
                data={'csrf_token': token, 'action': 'waiting_parts'},
                follow_redirects=True,
            )
            assert resp.status_code == 200

        with app.app_context():
            ticket = db.session.get(Ticket, uuid.UUID(ticket_id))
            assert ticket.internal_status == "awaiting_parts"
