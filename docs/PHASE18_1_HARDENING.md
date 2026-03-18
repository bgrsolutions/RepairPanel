# Phase 18.1 — Device Intelligence Hardening, Secure Access Fixes, UI Completion

## Overview

Phase 18.1 is a focused hardening and completion patch for Phase 18. It addresses:
- Insecure XOR-based unlock value storage → proper authenticated encryption
- Backend-only IMEI lookup, pre-checks, and service catalog → fully wired staff UI
- Missing device detail fields in the intake form
- Missing quote-side service selection

## 1. Secure Access Storage Hardening

### Previous Implementation (Phase 18)
XOR+base64 obfuscation derived from `SECRET_KEY`. Trivially reversible.

### New Implementation (Phase 18.1)
Authenticated encryption using Python stdlib (`hmac`, `hashlib`, `os`):

| Component | Detail |
|-----------|--------|
| Key derivation | PBKDF2-HMAC-SHA256, 100,000 iterations, fixed salt |
| Encryption | CTR-mode stream cipher with HMAC-SHA256 as PRF |
| Authentication | HMAC-SHA256 tag over (version + nonce + ciphertext) |
| Nonce | 16 bytes, `os.urandom()` |
| Wire format | `v1 (1B) | nonce (16B) | ciphertext (NB) | HMAC tag (32B)` → base64url |

### Backward Compatibility
- Decryption attempts v1 format first (checks version byte + HMAC)
- Falls back to legacy XOR+base64 for existing stored values
- **No data migration required** — old values decrypt transparently
- New writes always use v1 authenticated format

### Configuration
```bash
# Optional: dedicated key for unlock encryption (defaults to SECRET_KEY)
DEVICE_UNLOCK_KEY=your-dedicated-key-here
```

### Why Not `cryptography` Library?
The `cryptography` package is installed but its native backend (`_cffi_backend`) fails to load in this environment. The stdlib-based solution provides equivalent security guarantees for the unlock data use case.

## 2. IMEI Lookup UI

### Staff Intake Form
- IMEI field has an inline **Lookup** button (visible only with `can_lookup_imei` permission)
- Clicking triggers `POST /intake/imei-lookup` via AJAX
- On success: auto-populates brand, model, serial, storage, color, carrier lock, FMI status
- On failure: shows error message, staff can enter details manually
- Phone/tablet detail fields auto-show when IMEI lookup returns data

### Fast Check-In / Tickets
- Same IMEI lookup available at `POST /tickets/imei-lookup`
- Both endpoints require authentication and return graceful errors

### Behavior When Disabled
- If `IMEICHECK_API_KEY` is empty, the lookup button still appears but returns a "not configured" message
- All form fields remain fully manual-entry capable

## 3. Device-Specific Pre-Check UI

### Dynamic Pre-Checks
- When the device category dropdown changes, the pre-check section auto-loads category-specific checks via `GET /intake/prechecks/<category>`
- Checks render as styled checkboxes matching the existing UI design
- Results are serialized to JSON on form submit

### Categories and Check Counts
| Category | Checks |
|----------|--------|
| Phones | 10 |
| Tablets | 7 |
| Laptops | 11 |
| Desktops | 6 |
| Game Consoles | 6 |
| Smartwatches | 5 |
| Other | 3 |

### Legacy Compatibility
- Static legacy checkboxes (powers_on, screen, charging, buttons, water_damage) are preserved as hidden fields
- Backend `parse_precheck_results()` handles both dynamic and legacy formats

## 4. Quote Service Catalog Selection

### UI Location
- New "Quick Fill from Service Catalog" panel in the quote builder, above repair options
- Service dropdown populated from active `RepairService` records

### Workflow
1. Staff selects a service from the dropdown
2. Preview shows service name, labour price, and estimated minutes
3. Clicking "Apply Service" fetches `/tickets/service-detail-json/<id>`
4. First repair option gets auto-populated with:
   - Labour line (service name + code, labour price)
   - Part lines (linked parts from `service_part_links` with sale prices)
5. Staff can edit/override all populated values
6. Existing manual quote workflow remains fully functional

## 5. Booking Carry-Through

Phase 18 device details carry through from booking → ticket automatically because:
- Both reference the same `Device` record (shared ID)
- All Phase 18 fields (storage, color, carrier_lock, etc.) live on the Device model
- Booking conversion summary now shows richer device details

## 6. Permissions

| Permission | Roles | UI Effect |
|------------|-------|-----------|
| `can_view_secure_access` | Management, Workshop | Unlock fields visible in intake form |
| `can_lookup_imei` | Management, Front Desk, Workshop | IMEI Lookup button visible |
| `can_manage_service_catalog` | Management | Service catalog admin |
| `can_create_quote` | Management, Front Desk | Quote builder with service selector |

## 7. Files Changed

### Services
- `app/services/device_unlock_service.py` — Complete rewrite: authenticated encryption with legacy fallback

### Configuration
- `app/config.py` — Added `DEVICE_UNLOCK_KEY`

### Templates
- `app/templates/intake/new.html` — IMEI lookup button, dynamic pre-checks, device detail fields (category-dependent), secure access section
- `app/templates/quotes/new.html` — Service catalog quick-fill selector
- `app/templates/bookings/convert.html` — Richer device details in booking summary

### Routes
- `app/blueprints/quotes/routes.py` — Added `_get_services_data()`, passes services to quote template

### Translations
- `app/translations/es/LC_MESSAGES/messages.po` — 35+ new strings
- `app/translations/es/LC_MESSAGES/messages.mo` — Recompiled

### Tests
- `tests/test_phase18_1_hardening.py` — 35 new tests

### Documentation
- `docs/PHASE18_1_HARDENING.md` — This file
- `docs/CHANGELOG.md` — Updated
