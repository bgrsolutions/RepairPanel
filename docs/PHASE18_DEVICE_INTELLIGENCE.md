# Phase 18 — Device Intelligence, Secure Access, and Service Catalog

## Overview

Phase 18 expands the repair intake and quoting system to better match real repair-shop operations with structured device data, secure access storage, device-type workflows, optional IMEI lookup, and an enhanced service catalog.

## Secure Access / Unlock Data

Device unlock codes (PIN, password, pattern, etc.) are stored with XOR+base64 obfuscation derived from `SECRET_KEY`, not in plain text.

- **Fields**: `unlock_type`, `unlock_value_encrypted`, `unlock_notes` on the Device model
- **Display**: Values are masked in normal UI (e.g., `••••56`)
- **Permission**: `can_view_secure_access` — Management and Workshop roles only
- **Service functions**: `set_device_unlock()`, `get_device_unlock_display()`, `mask_unlock_value()`

## Archived Ticket Exclusion

Dashboard and reporting stats now filter out `internal_status = "archived"` tickets:
- Active ticket queries in `core/routes.py` (dashboard) and `reports/routes.py` (KPI dashboard) add `Ticket.internal_status != Ticket.STATUS_ARCHIVED`
- Archived tickets remain accessible via direct URL and search
- `Ticket.CLOSED_STATUSES` still includes `archived` for status classification

## Device-Type Pre-Check Workflows

### Categories
| Category | Key | Example Pre-Checks |
|----------|-----|---------------------|
| Phones | `phones` | Powers on, screen, touch, charging, cameras, biometrics |
| Tablets | `tablets` | Powers on, screen, touch, charging, cameras |
| Laptops | `laptops` | Powers on, screen, keyboard, trackpad, battery, hinges |
| Desktops | `desktops` | Powers on, display output, fans, storage, network |
| Game Consoles | `game_consoles` | Powers on, display, disc drive, controllers |
| Smartwatches | `smartwatches` | Powers on, screen, charging, heart rate |
| Other | `other` | Powers on, basic function, physical condition |

### Architecture
- `DevicePreCheckTemplate` database table stores templates with EN/ES labels
- Migration seeds default templates for all categories
- `precheck_service.py` provides `get_prechecks_for_category()` with DB-first, fallback-to-hardcoded pattern
- API endpoints: `GET /tickets/prechecks/<category>` and `GET /intake/prechecks/<category>`

## Richer Device Details

### Phone/Tablet Fields
| Field | Description |
|-------|-------------|
| `storage` | Storage capacity (128GB, 256GB, etc.) |
| `color` | Device color |
| `carrier_lock` | Network lock status (Unlocked, Carrier-locked, etc.) |
| `fmi_status` | Find My iPhone/device status (ON/OFF) |
| `cosmetic_condition` | Physical condition notes |
| `battery_health` | Battery health percentage |

### Laptop/Desktop Fields
| Field | Description |
|-------|-------------|
| `cpu` | Processor model |
| `ram` | Memory amount |
| `storage_type` | SSD/HDD type and capacity |
| `gpu` | Graphics card |
| `os_info` | Operating system info |
| `device_notes` | General notes |

All fields are nullable — manual entry is always possible regardless of device type.

## IMEIcheck.net Integration

### Configuration
```bash
IMEICHECK_ENABLED=true                    # Master switch
IMEICHECK_API_KEY=your-api-key-here       # Bearer token (empty = disabled)
IMEICHECK_API_URL=https://api.imeicheck.net  # Base URL
IMEICHECK_SERVICE_ID=12                   # Service ID for checks (see below)
IMEICHECK_TIMEOUT=10                      # Request timeout in seconds
```

### API Request Format (Phase 18.2)
The integration uses the IMEIcheck.net REST API v1:

```
POST https://api.imeicheck.net/v1/checks
Authorization: Bearer <IMEICHECK_API_KEY>
Accept: application/json
Content-Type: application/json

{"deviceId": "<IMEI>", "serviceId": <IMEICHECK_SERVICE_ID>}
```

The API returns **201 Created** on success with a check object containing device properties.

