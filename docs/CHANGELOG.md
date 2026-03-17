# Changelog

## [0.18.0] - 2026-03-17
### Added — Phase 17: Warranty, Branded Communications & Customer Aftercare
- **Warranty Model (17.1)**: New `TicketWarranty` model with warranty type (no_warranty/standard/custom), days, coverage (labour/parts), terms, repair summary, parts used, claim tracking, and email notification status. Migration creates `ticket_warranties` table.
- **Warranty Capture (17.2)**: Warranty capture form on ticket detail page for completed/closed tickets. Auto-fills warranty days and terms from company defaults. Auto-populates parts used from stock reservations.
- **Warranty Evaluation (17.3)**: Reusable warranty service with evaluate, create, claim, void, expire, and device/customer history lookup functions. Status logic: active, expired, claimed, voided, no warranty.
- **Warranty Visibility (17.4)**: Full warranty section on ticket detail page with status badge, type, period, coverage, remaining days, dates, terms, repair summary, parts used, and prior device warranties. Warranty column added to customer detail repair history table.
- **Parts History Awareness (17.5)**: `get_ticket_parts_summary()` builds readable summary of fitted parts from stock reservations. Auto-populated in warranty records for future warranty claim reference.
- **Branded Email Architecture (17.6)**: `branded_email_service.py` provides centralized, template-based email sending with company branding, language-aware template selection (EN/ES), safe fallback logging, and communication note creation.
- **Branded Email Templates (17.7)**: Four email templates in EN/ES: warranty confirmation, warranty expiry reminder, aftercare follow-up, and ticket update. All extend a professional branded base template with company header/footer.
- **Email Configuration (17.8)**: `MAIL_TRANSPORT` config for transport selection. Default `log` transport logs email intent safely. Clean extension points for SMTP/SendGrid.
- **Communication Logging (17.9)**: All warranty and email actions create ticket notes for audit trail. Warranty email sends tracked with `email_sent` flag and timestamp.
- **Permissions (17.10)**: Two new permissions: `can_manage_warranty` (management + workshop), `can_send_branded_email` (management + front desk + workshop). All routes server-side protected.
- **Internationalization (17.11)**: 70+ new EN/ES translation strings for warranty UI, flash messages, email subjects, form labels, and status labels.
- **Company Warranty Defaults (17.12)**: Companies can set `default_warranty_days` and `default_warranty_terms` for auto-filling warranty forms.
- **Warranty Actions (17.13)**: Record claim, void warranty, and send warranty email actions with modal dialogs, validation, and audit logging.
- **60+ New Tests**: Comprehensive test coverage for warranty model, service, routes, permissions, email templates, communication logging, parts history, translations, and edge cases.

### Changed
- `app/models/company.py` — added `default_warranty_days` and `default_warranty_terms` fields
- `app/models/__init__.py` — added `TicketWarranty` import and export
- `app/services/permission_service.py` — added `can_manage_warranty` and `can_send_branded_email` permissions with proxy properties
- `app/blueprints/tickets/routes.py` — added warranty context to ticket detail, 5 new warranty/email POST routes
- `app/blueprints/customers/routes.py` — added warranty data to customer detail context
- `app/templates/tickets/detail.html` — added warranty section, claim/void modals
- `app/templates/customers/detail.html` — added warranty column to repair history table
- `app/translations/en/LC_MESSAGES/messages.po` — added Phase 17 strings
- `app/translations/es/LC_MESSAGES/messages.po` — added Phase 17 Spanish translations

## [0.17.0] - 2026-03-17
### Added — Phase 16: Booking Operations, Intake Queue & Service Scheduling Foundations
- **Booking Lifecycle (16.1)**: Structured booking lifecycle with statuses: new, confirmed, arrived, no_show, converted, cancelled. Explicit validated transitions via `booking_service.py`. Terminal states prevent further changes.
- **Booking Data Enhancements (16.2)**: New fields: `device_id` (FK→devices), `staff_notes`, `customer_name`, `customer_phone`, `converted_ticket_id` (FK→tickets). Alembic migration with status data migration (scheduled→new, in_progress→arrived, completed→converted).
- **Intake Queue (16.3)**: Staff-facing `/bookings/?view=queue` showing overdue, today's, and upcoming bookings. Overdue section highlighted in red. Filters by status and location.
- **Booking Detail (16.4)**: Full booking detail page at `/bookings/<id>` with customer info, device info, notes, linked ticket display, and action sidebar with status transition buttons.
- **Status Actions (16.5)**: POST-only routes for confirm, arrive, no-show, cancel with server-side permission enforcement and transition validation.
- **Assisted Conversion (16.6)**: Manual staff action to create repair ticket from arrived booking. Pre-fills customer, device, service, notes. Creates ticket, portal token, intake note. Transaction-safe with duplicate prevention.
- **Permissions (16.7)**: Three new permission functions: `can_view_bookings` (all staff), `can_manage_bookings` (management + front desk), `can_convert_booking` (management + front desk). All routes server-side protected.
- **Internationalization (16.8)**: All new strings in EN/ES. Status labels, headings, buttons, flash messages, form labels fully translatable.
- **Navigation (16.9)**: Added "Intake Queue" link to Operations nav dropdown.
- **Reporting Compatibility (16.10)**: `get_booking_counts()` service function for future dashboard integration. Does not break Phase 14 dashboards.
- **72 New Tests**: Comprehensive test coverage for model, service, routes, permissions, conversion flow, status transitions, translations, and migration validation.

### Changed
- `app/models/booking.py` — expanded with new fields, lifecycle statuses, transition rules
- `app/forms/booking_forms.py` — updated status choices, added new fields, added `BookingConvertForm`
- `app/blueprints/bookings/routes.py` — full rewrite with permissions, detail page, status actions, conversion flow
- `app/services/permission_service.py` — added booking permissions and proxy properties
- `app/templates/bookings/` — new templates: detail.html, intake_queue.html, convert.html, _queue_row.html; updated list.html and form.html
- `app/templates/base.html` — added Intake Queue nav link
- `tests/test_phase6_business_identity.py` — updated booking tests for new status values

