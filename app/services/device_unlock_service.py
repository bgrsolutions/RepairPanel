"""Secure device unlock/access data handling.

Provides obfuscation for device unlock values using base64 encoding
with a salt derived from the application SECRET_KEY.

NOTE: For production deployments with strict security requirements,
consider upgrading to Fernet encryption from the `cryptography` package.
The current implementation provides obfuscation (not stored in plain text)
suitable for the repair shop context where the main goal is preventing
casual exposure in the database and UI.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging

from flask import current_app

logger = logging.getLogger(__name__)


def _get_key() -> bytes:
    """Derive an obfuscation key from SECRET_KEY."""
    secret = current_app.config.get("SECRET_KEY", "dev-secret")
    return hashlib.sha256(secret.encode("utf-8")).digest()


def encrypt_unlock_value(plaintext: str) -> str:
    """Encode a device unlock value. Returns base64-encoded obfuscated string."""
    if not plaintext:
        return ""
    key = _get_key()
    # XOR obfuscation with key + base64 encoding
    key_cycle = (key * ((len(plaintext) // len(key)) + 1))[:len(plaintext)]
    obfuscated = bytes(a ^ b for a, b in zip(plaintext.encode("utf-8"), key_cycle))
    return base64.urlsafe_b64encode(obfuscated).decode("utf-8")


def decrypt_unlock_value(ciphertext: str) -> str:
    """Decode an obfuscated device unlock value."""
    if not ciphertext:
        return ""
    try:
        key = _get_key()
        obfuscated = base64.urlsafe_b64decode(ciphertext.encode("utf-8"))
        key_cycle = (key * ((len(obfuscated) // len(key)) + 1))[:len(obfuscated)]
        plaintext = bytes(a ^ b for a, b in zip(obfuscated, key_cycle))
        return plaintext.decode("utf-8")
    except Exception as e:
        logger.warning("Failed to decrypt unlock value: %s", e)
        return ""


def mask_unlock_value(plaintext: str) -> str:
    """Mask an unlock value for display: show last 2 chars only."""
    if not plaintext:
        return ""
    if len(plaintext) <= 2:
        return "••"
    return "•" * (len(plaintext) - 2) + plaintext[-2:]


def set_device_unlock(device, unlock_type: str | None, unlock_value: str | None, unlock_notes: str | None) -> None:
    """Set unlock data on a device with obfuscation."""
    device.unlock_type = unlock_type or None
    device.unlock_value_encrypted = encrypt_unlock_value(unlock_value) if unlock_value else None
    device.unlock_notes = unlock_notes or None


def get_device_unlock_display(device) -> dict:
    """Get unlock data for display, with masked value."""
    plaintext = decrypt_unlock_value(device.unlock_value_encrypted or "")
    return {
        "unlock_type": device.unlock_type or "",
        "unlock_value_masked": mask_unlock_value(plaintext),
        "unlock_value_plain": plaintext,
        "unlock_notes": device.unlock_notes or "",
        "has_unlock": bool(device.unlock_type),
    }
