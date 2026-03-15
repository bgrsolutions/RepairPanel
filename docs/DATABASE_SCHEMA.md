# IRONCore Database Schema (Logical)

## 1. Core Entities
- `branches`
- `users`
- `roles`
- `permissions`
- `user_roles`
- `role_permissions`
- `user_branch_access`

## 2. Customer & Device
- `customers` (retail/business, contacts, preferred language)
- `customer_addresses`
- `devices` (normalized identity: serial/IMEI/asset id, category)
- `device_category_definitions` (admin-managed)
- `device_custom_field_definitions`
- `device_custom_field_values`

## 3. Ticketing & Workflow
- `tickets`
- `ticket_status_history`
- `ticket_assignments`
- `ticket_tags`
- `ticket_tag_links`
- `ticket_notes` (internal/customer-facing/call log etc.)
- `ticket_attachments`
- `ticket_disclaimers`
- `ticket_signatures`
- `ticket_jobs` (multiple repair lines under one ticket)
- `diagnostics`
- `qa_checklists`
- `qa_checklist_items`
- `collections`

## 4. Quotes
- `quotes` (header, versioning metadata; `ticket_id` nullable for standalone quotes; optional `customer_id`, `customer_name`, `device_description` for standalone)
- `quote_options` (option A/B paths)
- `quote_lines` (labour/part/fixed; optional `part_id` FK)
- `quote_approvals` (method, token, actor, timestamp, payment fields)
- `quote_terms_snapshots`

## 4a. Repair Checklists
- `repair_checklists` (per-ticket, `checklist_type`: pre_repair / post_repair, device category)
- `checklist_items` (individual check items with position, label, checked state, notes)

## 5. Parts, Inventory, Suppliers
- `suppliers`
- `supplier_contacts`
- `parts`
- `part_compatibility`
- `stock_locations`
- `stock_levels`
- `stock_movements`
- `stock_reservations`
- `ticket_parts_usage`
- `part_orders`
- `part_order_lines`
- `part_order_events`

## 6. Labels, Documents, Notifications, Portals
- `label_templates`
- `printer_profiles`
- `print_jobs`
- `documents` (PDF snapshots, receipts, quote PDFs)
- `portal_tokens` (status/approval/check-in access)
- `notification_templates`
- `notification_events`
- `notification_deliveries`

## 7. Audit & Integrations
- `audit_logs`
- `integration_exports`
- `integration_export_items`
- `settings` (global/branch scoped JSON settings)

## 8. Key Fields & Data Strategy
- UUID primary keys (recommended) + human-readable references for tickets/orders.
- `created_at`, `updated_at`, `deleted_at` (soft delete) on major business tables.
- `created_by`, `updated_by` foreign keys for accountability.
- JSONB/JSON fields for dynamic intake data (validated by category schema).

## 9. Entity Relationship Highlights
- Customer 1..N Devices; Device 1..N Tickets.
- Ticket 1..N Diagnostics, Quotes, Notes, Attachments, Stock Reservations.
- Quote 1..N Options; Option 1..N Lines; Quote 1..N Approvals.
- Part 1..N Stock Levels per Branch Location.
- Ticket 1..N Part Orders; Part Order 1..N Events.

## 10. Indexing Strategy
- Unique: `tickets.ticket_number`, optionally per-branch sequence key.
- Search indexes: customer phone/email, device serial/IMEI, part SKU/barcode.
- Composite indexes:
  - `(branch_id, internal_status, priority, due_date)` on tickets.
  - `(ticket_id, created_at)` on timeline/event tables.
  - `(part_id, branch_id, location_id)` on stock tables.
- Partial index for active rows where `deleted_at IS NULL`.

## 11. Soft Deletes
Apply soft delete to customers, devices, tickets, parts, suppliers, templates.
Hard deletes restricted to low-risk lookup tables.

## 12. Audit Logging
- Immutable append-only log for status transitions, approvals, sensitive field access, stock adjustments, export actions.
- Include actor, action, entity_type, entity_id, old/new snapshots (where appropriate), IP/user-agent for public actions.

## 13. Migration Strategy
- Alembic migrations grouped by functional milestone.
- Forward-only schema migrations; data correction via scripted migrations.
- Seed baseline roles, permissions, statuses, default categories, EN/ES locales.
