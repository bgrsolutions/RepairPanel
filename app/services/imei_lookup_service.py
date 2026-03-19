"""IMEIcheck.net integration service.

Provides optional IMEI lookup with manual fallback. The lookup is
non-blocking — if the API is unavailable, misconfigured, or returns
errors, staff can still manually enter device details.

API reference: https://app.theneo.io/webanite/imeicheck-net/api-reference

Config keys:
    IMEICHECK_API_KEY:      API key (Bearer token) for IMEIcheck.net
    IMEICHECK_API_URL:      Base URL (default: https://api.imeicheck.net)
    IMEICHECK_SERVICE_ID:   Default service ID for checks (default: 12)
    IMEICHECK_SERVICE_MAP:  JSON brand→serviceId map (optional)
    IMEICHECK_TIMEOUT:      Request timeout in seconds (default: 10)
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field

import requests
from flask import current_app

logger = logging.getLogger(__name__)

# Known API error codes from IMEIcheck.net docs
_ERROR_LABELS = {
    "client_blocked": "Account blocked by provider",
    "api_disabled": "API access is disabled for this account",
    "ip_not_allowed": "Server IP not whitelisted in API settings",
    "insufficient_balance": "Insufficient account balance",
    "invalid_service": "Invalid or unavailable service ID",
    "invalid_device_id": "Invalid IMEI / device identifier",
    "validation_error": "Request validation failed",
}


@dataclass
class IMEILookupResult:
    """Parsed result from IMEI lookup."""
    success: bool = False
    error: str | None = None
    brand: str = ""
    model: str = ""
    storage: str = ""
    color: str = ""
    carrier_lock: str = ""
    fmi_status: str = ""
    imei: str = ""
    serial_number: str = ""
    # Extended metadata from richer checks
    warranty_status: str = ""
    blacklist_status: str = ""
    purchase_country: str = ""
    model_number: str = ""
    device_image: str = ""
    service_id_used: int = 0
    fields_populated: int = 0
    raw_data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {
            "success": self.success,
            "error": self.error,
            "brand": self.brand,
            "model": self.model,
            "storage": self.storage,
            "color": self.color,
            "carrier_lock": self.carrier_lock,
            "fmi_status": self.fmi_status,
            "imei": self.imei,
            "serial_number": self.serial_number,
            "warranty_status": self.warranty_status,
            "blacklist_status": self.blacklist_status,
            "purchase_country": self.purchase_country,
            "model_number": self.model_number,
            "device_image": self.device_image,
            "service_id_used": self.service_id_used,
            "fields_populated": self.fields_populated,
        }
        return d


def is_imei_lookup_configured() -> bool:
    """Check if IMEI lookup is configured and enabled."""
    return bool(current_app.config.get("IMEICHECK_API_KEY", ""))


def resolve_service_id(brand_hint: str = "") -> int:
    """Resolve the best service ID for a given brand hint.

    Uses IMEICHECK_SERVICE_MAP if configured, otherwise falls back
    to IMEICHECK_SERVICE_ID.
    """
    default_id = current_app.config.get("IMEICHECK_SERVICE_ID", 12)
    service_map = current_app.config.get("IMEICHECK_SERVICE_MAP", {})
    if not service_map or not brand_hint:
        return default_id

    key = brand_hint.strip().lower()
    # Exact match
    if key in service_map:
        return service_map[key]
    # Partial match (e.g. "apple iphone" matches "apple")
    for map_key, sid in service_map.items():
        if map_key in key or key in map_key:
            return sid
    # Fallback key
    return service_map.get("default", service_map.get("*", default_id))


def lookup_imei(imei: str, service_id: int | None = None, brand_hint: str = "") -> IMEILookupResult:
    """Look up device details by IMEI using IMEIcheck.net.

    Args:
        imei: The IMEI to look up.
        service_id: Optional explicit service ID override.
        brand_hint: Optional brand name to auto-select the best service.

    Returns IMEILookupResult with success=False if the API is not
    configured, unreachable, or returns an error. Staff can always
    fall back to manual entry.
    """
    api_key = current_app.config.get("IMEICHECK_API_KEY", "")
    if not api_key:
        return IMEILookupResult(
            success=False,
            error="IMEI lookup not configured",
            imei=imei,
        )

    if not imei or len(imei) < 14:
        return IMEILookupResult(
            success=False,
            error="Invalid IMEI format",
            imei=imei,
        )

    base_url = current_app.config.get(
        "IMEICHECK_API_URL", "https://api.imeicheck.net"
    ).rstrip("/")
    # Resolve service ID: explicit override > brand-aware > config default
    if service_id is None:
        service_id = resolve_service_id(brand_hint)
    timeout = current_app.config.get("IMEICHECK_TIMEOUT", 10)

    url = f"{base_url}/v1/checks"

    try:
        resp = requests.post(
            url,
            json={"deviceId": imei, "serviceId": service_id},
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
            timeout=timeout,
        )

        result = _handle_response(imei, resp)
        result.service_id_used = service_id
        return result

    except requests.Timeout:
        logger.warning("IMEI lookup timeout for %s (url=%s)", imei, url)
        return IMEILookupResult(
            success=False,
            error="IMEI lookup timed out — try again or enter details manually",
            imei=imei,
            service_id_used=service_id,
        )
    except requests.ConnectionError:
        logger.warning("IMEI lookup connection error for %s (url=%s)", imei, url)
        return IMEILookupResult(
            success=False,
            error="IMEI lookup service unreachable — check network or enter details manually",
            imei=imei,
            service_id_used=service_id,
        )
    except Exception as e:
        logger.error("IMEI lookup unexpected error: %s", e)
        return IMEILookupResult(
            success=False,
            error=f"Unexpected error: {e}",
            imei=imei,
            service_id_used=service_id,
        )


def _handle_response(imei: str, resp: requests.Response) -> IMEILookupResult:
    """Handle the HTTP response from IMEIcheck.net."""
    try:
        data = resp.json()
    except (ValueError, TypeError):
        data = {}

    # 2xx = success (API returns 201 Created for new checks)
    if 200 <= resp.status_code < 300:
        status = data.get("status", "")
        if status in ("pending", "processing"):
            check_id = data.get("id")
            if check_id:
                return _poll_check_result(imei, check_id, data)
            return _parse_response(imei, data)
        return _parse_response(imei, data)

    # Non-2xx — extract a meaningful error
    error_msg = _extract_error_message(resp.status_code, data)
    _log_api_error(imei, resp.status_code, data)

    return IMEILookupResult(
        success=False,
        error=error_msg,
        imei=imei,
        raw_data=data,
    )


def _poll_check_result(imei: str, check_id: int, initial_data: dict) -> IMEILookupResult:
    """Poll the check result endpoint once after a short delay."""
    api_key = current_app.config.get("IMEICHECK_API_KEY", "")
    base_url = current_app.config.get(
        "IMEICHECK_API_URL", "https://api.imeicheck.net"
    ).rstrip("/")
    timeout = current_app.config.get("IMEICHECK_TIMEOUT", 10)

    time.sleep(2)

    try:
        resp = requests.get(
            f"{base_url}/v1/checks/{check_id}",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
            timeout=timeout,
        )
        if 200 <= resp.status_code < 300:
            data = resp.json()
            return _parse_response(imei, data)
    except Exception as e:
        logger.warning("IMEI poll failed for check %s: %s", check_id, e)

    return _parse_response(imei, initial_data)


def _extract_error_message(status_code: int, data: dict) -> str:
    """Build a human-readable error message from the API response."""
    error_code = data.get("error", data.get("code", ""))
    if error_code and error_code in _ERROR_LABELS:
        return f"IMEI provider: {_ERROR_LABELS[error_code]}"

    message = data.get("message", "")

    if status_code == 401:
        return "IMEI API authentication failed — check your API key"
    if status_code == 403:
        detail = message or error_code or "access denied"
        return f"IMEI API access denied: {detail}"
    if status_code == 404:
        return "IMEI API endpoint not found — check IMEICHECK_API_URL config"
    if status_code == 422:
        errors = data.get("errors", {})
        if errors:
            parts = []
            for field_name, msgs in errors.items():
                if isinstance(msgs, list):
                    parts.append(f"{field_name}: {', '.join(str(m) for m in msgs)}")
                else:
                    parts.append(f"{field_name}: {msgs}")
            return f"IMEI API validation error: {'; '.join(parts)}"
        if message:
            return f"IMEI API validation error: {message}"
        return "IMEI API validation error — check service ID and IMEI format"
    if status_code == 429:
        return "IMEI API rate limit exceeded — try again later"
    if status_code >= 500:
        return "IMEI provider is experiencing issues — try again later"

    if message:
        return f"IMEI API error ({status_code}): {message}"
    return f"IMEI API returned unexpected status {status_code}"


def _log_api_error(imei: str, status_code: int, data: dict) -> None:
    """Log API errors with response details but never log secrets."""
    safe_data = {k: v for k, v in data.items() if k.lower() not in ("token", "key", "secret", "authorization")}
    logger.warning(
        "IMEI lookup failed: imei=%s status=%d response=%s",
        imei, status_code, json.dumps(safe_data, default=str)[:500],
    )


def _parse_response(imei: str, data: dict) -> IMEILookupResult:
    """Parse the IMEIcheck.net API response into our result structure.

    Handles multiple response shapes and extracts all available
    device metadata for richer autofill.
    """
    try:
        properties = data.get("properties", data.get("result", data))

        if not isinstance(properties, dict):
            return IMEILookupResult(
                success=False,
                error="Unexpected API response format",
                imei=imei,
                raw_data=data,
            )

        # --- Core fields ---
        brand = _pick(properties, "brand", "deviceBrand", "manufacturer") or data.get("deviceBrand", "")
        model_name = (
            _pick(properties, "modelName", "model", "deviceName", "marketName")
            or data.get("deviceName", "")
        )
        storage = _pick(properties, "storage", "internalMemory", "capacity", "storageCapacity")
        color = _pick(properties, "color", "colour", "deviceColor")
        serial = _pick(properties, "serialNumber", "serial", "sn")

        # --- Lock / Security fields ---
        carrier_raw = _pick(properties, "simLock", "carrierLock", "networkLock", "simLockStatus")
        fmi_raw = _pick(properties, "fmiStatus", "findMyIphone", "fmi", "fmip",
                        "findMyIPhoneStatus", "findMyMobile")

        # --- Extended metadata ---
        warranty = _pick(properties, "warrantyStatus", "warranty", "appleCareEligible",
                         "warrantyInfo", "limitedWarranty")
        blacklist = _pick(properties, "blacklistStatus", "blacklisted", "gsmaBlacklisted",
                          "blacklistResult", "lostStolenStatus")
        purchase_country = _pick(properties, "purchaseCountry", "country", "soldBy",
                                 "initialCarrier", "firstActivationCountry")
        model_number = _pick(properties, "modelNumber", "modelNum", "partNumber",
                             "appleModelNumber")
        image_url = _pick(properties, "image", "deviceImage", "imageUrl",
                          "thumbnail") or data.get("deviceImage", "")

        # --- Normalize boolean-ish values ---
        carrier = _normalize_lock(carrier_raw)
        fmi = _normalize_fmi(fmi_raw)
        blacklist = _normalize_blacklist(blacklist)
        warranty = str(warranty) if warranty else ""

        # --- Count populated fields ---
        core_fields = [brand, model_name, storage, color, serial, carrier, fmi]
        extra_fields = [warranty, blacklist, purchase_country, model_number]
        fields_populated = sum(1 for f in core_fields + extra_fields if f)

        has_data = bool(brand or model_name)

        return IMEILookupResult(
            success=has_data,
            error=None if has_data else "IMEI lookup returned no device details",
            brand=str(brand),
            model=str(model_name),
            storage=str(storage) if storage else "",
            color=str(color) if color else "",
            carrier_lock=carrier,
            fmi_status=fmi,
            imei=imei,
            serial_number=str(serial) if serial else "",
            warranty_status=warranty,
            blacklist_status=blacklist,
            purchase_country=str(purchase_country) if purchase_country else "",
            model_number=str(model_number) if model_number else "",
            device_image=str(image_url) if image_url else "",
            fields_populated=fields_populated,
            raw_data=data,
        )
    except Exception as e:
        logger.error("IMEI response parse error: %s", e)
        return IMEILookupResult(
            success=False,
            error=f"Response parse error: {e}",
            imei=imei,
            raw_data=data,
        )


def _pick(d: dict, *keys: str):
    """Return the first non-empty value from a dict for any of the given keys."""
    for k in keys:
        v = d.get(k)
        if v is not None and v != "":
            return v
    return ""


def _normalize_lock(val) -> str:
    """Normalize carrier/SIM lock values to human-readable strings."""
    if val is None or val == "":
        return ""
    if isinstance(val, bool):
        return "Locked" if val else "Unlocked"
    s = str(val).strip().lower()
    if s in ("true", "locked", "1", "yes"):
        return "Locked"
    if s in ("false", "unlocked", "0", "no"):
        return "Unlocked"
    return str(val)


def _normalize_fmi(val) -> str:
    """Normalize Find My iPhone / Find My Device status."""
    if val is None or val == "":
        return ""
    if isinstance(val, bool):
        return "ON" if val else "OFF"
    s = str(val).strip().lower()
    if s in ("on", "true", "1", "yes", "enabled"):
        return "ON"
    if s in ("off", "false", "0", "no", "disabled"):
        return "OFF"
    return str(val)


def _normalize_blacklist(val) -> str:
    """Normalize blacklist status."""
    if val is None or val == "":
        return ""
    if isinstance(val, bool):
        return "Blacklisted" if val else "Clean"
    s = str(val).strip().lower()
    if s in ("true", "1", "yes", "blacklisted"):
        return "Blacklisted"
    if s in ("false", "0", "no", "clean", "clear"):
        return "Clean"
    return str(val)


def list_services() -> dict:
    """Retrieve available services from IMEIcheck.net.

    Returns a dict with 'success' bool and 'services' list or 'error' string.
    """
    api_key = current_app.config.get("IMEICHECK_API_KEY", "")
    if not api_key:
        return {"success": False, "error": "IMEI lookup not configured"}

    base_url = current_app.config.get(
        "IMEICHECK_API_URL", "https://api.imeicheck.net"
    ).rstrip("/")
    timeout = current_app.config.get("IMEICHECK_TIMEOUT", 10)

    try:
        resp = requests.get(
            f"{base_url}/v1/services",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
            timeout=timeout,
        )

        if 200 <= resp.status_code < 300:
            data = resp.json()
            services = data if isinstance(data, list) else data.get("data", data.get("services", []))
            return {"success": True, "services": services}

        try:
            data = resp.json()
        except (ValueError, TypeError):
            data = {}

        return {
            "success": False,
            "error": _extract_error_message(resp.status_code, data),
        }

    except requests.Timeout:
        return {"success": False, "error": "Request timed out"}
    except requests.ConnectionError:
        return {"success": False, "error": "Service unreachable"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_account_balance() -> dict:
    """Retrieve account balance from IMEIcheck.net."""
    api_key = current_app.config.get("IMEICHECK_API_KEY", "")
    if not api_key:
        return {"success": False, "error": "IMEI lookup not configured"}

    base_url = current_app.config.get(
        "IMEICHECK_API_URL", "https://api.imeicheck.net"
    ).rstrip("/")
    timeout = current_app.config.get("IMEICHECK_TIMEOUT", 10)

    try:
        resp = requests.get(
            f"{base_url}/v1/account",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
            timeout=timeout,
        )

        if 200 <= resp.status_code < 300:
            return {"success": True, **resp.json()}

        return {"success": False, "error": f"API returned status {resp.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_secondary_services() -> dict:
    """Return configured secondary check services.

    Returns a dict like {"fmi": 18, "carrier": 17, "warranty": 25, "blacklist": 16}.
    Empty dict if not configured.
    """
    return current_app.config.get("IMEICHECK_SECONDARY_SERVICES", {})


def secondary_check(imei: str, check_type: str) -> IMEILookupResult:
    """Run a secondary IMEI check for a specific check type.

    Args:
        imei: The IMEI to check.
        check_type: One of "fmi", "carrier", "warranty", "blacklist".

    Returns IMEILookupResult from the secondary service.
    """
    services = get_secondary_services()
    if not services:
        return IMEILookupResult(
            success=False,
            error="Secondary IMEI checks not configured",
            imei=imei,
        )

    service_id = services.get(check_type.lower())
    if not service_id:
        return IMEILookupResult(
            success=False,
            error=f"No service configured for check type '{check_type}'",
            imei=imei,
        )

    return lookup_imei(imei, service_id=service_id)


def merge_results(base: IMEILookupResult, extra: IMEILookupResult) -> IMEILookupResult:
    """Merge extra lookup result into the base, preserving non-empty base values.

    Only fills in fields that are empty/blank in the base result.
    """
    if not extra.success:
        return base

    merge_fields = [
        "brand", "model", "storage", "color", "carrier_lock", "fmi_status",
        "serial_number", "warranty_status", "blacklist_status",
        "purchase_country", "model_number", "device_image",
    ]
    for field in merge_fields:
        base_val = getattr(base, field, "")
        extra_val = getattr(extra, field, "")
        if not base_val and extra_val:
            setattr(base, field, extra_val)

    # Recount populated fields
    core_fields = [base.brand, base.model, base.storage, base.color,
                   base.serial_number, base.carrier_lock, base.fmi_status]
    extra_fields = [base.warranty_status, base.blacklist_status,
                    base.purchase_country, base.model_number]
    base.fields_populated = sum(1 for f in core_fields + extra_fields if f)

    return base


def cache_lookup_result(device, result: IMEILookupResult) -> None:
    """Store the raw lookup result JSON on the device for reference."""
    if result.raw_data:
        device.imei_lookup_data = json.dumps(result.raw_data, default=str)
