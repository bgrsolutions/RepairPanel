# Phase 18.5 — Intake/Device Enrichment, Structured Pre-Checks, and Archiving

## Overview

Phase 18.5 enriches the device, intake, and ticket workflows with richer data at every stage:
- The `Device` model gains 13 new fields for Apple/Samsung-specific attributes returned by deeper IMEI/serial lookups.
- Intake submissions gain structured JSON pre-check storage (`precheck_data`) and a full archive/unarchive workflow.
- The `RepairChecklist` table gains a direct link to the intake submission, allowing pre-checks captured at intake to carry through as a completed pre-repair checklist on ticket conversion.
- A dedicated Device Detail page (`/customers/devices/<id>`) gives staff a single page with all structured device data, lookup history, linked tickets, and linked intakes.
- Ticket detail and intake detail both gain rich sidebar panels showing device info (including Phase 18.5 fields) plus SLA/timing visibility.
- The public portal displays richer device info on the status page, and the public check-in form supports customer search/prefill by phone or email.
- Both public check-in routes (`/public/check-in` and `/public/kiosk/check-in`) are consolidated into a shared `_render_public_checkin()` function distinguished by a `kiosk_mode` flag.

---

## Database Changes

**Migration**: `c4d5e6f7a8b9_phase18_5_intake_device_enrichment.py`
Revises: `a1b2c3d4e5f7` (Phase 18 Device Intelligence)

### `devices` table — 13 new columns

| Column | Type | Description |
|--------|------|-------------|
| `imei2` | String(60) | Secondary IMEI (dual-SIM devices) |
| `eid` | String(60) | eSIM Identifier |
| `model_number` | String(120) | Part/model number (e.g., Apple model number) |
| `purchase_country` | String(120) | Country of first sale/activation |
| `sold_by` | String(200) | Original seller/retailer name |
| `production_date` | String(60) | Manufacturing date |
| `warranty_status` | String(200) | Device warranty status from provider |
| `activation_status` | String(120) | Activation lock / registered status |
| `applecare_eligible` | String(120) | AppleCare+ eligibility |
| `technical_support` | String(120) | Technical support coverage status |
| `blacklist_status` | String(60) | GSMA/carrier blacklist status (Clean/Blacklisted) |
| `buyer_code` | String(120) | Sales buyer code from provider |
| `last_lookup_at` | DateTime | Timestamp of most recent IMEI/serial lookup |

All columns are nullable. All Phase 18 device fields (`storage`, `color`, `carrier_lock`, `fmi_status`, etc.) remain.

### `intake_submissions` table — 3 new columns

| Column | Type | Description |
|--------|------|-------------|
| `precheck_data` | Text (JSON) | Structured pre-check results as a JSON array |
| `archived_at` | DateTime | Set when intake is archived; null = active |
| `archived_by_user_id` | UUID FK → users | Staff member who archived |

`IntakeSubmission.is_archived` is a computed property: `return self.archived_at is not None`.

### `repair_checklists` table — 1 new column + index

| Column | Type | Description |
|--------|------|-------------|
| `intake_submission_id` | UUID FK → intake_submissions | Links checklist to the originating intake |

Index: `ix_repair_checklists_intake_submission_id`

---

## IMEI Lookup Enhancements

### Richer Data Fields (Phase 18.5)

The `IMEILookupResult` dataclass now carries 10 additional fields mapped from provider-specific API responses:

| Field | Source Keys (parsed from response) |
|-------|------------------------------------|
| `imei2` | `imei2`, `secondImei`, `IMEI2` |
| `eid` | `eid`, `EID`, `esimId` |
| `activation_status` | `activationStatus`, `activation`, `activationState` |
| `estimated_purchase_date` | `estimatedPurchaseDate`, `purchaseDate`, `soldDate`, `warrantyStartDate` |
| `applecare_eligible` | `appleCareEligible`, `appleCareStatus`, `acEligible`, `appleCare` |
| `technical_support` | `technicalSupportStatus`, `telephoneSupport`, `techSupport` |
| `sold_by` | `soldBy`, `sellerName`, `buyerName`, `salesBuyerName` |
| `production_date` | `productionDate`, `manufactureDate`, `mfgDate` |
| `buyer_code` | `buyerCode`, `salesBuyerCode`, `buyerName` |
| `sim_lock_country` | `simLockCountry`, `lockCountry`, `carrierCountry` |

### Serial Number Lookup

`lookup_serial(serial, service_id, brand_hint)` is a new function in `imei_lookup_service.py`. Serial-based lookup uses the same IMEIcheck.net API endpoint (`POST /v1/checks`) with the serial number as `deviceId`. Minimum serial length: 8 characters.

