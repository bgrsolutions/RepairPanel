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
IMEICHECK_SERVICE_ID=12                   # Default service ID for checks
IMEICHECK_TIMEOUT=10                      # Request timeout in seconds
# Brand-aware service mapping (optional, JSON):
IMEICHECK_SERVICE_MAP={"apple": 12, "samsung": 3, "default": 1}
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

### Phase 18.3 — Richer Autofill and Brand-Aware Service Selection

#### Auto-Populated Fields
When an IMEI lookup succeeds, the following fields can be populated:

| Field | Source Key(s) | Notes |
|-------|--------------|-------|
| Brand | `brand`, `deviceBrand`, `manufacturer` | |
| Model | `modelName`, `model`, `deviceName`, `marketName` | |
| Storage | `storage`, `internalMemory`, `capacity` | |
| Color | `color`, `colour`, `deviceColor` | |
| Serial Number | `serialNumber`, `serial`, `sn` | |
| Carrier/SIM Lock | `simLock`, `carrierLock`, `networkLock` | Normalized: Locked/Unlocked |
| FMI Status | `fmiStatus`, `findMyIphone`, `fmi` | Normalized: ON/OFF |
| Warranty | `warrantyStatus`, `warranty`, `appleCareEligible` | |
| Blacklist | `blacklistStatus`, `blacklisted`, `gsmaBlacklisted` | Normalized: Clean/Blacklisted |
| Purchase Country | `purchaseCountry`, `country`, `firstActivationCountry` | |
| Model Number | `modelNumber`, `partNumber`, `appleModelNumber` | |
| Device Image | `image`, `deviceImage`, `imageUrl` | URL if available |

All fields remain editable after autofill. Staff can always override any value.

#### Brand-Aware Service Selection
Different IMEIcheck services return different data. The app supports automatic service selection based on device brand:

1. **`IMEICHECK_SERVICE_MAP`** (env var, JSON): Maps brand names to service IDs.
   ```json
   {"apple": 12, "samsung": 3, "default": 1}
   ```
2. When staff types a brand before clicking "Lookup", the `brand_hint` is sent with the request.
3. The service resolver checks: explicit `service_id` override > brand match in service map > `default` key > `IMEICHECK_SERVICE_ID` config.

#### Partial Data Handling
When the API returns only some fields, the UI indicates this:
- Shows "Partial device details populated — verify and complete manually" in amber
- Displays a field count badge (e.g., "3 fields populated")
- Missing fields remain empty for manual entry

#### Lookup Result Panel
After a successful lookup, a summary panel appears in the intake form showing:
- Color-coded badges for each populated field
- Warning badges for security-sensitive values (SIM Locked, FMI ON, Blacklisted)
- A reminder that all fields are editable

### Phase 18.4 — Intelligent Service Routing and Secondary Checks

#### Recommended Service Map
The following brand-to-service mappings are recommended for IMEIcheck.net:

```bash
IMEICHECK_SERVICE_MAP={"apple": 2, "samsung": 5, "xiaomi": 6, "oneplus": 7, "motorola": 8, "zte": 9, "google": 10, "pixel": 10, "huawei": 11, "lg": 4, "default": 22}
```

| Brand | Service ID | Notes |
|-------|-----------|-------|
| Apple | 2 | Apple device info |
| Samsung | 5 | Samsung device info |
| Xiaomi | 6 | Xiaomi device info |
| OnePlus | 7 | OnePlus device info |
| Motorola | 8 | Motorola device info |
| ZTE | 9 | ZTE device info |
| Google / Pixel | 10 | Google device info |
| Huawei | 11 | Huawei device info |
| LG | 4 | LG device info |
| Default | 22 | Generic IMEI check |

#### Secondary IMEI Checks
Optional additional checks can be triggered from the intake UI after a primary lookup:

```bash
IMEICHECK_SECONDARY_SERVICES={"fmi": 18, "carrier": 17, "warranty": 25, "blacklist": 16}
```

| Check Type | Service ID | Returns |
|-----------|-----------|---------|
| FMI (Find My iPhone) | 18 | `fmi_status`: ON/OFF |
| Carrier / SIM Lock | 17 | `carrier_lock`: Locked/Unlocked |
| Warranty | 25 | `warranty_status` |
| Blacklist | 16 | `blacklist_status`: Clean/Blacklisted |

Secondary checks:
- Are triggered manually via buttons that appear after a successful primary lookup
- Use the same API (`POST /v1/checks`) with the secondary service ID
- Results are merged into existing form fields without overwriting non-empty values
- Each button shows its result status (success/fail) after completion

#### API Endpoints
- `POST /intake/imei-secondary-check` — Run a secondary check from intake
- `POST /tickets/imei-secondary-check` — Run a secondary check from tickets
- Request body: `{"imei": "...", "check_type": "fmi|carrier|warranty|blacklist"}`

#### Field Merge Logic
When a secondary check returns data, the `merge_results()` function:
1. Only fills in fields that are empty in the base result
2. Never overwrites existing non-empty values
3. Recalculates `fields_populated` count after merge

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
