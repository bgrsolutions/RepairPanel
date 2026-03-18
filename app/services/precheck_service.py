"""Device-type-specific pre-check service.

Provides pre-check template retrieval by device category and
fallback defaults for when database templates are unavailable.
"""
from __future__ import annotations

import logging
from flask import request

from app.extensions import db

logger = logging.getLogger(__name__)

# Fallback pre-checks when database templates are unavailable
_FALLBACK_CHECKS = {
    "phones": [
        ("powers_on", "Device powers on", "El dispositivo enciende"),
        ("screen_condition", "Screen displays correctly", "La pantalla muestra correctamente"),
        ("touch_responsive", "Touch screen responsive", "Pantalla táctil responde"),
        ("charging_port", "Charging port functional", "Puerto de carga funcional"),
        ("buttons_work", "Physical buttons work", "Botones físicos funcionan"),
        ("speakers_mic", "Speakers and microphone work", "Altavoces y micrófono funcionan"),
        ("cameras", "Cameras functional", "Cámaras funcionan"),
        ("wifi_bluetooth", "WiFi/Bluetooth working", "WiFi/Bluetooth funciona"),
        ("water_damage", "No visible water damage", "Sin daño por agua visible"),
        ("biometrics", "Biometrics functional", "Biometría funcional"),
    ],
    "tablets": [
        ("powers_on", "Device powers on", "El dispositivo enciende"),
        ("screen_condition", "Screen displays correctly", "La pantalla muestra correctamente"),
        ("touch_responsive", "Touch screen responsive", "Pantalla táctil responde"),
        ("charging_port", "Charging port functional", "Puerto de carga funcional"),
        ("buttons_work", "Physical buttons work", "Botones físicos funcionan"),
        ("cameras", "Cameras functional", "Cámaras funcionan"),
        ("wifi_bluetooth", "WiFi/Bluetooth working", "WiFi/Bluetooth funciona"),
    ],
    "laptops": [
        ("powers_on", "Device powers on", "El dispositivo enciende"),
        ("screen_condition", "Screen displays correctly", "La pantalla muestra correctamente"),
        ("keyboard", "Keyboard functional", "Teclado funcional"),
        ("trackpad", "Trackpad functional", "Trackpad funcional"),
        ("charging", "Charges correctly", "Carga correctamente"),
        ("battery_holds", "Battery holds charge", "Batería mantiene carga"),
        ("wifi_bluetooth", "WiFi/Bluetooth working", "WiFi/Bluetooth funciona"),
        ("usb_ports", "USB/ports functional", "Puertos USB funcionales"),
        ("speakers_mic", "Speakers and microphone work", "Altavoces y micrófono funcionan"),
        ("webcam", "Webcam functional", "Webcam funcional"),
        ("hinges", "Hinges intact", "Bisagras intactas"),
    ],
    "desktops": [
        ("powers_on", "System powers on", "El sistema enciende"),
        ("display_output", "Display output working", "Salida de video funcional"),
        ("usb_ports", "USB/ports functional", "Puertos USB funcionales"),
        ("fans_cooling", "Fans/cooling working", "Ventiladores/refrigeración funciona"),
        ("storage_detected", "Storage drives detected", "Unidades de almacenamiento detectadas"),
        ("network", "Network connectivity", "Conectividad de red"),
    ],
    "game_consoles": [
        ("powers_on", "Console powers on", "La consola enciende"),
        ("display_output", "Display output working", "Salida de video funcional"),
        ("disc_drive", "Disc drive functional", "Unidad de disco funcional"),
        ("controllers", "Controllers connect", "Controles se conectan"),
        ("wifi", "WiFi working", "WiFi funciona"),
        ("fans_cooling", "Fans/cooling working", "Ventiladores/refrigeración funciona"),
    ],
    "smartwatches": [
        ("powers_on", "Device powers on", "El dispositivo enciende"),
        ("screen_condition", "Screen displays correctly", "La pantalla muestra correctamente"),
        ("charging", "Charges correctly", "Carga correctamente"),
        ("heart_rate", "Heart rate sensor works", "Sensor de ritmo cardíaco funciona"),
        ("buttons_crown", "Buttons/crown functional", "Botones/corona funcionales"),
    ],
    "other": [
        ("powers_on", "Device powers on", "El dispositivo enciende"),
        ("basic_function", "Basic function works", "Función básica funciona"),
        ("physical_condition", "Physical condition noted", "Condición física registrada"),
    ],
}

# Device categories
DEVICE_CATEGORIES = [
    ("phones", "Phones", "Teléfonos"),
    ("tablets", "Tablets", "Tablets"),
    ("laptops", "Laptops", "Portátiles"),
    ("desktops", "Desktops", "Ordenadores de escritorio"),
    ("game_consoles", "Game Consoles", "Consolas de juegos"),
    ("smartwatches", "Smartwatches", "Relojes inteligentes"),
    ("other", "Other", "Otros"),
]


def get_prechecks_for_category(category: str, language: str = "en") -> list[dict]:
    """Return pre-check items for a device category.

    Tries database templates first, falls back to hardcoded defaults.
    Returns list of dicts with keys: check_key, label.
    """
    try:
        from app.models.device import DevicePreCheckTemplate
        templates = DevicePreCheckTemplate.query.filter_by(
            device_category=category, is_active=True
        ).order_by(DevicePreCheckTemplate.position).all()

        if templates:
            result = []
            for t in templates:
                label = t.label_es if language == "es" and t.label_es else t.label_en
                result.append({"check_key": t.check_key, "label": label})
            return result
    except Exception:
        pass

    # Fallback to hardcoded
    checks = _FALLBACK_CHECKS.get(category, _FALLBACK_CHECKS["other"])
    idx = 2 if language == "es" else 1
    return [{"check_key": c[0], "label": c[idx]} for c in checks]


def get_all_categories() -> list[dict]:
    """Return all device categories with labels."""
    return [{"key": k, "label_en": en, "label_es": es} for k, en, es in DEVICE_CATEGORIES]


def parse_precheck_results(form_data: dict, category: str) -> list[dict]:
    """Parse pre-check results from submitted form data.

    Pre-checks are submitted as precheck_<check_key> = "on" or absent.
    Returns list of dicts with check_key and passed (bool).
    """
    checks = get_prechecks_for_category(category)
    results = []
    for check in checks:
        key = f"precheck_{check['check_key']}"
        results.append({
            "check_key": check["check_key"],
            "label": check["label"],
            "passed": key in form_data,
        })
    return results


def format_precheck_notes(results: list[dict]) -> str:
    """Format pre-check results as a readable text block for notes."""
    if not results:
        return ""
    lines = ["Pre-check results:"]
    for r in results:
        mark = "[x]" if r["passed"] else "[ ]"
        lines.append(f"  {mark} {r['label']}")
    return "\n".join(lines)