## [0.16.0] - 2026-03-17
### Added — Phase 15: Internationalization, Spanish Translation & Customer Language Preferences
- **Full Staff UI Translation (15.1)**: All 68 Jinja2 templates wrapped with `{{ _("...") }}` for i18n. Covers navigation, page titles, headings, buttons, empty states, flash messages, dashboard labels, ticket/quote/inventory/settings text.
- **Public Portal Localization (15.2)**: Public repair status page, quote approval page, check-in form, and thank-you page fully localized with `{{ _("...") }}`. Language switcher available on public pages.
- **Customer Communication Template Localization (15.3)**: `customer_communication_service.py` refactored to resolve message templates via Flask-Babel gettext at render time. Supports `language` parameter to force a specific locale for outbound messages using `force_locale()`.
- **Customer Language Preference (15.4)**: Customer model already had `preferred_language` field (String(5), default="en"). No schema migration needed. Communication generation now passes customer language to `force_locale()`.
- **Locale Selection Behavior (15.5)**: Staff UI follows session → user preference → browser Accept-Language → English fallback. Customer messages use customer's `preferred_language` via `force_locale()`. Public portal uses session-based language switcher.
- **Form Localization (15.6)**: All 16 WTForms form files updated with `lazy_gettext` for labels, choices, and submit buttons. Validation messages wrapped with `_()` in route handlers.
- **Translation Catalog (15.7)**: Complete `es/LC_MESSAGES/messages.po` with 450+ Spanish translations. Proper catalog structure with `.po`/`.mo` files for `en` and `es`. Updated `app/translations/README.md` with maintenance instructions.
- **Safe Fallbacks (15.8)**: Flask-Babel returns source English string when translation is missing. `customer_status_service.py` uses function-based lookups to resolve labels in active locale.
- **Customer Status Service Localization**: `customer_status_service.py` refactored to use `gettext`/`lazy_gettext` for all customer-facing status labels, progress steps, communication messages, and timeline event labels.

### Changed
- `app/services/customer_communication_service.py` — templates now built dynamically via `_build_templates()` for locale resolution
- `app/services/customer_status_service.py` — static dicts replaced with function-based lookups for locale-aware rendering
- `app/blueprints/public_portal/routes.py` — uses `progress_steps()` function instead of module-level `PROGRESS_STEPS` constant

## [0.15.0] - 2026-03-16
### Added
- **Reporting Service Layer (14.1)**: Centralized `app/services/reporting_service.py` with query/aggregation functions for all management reporting: `management_overview()`, `technician_workload()`, `ticket_throughput()`, `quote_report()`, `inventory_report()`, `communication_report()`, and filter helpers.
- **Management Dashboard Enhancement (14.2)**: Comprehensive KPI dashboard at `/reports/` with overview tiles (total open, overdue, created today, completed today, unassigned), pipeline status tiles (awaiting diagnosis, awaiting quote, awaiting parts, in repair, ready for collection), throughput KPIs (avg age, avg turnaround, created/completed this week, stalled count), quote pipeline summary, technician workload summary, communication & portal metrics, and inventory quick glance.
- **Technician Workload Report (14.3)**: Dedicated `/reports/technician-workload` route with per-technician breakdown table showing active, in-repair, overdue, completed, and total ticket counts. Drill-down links to filtered ticket list per technician.
- **Quote Pipeline Report (14.4)**: Dedicated `/reports/quotes` route with quote status breakdown, approval rate, average time-to-approve metrics, and drill-down links to quotes list.
- **Inventory & Parts Report (14.5)**: Dedicated `/reports/inventory` route with most-used parts, low stock alerts, pending orders, reservation counts (consumed/reserved), and parts awaiting arrival.
- **Customer Communication & Portal Reporting (14.6)**: Communication metrics section on management dashboard showing active portal tokens, total tokens, expired tokens, and communication actions in the last 30 days.
- **Reporting Filters (14.7)**: All reporting routes support date range (today, last 7 days, last 30 days, this month, last month), branch, and technician filters via query parameters. Filter form included on all report pages.
- **Role-Aware Dashboard Access (14.8)**: All reporting routes protected server-side with `@permission_required(can_view_reports)` decorator. Only Super Admin, Admin, and Manager roles can access reports. Returns 403 for unauthorized users.
- **Drill-Down Links (14.9)**: Status breakdown items link to filtered ticket lists. Technician workload entries link to technician-filtered ticket views. Sub-report navigation links on dashboard (Technician Workload, Quote Report, Inventory Report).
- 45 new Phase 14 tests covering reporting service functions (overview, workload, throughput, quotes, inventory, communication), route protection (403 for Technician/Front Desk/Inventory/Read Only, 200 for Admin/Manager/Super Admin), filter integration, template content (tiles, metrics, drill-down links, filter forms), and edge cases (empty data).

## [0.14.0] - 2026-03-16
### Added
- **Permission Service Layer (13.1)**: Centralized `app/services/permission_service.py` with role constants, role groupings (`_ADMIN_ROLES`, `_MANAGEMENT_ROLES`, `_WORKSHOP_ROLES`, `_FRONTDESK_ROLES`, `_INVENTORY_ROLES`, `_ALL_STAFF_ROLES`), and 14+ permission check functions (`can_manage_settings`, `can_create_ticket`, `can_progress_workflow`, etc.).
- **Route Protection (13.2)**: Server-side enforcement via `@permission_required(check_fn)` decorator on all sensitive routes across tickets, settings, quotes, checklists, and inventory blueprints. Returns 403 for unauthorized users. 30+ routes protected.
- **UI Visibility by Role (13.3)**: Template-level conditional rendering using `perms` proxy. Admin dropdown, Settings link, Users link, Fast Check-In button, New Ticket button, Quick Actions panel, Customer Communication panel, Token management controls, New Part button, and Delete/Deactivate buttons all conditionally hidden based on role.
- **Permission Proxy (13.4)**: `_PermissionProxy` class injected via `permission_context()` into all templates as `perms`. Lazy evaluation of permission checks against `current_user`.
- **Safe Defaults (13.5)**: Unknown or missing roles get no privileged access. `_user_roles()` returns empty set for unauthenticated or None users. All checks require explicit role membership.
- **`permission_required` Decorator (13.6)**: New decorator in `app/utils/permissions.py` that takes a permission check function and gates route access. Complements existing `roles_required` decorator.
- Updated `docs/ROLES_AND_PERMISSIONS.md` with complete permission matrix, enforcement model, and architecture documentation.
- 46 new Phase 13 tests covering permission service functions, route protection (403 for unauthorized, 200/302 for authorized), UI visibility (nav elements hidden/shown by role), safe defaults, permission proxy, and regression.

## [0.13.0] - 2026-03-16
### Added
- **Staff Communication Panel (12.1)**: Enhanced "Customer Communication" panel on ticket detail replacing the simple portal link display. Includes portal URL copy, quote approval URL copy (when pending), Message Builder button, Ready Notification shortcut (when ready for collection), and Quote Notification shortcut (when pending quote exists).
- **Communication Event Logging (12.2)**: All communication actions (portal link copied, quote link copied, message generated, token regenerated/revoked) are logged as `communication` type TicketNote entries. Audit trail via `log_action()` for each event.
- **Customer Message Templates (12.3)**: New `customer_communication_service.py` with 7 message templates (Checked In, Awaiting Diagnosis, Quote Ready, Waiting for Parts, In Repair, Ready for Collection, Completed). Templates include portal URL, quote approval URL, ticket reference, device summary, customer name, and opening hours. AJAX endpoint `POST /tickets/<id>/generate-message` returns rendered JSON. Message Builder modal in ticket detail for staff use.
- **Portal Token Regeneration (12.4)**: `POST /tickets/<id>/regenerate-portal-token` creates a new token and deletes all previous ones. Old links immediately stop working. Staff confirmation required. Communication note logged.
- **Portal Token Revocation (12.4)**: `POST /tickets/<id>/revoke-portal-token` deletes the portal token without creating a new one. Customer loses direct URL access. Communication note logged.
- **Ready-for-Collection Communication Shortcut (12.5)**: One-click "Ready Notification" button generates a pre-filled customer message with collection instructions, portal URL, and opening hours (when available from branch data).
- **Quote Approval Communication Shortcut (12.6)**: One-click "Quote Notification" button generates a pre-filled message with quote approval URL and portal URL. Only appears when a pending quote with approval token exists.
- **Communication History Block (12.7)**: Staff-only section on ticket detail showing all `communication` type notes with timestamps and author attribution. Hidden when no communication notes exist. Never exposed on public portal.
- **Portal Security Hardening (12.8)**: Token format validation (reject < 20 or > 50 chars), token expiry checking (`expires_at`), revocation-aware validation (deleted tokens fail). Consistent error messaging for all invalid token scenarios.
- 40 new Phase 12 tests covering communication panel UI, event logging, message templates, token lifecycle, communication shortcuts, history block, security hardening, and Phase 8-11 regression.

