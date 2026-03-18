"""IMEIcheck.net integration service.

Provides optional IMEI lookup with manual fallback. The lookup is
non-blocking — if the API is unavailable, misconfigured, or returns
errors, staff can still manually enter device details.

Config keys:
    IMEICHECK_API_KEY: API key for IMEIcheck.net (empty = disabled)
    IMEICHECK_API_URL: Base URL (default: https://api.imeicheck.net)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

import requests
from flask import current_app

logger = logging.getLogger(__name__)


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
    )
    timeout = current_app.config.get("IMEICHECK_TIMEOUT", 10)

    try:
        resp = requests.post(
            f"{base_url}/v1/checks",
            json={"deviceId": imei, "serviceId": 1},
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )

        if resp.status_code == 401:
            return IMEILookupResult(
                success=False,
                error="IMEI API authentication failed",
                imei=imei,
            )

        if resp.status_code != 200:
            return IMEILookupResult(
                success=False,
                error=f"IMEI API returned status {resp.status_code}",
                imei=imei,
            )

        data = resp.json()
        return _parse_response(imei, data)

    except requests.Timeout:
        logger.warning("IMEI lookup timeout for %s", imei)
        return IMEILookupResult(
            success=False,
            error="IMEI lookup timed out",
            imei=imei,
        )
    except requests.ConnectionError:
        logger.warning("IMEI lookup connection error for %s", imei)
        return IMEILookupResult(
            success=False,
            error="IMEI lookup service unreachable",
            imei=imei,
        )
    except Exception as e:
        logger.error("IMEI lookup unexpected error: %s", e)
        return IMEILookupResult(
            success=False,
            error=f"Unexpected error: {e}",
            imei=imei,
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

            # Normalize boolean-ish values
            if isinstance(carrier, bool):
                carrier = "Locked" if carrier else "Unlocked"
            if isinstance(fmi, bool):
                fmi = "ON" if fmi else "OFF"

            return IMEILookupResult(
                success=True,
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


def cache_lookup_result(device, result: IMEILookupResult) -> None:
    """Store the raw lookup result JSON on the device for reference."""
    if result.raw_data:
        device.imei_lookup_data = json.dumps(result.raw_data, default=str)
