# IRONCore Roles and Permissions

## 1. Roles
- Super Admin
- Admin
- Manager
- Front Desk / Reception
- Technician
- Inventory / Parts Staff
- Read Only / Reporting

## 2. Permission Matrix (High-Level)
| Capability | Super Admin | Admin | Manager | Front Desk | Technician | Inventory | Read Only |
|---|---|---|---|---|---|---|---|
| Manage branches/settings | Y | Y | Limited | N | N | N | N |
| Manage users/roles | Y | Y | Limited | N | N | N | N |
| Create/edit tickets | Y | Y | Y | Y | Limited | N | N |
| Update diagnosis/repair | Y | Y | Y | N | Y | N | N |
| Manage quotes | Y | Y | Y | Y | Suggest only | N | View |
| Approve override actions | Y | Y | Y | N | N | N | N |
| Manage inventory/stock | Y | Y | Y | View | View | Y | View |
| Manage suppliers/orders | Y | Y | Y | N | N | Y | View |
| View all branches | Y | Configurable | Configurable | Branch only | Branch only | Branch only | Configurable |
| View sensitive credentials | Y | Restricted | Restricted | Restricted | Restricted | N | N |

## 3. Branch Visibility Rules
- Branch-scoped by default for all non-admin roles.
- Optional multi-branch access via explicit mapping.
- Shared customer/device history visible where policy permits.

## 4. Sensitive Field Restrictions
- Passcodes/passwords are encrypted and access-logged.
- Reveal action requires elevated permission and reason capture.
- Public portals can never expose internal notes or sensitive fields.

## 5. Audit Requirements by Role Action
- Ticket status changes, quote approvals, stock adjustments, permissions edits, sensitive-field access, and export actions are always audited.
