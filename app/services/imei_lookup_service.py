"""IMEIcheck.net integration service.

Provides optional IMEI lookup with manual fallback. The lookup is
non-blocking — if the API is unavailable, misconfigured, or returns
errors, staff can still manually enter device details.

API reference: https://app.theneo.io/webanite/imeicheck-net/api-reference

Config keys:
    IMEICHECK_API_KEY:    API key (Bearer token) for IMEIcheck.net
    IMEICHECK_API_URL:    Base URL (default: https://api.imeicheck.net)
    IMEICHECK_SERVICE_ID: Service ID for checks (default: 12)
    IMEICHECK_TIMEOUT:    Request timeout in seconds (default: 10)
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
    raw_data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
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
        }


def is_imei_lookup_configured() -> bool:
    """Check if IMEI lookup is configured and enabled."""
    return bool(current_app.config.get("IMEICHECK_API_KEY", ""))


def lookup_imei(imei: str) -> IMEILookupResult:
    """Look up device details by IMEI using IMEIcheck.net.

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
    service_id = current_app.config.get("IMEICHECK_SERVICE_ID", 12)
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

        return _handle_response(imei, resp)

    except requests.Timeout:
        logger.warning("IMEI lookup timeout for %s (url=%s)", imei, url)
        return IMEILookupResult(
            success=False,
            error="IMEI lookup timed out — try again or enter details manually",
            imei=imei,
        )
    except requests.ConnectionError:
        logger.warning("IMEI lookup connection error for %s (url=%s)", imei, url)
        return IMEILookupResult(
            success=False,
            error="IMEI lookup service unreachable — check network or enter details manually",
            imei=imei,
        )
    except Exception as e:
        logger.error("IMEI lookup unexpected error: %s", e)
        return IMEILookupResult(
            success=False,
            error=f"Unexpected error: {e}",
            imei=imei,
        )


def _handle_response(imei: str, resp: requests.Response) -> IMEILookupResult:
    """Handle the HTTP response from IMEIcheck.net."""
    # Try to parse response body regardless of status code
    try:
        data = resp.json()
    except (ValueError, TypeError):
        data = {}

    # 2xx = success (API returns 201 Created for new checks)
    if 200 <= resp.status_code < 300:
        # Check if the result is still processing (async)
        status = data.get("status", "")
        if status in ("pending", "processing"):
            # Try polling once after a short delay
            check_id = data.get("id")
            if check_id:
                return _poll_check_result(imei, check_id, data)
            # No check ID — return what we have
            return _parse_response(imei, data)
        return _parse_response(imei, data)

    # Non-2xx — extract a meaningful error from the API response
    error_msg = _extract_error_message(resp.status_code, data)
    _log_api_error(imei, resp.status_code, data)

    return IMEILookupResult(
        success=False,
        error=error_msg,
        imei=imei,
        raw_data=data,
    )


def _poll_check_result(imei: str, check_id: int, initial_data: dict) -> IMEILookupResult:
    """Poll the check result endpoint once after a short delay.

    IMEIcheck.net processes some checks asynchronously. We make one
    follow-up request to retrieve the result. If still pending, we
    return whatever data is available.
    """
    api_key = current_app.config.get("IMEICHECK_API_KEY", "")
    base_url = current_app.config.get(
        "IMEICHECK_API_URL", "https://api.imeicheck.net"
    ).rstrip("/")
    timeout = current_app.config.get("IMEICHECK_TIMEOUT", 10)

    time.sleep(2)  # Brief wait for processing

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

    # Fall back to initial data
    return _parse_response(imei, initial_data)


def _extract_error_message(status_code: int, data: dict) -> str:
    """Build a human-readable error message from the API response."""
    # Check for known error code field
    error_code = data.get("error", data.get("code", ""))
    if error_code and error_code in _ERROR_LABELS:
        return f"IMEI provider: {_ERROR_LABELS[error_code]}"

    # Check for message field
    message = data.get("message", "")

    if status_code == 401:
        return "IMEI API authentication failed — check your API key"
    if status_code == 403:
        detail = message or error_code or "access denied"
        return f"IMEI API access denied: {detail}"
    if status_code == 404:
        return "IMEI API endpoint not found — check IMEICHECK_API_URL config"
    if status_code == 422:
        # Validation error — surface the detail
        errors = data.get("errors", {})
        if errors:
            # Flatten validation errors like {"serviceId": ["invalid"]}
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
    # Sanitise — remove any fields that could contain sensitive data
    safe_data = {k: v for k, v in data.items() if k.lower() not in ("token", "key", "secret", "authorization")}
    logger.warning(
        "IMEI lookup failed: imei=%s status=%d response=%s",
        imei, status_code, json.dumps(safe_data, default=str)[:500],
    )


def _parse_response(imei: str, data: dict) -> IMEILookupResult:
    """Parse the IMEIcheck.net API response into our result structure."""
    try:
        properties = data.get("properties", data.get("result", data))

        if isinstance(properties, dict):
            brand = properties.get("brand", properties.get("deviceBrand", ""))
            model_name = properties.get("modelName", properties.get("model", properties.get("deviceName", "")))
            storage = properties.get("storage", properties.get("internalMemory", ""))
            color = properties.get("color", properties.get("colour", ""))
            carrier = properties.get("simLock", properties.get("carrierLock", properties.get("networkLock", "")))
            fmi = properties.get("fmiStatus", properties.get("findMyIphone", properties.get("fmi", "")))
            serial = properties.get("serialNumber", properties.get("serial", ""))

            # Also check top-level deviceName if properties didn't have model
            if not model_name:
                model_name = data.get("deviceName", "")
            if not brand:
                brand = data.get("deviceBrand", "")

            # Normalize boolean-ish values
            if isinstance(carrier, bool):
                carrier = "Locked" if carrier else "Unlocked"
            if isinstance(fmi, bool):
                fmi = "ON" if fmi else "OFF"

            # Only consider it a success if we got at least a brand or model
            has_data = bool(brand or model_name)

            return IMEILookupResult(
                success=has_data,
                error=None if has_data else "IMEI lookup returned no device details",
                brand=str(brand),
                model=str(model_name),
                storage=str(storage) if storage else "",
                color=str(color) if color else "",
                carrier_lock=str(carrier) if carrier else "",
                fmi_status=str(fmi) if fmi else "",
                imei=imei,
                serial_number=str(serial) if serial else "",
                raw_data=data,
            )
        else:
            return IMEILookupResult(
                success=False,
                error="Unexpected API response format",
                imei=imei,
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


def list_services() -> dict:
    """Retrieve available services from IMEIcheck.net.

    Returns a dict with 'success' bool and 'services' list or 'error' string.
    Useful for debugging configuration and finding the right service ID.
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
    """Retrieve account balance from IMEIcheck.net.

    Returns a dict with 'success' bool and 'balance' or 'error'.
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


def cache_lookup_result(device, result: IMEILookupResult) -> None:
    """Store the raw lookup result JSON on the device for reference."""
    if result.raw_data:
        device.imei_lookup_data = json.dumps(result.raw_data, default=str)