## [0.12.0] - 2026-03-16
### Added
- **Public Repair Status Page (11.1)**: Customer-facing repair status page at `/public/repair/<token>` with secure tokenized URL access — no login or verifier needed. Displays device summary, customer-friendly status label, visual 6-step progress indicator, contextual communication summary, and customer-safe notes timeline.
- **Customer-Friendly Status Mapping (11.2)**: Presentation-layer mapping service (`customer_status_service.py`) translating all 11 internal workflow states into 6 customer-friendly labels (Checked In, Diagnosing, Approved, Repairing, Quality Check, Ready). Includes progress step index mapping and contextual communication message generation.
- **Public Quote Visibility Integration (11.3)**: Pending quote approval shown on the public status page with amber "Your approval is needed" banner and direct link to quote approval page when a quote is in sent/draft status.
- **Repair Progress Timeline (11.4)**: Visual 6-step progress indicator (Checked In → Diagnosing → Approved → Repairing → Quality Check → Ready) with completed/active/pending step styling. Cancelled/archived tickets show a special cancelled state.
- **Public Portal Entry Path (11.5)**: Automatic `PortalToken` generation (URL-safe 24-char via `secrets.token_urlsafe(24)`) when tickets are created. Tokens stored in `portal_tokens` table with `token_type="public_status_lookup"` and `ticket_id` foreign key. Staff ticket detail page shows "Customer Portal" section with copyable public URL.
- **Customer Communication Summary (11.6)**: Context-aware status banners — emerald for ready-for-collection, amber for pending quote approval, indigo for all other states. Each includes a plain-language explanation of what is happening with the repair.
- **Customer-Safe Last Update Text (11.7)**: Only `customer`, `customer_update`, and `communication` note types are shown on the public status page. Internal notes, technician names, assignment data, and inventory details are never exposed.
- Migration `d8e0f2a4b6c8` adds `ticket_id` column to `portal_tokens` table with foreign key and index.
- 26 new Phase 11 tests covering status mapping (all states, specific values, progress steps, step indices, communication messages), token access (success, invalid, no login), verifier lookup (email, phone, wrong verifier), security (internal notes hidden, customer notes visible, deleted ticket blocked), UI (banners, progress steps, communication summary), token generation on ticket creation, and Phase 10 regression.

## [0.11.0] - 2026-03-16
### Added
- **Parts consumption on tickets (10.1)**: Technicians can now install/consume reserved parts directly from the ticket detail sidebar. The "Install" button on reserved parts triggers `POST /tickets/<id>/consume-reservation/<reservation_id>`, which marks the reservation as consumed, deducts on-hand stock via `apply_stock_movement("install")`, releases the reserved quantity, and creates an audit note.
- **Technician quick actions (10.2)**: New quick-action buttons on the ticket detail page — "Assign to me" (`POST /tickets/<id>/assign-to-me`), plus context-aware workflow shortcuts: "Diagnosis complete", "Waiting for parts", "Start repair", "Repair complete", "Ready for collection". Each validates the transition and creates an audit note.
- **Quick status transitions (10.3)**: `POST /tickets/<id>/quick-status` endpoint accepts an `action` parameter mapping to pre-defined workflow transitions. Enforces the same transition validation and post-repair checklist rules as the standard status form.
- **Inline bench notes (10.4)**: Quick Bench Note form on the ticket detail page lets technicians add internal notes without opening the full modal. `POST /tickets/<id>/quick-note` creates an internal note instantly.
- **AJAX checklist item toggle (10.5)**: `POST /checklists/item/<id>/toggle` endpoint for toggling individual checklist items without a full form submit. Returns updated progress (checked_count, total_count, all_checked) for live UI updates. Checkboxes on the ticket detail page use this for faster interaction.
- **Inventory service: consume_reservation()**: New service function that atomically consumes a reserved part — sets status to "consumed", releases reserved qty from StockLevel, and creates an "install" stock movement.
- **24 new Phase 10 tests**: Consume reservation (success, already consumed, creates install movement, creates note), assign-to-me, quick status (start repair, invalid transition, unknown action, diagnosis complete, repair complete, waiting parts, creates note), quick bench note (success, empty rejected), checklist toggle (check, uncheck, all checked, completed rejected), UI presence (quick actions panel, install button, bench note form), inventory service (consume_reservation, invalid qty), Phase 9 regression (search endpoints).

## [0.10.0] - 2026-03-16
### Added
- **Improved ticket creation flow (9.1)**: Inline "Quick Add Device" form during ticket creation — staff can add a new device (brand, model, serial, IMEI, category) without leaving the check-in page. New device is immediately selectable in the device dropdown.
- **Device search AJAX endpoint (9.1)**: `GET /tickets/device-search` searches devices by brand, model, serial number, or IMEI. Supports optional `customer_id` scoping. Integrated into ticket creation with live search below the device dropdown.
- **Device creation AJAX endpoint (9.1)**: `POST /tickets/device-create-json` creates a new device linked to a customer during ticket creation. Returns the new device ID for immediate selection.
- **Customer list instant filter (9.2)**: Client-side live filtering on the customer list page — rows filter as the user types without a page reload.
- **Parts list instant filter (9.3)**: Client-side live filtering on the parts catalog page — rows filter as the user types.
- **Safe part deletion (9.4)**: `POST /inventory/parts/<id>/delete` with dependency safety checks. Refuses deletion if the part has stock movements, reservations, part order lines, quote lines, or is a default part for a repair service. Shows a warning directing the user to deactivate instead. Unreferenced parts are soft-deleted (deleted_at + is_active=false). Delete buttons added to the parts list UI with confirmation dialog.
- **26 new Phase 9 tests**: Device search (model, serial, IMEI, customer-scoped, min length), device AJAX creation (success, missing fields), customer search (tickets, customers blueprint, min length, list page, query filter), part search (name, SKU, min length, live search, delete button), safe deletion (unused part deletes, stock movement blocks, order line blocks), ticket creation (page loads, customer devices, existing device), Phase 8 regression (bench board, transitions, dashboard).

