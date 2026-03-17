# Phase 16 — Booking Operations, Intake Queue & Service Scheduling Foundations

## Overview

Phase 16 expands the existing booking/services foundation (Phase 6) into a proper
operational workflow layer for front-desk and workshop staff. Bookings now have a
structured lifecycle, an intake queue view, a booking detail page with status
actions, and an assisted conversion flow to create repair tickets from bookings.

## Booking Lifecycle

### Status Definitions

| Status      | Description                                                  |
|-------------|--------------------------------------------------------------|
| `new`       | Default status for newly created bookings                    |
| `confirmed` | Booking has been confirmed with the customer                 |
| `arrived`   | Customer has arrived at the repair shop                      |
| `no_show`   | Customer did not arrive for the appointment                  |
| `converted` | Booking has been converted into a repair ticket              |
| `cancelled` | Booking was cancelled                                        |

### Status Transitions

```
new → confirmed → arrived → converted
 ↓        ↓          ↓
 ↓    cancelled   cancelled
 ↓     no_show
 ↓
 arrived → converted
 cancelled
 no_show
```

- **new** → confirmed, arrived, cancelled, no_show
- **confirmed** → arrived, cancelled, no_show
- **arrived** → converted, cancelled
- **no_show**, **converted**, **cancelled** → (terminal, no further transitions)

### Active vs Terminal States

- **Active:** new, confirmed, arrived (appear in intake queue, count toward metrics)
- **Terminal:** no_show, converted, cancelled (resolved, no longer pending)

## Booking Data Model

### New Fields (Phase 16)

| Field                | Type         | Description                                  |
|----------------------|--------------|----------------------------------------------|
| `device_id`          | UUID (FK)    | Optional reference to customer's device       |
| `staff_notes`        | Text         | Internal notes visible only to staff          |
| `customer_name`      | String(200)  | Customer name snapshot (for walk-ins)          |
| `customer_phone`     | String(50)   | Customer phone snapshot                        |
| `converted_ticket_id`| UUID (FK)    | Reference to ticket created from this booking |

### Existing Fields (Phase 6)

- `location_id` — branch/location (required)
- `customer_id` — customer reference (optional)
- `repair_service_id` — expected repair service (optional)
- `linked_ticket_id` — legacy ticket link
- `start_time` / `end_time` — appointment window
- `status` — lifecycle status
- `notes` — customer-facing booking notes

## Pages & Routes

### Booking List (Day View)
- **URL:** `/bookings/`
- **Permission:** `can_view_bookings` (all staff roles)
- Day-based view with date navigation, week quick-links
- Filters: status, location
- Click any booking to view detail

### Intake Queue
- **URL:** `/bookings/?view=queue`
- **Permission:** `can_view_bookings` (all staff roles)
- Sections: Overdue (past active bookings), Today, Upcoming (next 7 days)
- Filters: status, location
- Red-highlighted overdue section for bookings past their date without resolution

### Booking Detail
- **URL:** `/bookings/<booking_id>`
- **Permission:** `can_view_bookings` (all staff roles)
- Shows: booking info, customer info, device info, notes, linked ticket
- Action sidebar with status transition buttons (confirm, arrive, no-show, cancel)
- Convert-to-ticket button for arrived bookings

### Create Booking
- **URL:** `/bookings/new`
- **Permission:** `can_manage_bookings` (Management, Front Desk)

### Edit Booking
- **URL:** `/bookings/<booking_id>/edit`
- **Permission:** `can_manage_bookings` (Management, Front Desk)

### Status Actions (POST only)
- `/bookings/<id>/confirm` — `can_manage_bookings`
- `/bookings/<id>/arrive` — `can_manage_bookings`
- `/bookings/<id>/no-show` — `can_manage_bookings`
- `/bookings/<id>/cancel` — `can_manage_bookings`

### Assisted Conversion
- **URL:** `/bookings/<booking_id>/convert`
- **Permission:** `can_convert_booking` (Management, Front Desk)
- Prefills ticket from booking data (customer, device, service, notes)
- Creates ticket, portal token, intake note
- Marks booking as converted with `converted_ticket_id` reference
- Transaction-safe: rollback on failure, no partial conversion

## Permission Model

### New Permission Functions

| Function              | Allowed Roles                                  |
|-----------------------|------------------------------------------------|
| `can_view_bookings`   | All staff roles (Super Admin through Read Only) |
| `can_manage_bookings` | Super Admin, Admin, Manager, Front Desk         |
| `can_convert_booking` | Super Admin, Admin, Manager, Front Desk         |

### Permission Enforcement

- All routes protected server-side with `@permission_required(check_fn)`
- All POST endpoints require appropriate permissions
- Template-level controls via `perms.can_manage_bookings` and `perms.can_convert_booking`

## Assisted Conversion Flow

1. Staff views arrived booking detail
2. Clicks "Create Ticket from Booking"
3. Conversion form pre-filled with:
   - Device from booking (or select from customer's devices)
   - Repair service from booking
   - Issue summary from booking notes
4. Staff reviews/adjusts and submits
5. System creates:
   - Ticket with booking's customer, device, branch
   - Intake note with issue summary, device condition, accessories, service info
   - Portal token for customer status tracking
6. Booking marked as `converted` with `converted_ticket_id` set
7. Booking detail shows linked ticket with direct link

### Guards
- Cannot convert if already converted (duplicate prevention)
- Cannot convert without a customer assigned
- Cannot convert from non-convertible status (only arrived/in_progress)
- Transaction rollback on any failure

## Internationalization

All new strings support EN/ES translation:
- Status labels (New, Confirmed, Arrived, No Show, Converted, Cancelled)
- Page headings, buttons, form labels
- Flash messages (success, warning)
- Intake queue section headings
- Action button labels

## Migration

**File:** `migrations/versions/e9f0a1b2c3d4_phase16_booking_operations.py`
**Revises:** `d8e0f2a4b6c8`

### Schema Changes
- Added `device_id` (UUID, FK→devices.id, nullable, indexed)
- Added `staff_notes` (Text, nullable)
- Added `customer_phone` (String(50), nullable)
- Added `customer_name` (String(200), nullable)
- Added `converted_ticket_id` (UUID, FK→tickets.id, nullable, indexed)
- Changed default status from 'scheduled' to 'new'

### Data Migration
- `scheduled` → `new`
- `in_progress` → `arrived`
- `completed` → `converted`

## Reporting Compatibility

- `get_booking_counts()` service function returns `today_total`, `today_arrived`, `overdue`
- Ready for future dashboard integration
- Does not break Phase 14 reporting dashboards

## Communication Compatibility

- Booking operations are logged via audit service
- Architecture does not block future booking reminder/notification hooks
- Portal token created on conversion for customer access

## Operational Notes

### For Front-Desk Staff
- Use Intake Queue view to see today's expected arrivals
- Mark customers as arrived when they walk in
- Convert arrived bookings to tickets to start the repair workflow
- Overdue section shows bookings that were missed

### For Administrators
- New permissions `can_view_bookings`, `can_manage_bookings`, `can_convert_booking`
  are automatically available based on existing role structure
- No seed/config changes needed
- Technician and Inventory roles can view but not manage bookings
- Read Only role can view the booking list
