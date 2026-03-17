# Phase 17.2 — Intake Entry Flow and Navigation Stabilisation

Post-implementation patch applied after live UI testing of Phase 17/17.1.

## Overview

This patch resolves operational issues discovered during live testing of the two primary ticket creation paths and the navigation menu. It does not introduce new features but ensures all existing entry flows work end-to-end.

## Root Causes Identified

### 1. Intake Form POST Crash (`/intake/new`)

**Symptom**: Submitting the "Create New Ticket" intake form caused a 500 error.

**Cause**: `current_app.config["DEFAULT_INTAKE_DISCLAIMER_TEXT"]` at line 184 of `app/blueprints/intake/routes.py` raised `KeyError` when the config key was not present (e.g., in environments that didn't load `app/config.py`'s defaults).

**Fix**: Changed to `current_app.config.get("DEFAULT_INTAKE_DISCLAIMER_TEXT", "I confirm the provided details are accurate and accept the intake terms.")`. Same pattern applied to `UPLOAD_ROOT` config access.

### 2. Fast Check-In Flow (`/tickets/new`)

**Symptom**: Reported as non-functional.

**Finding**: After audit, the fast check-in POST was actually working correctly. The GET form loads, AJAX customer/device search endpoints respond, and POST creates tickets with proper status logic, intake notes, and portal tokens. Likely the reported issue was related to the intake form crash (users may have confused the two paths).

### 3. Navigation Menu

**Symptom**: Menu links may not point to working routes.

**Finding**: Navigation was correctly updated in Phase 17.1:
- "New Booking" → `/bookings/new` (gated by `can_manage_bookings`)
- "Create New Ticket" → `/intake/new` (gated by `can_create_ticket`)
- "Fast Check-In" → `/tickets/new` (gated by `can_create_ticket`)

Both desktop and mobile menus were already correct.

## Entry Flow Architecture

### Path 1: Full Intake ("Create New Ticket")

```
/intake/new → IntakeSubmission → /intake/<id>/convert → Ticket
```

- Multi-step form with branch, customer, device, fault, pre-checks, diagnosis, disclaimer, signature, photo
- Creates `IntakeSubmission` record with status `pre_check_in`
- Creates `IntakeDisclaimerAcceptance` and optional `IntakeSignature` records
- Creates `PortalToken` for customer status lookup
- Conversion to ticket is a separate step from the intake detail page

### Path 2: Fast Check-In

```
/tickets/new → Ticket (direct)
```

- Streamlined form with branch, customer (AJAX search), device (AJAX search/create), service, condition, accessories
- Creates `Ticket` directly with status `unassigned` or `assigned`
- Creates intake notes as `TicketNote` record
- Creates `PortalToken` for customer status lookup
- Service availability and part stock displayed inline

## Files Changed

| File | Change |
|------|--------|
| `app/blueprints/intake/routes.py` | Safe config access for `DEFAULT_INTAKE_DISCLAIMER_TEXT` and `UPLOAD_ROOT` |
| `docs/CHANGELOG.md` | Added Phase 17.2 entry |
| `docs/INTAKE_CHECKIN_STABILISATION.md` | This document |
| `tests/test_phase17_2_intake_checkin.py` | 38 new tests |

## Test Coverage

38 tests covering:
- Intake form GET/POST (8 tests)
- Config fallback resilience (1 test)
- Intake detail and receipt pages (2 tests)
- Intake conversion to ticket (1 test)
- Fast check-in GET/POST (8 tests)
- AJAX endpoints — tickets blueprint (6 tests)
- AJAX endpoints — intake blueprint (2 tests)
- Navigation link verification (3 tests)
- Permission enforcement (2 tests)
- Intake list (2 tests)
- End-to-end flows (2 tests)