## [0.9.10] - 2026-03-16
### Fixed
- **QR code dependency (7I fix)**: Added `qrcode` and `Pillow` to `requirements.txt`. These were installed at development time but missing from the dependency manifest, causing `generate_qr_data_uri()` to silently return `None` on fresh deployments and rendering device labels without QR codes.

### Validated
- **Phase 8 workshop workflow review**: Verified transition map, blocker detection, bench board column groupings, dashboard metrics, and ticket detail workflow panel all match the documented specification in `WORKSHOP_OPERATIONS.md`.
- **Full test suite**: All 201 tests pass (172 existing + 29 Phase 8) with zero regressions.

## [0.9.9] - 2026-03-16
### Added
- **Bench Board overhaul (8A)**: Redesigned bench board with workflow-oriented columns — Awaiting Diagnosis, Awaiting Quote Approval, Awaiting Parts, Ready For Repair, Testing/QA, Ready For Collection. Compact ticket cards show customer, device, issue summary, technician, SLA dates, and blocker badges.
- **Workflow status transitions (8B)**: Formal transition validation via `workflow_service.py`. Invalid transitions (e.g., unassigned→completed) are rejected with error messages. Transition map covers all 11 statuses.
- **Blocker detection (8C)**: Automatic detection of quote blockers (unapproved quotes), parts blockers (open/overdue orders), checklist blockers (incomplete post-repair checklists), and SLA blockers (overdue tickets). Surfaced on bench board cards, ticket detail, and dashboard.
- **Technician assignment improvements (8D)**: Quick-assign AJAX endpoint (`POST /tickets/<id>/quick-assign`) for fast technician assignment. Technician name displayed on board cards. Board filterable by technician.
- **Bench Board filters (8E)**: Added filters for branch, technician, status, date range, overdue only, waiting parts, and waiting quote. Filters update the board dynamically.
- **SLA & overdue visibility (8F)**: Dedicated "Overdue Tickets" widget on dashboard listing all overdue tickets. OVERDUE badges on bench board cards and ticket detail. SLA dates highlighted when past due.
- **Dashboard improvements (8G)**: Attention widget now uses blocker detection for richer reason labels. Overdue tickets shown in dedicated section. Activity feed improved with ticket number and customer name references.
- **Ticket detail workflow panel (8H)**: New sidebar panel showing current status, next recommended action, and active blockers with details. Context-aware next-step suggestions.
- **Workshop metrics (8I)**: Operational metrics row on dashboard showing counts for In Diagnosis, Awaiting Quote, Awaiting Parts, In Repair, Testing/QA, and Unassigned tickets.
- **29 new Phase 8 tests (8J)**: Tests for bench board loading, column grouping, blocker badges, filter functionality, status transition validation, blocker detection (quote/parts/checklist/SLA), technician quick-assign, overdue detection, dashboard metrics, and workflow panel.
- **Workshop Operations documentation (8K)**: New `docs/WORKSHOP_OPERATIONS.md` covering bench board, ticket lifecycle, status transitions, blocker detection, workshop metrics, and technician assignment.

## [0.9.8] - 2026-03-16
### Added
- **Customer business identity (7A)**: Extended Customer model with `customer_type` (individual/business), `company_name`, `cif_vat`, and full billing address fields (address, postcode, city, region, country, email, phone). New customer edit page at `/customers/<id>/edit` with toggle between individual and business modes. Business customers show "BIZ" badges in lists and detail views.
- **Company-aware ticket/quote context (7B-7C)**: Ticket detail, quote detail, and customer views now display business customer company name, CIF/VAT, and "BIZ" badge. Quote `display_customer_name` property uses `display_name` for business-aware rendering. Standalone quotes support business customer details.
- **Printable quote (7D)**: Professional print-friendly quote at `/print/quote/<id>` with company/branch identity header, customer block (individual or business-aware), device details, diagnostic summary, line items table with IGIC tax, subtotal/tax/grand total block, terms, signature area, and QR code.
- **Printable ticket/intake slip (7E)**: Print-friendly repair ticket at `/print/ticket/<id>` with ticket number, branch identity, customer/device details, IMEI/serial, issue summary, intake notes, diagnostics, pre-repair check summary, repair terms, and customer signature area.
- **Printable checklist (7F)**: Print-friendly checklist summary at `/print/ticket/<id>/checklist` showing all pre-repair and post-repair checklists with item status, notes, and completion timestamps.
- **Device sticky label (7G)**: Compact label at `/print/ticket/<id>/label/device` (62mm×29mm) with ticket number, device model, customer surname, IMEI/serial, branch code, QR code. Optimized for label printers.
- **Accessory sticky label (7G)**: Per-accessory labels at `/print/ticket/<id>/label/accessory` parsed from intake notes, each with ticket number, accessory name, customer surname, branch code.
- **Document service (7H)**: Shared `document_service.py` with `resolve_branch_identity()`, `customer_block()`, and `generate_qr_data_uri()` helpers. Reusable `print/base_print.html` base template with professional print CSS, screen preview toolbar, and document layout components.
- **QR code foundation (7I)**: `qrcode` library integration for generating QR codes as base64 data URIs. Used on printed quotes (quote reference), tickets (ticket number), and device labels.
- **Print action buttons (7J)**: Ticket detail page now has Print section with Ticket Slip, Checklist, Device Label, and Accessory Label buttons. Quote detail page has Print Quote button.
- Migration `c7d9e1f3a5b7` adds 11 columns to customers table with index on customer_type.
- 29 new Phase 7 tests covering customer business fields, edit flow, business badges on ticket/quote detail, printable quote/ticket/checklist/label routes, document service helpers, QR code generation, print buttons, and migration validation.

## [0.9.7] - 2026-03-16
### Added
- **Company model (6A)**: New `Company` entity for business/legal identity management with legal_name, trading_name, CIF/NIF, tax_mode, contact details, logo_path, default quote/repair terms, document footer. Admin UI at `/admin/companies/` with full CRUD.
- **Branch/Store extension (6B)**: Extended existing `Branch` model with 12 new columns — company_id (FK), address_line_1, address_line_2, postcode, city, island_or_region, country, phone, email, opening_hours, ticket_prefix, quote_prefix. New edit UI at `/settings/branches/<id>/edit`. Added `full_address` property.
- **Service Catalogue (6C)**: New `RepairService` model with name, device_category, description, default_part_id (FK to parts), labour_minutes, suggested_sale_price, is_active. Admin UI at `/services/` with CRUD, category badges, and part links.
- **Smart Check-In service selector (6D)**: Fast Check-In (`/tickets/new`) now includes repair service selector, part availability panel, and ETA suggestion panel. Service info sidebar shows labour time and suggested price.
- **Part availability during check-in (6E)**: AJAX endpoint `/tickets/service-availability` returns real-time stock data for the selected service's default part — stock in current store, other stores, needs ordering flag, supplier lead time.
- **ETA suggestion (6F)**: Automatic promised repair time calculation based on service labour_minutes, stock availability, and supplier lead_time_days. Rounds to business hours.
- **Booking/Calendar foundation (6G)**: New `Booking` model with location_id, customer_id, repair_service_id, linked_ticket_id, start/end time, status (scheduled/confirmed/in_progress/completed/cancelled/no_show), notes. UI at `/bookings/` with day view, week navigation, date picker, and location filter.
- **Dashboard bookings widget (6H)**: Today's Bookings section on dashboard showing up to 5 upcoming bookings with time, customer, service, and status badges.
- **Document identity foundations (6I)**: Company and Branch models now carry all fields needed for quote/ticket document headers (company identity, branch address, prefixes).
- **Navigation**: Added Bookings and Services links to desktop and mobile navigation under Operations dropdown. Settings page links to Companies, Service Catalogue, and Bookings.
- Migration `b5c7d9e1f3a5` creates companies, repair_services, bookings tables and extends branches with new columns.
- 26 new Phase 6 tests covering company CRUD, branch editing, service catalogue, check-in service selector, part availability API, ETA suggestion, booking CRUD, dashboard widget, model properties, migration validation, and navigation.

