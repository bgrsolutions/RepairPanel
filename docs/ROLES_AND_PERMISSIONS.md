# IRONCore Roles and Permissions

## 1. Roles

| Role | Description |
|---|---|
| Super Admin | Full system access. Can manage all settings, users, and data. |
| Admin | Administrative access. Settings, users, all operational actions. |
| Manager | Management-level. Users, quotes, reports, portal tokens. |
| Front Desk | Reception staff. Ticket creation, quote creation, customer updates. |
| Technician | Workshop staff. Ticket workflow, checklists, bench notes, part consumption. |
| Inventory | Parts staff. Inventory CRUD, stock movements, locations. |
| Read Only | View-only access. Can browse tickets, inventory, and data but cannot modify. |

## 2. Role Hierarchy

```
Super Admin > Admin > Manager > Front Desk / Technician / Inventory > Read Only
```

## 3. Permission Matrix

| Permission | Super Admin | Admin | Manager | Front Desk | Technician | Inventory | Read Only |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Settings & branches** | Y | Y | — | — | — | — | — |
| **Manage users** | Y | Y | Y | — | — | — | — |
| **Create tickets** | Y | Y | Y | Y | Y | — | — |
| **Workflow actions** (status, assign, notes) | Y | Y | Y | — | Y | — | — |
| **Checklists** (create, update, complete) | Y | Y | Y | — | Y | — | — |
| **Consume reserved parts** | Y | Y | Y | — | Y | — | — |
| **Create/edit quotes** | Y | Y | Y | Y | — | — | — |
| **Send/approve/expire quotes** | Y | Y | Y | — | — | — | — |
| **Portal token lifecycle** | Y | Y | Y | — | — | — | — |
| **Customer communication** | Y | Y | Y | Y | Y | — | — |
| **Manage inventory** (CRUD parts, categories, locations, movements) | Y | Y | Y | — | — | Y | — |
| **Delete parts** | Y | Y | Y | — | — | — | — |
| **View inventory** | Y | Y | Y | Y | Y | Y | Y |
| **View reports** | Y | Y | Y | — | — | — | — |
| **View tickets & data** | Y | Y | Y | Y | Y | Y | Y |

## 4. Enforcement Model

### Server-Side (Mandatory)
All sensitive routes are protected with `@permission_required(check_fn)` decorators that abort with **403** if the user lacks the required role. This runs server-side and cannot be bypassed.

**Protected route groups:**
- `tickets/new`, `tickets/*/quick-status`, `tickets/*/assign-to-me`, `tickets/*/quick-note` — `can_progress_workflow` / `can_create_ticket`
- `tickets/*/consume-reservation` — `can_consume_reservation`
- `tickets/*/regenerate-portal-token`, `tickets/*/revoke-portal-token` — `can_manage_customer_portal`
- `tickets/*/generate-message`, `tickets/*/log-communication` — `can_send_customer_updates`
- `settings/*` (all routes) — `can_manage_settings`
- `quotes/*/create`, `quotes/*/edit`, `quotes/*/update` — `can_create_quote`
- `quotes/*/send`, `quotes/*/mark-expired`, `quotes/*/manual-approval` — `can_manage_quote`
- `quotes/*/create-ticket` — `can_create_ticket`
- `checklists/*` (all routes) — `can_manage_checklists`
- `inventory/parts/new`, `inventory/parts/*/edit`, `inventory/parts/create-json` — `can_manage_inventory`
- `inventory/categories/new`, `inventory/locations/new`, `inventory/movements/new` — `can_manage_inventory`
- `inventory/parts/*/toggle-active`, `inventory/parts/*/delete`, `inventory/categories/*/delete` — `roles_required("Super Admin", "Admin", "Manager")`
- `users/*` — `roles_required("Super Admin", "Admin", "Manager")`

### Template-Level (UI Visibility)
Templates conditionally show/hide UI elements using the `perms` proxy:
- `{% if perms.can_create_ticket %}` — Fast Check-In and New Ticket buttons
- `{% if perms.can_progress_workflow %}` — Quick Actions panel on ticket detail
- `{% if perms.can_send_customer_updates %}` — Customer Communication panel
- `{% if perms.can_manage_customer_portal %}` — Token management (regenerate/revoke)
- `{% if perms.can_manage_settings %}` — Settings nav link
- `{% if perms.can_manage_users %}` — Users/Staff nav link
- `{% if perms.can_view_reports %}` — Reports nav link
- `{% if perms.can_manage_inventory %}` — New Part button
- `{% if perms.can_delete_part %}` — Deactivate/Delete buttons on parts list

## 5. Permission Service Architecture

Central module: `app/services/permission_service.py`

- **Role constants**: `ROLE_SUPER_ADMIN`, `ROLE_ADMIN`, `ROLE_MANAGER`, etc.
- **Role groupings**: `_ADMIN_ROLES`, `_MANAGEMENT_ROLES`, `_WORKSHOP_ROLES`, `_FRONTDESK_ROLES`, `_INVENTORY_ROLES`, `_ALL_STAFF_ROLES`
- **Check functions**: `is_admin()`, `is_management()`, `is_workshop()`, `is_frontdesk()`, `is_inventory_staff()`
- **Specific permissions**: `can_manage_settings()`, `can_create_ticket()`, `can_progress_workflow()`, etc.
- **Template proxy**: `_PermissionProxy` class injected via `permission_context()` into all templates as `perms`

## 6. Safe Defaults

- Unknown or missing roles get **no privileged access**
- `_user_roles()` returns an empty set for unauthenticated users or None
- All permission checks require explicit membership in a known role set
- The `permission_required` decorator returns 401 for unauthenticated users and 403 for unauthorized users

## 7. Audit Requirements

Ticket status changes, quote approvals, stock adjustments, portal token operations, and communication actions are always audit-logged via `log_action()`.
