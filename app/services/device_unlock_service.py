"""Secure device unlock/access data handling.

Uses authenticated encryption built from Python stdlib primitives:
- Key derivation: PBKDF2-HMAC-SHA256 with a per-app salt from SECRET_KEY
- Encryption: CTR-mode stream cipher using HMAC-SHA256 as the keystream PRF
- Authentication: HMAC-SHA256 tag over (nonce + ciphertext) to detect tampering

Wire format (base64url-encoded):
    version (1 byte) | nonce (16 bytes) | ciphertext (N bytes) | HMAC tag (32 bytes)

Backward compatibility:
    - Decryption attempts the new v1 format first.
    - If that fails (wrong version byte or bad HMAC), it falls back to the
      legacy XOR+base64 format from Phase 18, so existing stored values
      continue to work without a data migration.
    - New writes always use the v1 authenticated format.

Config:
    DEVICE_UNLOCK_KEY: Optional dedicated key (defaults to SECRET_KEY).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os

from flask import current_app

logger = logging.getLogger(__name__)

_VERSION_1 = b"\x01"
_NONCE_SIZE = 16
_HMAC_SIZE = 32
_KDF_ITERATIONS = 100_000
_KDF_SALT = b"ironcore-unlock-kdf-v1"


# ---------------------------------------------------------------------------
# Key derivation
# ---------------------------------------------------------------------------

def _get_master_key() -> bytes:
    """Derive a 32-byte master key using PBKDF2."""
    secret = current_app.config.get("DEVICE_UNLOCK_KEY") or current_app.config.get("SECRET_KEY", "dev-secret")
    return hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), _KDF_SALT, _KDF_ITERATIONS)


def _derive_keys(master: bytes) -> tuple[bytes, bytes]:
    """Derive separate encryption and authentication keys from the master key."""
    enc_key = hmac.new(master, b"enc", hashlib.sha256).digest()
    mac_key = hmac.new(master, b"mac", hashlib.sha256).digest()
    return enc_key, mac_key


# ---------------------------------------------------------------------------
# CTR-mode stream cipher using HMAC-SHA256 as PRF
# ---------------------------------------------------------------------------

def _ctr_keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    """Generate *length* bytes of keystream in CTR mode."""
    blocks = []
    counter = 0
    while len(b"".join(blocks)) < length:
        block_input = nonce + counter.to_bytes(4, "big")
        blocks.append(hmac.new(key, block_input, hashlib.sha256).digest())
        counter += 1
    return b"".join(blocks)[:length]


def _xor_bytes(a: bytes, b_: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b_))


# ---------------------------------------------------------------------------
# Public API — encrypt / decrypt
# ---------------------------------------------------------------------------

def encrypt_unlock_value(plaintext: str) -> str:
    """Encrypt a device unlock value with authenticated encryption.

    Returns a base64url-encoded string containing version, nonce,
    ciphertext, and HMAC tag.
    """
    if not plaintext:
        return ""
    master = _get_master_key()
    enc_key, mac_key = _derive_keys(master)

    nonce = os.urandom(_NONCE_SIZE)
    plaintext_bytes = plaintext.encode("utf-8")
    keystream = _ctr_keystream(enc_key, nonce, len(plaintext_bytes))
    ciphertext = _xor_bytes(plaintext_bytes, keystream)

    # Authenticate: HMAC over version + nonce + ciphertext
    payload = _VERSION_1 + nonce + ciphertext
    tag = hmac.new(mac_key, payload, hashlib.sha256).digest()

    return base64.urlsafe_b64encode(payload + tag).decode("utf-8")


def decrypt_unlock_value(ciphertext: str) -> str:
    """Decrypt a device unlock value.

    Tries v1 authenticated format first, falls back to legacy XOR+base64.
    """
    if not ciphertext:
        return ""
    try:
        raw = base64.urlsafe_b64decode(ciphertext.encode("utf-8"))
    except Exception:
        return ""

    # Try v1 authenticated decryption
    if len(raw) >= 1 + _NONCE_SIZE + _HMAC_SIZE + 1 and raw[0:1] == _VERSION_1:
        result = _decrypt_v1(raw)
        if result is not None:
            return result

    # Fallback: legacy XOR+base64 (Phase 18 original format)
    return _decrypt_legacy(raw)


def _decrypt_v1(raw: bytes) -> str | None:
    """Attempt v1 authenticated decryption. Returns None on failure."""
    try:
        master = _get_master_key()
        enc_key, mac_key = _derive_keys(master)

        tag = raw[-_HMAC_SIZE:]
        payload = raw[:-_HMAC_SIZE]

        # Verify HMAC
        expected_tag = hmac.new(mac_key, payload, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expected_tag):
            return None

        nonce = payload[1:1 + _NONCE_SIZE]
        ciphertext = payload[1 + _NONCE_SIZE:]

        keystream = _ctr_keystream(enc_key, nonce, len(ciphertext))
        plaintext_bytes = _xor_bytes(ciphertext, keystream)
        return plaintext_bytes.decode("utf-8")
    except Exception as e:
        logger.debug("v1 decryption failed: %s", e)
        return None


def _decrypt_legacy(raw: bytes) -> str:
    """Decrypt using the legacy XOR+base64 format from Phase 18."""
    try:
        secret = current_app.config.get("SECRET_KEY", "dev-secret")
        key = hashlib.sha256(secret.encode("utf-8")).digest()
        key_cycle = (key * ((len(raw) // len(key)) + 1))[:len(raw)]
        plaintext = bytes(a ^ b for a, b in zip(raw, key_cycle))
        return plaintext.decode("utf-8")
    except Exception as e:
        logger.warning("Legacy decryption failed: %s", e)
        return ""


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def mask_unlock_value(plaintext: str) -> str:
    """Mask an unlock value for display: show last 2 chars only."""
    if not plaintext:
        return ""
    if len(plaintext) <= 2:
        return "••"
    return "•" * (len(plaintext) - 2) + plaintext[-2:]


# ---------------------------------------------------------------------------
# Device-level operations
# ---------------------------------------------------------------------------

def set_device_unlock(device, unlock_type: str | None, unlock_value: str | None, unlock_notes: str | None) -> None:
    """Set unlock data on a device with authenticated encryption."""
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