## [0.9.6] - 2026-03-15
### Added
- **Intake form redesign (6A)**: Reworked `/intake/new` with 6 numbered step sections — Branch & Customer, Device Details, Fault & Condition, Pre-Repair Quick Check (5 checkboxes), Initial Diagnosis, and Attachments & Disclaimer. Sidebar intake checklist guide for staff reference.
- **Pre-repair quick checks on intake**: Five toggle checks (powers on, screen condition, charging, buttons, water damage) captured at intake and stored as structured notes.
- **Initial diagnosis fields on intake**: Optional diagnosis and recommended repair fields for technician use during check-in.
- **Checklist numbering and multi-display (6B)**: Ticket detail now shows all pre-repair and post-repair checklists (not just the first), numbered as "Pre-Repair Check #1", "#2", etc., with Active/Complete badges and completion timestamps.
- **Attention widget reason tags (6E)**: "Tickets Need Attention" widget now shows explicit reason badges (Overdue SLA, Parts overdue, Unassigned, Awaiting diagnosis 2+ days, Awaiting quote response, Waiting on parts 5+ days).
- **Human-friendly activity feed (6D)**: Recent Activity widget now shows action descriptions, actor names, action-type color coding, and ticket number link badges instead of raw audit tokens.
- **Navigation updates (6F)**: "New Ticket" nav button renamed to "Fast Check-In"; added "Intakes" button in both desktop and mobile navigation.
- 11 new Phase 6 tests covering intake form structure, pre-check submission, multiple checklists display, overdue consistency, activity feed format, attention widget reasons, and navigation labels.

### Fixed
- **Overdue logic consistency (6C)**: Dashboard, bench board, my queue, ticket list, and reports now all use the shared `is_ticket_overdue()` helper with `sla_days` from `DEFAULT_TICKET_SLA_DAYS` config. Previously, reports used inline date arithmetic and bench board omitted the `sla_days` parameter.
- **Checklist display bug (6B)**: Fixed `.first()` queries that returned only one checklist per type; changed to `.all()` with ordering by `created_at`. Completed checklists are now always visible.
- **Checklist creation guard**: "Create new" button only appears when no active (incomplete) checklist exists for that type.

## [0.9.5] - 2026-03-15
### Fixed
- **Quote total calculation**: Added `change` event listeners alongside `input` for broader browser compatibility (paste, autofill). New lines default quantity to 1 instead of empty, so typing a price immediately shows a total.

### Added
- **Purchase order line sale price**: `PartOrderLine` now has a `sale_price` column. When receiving stock, the part's sale price is updated from the line if set.
- **Receive All Stock**: Bulk receive button on order detail page receives all remaining quantities in one action, updating stock levels and part prices.
- **Stock overview grouping**: Inventory overview groups stock levels by part with expandable sub-rows showing per-branch/location breakdown.
- **Part creation UX**: Numbered section headers (Identity, Pricing, Suppliers, Categories, Details) with live gross margin preview on both new and edit forms.
- **CSRF on toggle-active**: Parts list deactivate/reactivate forms now include CSRF token.
- Migration `a4b6c8d0e2f4` adds `sale_price` column to `part_order_lines`.
- 11 new Phase 4 tests covering quote JS events, part form UX, order line sale price, bulk receive, stock overview grouping, and migration coverage.

## [0.9.4] - 2026-03-15
### Fixed (Critical Regression)
- **Missing migration for standalone quote columns**: Added migration `f3a5b7c9d1e2` that adds `customer_id`, `customer_name`, `device_description` columns to `quotes` table and makes `ticket_id` nullable. Without this migration, PostgreSQL crashed with `column quotes.customer_id does not exist` on any route that queried the quotes table.
- **Missing migration for checklist tables**: Same migration creates `repair_checklists` and `checklist_items` tables required by the Phase 3 checklist feature.
- **Routes restored**: `/quotes/list`, ticket detail (when loading quotes), `/reports/` KPI dashboard, and quote detail pages all crashed due to the missing columns. Fixed by the migration.
- **Checklist table guard**: Ticket detail and status update routes now check for `repair_checklists` table existence before querying, preventing crashes when the migration hasn't been applied yet.

### Added
- **Schema/migration consistency tests**: New `test_regression_schema_routes.py` with 13 tests that validate migration files cover all model columns, migration chain integrity, route availability for critical pages, and standalone quote rendering.
- Migration chain validator test catches orphan or disconnected migration revisions.
- Route smoke tests for `/quotes/list`, `/tickets/<id>`, `/intake/new`, `/reports/`, `/tickets/new`, and standalone quote detail.

### Why Previous Tests Missed This
SQLite-based tests create tables directly from the SQLAlchemy model definition (which includes all columns), so missing migrations are invisible. The new schema consistency tests parse migration files to verify every model column appears in a migration, catching this class of bug regardless of test database engine.

## [0.9.3] - 2026-03-15
### Added
- **Standalone quotes**: Quotes can now be created without a linked ticket (for WhatsApp, phone, walk-in enquiries). New `/quotes/standalone/new` route and quotes list page at `/quotes/list`.
- **Pre-repair and post-repair checklists**: Device-category-aware checklist templates (phones, tablets, laptops, desktops, game consoles) auto-populate when creating a checklist for a ticket. Checklists track individual item checks with timestamps and user attribution.
- **Friendly public quote URLs**: `/public/quote/Q-<version>/<token>` provides human-readable quote approval links alongside the existing token-only URL.
- **Dashboard real activity feed**: Replaced hardcoded placeholder with live activity from AuditLog (PostgreSQL) or TicketNote (SQLite fallback).
- **Inline diagnostics on ticket detail**: Diagnostic entries now display directly on the ticket detail page, not only via modal.
- **ETA preset buttons on ticket intake**: Quick "Today", "Tomorrow", "3 Days", "1 Week" buttons for setting promised completion at 18:00.
- **Customer search card UX**: Ticket intake now shows selected customer as a visual card with "Change" button instead of a raw dropdown.
- **Numbered step sections in ticket intake**: Form divided into clear steps (Branch & Customer, Device, Issue Details, Promised Completion).
- **Quote builder inline part autocomplete**: Typing in the description field triggers async part search; selecting a part auto-fills description, price, and line type.
- New `RepairChecklist` and `ChecklistItem` models with cascade delete.
- New `/checklists/` blueprint with create, update, and complete routes.
- 19 new tests covering standalone quotes, quote builder UX, intake UX, checklists, dashboard activity, diagnostics visibility, and public quote URLs.