A new route `POST /intake/serial-lookup` provides AJAX serial lookup from the staff intake form. The device detail page also supports triggering serial lookups via `POST /customers/devices/<id>/lookup`, which auto-detects whether the identifier is an IMEI (≥14 digits) or a serial number.

### `cache_lookup_result` Improvements

`cache_lookup_result(device, result)` now persists all Phase 18.5 fields to the device record in addition to storing the raw JSON in `imei_lookup_data` and updating `last_lookup_at`:

```
imei2, model_number, purchase_country, sold_by, production_date,
warranty_status, activation_status, applecare_eligible,
technical_support, blacklist_status, buyer_code, eid
```

Fields are only written if the lookup result returns a non-empty value.

---

## Intake Archiving

### Workflow

- **Archive**: `POST /intake/<id>/archive` — sets `archived_at = now()` and `archived_by_user_id = current_user.id`.
- **Unarchive**: `POST /intake/<id>/unarchive` — clears both fields back to `None`.
- Both actions are logged via `log_action()` with events `intake.archive` and `intake.unarchive`.
- The intake list (`GET /intake/`) defaults to showing only active (non-archived) intakes. Pass `?archived=1` to view the archived list.

### Permission

`can_archive_intake()` — defined in `permission_service.py`:
- Allowed roles: **Management**, **Front Desk**
- Workshop and lower roles cannot archive intakes.
- The permission is exposed as `perms.can_archive_intake` in templates.

The archive/unarchive routes currently use `can_manage_bookings()` as a proxy (both resolve to Management + Front Desk), and `can_archive_intake` is the dedicated permission function for future explicit use.

---

## Structured Pre-Checks

### `precheck_data` JSON Column

At intake submission, all pre-check results are serialized to JSON and stored in `IntakeSubmission.precheck_data`. The JSON format is a list of objects:

```json
[
  {"check_key": "check_powers_on", "label": "Powers on", "passed": true},
  {"check_key": "check_screen_condition", "label": "Screen OK", "passed": false},
  {"check_key": "powers_on", "label": "Powers on", "passed": true}
]
```

Both the legacy static checks (powers on, screen, charging, buttons, water damage) and dynamic device-type-specific checks from Phase 18.1 are combined into this single array before storage.

### Structured Storage vs Note Text

Pre-check results are stored in two places simultaneously:
1. **`precheck_data` (JSON)**: Machine-readable structured array for programmatic access (e.g., populating checklists, displaying in the intake detail sidebar).
2. **`intake_notes` (text)**: Human-readable summary embedded in the notes field for backward compatibility and quick visual review.

### Intake-to-Ticket Conversion Carry-Through

When an intake is converted to a ticket, if `precheck_data` is present, the conversion route automatically creates a `RepairChecklist` of type `pre_repair` linked to both the ticket and the intake submission (`intake_submission_id`). Each pre-check item becomes a `ChecklistItem` with `is_checked` set from `passed`. Errors during checklist creation do not block conversion.

---

## Device Detail Page

**Route**: `GET /customers/devices/<uuid:device_id>`
**Template**: `app/templates/customers/device_detail.html`
**Permission**: `@login_required`

The device detail page centralizes all structured data for a single device:

- Full Phase 18 and Phase 18.5 fields displayed in organized sections
- Raw IMEI lookup data (`imei_lookup_data`) parsed and shown if present (`last_lookup_at` timestamp displayed)
- Linked tickets list (most recent first)
- Linked intakes list (most recent first)
- "Trigger Lookup" action: `POST /customers/devices/<id>/lookup` refreshes data from IMEI/serial lookup API and persists results (requires `can_lookup_imei`)

### Customer → Device Navigation

Customer detail page (`/customers/<id>`) links each device in the device list to its device detail page. Intake detail and ticket detail sidebars both include a "Full details →" link to the device detail page.

---

## Rich Device Info on Ticket Detail

The ticket detail right sidebar (`app/templates/tickets/detail.html`) has two new panels added in Phase 18.5:

### Device Information Panel

Displays all populated device fields with color-coded security indicators:
- `carrier_lock`: amber for Locked, emerald for Unlocked
- `fmi_status`: amber for ON, emerald for OFF
- `blacklist_status`: rose for Blacklisted, emerald for Clean
- Phase 18.5 fields shown: `imei2`, `model_number`, `blacklist_status`, `warranty_status`, `applecare_eligible`, `purchase_country`, `activation_status`
- "Full details →" link to `/customers/devices/<id>`

### Timing & SLA Panel

Displays ticket timing information with overdue state:
- Created date/time
- Age in days
- SLA target (highlighted in rose if overdue)
- Promised completion (emerald)
- OVERDUE badge when `is_overdue` is true; panel border turns rose

---

## Rich Device Info on Intake Detail

