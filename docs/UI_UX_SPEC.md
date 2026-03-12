# IRONCore UI/UX Specification

## 1. Design Principles
- Premium, modern SaaS look.
- Dark theme default; light theme optional.
- Fast interaction density for reception and technicians.
- Clear status communication with semantic colors and badges.

## 2. Layout System
- Persistent left sidebar navigation.
- Top context bar: branch switcher, global search, quick actions, profile.
- Main content in card-grid + table hybrids with responsive breakpoints.
- Sticky action bars on forms and ticket workflows.

## 3. Dashboard Design
- KPI tiles with trend indicators.
- Queue widgets by status and technician workload.
- Alerts panel (overdue tickets, delayed parts, pending approvals).
- Branch filter and saved dashboard presets.

## 4. Table Patterns
- Server-side pagination, sorting, column visibility toggles.
- Saved filter views by role.
- Bulk actions with permission checks.
- Badge-driven statuses and SLA highlighting.

## 5. Ticket View Design
- Split-pane layout:
  - left: summary/status/actions.
  - center: timeline and workflow tabs.
  - right: customer/device/parts/quote snapshot.
- Tabs: Intake, Diagnosis, Quotes, Parts, QA, Attachments, Audit.
- Quick scan target for barcode/QR open action.

## 6. Mobile/Tablet Behaviour
- Responsive tables collapse to cards.
- Sticky footer quick actions on mobile.
- Technician queue optimized for tablet one-hand operation.

## 7. Kiosk Design
- Full-screen, distraction-free mode.
- Large touch targets and step wizard flow.
- Auto-reset timeout and privacy screen after submission.
- Branch-brandable theme block (logo/colors/welcome text).

## 8. Theme Rules
- Tailwind tokenized color system with semantic aliases.
- High contrast for status and warning states.
- Motion: subtle transitions only; reduced-motion preference respected.
- Typography: clean sans-serif with clear hierarchy for intake/legal text.