### Changed
- `Quote.ticket_id` is now nullable to support standalone quotes. Added `customer_id`, `customer_name`, `device_description` fields.
- `Quote` model gains `is_standalone`, `display_customer_name`, `display_device` properties.
- `QuoteLineForm.linked_part_id` changed from `SelectField` to `HiddenField` (eliminates choices overhead).
- `TicketCreateForm.customer_id` changed from `SelectField` to `HiddenField` (JS-driven search replaces dropdown).
- Ticket detail SLA & Promise section now shows "Past due" / "Overdue" badges with color indicators.
- Checklist enforcement on ticket status changes is guarded by table existence check (graceful degradation).
- Base navigation includes "Quotes" link in both desktop dropdown and mobile nav.
- Parts search API (`/inventory/parts/search`) now returns `sku` field in response.

### Fixed
- Checklist queries in ticket detail guarded behind `has_table()` check to prevent SQLite test failures.
- Dashboard activity feed gracefully falls back when AuditLog JSONB is unsupported (SQLite).

## [0.9.2] - 2026-03-15
### Fixed
- Quote part search/autocomplete fully reworked: global `partsData` JSON map replaces fragile data-attribute approach, ensuring autofill works for both initial dropdown selections and search results.
- Quote search clears properly: restores full parts list when search input is emptied (< 2 chars).
- Search results enrich global `partsData` so cloned/added lines can still reference part metadata.
- Updated public status and check-in test assertions to match redesigned template text.

### Added
- Mobile hamburger navigation menu for small screens with grouped section labels.
- Flash message icons (success/error/warning/info) with SVG indicators in base layout.
- Dropdown chevron indicators on navigation menu items with auto-close on outside click.
- Improved `empty_state` macro with placeholder icon for better visual empty states.
- Stat card gradient accent glow based on color accent parameter.
- Focus ring styles for keyboard accessibility on form inputs.
- CSS `shadow-panel` utility class, smooth transitions on interactive elements.
- Part badge display on quote lines showing selected part with clear button.

### Improved
- Comprehensive UI/UX polish pass across all 50+ templates for visual consistency.
- Base layout: better logo sizing, dropdown menus with rounded-xl and shadow-xl, separator dividers in dropdown groups.
- Public portal: redesigned check-in with step progress indicator, status page with visual progress tracker and timeline updates, quote approval with professional line-item display.
- Ticket pages: list, board, queue, new ticket, and detail all use consistent card/table/button styling.
- Quote builder: improved line layout, badge-based part selection feedback, consistent spacing.
- Inventory pages: overview, parts list/detail/edit/new, categories, locations, movements all polished.
- Customer, supplier, order pages: consistent table hover states, card layouts, form styling.
- Dashboard, reports, settings, notifications, exports, integrations: unified design language.
- Users/staff management: consistent form and list styling.
- Intake pages: list, detail, new, receipt all updated with consistent card layouts.
- Auth login page: improved dark theme form styling.
- UI macros: `section_card` with better spacing, `ticket_card` with grouped layout and technician icon, `stat_card` with gradient accent.

## [0.9.1] - 2026-03-15
### Fixed
- Quote part search now auto-fills description and unit price when a part is selected from search results (no extra fetch needed).
- Removed redundant `inspect(db.engine)` calls in parts list route.
- Added CSRF tokens to ticket archive, reopen, reservation release, supplier toggle, and category delete forms.
- Made `csrf_token` globally available in Jinja2 template context via `generate_csrf`.

### Added
- Supplier toggle-active route (`/suppliers/<id>/toggle-active`) with admin role protection and confirmation dialog.
- Category soft-delete route (`/inventory/categories/<id>/delete`) with admin role protection and confirmation dialog.
- Reservation release route (`/tickets/<id>/release-reservation/<id>`) to free allocated stock back to available pool.
- Reserved parts section on ticket detail now shows reservation status (Reserved/Released) with color-coded badges.
- Stock overview navigation now includes Categories link.
- Stock overview available column now uses per-part `low_stock_threshold` instead of hardcoded value.

### Improved
- Quote builder JS: `wirePartAutofill` now reads part name and sale price directly from search result data attributes, eliminating the separate `/quotes/part-price` fetch.
- Reserved vs ordered parts sections on ticket detail have clearer descriptions and visual distinction.
- Archive/reopen buttons now include confirmation dialogs to prevent accidental clicks.

## [0.9.0] - 2026-03-15
### Fixed
- Removed duplicate technician/workflow controls from ticket detail top panel; controls remain in right sidebar only.
- Removed duplicate Terms Snapshot field from quote create/edit form.
- Fixed diagnostics modal layout to fill available width properly (max-w-5xl, improved field arrangement).
- Fixed quotes section placement on ticket detail page (was outside grid column).

### Added
- Staff quote approve/decline workflow: Approve/Decline button and modal on quote detail page for internal decisions.
- Mark Expired button on quote detail page for sent quotes.
- Ticket archive and reopen actions: Archive button on active tickets, Reopen button on closed/archived tickets.
- Archived ticket status with badge styling, list filter, and proper exclusion from default ticket list.
- Audit logging for ticket send-update, archive, and reopen actions.
- Prominent quotes section on ticket detail with status-colored borders, inline totals, and quick New Quote button.

### Improved
- Quote builder UX: separated terms field to full-width row, improved line layout with description given more space, better placeholders and helper text, part search moved to secondary row, improved add-line button styling.
- Send Update modal already supported optional email; added audit logging for consistency.

## [0.1.0] - 2026-03-11
### Added
- Initial governance documentation set for IRONCore.
- Scope, requirements, architecture, schema, workflow, role model, portal specs.
- Parts/inventory, quotes/approvals, labels/printing, Odoo readiness plans.
- Phased implementation roadmap and decision register bootstrap.

## [0.2.0] - 2026-03-11
### Added
- Implemented Phase 1 application scaffold with Flask app factory, modular blueprints, SQLAlchemy models, Flask-Migrate setup, Flask-Login auth flow, and Flask-Babel multilingual foundation.
- Added core Phase 1 data models: User, Role, Branch, Customer, Device, Ticket, AuditLog.
- Added initial Alembic migration and seed command for baseline roles/branch/admin/demo records.
- Added Dockerfile and docker-compose configuration for Flask + PostgreSQL local development.
- Added dashboard shell, base layout, login view, ticket list/create views, and Tailwind-ready static structure.

## [0.2.1] - 2026-03-11
### Added
- Internal operations UI pass with RepairDesk-inspired dark dashboard shell enhancements.
- New internal templates for ticket detail shell, technician My Queue, and repair bench board views.
- Reusable UI component macros for status/priority badges, stat cards, ticket cards, section cards, and empty states.

