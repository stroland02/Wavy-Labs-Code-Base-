"""
Thin synchronous wrapper around the Supabase REST and Auth APIs.

Used by the Wavy Labs license server to:
  - Authenticate users (email + password → JWT)
  - Verify access tokens
  - Read / upsert user profiles (tier, Stripe IDs)
  - Refresh access tokens
  - Look up Supabase user IDs by email (for Stripe webhook sync)

All calls are synchronous (httpx) because FastAPI endpoints are sync here.
Set SUPABASE_URL, SUPABASE_ANON_KEY, and SUPABASE_SERVICE_KEY in .env
to enable account-based auth.  If SUPABASE_URL is empty the functions raise
RuntimeError so callers can return a 503 gracefully.
"""

from __future__ import annotations

import httpx
from loguru import logger

from config import settings


# ── Internal helpers ─────────────────────────────────────────────────────────

def _base() -> str:
    url = settings.supabase_url.rstrip("/")
    if not url:
        raise RuntimeError("SUPABASE_URL is not configured.")
    return url


def _anon_headers() -> dict:
    return {
        "apikey": settings.supabase_anon_key,
        "Content-Type": "application/json",
    }


def _service_headers() -> dict:
    return {
        "apikey": settings.supabase_service_key,
        "Authorization": f"Bearer {settings.supabase_service_key}",
        "Content-Type": "application/json",
    }


# ── Auth ─────────────────────────────────────────────────────────────────────

def login_with_password(email: str, password: str) -> dict:
    """Authenticate a user; return Supabase auth payload (access_token, etc.)."""
    resp = httpx.post(
        f"{_base()}/auth/v1/token?grant_type=password",
        headers=_anon_headers(),
        json={"email": email, "password": password},
        timeout=20,
    )
    if resp.status_code in (400, 401, 422):
        body = ""
        try:
            body = resp.json().get("error_description") or resp.json().get("msg") or resp.text
        except Exception:
            body = resp.text
        logger.warning(f"Supabase auth denied ({resp.status_code}): {body}")
        raise ValueError("Invalid email or password.")
    if not resp.is_success:
        logger.error(f"Supabase auth unexpected status {resp.status_code}: {resp.text[:300]}")
        resp.raise_for_status()
    return resp.json()


def get_user(access_token: str) -> dict:
    """Verify an access token and return the Supabase user object."""
    resp = httpx.get(
        f"{_base()}/auth/v1/user",
        headers={
            "apikey": settings.supabase_anon_key,
            "Authorization": f"Bearer {access_token}",
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def refresh_access_token(refresh_token: str) -> dict:
    """Exchange a refresh token for a new access token."""
    resp = httpx.post(
        f"{_base()}/auth/v1/token?grant_type=refresh_token",
        headers=_anon_headers(),
        json={"refresh_token": refresh_token},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


# ── Profiles ─────────────────────────────────────────────────────────────────

def get_profile(user_id: str) -> dict:
    """
    Fetch a user's profile row and normalise to internal field names.

    The live Supabase schema (from the website) uses:
      subscription_plan   → our internal "tier"  (free / pro / studio)
      subscription_status → our internal "sub_status"
      stripe_customer_id  → our internal "stripe_customer"
    """
    resp = httpx.get(
        f"{_base()}/rest/v1/profiles",
        headers=_service_headers(),
        params={
            "id": f"eq.{user_id}",
            "select": "subscription_plan,subscription_status,stripe_customer_id",
        },
        timeout=10,
    )
    resp.raise_for_status()
    rows = resp.json()
    if not rows:
        return {"tier": "free"}
    row = rows[0]
    return {
        "tier":           row.get("subscription_plan", "free") or "free",
        "sub_status":     row.get("subscription_status", "none") or "none",
        "stripe_customer": row.get("stripe_customer_id"),
    }


def upsert_profile(user_id: str, email: str, **fields) -> None:
    """
    Create or update a profile row using the service role key.

    Accepts internal field names (tier, sub_status, stripe_customer) and
    maps them to the website's actual column names before writing.
    """
    # Map internal names → live Supabase column names
    column_map = {
        "tier":           "subscription_plan",
        "sub_status":     "subscription_status",
        "stripe_customer": "stripe_customer_id",
        "stripe_sub_id":  "stripe_customer_id",   # legacy alias
    }
    payload: dict = {"id": user_id, "email": email}
    for k, v in fields.items():
        col = column_map.get(k, k)
        payload[col] = v

    resp = httpx.post(
        f"{_base()}/rest/v1/profiles",
        headers={
            **_service_headers(),
            "Prefer": "resolution=merge-duplicates,return=minimal",
        },
        json=payload,
        timeout=10,
    )
    resp.raise_for_status()


def find_user_id_by_email(email: str) -> str | None:
    """
    Find a Supabase auth user ID by email using the admin API.
    Requires service_role key.  Returns None on failure.
    """
    try:
        resp = httpx.get(
            f"{_base()}/auth/v1/admin/users",
            headers=_service_headers(),
            params={"page": 1, "per_page": 1000},
            timeout=15,
        )
        resp.raise_for_status()
        for user in resp.json().get("users", []):
            if user.get("email", "").lower() == email.lower():
                return user["id"]
    except Exception as exc:
        logger.warning(f"find_user_id_by_email failed for {email}: {exc}")
    return None