### Service ID (`IMEICHECK_SERVICE_ID`)
Each service ID corresponds to a different type of device check (Apple Info, Samsung Info, etc.).
To list available services for your account, use `GET /v1/services` or the `list_services()` helper.
The default is `12`. Set `IMEICHECK_SERVICE_ID` in your `.env` to match your account's available services.

### Service Discovery
The service module provides helpers for debugging:
- `list_services()` — lists all services available on your account
- `get_account_balance()` — checks your account balance

### Behavior
- **Optional**: Lookup is never required; staff can always enter details manually
- **Non-blocking**: API failures (timeout, connection error, auth error) return graceful error messages
- **Endpoints**: `POST /tickets/imei-lookup` and `POST /intake/imei-lookup`
- **Caching**: Successful results stored as JSON on `device.imei_lookup_data`
- **Data flow**: Brand, model, storage, color, carrier lock, FMI status, serial number parsed from response
- **Async handling**: If the API returns a pending check, one polling request is made automatically

### Error Handling
The service provides detailed, human-readable error messages for:

| HTTP Status | Meaning | Error shown to staff |
|------------|---------|----------------------|
| 401 | Bad API key | "IMEI API authentication failed" |
| 403 | IP blocked / account blocked | "IMEI API access denied: ..." |
| 404 | Wrong endpoint URL | "IMEI API endpoint not found" |
| 422 | Validation error (bad serviceId, bad IMEI) | "IMEI API validation error: serviceId: ..." |
| 429 | Rate limited | "IMEI API rate limit exceeded" |
| 500+ | Provider outage | "IMEI provider is experiencing issues" |

API keys are **never** logged or included in error messages.

### Common Failure Modes
1. **"IMEI API validation error: serviceId: invalid"** — Your `IMEICHECK_SERVICE_ID` is not available on your account. Use `list_services()` to find valid IDs.
2. **"IMEI API authentication failed"** — Your `IMEICHECK_API_KEY` is wrong or expired. Regenerate it at [imeicheck.net/developer-api](https://imeicheck.net/developer-api).
3. **"IMEI API access denied: IP not whitelisted"** — Add your server's IP to the API whitelist in your IMEIcheck account.
4. **"IMEI lookup service unreachable"** — Network issue between your server and the API.

### When Lookup Fails
Staff should proceed with manual device entry. All device fields are editable regardless of whether the IMEI lookup succeeds. The lookup is a convenience feature, not a requirement.

### Response Adapter
The service uses a flexible response parser that handles multiple API response formats (`properties`, `result`, or flat dict) to accommodate IMEIcheck.net API variations.

## Service Catalog

### Enhanced RepairService Model
| New Field | Description |
|-----------|-------------|
| `service_code` | Unique service identifier (e.g., `SCR-REP`) |
| `labour_price` | Separate labour price for quotes |
| `parts` | Many-to-many relationship to Parts via `service_part_links` |

### Service-Parts Linking
Services can bundle multiple parts. The `service_part_links` table stores `service_id`, `part_id`, and `quantity`.

### Quote Integration
`GET /tickets/service-detail-json/<service_id>` returns:
```json
{
  "ok": true,
  "name": "Screen Repair",
  "service_code": "SCR-REP",
  "labour_price": 35.00,
  "parts": [{"id": "...", "sku": "SCR-IP14", "name": "iPhone 14 Screen", "sale_price": 89.99}]
}
```
This endpoint enables quote forms to auto-populate labour + parts when a service is selected.

## Permissions

| Permission | Roles | Purpose |
|------------|-------|---------|
| `can_view_secure_access` | Management, Workshop | View device unlock data |
| `can_manage_service_catalog` | Management | Create/edit service catalog entries |
| `can_lookup_imei` | Management, Front Desk, Workshop | Trigger IMEI lookups |

## Migration

**Name**: `a1b2c3d4e5f7_phase18_device_intelligence.py`

**Changes**:
1. Adds 16 new columns to `devices` table
2. Adds `service_code` and `labour_price` to `repair_services`
3. Creates `device_precheck_templates` table
4. Creates `service_part_links` table
5. Seeds default pre-check templates for 7 device categories (48 entries)
