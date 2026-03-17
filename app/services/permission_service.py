"""Permission service — role-based access control helpers.

Provides a clean, centralized permission-checking layer for IRONCore RepairPanel.
All permission decisions flow through this module so that role logic is defined
once and reused across routes, templates, and services.

Role hierarchy (highest to lowest privilege):
    Super Admin > Admin > Manager > Front Desk / Technician / Inventory > Read Only

Safe default: unknown or missing roles get no privileged access.
"""
from __future__ import annotations

from flask_login import current_user


# ---------------------------------------------------------------------------
# Role constants
# ---------------------------------------------------------------------------

ROLE_SUPER_ADMIN = "Super Admin"
ROLE_ADMIN = "Admin"
ROLE_MANAGER = "Manager"
ROLE_FRONT_DESK = "Front Desk"
ROLE_TECHNICIAN = "Technician"
ROLE_INVENTORY = "Inventory"
ROLE_READ_ONLY = "Read Only"

# Convenience groupings
_ADMIN_ROLES = {ROLE_SUPER_ADMIN, ROLE_ADMIN}
_MANAGEMENT_ROLES = {ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_MANAGER}
_WORKSHOP_ROLES = {ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_MANAGER, ROLE_TECHNICIAN}
_FRONTDESK_ROLES = {ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_MANAGER, ROLE_FRONT_DESK}
_INVENTORY_ROLES = {ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_MANAGER, ROLE_INVENTORY}
_ALL_STAFF_ROLES = {
    ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_MANAGER, ROLE_FRONT_DESK,
    ROLE_TECHNICIAN, ROLE_INVENTORY, ROLE_READ_ONLY,
}


def _user_roles(user=None) -> set[str]:
    """Return the set of role names for the given user (or current_user)."""
    u = user or current_user
    if not u or not getattr(u, "is_authenticated", False):
        return set()
    return {role.name for role in (u.roles or [])}


# ---------------------------------------------------------------------------
# Permission check functions
# ---------------------------------------------------------------------------

def is_admin(user=None) -> bool:
    """Super Admin or Admin."""
    return bool(_user_roles(user) & _ADMIN_ROLES)


def is_management(user=None) -> bool:
    """Super Admin, Admin, or Manager."""
    return bool(_user_roles(user) & _MANAGEMENT_ROLES)


def is_workshop(user=None) -> bool:
    """Super Admin, Admin, Manager, or Technician — workshop-capable roles."""
    return bool(_user_roles(user) & _WORKSHOP_ROLES)


def is_frontdesk(user=None) -> bool:
    """Super Admin, Admin, Manager, or Front Desk."""
    return bool(_user_roles(user) & _FRONTDESK_ROLES)


def is_inventory_staff(user=None) -> bool:
    """Super Admin, Admin, Manager, or Inventory."""
    return bool(_user_roles(user) & _INVENTORY_ROLES)


# --- Specific permission checks ---

def can_manage_settings(user=None) -> bool:
    """System settings, branch config, portal config."""
    return is_admin(user)


def can_manage_users(user=None) -> bool:
    """Create/edit/deactivate staff users."""
    return is_management(user)


def can_manage_inventory(user=None) -> bool:
    """Create/edit/delete parts, categories, locations, stock movements."""
    return is_inventory_staff(user)


def can_delete_part(user=None) -> bool:
    """Delete or deactivate parts."""
    return is_management(user)


def can_create_quote(user=None) -> bool:
    """Create, edit, send, approve quotes."""
    return is_management(user) or is_frontdesk(user)


def can_manage_quote(user=None) -> bool:
    """Send quotes, manual approval, mark expired."""
    return is_management(user)


def can_create_ticket(user=None) -> bool:
    """Create new tickets."""
    return is_management(user) or is_frontdesk(user) or is_workshop(user)


def can_progress_workflow(user=None) -> bool:
    """Quick status transitions, assign-to-me, workflow actions."""
    return is_workshop(user)


