# Phase 9: Ticket Creation, Search & Workshop Usability

## Ticket Creation Flow

The ticket creation page (`/tickets/new`) provides a guided 5-step check-in workflow:

1. **Branch & Customer** — Search customers by name, phone, or email using the AJAX autocomplete. Selecting a customer loads their registered devices.
2. **Device** — Select an existing device from the dropdown, search for devices by brand/model/serial/IMEI, or use the **Quick Add Device** form to register a new device inline.
3. **Service & Issue** — Select a repair service, view part availability and stock status, describe the issue.
4. **Condition & Accessories** — Note device condition and list accessories received.
5. **Promised Completion** — Set ETA using presets (Today, Tomorrow, 3 Days, 1 Week) or accept the service-suggested ETA.

### Quick Add Device

When a customer has no registered devices or needs a new one, click **+ New Device** to expand the inline form. Fill in:
- **Category** (phones, tablets, laptops, desktops, consoles, wearables, other)
- **Brand** (required)
- **Model** (required)
- **Serial Number** (optional)
- **IMEI** (optional)

Click **Add Device** to create it via AJAX — the new device is immediately added to the device dropdown and auto-selected.

### Device Search

Below the device dropdown, a search field allows searching across all devices by brand, model, serial number, or IMEI. When a customer is selected, results are scoped to that customer's devices. Selecting a search result sets the device dropdown.

## Search Endpoints

### Customer Search
- **`GET /tickets/customer-search?q=...`** — Returns customers matching name, phone, or email. Used by the ticket creation autocomplete.
- **`GET /customers/search?q=...`** — Returns customers with `display_name` and business status. Used by other areas.

### Device Search
- **`GET /tickets/device-search?q=...&customer_id=...`** — Returns devices matching brand, model, serial, or IMEI. Optional `customer_id` scopes results. Returns brand, model, serial_number, and customer_name.

### Part Search
- **`GET /inventory/parts/search?q=...`** — Returns active parts matching name, SKU, barcode, or supplier SKU. Returns pricing information. Used by stock movement forms and other inventory UIs.

### Customer List
The customer list page (`/customers/`) has instant client-side filtering — table rows filter as the user types in the search box without requiring a page reload.

### Parts Catalog
The parts catalog page (`/inventory/parts`) has instant client-side filtering — table rows filter as the user types, in addition to the server-side category/supplier/stock filters.

## Part Deletion

### Safe Delete Rules

Parts can be deleted via `POST /inventory/parts/<id>/delete`. The system performs dependency safety checks before deletion:

**Blocked if the part is referenced by:**
- Stock movements (historical audit trail)
- Stock reservations (reserved for tickets)
- Part order lines (ordered from suppliers)
- Quote lines (quoted to customers)
- Repair services (as default part)

When deletion is blocked, the user sees a warning explaining which records reference the part and is directed to **deactivate** the part instead.

**Allowed when:**
- The part has no references in any of the above tables.
- Performs a soft delete (sets `deleted_at` timestamp and `is_active = false`).

### Deactivation vs Deletion

- **Deactivate**: Hides the part from active use (search results, new tickets) but preserves it for historical records. Can be reactivated later.
- **Delete**: Soft-removes the part entirely. Only possible for unreferenced parts. The part no longer appears in any listing.

Both actions require Admin, Manager, or Super Admin role.
