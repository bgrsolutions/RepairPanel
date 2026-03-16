# Phase 10: Repair Execution, Parts Usage & Technician Actions

## Parts Usage On Tickets

### Consuming Reserved Parts

Reserved parts can be installed (consumed) directly from the ticket detail page:

1. Reserve a part using the existing "Reserve Part" modal
2. Click **Install** on the reserved part in the sidebar
3. The system:
   - Marks the reservation as `consumed`
   - Creates an `install` stock movement (deducts on-hand qty)
   - Releases the reserved qty from StockLevel
   - Creates an internal audit note ("Part installed: ...")

### Endpoints

- **`POST /tickets/<id>/consume-reservation/<reservation_id>`** — Consume a reserved part. Validates the reservation belongs to the ticket and is in `reserved` status.

### Inventory Integration

The `consume_reservation()` service function in `inventory_service.py` handles the atomic operation:
- Validates quantity
- Sets reservation status to `consumed`
- Releases reserved_qty from StockLevel
- Calls `apply_stock_movement()` with `movement_type="install"` to deduct on-hand stock and create FIFO layer consumption

## Technician Quick Actions

The ticket detail page provides one-click workflow shortcuts in the **Quick Actions** panel:

| Action | Target Status | Available When |
|--------|--------------|----------------|
| **Assign to me** | (assigns current user) | Ticket not assigned to current user |
| **Diagnosis complete** | `awaiting_quote_approval` | Status is `awaiting_diagnostics` |
| **Waiting for parts** | `awaiting_parts` | Status is `awaiting_diagnostics`, `awaiting_quote_approval`, or `in_repair` |
| **Start repair** | `in_repair` | Status is `assigned`, `awaiting_diagnostics`, `awaiting_quote_approval`, or `awaiting_parts` |
| **Repair complete** | `testing_qa` | Status is `in_repair` |
| **Ready for collection** | `ready_for_collection` | Status is `testing_qa` |

### Endpoints

- **`POST /tickets/<id>/assign-to-me`** — Assigns the ticket to the current logged-in user
- **`POST /tickets/<id>/quick-status`** — Accepts `action` form parameter (see table above). Validates the transition using the workflow service's `is_valid_transition()`.

All quick actions create an internal audit note recording the change.

## Internal Bench Notes

### Quick Bench Note

An inline form on the ticket detail page allows technicians to add internal notes without opening the full notes modal:

- Simple text input + "Add Note" button
- Creates an `internal` note type
- Appears immediately in the notes timeline

### Endpoint

- **`POST /tickets/<id>/quick-note`** — Accepts `content` form parameter. Rejects empty content.

## Checklist Improvements

### AJAX Item Toggle

Individual checklist items can be toggled without submitting the full form:

- **`POST /checklists/item/<id>/toggle`** — Accepts JSON `{"is_checked": true/false}`
- Returns `{"ok": true, "is_checked": bool, "checked_count": int, "total_count": int, "all_checked": bool}`
- Updates the progress display and complete button visibility in real-time
- Rejects toggles on completed checklists

### Workflow

1. Technician clicks a checklist checkbox
2. JavaScript sends AJAX request to toggle endpoint
3. Server updates the item and returns updated progress
4. UI updates the progress counter without page reload
5. When all items are checked, the "Mark Complete" button appears
