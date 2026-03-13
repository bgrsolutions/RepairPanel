import os
from datetime import datetime

from app.utils.ticketing import default_sla_target

from app.config import Config
from app.extensions import db
from app.models import Branch, Customer, Device, Role, Ticket, User
from app.utils.ticketing import generate_ticket_number


DEMO_ADMIN_EMAIL = "admin@ironcore.com"
LEGACY_DEMO_ADMIN_EMAILS = {"admin@ironcore.local", "admin@ironcore.test"}
DEMO_ADMIN_PASSWORD = "admin1234"


def _should_reset_demo_password() -> bool:
    env = os.getenv("FLASK_ENV", "development").lower()
    return env in {"development", "dev", "demo", "testing"}


def _normalize_demo_admin(branch: Branch) -> User:
    candidate_emails = {DEMO_ADMIN_EMAIL, *LEGACY_DEMO_ADMIN_EMAILS}
    admin_candidates = User.query.filter(User.email.in_(candidate_emails)).all()

    canonical_admin = next((u for u in admin_candidates if u.email == DEMO_ADMIN_EMAIL), None)

    if canonical_admin is None:
        if admin_candidates:
            canonical_admin = admin_candidates[0]
            canonical_admin.email = DEMO_ADMIN_EMAIL
        else:
            canonical_admin = User(full_name="IRONCore Admin", email=DEMO_ADMIN_EMAIL, preferred_language="en")
            db.session.add(canonical_admin)

    # Merge relationships from legacy demo accounts (if both canonical + legacy rows exist).
    for candidate in admin_candidates:
        if candidate is canonical_admin:
            continue

        for role in candidate.roles:
            if role not in canonical_admin.roles:
                canonical_admin.roles.append(role)

        for candidate_branch in candidate.branches:
            if candidate_branch not in canonical_admin.branches:
                canonical_admin.branches.append(candidate_branch)

        if canonical_admin.default_branch is None and candidate.default_branch is not None:
            canonical_admin.default_branch = candidate.default_branch

        candidate.is_active = False
        if candidate.deleted_at is None:
            candidate.deleted_at = datetime.utcnow()

        # Keep uniqueness while clearly marking legacy normalized account.
        candidate.email = f"legacy+{str(candidate.id).replace('-', '')[:12]}@example.invalid"

    canonical_admin.full_name = canonical_admin.full_name or "IRONCore Admin"
    canonical_admin.is_active = True
    canonical_admin.deleted_at = None
    canonical_admin.preferred_language = canonical_admin.preferred_language or "en"

    if _should_reset_demo_password() or not canonical_admin.password_hash:
        canonical_admin.set_password(DEMO_ADMIN_PASSWORD)

    canonical_admin.default_branch = branch
    if branch not in canonical_admin.branches:
        canonical_admin.branches.append(branch)

    return canonical_admin


def seed_phase1_data():
    role_names = [
        "Super Admin",
        "Admin",
        "Manager",
        "Front Desk",
        "Technician",
        "Inventory",
        "Read Only",
    ]

    for role_name in role_names:
        if not Role.query.filter_by(name=role_name).first():
            db.session.add(Role(name=role_name, description=f"Seeded role: {role_name}"))

    db.session.flush()

    branch = Branch.query.filter_by(code=Config.DEFAULT_BRANCH_CODE).first()
    if not branch:
        branch = Branch(code=Config.DEFAULT_BRANCH_CODE, name="Main Branch")
        db.session.add(branch)
        db.session.flush()

    admin = _normalize_demo_admin(branch)

    admin_role = Role.query.filter_by(name="Admin").first()
    if admin_role and admin_role not in admin.roles:
        admin.roles.append(admin_role)

    customer = Customer.query.filter_by(email="customer@demo.local").first()
    if not customer:
        customer = Customer(
            full_name="Demo Customer",
            phone="+10000000000",
            email="customer@demo.local",
            preferred_language="es",
            primary_branch=branch,
        )
        db.session.add(customer)
        db.session.flush()

    device = Device.query.filter_by(serial_number="DEMO-SN-001").first()
    if not device:
        device = Device(
            category="phones",
            brand="DemoBrand",
            model="X1",
            serial_number="DEMO-SN-001",
            imei="123456789012345",
            customer=customer,
        )
        db.session.add(device)
        db.session.flush()

    existing_ticket = Ticket.query.filter_by(customer_id=customer.id).first()
    if not existing_ticket:
        ticket = Ticket(
            ticket_number=generate_ticket_number(branch.code, 1),
            branch=branch,
            customer=customer,
            device=device,
            internal_status="unassigned",
            customer_status="Received",
            priority="normal",
            assigned_technician=None,
            sla_target_at=default_sla_target(datetime.utcnow(), Config.DEFAULT_TICKET_SLA_DAYS),
        )
        db.session.add(ticket)

    db.session.commit()