def can_manage_checklists(user=None) -> bool:
    """Create, update, complete, toggle checklist items."""
    return is_workshop(user)


def can_consume_reservation(user=None) -> bool:
    """Install/consume reserved parts."""
    return is_workshop(user)


def can_manage_customer_portal(user=None) -> bool:
    """Regenerate/revoke portal tokens."""
    return is_management(user)


def can_send_customer_updates(user=None) -> bool:
    """Send customer updates, generate messages, log communication."""
    return is_management(user) or is_frontdesk(user) or is_workshop(user)


def can_view_inventory(user=None) -> bool:
    """View parts, stock, categories (read-only)."""
    roles = _user_roles(user)
    return bool(roles & _ALL_STAFF_ROLES)


def can_view_reports(user=None) -> bool:
    """Access reports dashboard."""
    return is_management(user)


def can_view_bookings(user=None) -> bool:
    """View booking list and intake queue."""
    roles = _user_roles(user)
    return bool(roles & _ALL_STAFF_ROLES)


def can_manage_bookings(user=None) -> bool:
    """Create, edit, cancel bookings, mark arrived/no-show."""
    return is_management(user) or is_frontdesk(user)


def can_convert_booking(user=None) -> bool:
    """Convert a booking into a repair ticket."""
    return is_management(user) or is_frontdesk(user)


def can_manage_warranty(user=None) -> bool:
    """Create, edit, void, and claim warranties on tickets."""
    return is_management(user) or is_workshop(user)


def can_send_branded_email(user=None) -> bool:
    """Send branded email communications to customers."""
    return is_management(user) or is_frontdesk(user) or is_workshop(user)


# ---------------------------------------------------------------------------
# Template context injection
# ---------------------------------------------------------------------------

def permission_context() -> dict:
    """Return a dict of permission flags for template rendering.

    Register this via app.context_processor so all templates can use:
        {% if perms.can_delete_part %}
    """
    return {
        "perms": _PermissionProxy(),
    }


class _PermissionProxy:
    """Lazy proxy that evaluates permission checks against current_user."""

    @property
    def is_admin(self) -> bool:
        return is_admin()

    @property
    def is_management(self) -> bool:
        return is_management()

    @property
    def is_workshop(self) -> bool:
        return is_workshop()

    @property
    def is_frontdesk(self) -> bool:
        return is_frontdesk()

    @property
    def can_manage_settings(self) -> bool:
        return can_manage_settings()

    @property
    def can_manage_users(self) -> bool:
        return can_manage_users()

    @property
    def can_manage_inventory(self) -> bool:
        return can_manage_inventory()

    @property
    def can_delete_part(self) -> bool:
        return can_delete_part()

    @property
    def can_create_quote(self) -> bool:
        return can_create_quote()

    @property
    def can_manage_quote(self) -> bool:
        return can_manage_quote()

    @property
    def can_create_ticket(self) -> bool:
        return can_create_ticket()

    @property
    def can_progress_workflow(self) -> bool:
        return can_progress_workflow()

    @property
    def can_manage_checklists(self) -> bool:
        return can_manage_checklists()

    @property
    def can_consume_reservation(self) -> bool:
        return can_consume_reservation()

    @property
    def can_manage_customer_portal(self) -> bool:
        return can_manage_customer_portal()

    @property
    def can_send_customer_updates(self) -> bool:
        return can_send_customer_updates()

    @property
    def can_view_inventory(self) -> bool:
        return can_view_inventory()

    @property
    def can_view_reports(self) -> bool:
        return can_view_reports()

    @property
    def can_view_bookings(self) -> bool:
        return can_view_bookings()

    @property
    def can_manage_bookings(self) -> bool:
        return can_manage_bookings()

    @property
    def can_convert_booking(self) -> bool:
        return can_convert_booking()

    @property
    def can_manage_warranty(self) -> bool:
        return can_manage_warranty()

    @property
    def can_send_branded_email(self) -> bool:
        return can_send_branded_email()
