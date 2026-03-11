# IRONCore Parts and Inventory

## 1. Parts Model
- Master part with SKU, barcode, names, supplier SKU, compatibility, pricing, and optional serial tracking.
- Branch-independent part definition with branch-level stock levels.

## 2. Stock Model
- Location-based stock ledger (on-hand, reserved, available).
- All changes represented as stock movements (inbound, outbound, transfer, adjustment, reservation, release, install).

## 3. Stock Locations
- Main stock
- Front desk
- Workshop bench
- Back room
- Ordered for client
- Transit
- Branch-specific bins/shelves

## 4. Reservations
- Reservation tied to ticket + part + quantity.
- Configurable strategy:
  - reduce available on reserve (default), or
  - reserve as soft hold until install.
- Release reservation on cancellation or substitution.

## 5. Ordered Parts Tracking
- Ticket-linked part order lines with supplier, ETA, shipping ref, and status events.
- Support partial arrivals and split supplier deliveries.
- Distinguish `arrived` vs `installed` states for true operational visibility.

## 6. Supplier Links
- Preferred supplier mapping per part.
- Supplier lead-time used to project ETA and overdue alerts.
- Performance metrics basis: delay rates, fulfillment speed, partial fill frequency.

## 7. Alerting & Reporting Rules
- Low stock threshold alerts by branch/location.
- Overdue ordered parts dashboard panel.
- Uninstalled arrived parts report.