### Changed
- Upgraded base layout/navbar, dashboard, ticket list, and new ticket pages for premium spacing, hierarchy, and responsive behavior.
- Kept Tailwind CDN strategy and minimal custom CSS approach while improving dark-theme polish.

## [0.2.2] - 2026-03-11
### Fixed
- Login form email validation now supports local demo domains (`*.local`) by disabling deliverability checks for login input validation.
- Authentication now rejects inactive or soft-deleted users before login.
- Seed logic is now deterministic/idempotent for demo admin setup, including active flag, default branch, branch access, role assignment, and documented demo password reset in dev/demo/testing environments.

### Added
- Automated auth/seed integration test covering seed idempotency, working demo credentials, successful login redirect, and invalid-credential error handling.

## [0.2.3] - 2026-03-12
### Fixed
- Canonical demo admin is now `admin@ironcore.com` with deterministic seed normalization from legacy demo addresses (`admin@ironcore.local`, `admin@ironcore.test`).
- Seed process now enforces active canonical admin state, role linkage, default branch, and branch access on every run in dev/demo/testing.
- Local host-based setup defaults now point Flask to `127.0.0.1:5432` for PostgreSQL when DB runs in Docker.

### Added
- Auth/seed integration coverage now includes CSRF-backed login POST validation, canonical seed normalization checks, successful login redirect assertions, and invalid credential behavior.

## [0.3.0] - 2026-03-12
### Added
- Phase 2 intake foundations: internal intake workflow, public check-in portal, kiosk mode entrypoint, intake detail/review, and pre-check-in to ticket conversion flow.
- New intake domain models for intake submissions, disclaimer acceptance records, signatures, attachments, and portal tokens.
- Intake/public forms for required Phase 2 categories (phones, laptops, desktops, game consoles, other).
- Attachment upload utility with safe filename handling and image extension allowlist.
- Printable intake receipt foundation with reference and device/customer summary.
- Phase 2 migration introducing intake-related tables and indexes.
- Automated tests for internal intake creation+conversion and public pre-check-in submission (including CSRF-backed flows).

### Changed
- Base navigation now exposes intake management to internal staff users.
- App configuration expanded with upload/disclaimer defaults for intake workflows.

## [0.3.1] - 2026-03-12
### Changed
- Added isolated public-facing layout for `/public/check-in`, `/public/kiosk/check-in`, and public thank-you flow to remove internal staff navigation from kiosk/public screens.
- Added customer-centered internal workflow UI with searchable customers list and customer profile pages showing linked devices and ticket/repair history.
- Updated internal navigation to include Customers and added direct customer profile links from dashboard, ticket, and intake views.
- Improved intake detail page linkage visibility for linked customer, linked device, and converted ticket status/actions.

## [0.4.0] - 2026-03-12
### Added
- Phase 3 repair workflow foundations: ticket diagnostics capture with versioned diagnostic history, quote modeling (header/options/lines), and quote approval records.
- New staff quote module with quote creation, quote detail, send-for-approval action, manual in-store approval/decline placeholder, and expiry status controls.
- Public customer status lookup page (`/public/status`) with safe verifier-based lookup (`ticket number + phone/email`) and customer-facing data minimization.
- Public quote approval page (`/public/quote/<token>`) with tokenized decision flow (approve/decline), method metadata, and timestamp capture.
- Automated Phase 3 tests for diagnostics/quote lifecycle and public status/quote approval flows.

### Changed
- Ticket detail page now integrates diagnosis form/history, quote summaries, quote approval status visibility, and direct quote creation links.
- Internal/public route registration expanded with dedicated diagnostics and quotes blueprints.

## [0.5.0] - 2026-03-12
### Added
- Phase 4 operational workflow foundation for technician assignment and ticket notes (`internal`, `customer`, `communication`) with author/timestamp capture.
- Inventory foundation models and UI for parts catalog, suppliers, stock locations, stock levels, stock movements, and stock reservations.
- Ordered parts tracking foundation with ticket-linked part orders, order lines, and order event/status timeline (`ordered`, `shipped`, `delayed`, `partially_arrived`, `arrived`, `installed`).
- New blueprints/modules for inventory, suppliers, and orders, plus stock/order service helpers.
- Phase 4 migration introducing ticket notes and inventory/order schema tables.
- Automated tests for assignment/notes, inventory/reservations, and order creation/status transitions.

### Changed
- Ticket detail now includes technician assignment controls, structured note entry, reserved parts section, and ordered parts visibility.
- Ticket list, bench board, and my queue views now surface technician ownership more clearly.
- Internal navigation now exposes Inventory, Suppliers, and Orders operational pages.

## [0.6.0] - 2026-03-12
### Added
- Phase 5 foundation modules for reports (`/reports`), notifications (`/notifications`), settings (`/settings`), and export readiness (`/integrations/exports`).
- KPI dashboard widgets for status/branch distribution, aging tickets, technician workload, most-used parts, and parts awaiting arrival.
- Notification foundation schema and UI placeholders for templates, events, and delivery logs.
- Odoo export readiness foundation with ticket payload preview and export queue logging.
- Migration adding notification and export queue tables.
- Automated Phase 5 integration test covering new pages and export queue flow.

### Changed
- Internal navigation and dashboard quick actions now link to Reports, Notifications, Exports, and Settings.


## [0.6.1] - 2026-03-12
### Added
- Staff user management module (`/users`) with list/create/edit flows for login-capable users, role assignment, branch access, and active/inactive control.
- Ticket workflow status update endpoint/UI and SLA target foundation (`tickets.sla_target_at`) with overdue/aging calculations used across dashboard and bench board.
- Ticket creation customer-device usability improvement via customer-scoped device filtering endpoint and dynamic form behavior.
- Inventory parts operational improvements: multi-field search (name/SKU/barcode/supplier SKU) and safe activate/deactivate action instead of destructive delete behavior.
- Refinement pass integration test coverage for user management, assignment/status lifecycle, customer-device filtering, and parts deactivate flow.

### Changed
- Bench board now groups operational buckets (Unassigned, Assigned, Awaiting Diagnostics, Awaiting Parts, In Repair, Ready for Collection, Overdue, Aging) using real status + assignment + SLA logic.
- Dashboard metrics now expose distinct aging and overdue counters based on SLA foundations.
- Internal navigation reorganized into grouped operations menus with persistent New Ticket CTA and added Users/Staff access.

## [0.6.2] - 2026-03-12
### Added
- Ticket create/check-in workflow improvements: searchable customer finder pattern, create-time technician assignment, create-time operational status selection, issue summary capture, and promised completion datetime capture.
- Ticket detail metadata edit flow for issue summary + promised completion, with continued SLA visibility side-by-side.
- Quote workflow upgrades for practical multi-line quoting including optional part-linked quote lines and draft quote editing.
- Part order workflow upgrades for multi-line orders with line-level metadata, supplier reference/tracking/ETA fields, optional ticket linkage for general stock orders, and order edit flow.
- Receiving workflow for part orders that records inbound stock movements, supports partial receipts, and updates order/line statuses.
- New integration coverage for Pass B+ (ticket create assignment/ETA, multi-line quote, stock order without ticket, and partial receiving behavior).

