# Phase 17.1 — Booking Intake UX and Navigation Corrections

Post-implementation patch applied after live UI testing of Phase 16/17.

## Overview

This patch addresses usability issues discovered during operational testing of the booking intake workflow. It does not introduce new architectural features but corrects UX friction points in customer selection, device handling, navigation clarity, and booking conversion flow.

## Changes

### 1. Customer Search & Selection on Booking Form

The booking form (`/bookings/new` and `/bookings/<id>/edit`) now includes:

- **Live customer search** — staff can type a name, phone number, or email to find existing customers. Results appear in a dropdown populated via `GET /bookings/customer-search?q=...` (reuses the same pattern as intake and ticket customer search).
- **Selected customer display** — once a customer is selected, a green card shows the selected customer's name and contact info with a "Change" button to re-search.
- **Inline customer creation** — if the customer doesn't exist, staff can click "Create new customer" to expand a creation form supporting full name, phone, and email. The `POST /bookings/customer-create` endpoint performs **duplicate detection** by email (first) and then phone before creating a new record.

### 2. Device Handling

The booking form device section now provides:

- **Dynamic device dropdown** — when a customer is selected, the dropdown is populated with their registered devices via `GET /bookings/customer/<id>/devices`.
- **Free-text device description** — a new `device_description` field allows staff to enter a quick description (e.g., "iPhone 15 Pro, cracked screen") when the device is not yet registered. This avoids forcing structured device creation at the booking stage.

The device description is stored on the booking and displayed on the booking detail page. Formal device record creation happens later during ticket conversion/intake.

### 3. Navigation Menu

The top navigation bar primary actions have been updated:

| Before | After |
|--------|-------|
| "Intakes" button → intake list | **"New Booking"** → `/bookings/new` (visible to `can_manage_bookings`) |
| "Fast Check-In" → ticket create | **"Create New Ticket"** → `/intake/new` (visible to `can_create_ticket`) |
| — | **"Fast Check-In"** → `/tickets/create` (preserved, visible to `can_create_ticket`) |

Both desktop and mobile navigation menus are updated.

### 4. Conversion Eligibility

Booking conversion to ticket is now allowed from **confirmed** status in addition to **arrived** and **in_progress**:

- `confirmed → converted` — added to `Booking.VALID_TRANSITIONS`
- The "Create Ticket from Booking" button on the detail page now appears for `confirmed`, `arrived`, and `in_progress` statuses
- Terminal statuses (`cancelled`, `no_show`, `converted`) remain blocked

### 5. Post-Conversion Redirect

After successfully converting a booking to a ticket, the user is now redirected to the **ticket detail page** (previously redirected to the booking detail page). This provides a seamless continuation into the repair workflow — diagnostics, pre-check, checklists, quotes, etc.

### 6. Database Changes

Migration `b2c3d4e5f6a7_phase17_1_booking_ux.py` adds two columns to the `bookings` table:

- `customer_email` (String 255, nullable) — stores customer email at booking stage
- `device_description` (String 500, nullable) — free-text device description for booking stage

### 7. New API Endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/bookings/customer-search?q=...` | login_required | Search customers by name/phone/email |
| POST | `/bookings/customer-create` | can_manage_bookings | Create customer with duplicate detection |
| GET | `/bookings/customer/<id>/devices` | login_required | List customer's devices |

### 8. Permissions

All existing booking permissions are preserved. No new permissions were added. The customer search endpoint requires login; the customer create endpoint requires `can_manage_bookings` permission.