The intake detail page (`app/templates/intake/detail.html`) has a sidebar with:

### Device Sidebar Panel

Shows device brand/model, category, serial, IMEI, and all available Phase 18/18.5 fields (same color-coded display as ticket detail). Includes a "Full details →" link to the device detail page.

Context: `device` is loaded explicitly in `intake_detail()` from `db.session.get(Device, intake.device_id)` and passed to the template as `device`.

### Structured Pre-Check Display

`precheck_items` is parsed from `intake.precheck_data` JSON in the route and passed to the template. The template renders each item with a pass/fail indicator. The section only renders if `precheck_items` is non-empty.

### Archived State

Archived intakes display an "Archived" badge in the header. Archive and unarchive action buttons are shown conditionally based on `intake.is_archived` and the conversion state.

---

## Public Portal Enhancements

### Device Info on Status Page

`_build_lookup_result()` in `public_portal/routes.py` now returns a `device_detail` dict when a device is linked to the ticket:

```python
"device_detail": {
    "storage": ticket.device.storage or "",
    "color": ticket.device.color or "",
    "serial_short": (ticket.device.serial_number[-4:] ...),
}
```

The public status page (`app/templates/public/status.html`) renders these as pill badges beneath the device name when values are present (storage, color, last 4 of serial).

### Customer Search / Prefill on Check-In

**Route**: `GET /public/check-in/customer-search`
No authentication required. Accepts a query string (`q`) of at least 3 characters.

Uses `_safe_exact_customer_match()` — an exact-match-only lookup against `email` or `phone`. On match, returns:
```json
{"ok": true, "customer": {"full_name": "...", "phone": "...", "email": "..."}}
```

The public check-in form (`app/templates/public/check_in.html`) includes a prefill search field. The customer types their phone or email, clicks "Find", and if an exact match is found, their name/phone/email are filled into the form fields. The prefill is privacy-safe: no customer list is exposed, only exact-match data from the caller's own record.

---

## Public Check-In vs Kiosk Audit

Both public check-in entry points are handled by a single shared function:

| Route | Function | `kiosk_mode` flag |
|-------|----------|-------------------|
| `GET/POST /public/check-in` | `public_checkin()` → `_render_public_checkin(False)` | `False` |
| `GET/POST /public/kiosk/check-in` | `kiosk_checkin()` → `_render_public_checkin(True)` | `True` |

`_render_public_checkin(kiosk_mode: bool)` contains all form logic. The `kiosk_mode` flag controls:
- `intake.source`: `"public"` vs `"kiosk"` — stored on the intake record for reporting
- Template rendering: `kiosk_mode` is passed to `check_in.html`, which can suppress navigation or adjust layout for unattended kiosk use
- `portal_token.token_type`: both routes create a `"public_intake_confirmation"` token

**Distinct purposes**:
- `/public/check-in` is for customers using their own device (phone/computer)
- `/public/kiosk/check-in` is for an unattended shop kiosk — the `kiosk` flag is passed to the thank-you page so it can suppress "go back" navigation and display a clean reset screen

Both routes use `_safe_exact_customer_match()` for customer deduplication and create the same intake/device/portal-token structure.

---

## Configuration

Two new config keys added in Phase 18.5:

### `IMEICHECK_SERIAL_LOOKUP_BRANDS`

```bash
IMEICHECK_SERIAL_LOOKUP_BRANDS=["apple", "samsung"]
```

JSON list of brand names (lowercase) for which serial number lookup should be offered in addition to IMEI lookup. Defaults to `["apple", "samsung"]`. Used by the UI to show/hide the serial lookup button based on the selected brand.

### `IMEICHECK_SECONDARY_SERVICES`

```bash
IMEICHECK_SECONDARY_SERVICES={"fmi": 18, "carrier": 17, "warranty": 25, "blacklist": 16}
```

JSON map of check type to service ID for secondary IMEI checks. Introduced in Phase 18.4 and now formally documented. Empty by default (secondary checks disabled). Supported check types: `fmi`, `carrier`, `warranty`, `blacklist`.

Both config values are parsed at startup in `app/config.py` with safe fallbacks if the env var is absent or malformed.

---

## Permissions

| Permission | Function | Roles | Purpose |
|------------|----------|-------|---------|
| `can_archive_intake` | `can_archive_intake()` | Management, Front Desk | Archive and unarchive intake submissions |

This is a new permission added in Phase 18.5. It is registered in `permission_service.py` and exposed via the `_PermissionProxy` as `perms.can_archive_intake` in templates.

Existing permissions unchanged:
- `can_lookup_imei` — Management, Front Desk, Workshop (covers both IMEI and serial lookup)
- `can_view_secure_access` — Management, Workshop (unlock data)
