# IRONCore Implementation Roadmap

## Phase 1 – Core System
### Goals
- Project scaffold, auth, branches, RBAC, customers/devices, baseline tickets, dashboard shell.
### Files/Areas
- `app/blueprints/{auth,core,tickets,customers,devices,settings}`
- `app/models/{user,role,branch,customer,device,ticket}`
- `app/templates/{layout,dashboard,tickets}`
- `docker/`, `.env.example`, `migrations/`
### Models Impacted
- users, roles, permissions, branches, customers, devices, tickets.
### Routes/Views
- login/logout, dashboard, ticket list/detail (basic), customer/device CRUD.
### Migrations
- baseline identity + branch + customer/device + ticket core schema.
### Acceptance Criteria
- staff can authenticate, create branch-scoped ticket, and view dashboard counts.

## Phase 2 – Check-In System
### Goals
- Category-specific intake forms, public/kiosk intake, labels, signatures, timeline, attachments.
### Files/Areas
- `intake`, `public_portal`, `labels` blueprints/services.
- templates for intake wizard/kiosk and printable receipts.
### Models Impacted
- intake schemas/values, disclaimers, signatures, attachments, label templates, portal tokens.
### Routes/Views
- internal intake wizard, public check-in, kiosk mode, print endpoints.
### Migrations
- intake dynamic fields, signatures, attachments, print template tables.
### Acceptance Criteria
- public submission creates pre-check-in; reception converts to ticket and prints label.

## Phase 3 – Repair Workflow
### Goals
- Diagnostics, quote versioning/approvals, public status page, QA gating.
### Files/Areas
- `diagnostics`, `quotes`, `public_portal` extensions.
### Models Impacted
- diagnostics, quotes/options/lines/approvals, QA checklists.
### Routes/Views
- diagnosis editor, quote builder, approval portal, status lookup, QA completion.
### Migrations
- quote and QA domain tables.
### Acceptance Criteria
- quote approval updates ticket progression and is fully auditable.

## Phase 4 – Parts & Inventory
### Goals
- Inventory locations, stock movements, reservations, ordered parts, suppliers.
### Files/Areas
- `inventory`, `orders`, `suppliers` modules.
### Models Impacted
- parts, stock levels/movements/reservations, suppliers, part orders/events.
### Routes/Views
- parts catalog, stock adjustments/transfers, order tracking board, supplier records.
### Migrations
- full inventory and order-tracking schema.
### Acceptance Criteria
- ticket can reserve stock or track external order with partial-arrival lifecycle.

## Phase 5 – Reports & Notifications
### Goals
- KPI dashboards, exports, notification templates/events, Odoo export layer, admin polish.
### Files/Areas
- `reports`, `notifications`, `integrations` modules.
### Models Impacted
- report/materialized views (optional), notification templates/deliveries, integration exports.
### Routes/Views
- report dashboards, template manager, export queues, Odoo payload review.
### Migrations
- notification/integration/audit expansion.
### Acceptance Criteria
- branch and global KPI visibility with export and event-driven communications.

## Seed Data / Demo Strategy
- Seed default roles, permissions, statuses, EN/ES languages, sample branch, sample device categories.

## Testing Strategy
- Unit tests for services.
- Integration tests for lifecycle transitions and permission boundaries.
- UI smoke tests for intake, quote approval, and parts ordering flows.
