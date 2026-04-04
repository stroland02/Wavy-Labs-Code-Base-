"""License key generation and HMAC validation (must match the C++ implementation)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import string
from datetime import datetime

from config import settings


def _hmac8(payload: str) -> str:
    """Compute the first 8 hex chars of HMAC-SHA256(payload, secret)."""
    h = hmac.new(
        settings.license_hmac_secret.encode(),
        msg=payload.encode(),
        digestmod=hashlib.sha256,
    )
    return h.hexdigest()[:8]


def generate_key(tier: str) -> str:
    """
    Generate a new license key.
    Format: {PREFIX}-{RANDOM16}-{HMAC8}
    Where PREFIX = "PRO" | "STU"
    """
    prefix = {"pro": "PRO", "studio": "STU"}.get(tier.lower(), "PRO")
    alphabet = string.ascii_uppercase + string.digits
    random_part = "".join(secrets.choice(alphabet) for _ in range(16))
    payload = f"{prefix}-{random_part}"
    hmac_part = _hmac8(payload)
    return f"{payload}-{hmac_part}"


def validate_key(key: str) -> tuple[bool, str]:
    """
    Validate a license key.
    Returns (valid: bool, tier: str)  e.g. (True, "pro")
    """
    parts = key.split("-")
    if len(parts) < 3:
        return False, ""

    prefix    = parts[0]
    hmac_part = parts[-1]
    payload   = key[: len(key) - len(hmac_part) - 1]

    expected = _hmac8(payload)
    if not hmac.compare_digest(expected, hmac_part.lower()):
        return False, ""

    tier = {"PRO": "pro", "STU": "studio"}.get(prefix, "")
    if not tier:
        return False, ""

    return True, tier