### Changed
- Global and ticket-context order creation now uses explicit ticket selection (optional) to prevent stale/incorrect ticket associations.
- Order list/detail screens now expose repair-vs-stock context, ETA/tracking metadata, and overdue operational visibility.
- Intake conversion now supports optional technician assignment and promised completion datetime propagation into created tickets.

## [0.6.3] - 2026-03-13
### Added
- Unified internal searchable lookup endpoints for customers/tickets/parts to support intake, ticket creation, reservations, and order workflows without long static dropdown scrolling.
- Internal intake existing-customer search/select flow with safe prefill and persisted `existing_customer_id` linking behavior.
- Device ownership lifecycle actions in customer profile for transfer-to-another-customer and unlink operations while preserving historical ticket ownership context.
- Pass C automated coverage for unified search endpoints, public exact-match intake linking behavior, and device transfer/unlink workflows.

### Changed
- Public check-in customer matching now uses explicit exact-match policy for email/phone before creating a new customer, without exposing customer directory data publicly.
- Ticket create and part-order create screens now use server-backed search suggestion patterns for customer/ticket lookup consistency.
- Ticket detail reserve-part workflow now includes searchable part lookup and improved ordered-part ETA/tracking visibility cues.
- Parts catalog now surfaces operational supplier + lead-time + stock availability context for better procurement decisions.

## [0.6.4] - 2026-03-13
### Changed
- Ticket detail hierarchy is now more operationally compact: assignment + workflow controls are surfaced near the top and common updates (ticket details, notes, diagnostics) are collapsed into quick-action panels to reduce scrolling.
- Ticket ordered-parts visibility now highlights ETA/status scanability with clearer overdue cues for orders past ETA and not yet received/cancelled.
- Part-order create/edit UI now supports practical dynamic line add/remove behavior (no fixed 3-line reveal limit) while keeping server-side blank-line ignore behavior intact.

### Fixed
- Ticket detail reserve-part search prompt now explicitly aligns with supported part matching fields (name/SKU/barcode/supplier SKU).

## [0.7.0] - 2026-03-13
### Added
- Pass D ticket-detail modal workflow: read-only top summary with modal dialogs for ticket meta updates, note capture, and diagnostics entry.
- Inventory product record expansion with dedicated part detail page, category management pages, multi-supplier linkage support, and richer parts filtering (category/supplier/stock state).
- FIFO costing foundation via stock receipt layers (`stock_layers`) and oldest-layer consumption hooks in inventory movement service.
- Quote workflow enhancements for dynamic line add/remove and part-price autofill endpoint (`/quotes/part-price/<id>`).

### Changed
- Quotes now display commercial totals with default 7% IGIC (subtotal, IGIC, grand total) and expose IGIC policy in quote builder UX.
- Receiving workflow can now maintain/update part cost and sale prices at receive time.
- Parts list and stock overview now surface clickable part records with expanded pricing/lead-time/supplier visibility.

## [0.7.1] - 2026-03-13
### Added
- Bench board reworked into a tabbed workshop view (Unassigned, Assigned, Awaiting Diagnostics, Awaiting Parts, In Repair, Ready for Collection, Overdue, Aging) with lightweight in-page tab switching.
- Supplier detail/edit flow with clickable supplier records from supplier and inventory screens.
- Part edit page for operational product maintenance (pricing, lead time, suppliers, categories, metadata).

### Changed
- Ticket detail actions now include modal entry points for Create Quote and Reserve Part, with clearer ordered/reserved part visibility and restored note type color differentiation.
- My Queue now highlights waiting-on-parts, overdue-parts, and overdue-ticket buckets for technician actionability.
- Intake conversion now accepts both promised completion and explicit SLA target inputs, keeping customer-facing ETA and internal SLA distinct.
- Dashboard attention list now focuses on exception tickets (overdue SLA and overdue part ETA blockers).
- Quote builder adds searchable part lookup per line while preserving sale-price autofill and manual override behavior.
- Parts list adds lead-time presence/range filtering and supplier links to supplier detail pages.

## [0.8.0] - 2026-03-13
### Added
- Pass F bench board operational controls: technician/branch/date/sort filters and waiting-parts/overdue toggles.
- Ticket operations list filters for status, branch, technician, date ranges, and due-date-oriented sorting.
- Public customer update flow: ticket-side “Send Update” action creates customer-facing updates rendered in public status view.
- Public portal contact update form on status page for contact person/phone/email and customer remarks.
- Quote payment-choice foundation during public approval (pay now online vs pay in store) with Stripe session service scaffold and persisted payment metadata.
- Persistent public portal settings foundation via `app_settings` table and editable portal settings page.

### Changed
- Quote builder line persistence/autofill hardened: part selection updates unit price from sale price unless manually overridden; blank/invalid lines ignored safely.
- Quote detail and public quote approval pages now render professional line-item summaries with IGIC subtotal/tax/total context.
- Reports now show human-friendly status labels, branch names, richer awaiting-arrival context, and real quote approval/turnaround metrics.
- Ticket detail right-side operational context now groups quotes + reserved parts and keeps technician/workflow controls compact.

## [0.8.1] - 2026-03-13
### Added
- Pass F.1 technician queue improvements: waiting-on-parts now captures tickets with open linked orders and My Queue surfaces earliest part ETA with overdue ETA cues.
- Ticket detail Send Update flow now supports optional email intent logging through a new communication service hook while preserving customer-update note visibility.
- Intake/ticket multi-device fast path links (create another ticket for same customer) from intake conversion and ticket detail contexts.

### Changed
- Ticket detail modal UX now includes explicit field labels/help text for Edit Ticket Details, Add Note, Add Diagnostics, Create Quote, Reserve Part, and Send Update dialogs.
- Part create/edit forms now use clear labels and sectioned guidance for identity, suppliers, categories, pricing, lead time, stock behavior, and notes.
- Quote builder line rows were cleaned up with clearer field labels and repaired dynamic line wiring so part-price autofill works reliably on newly-added lines.

### Fixed
- Bench board “waiting on parts” filtering now includes tickets blocked by non-received/non-cancelled linked part orders, not only explicit awaiting_parts status.
- Quote dynamic add/remove rows now reset JS wiring correctly, fixing second+ row sale-price autofill behavior.

## [0.8.2] - 2026-03-13
### Changed
- Pass F.2 ticket/quote UI cleanup only: ticket detail now keeps technician/workflow controls solely in the right operations panel and promotes quote summaries into the main content area.
- Ticket quote cards now show richer summary context (status, subtotal, IGIC, total, expiry, note snippet, and latest approval/payment metadata) with a clear “View details” path to full quote detail.
- Add Diagnostics modal now uses a wider layout (`max-w-4xl`) and a responsive two-column grid for better field sizing and alignment.

### Fixed
- Create Quote page now renders a single Terms Snapshot field (duplicate removed).
