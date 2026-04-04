"""
Wavy Labs License Server — FastAPI application.
Handles license key activation, deactivation, and Stripe webhook events.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import stripe
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from config import settings
from database import get_db, init_db
from email_sender import send_license_email
from license_utils import generate_key, validate_key
from models import Customer, License, TierEnum

MAX_ACTIVATIONS = 2  # number of machines per license

# ── App setup ─────────────────────────────────────────────────────────────────

stripe.api_key = settings.stripe_secret_key


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    logger.info("Wavy Labs license server started.")
    yield


app = FastAPI(
    title="Wavy Labs License API",
    version="1.0.0",
    docs_url="/docs" if settings.app_env == "development" else None,
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ── Schemas ───────────────────────────────────────────────────────────────────

class ActivateRequest(BaseModel):
    key:   str
    email: EmailStr

class ActivateResponse(BaseModel):
    valid:   bool
    tier:    str
    message: str

class ValidateRequest(BaseModel):
    key: str

class ValidateResponse(BaseModel):
    valid:  bool
    tier:   str
    active: bool


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "wavy-license-server"}


@app.post("/activate", response_model=ActivateResponse)
def activate(req: ActivateRequest, db: Session = Depends(get_db)) -> ActivateResponse:
    """
    Validate a license key and associate it with an email.
    Called by the C++ app when the user enters a key for the first time.
    """
    valid, tier = validate_key(req.key)
    if not valid:
        raise HTTPException(status_code=400, detail="Invalid license key.")

    license_row = db.query(License).filter_by(key=req.key).first()
    if license_row is None:
        raise HTTPException(status_code=404, detail="License key not found.")
    if not license_row.active:
        raise HTTPException(status_code=403, detail="License key is inactive.")
    if license_row.activations >= MAX_ACTIVATIONS:
        raise HTTPException(
            status_code=403,
            detail=f"License already activated on {MAX_ACTIVATIONS} machines. "
                   "Deactivate one before activating here.",
        )

    # Create or update customer record
    customer = db.query(Customer).filter_by(email=req.email).first()
    if customer is None:
        customer = Customer(email=req.email)
        db.add(customer)
        db.flush()

    license_row.customer_id    = customer.id
    license_row.activations   += 1
    license_row.last_validated = datetime.now(timezone.utc)
    db.commit()

    logger.info(f"Activated {tier} key for {req.email}")
    return ActivateResponse(valid=True, tier=tier,
                            message=f"{tier.title()} license activated.")


@app.post("/validate", response_model=ValidateResponse)
def validate(req: ValidateRequest, db: Session = Depends(get_db)) -> ValidateResponse:
    """
    Re-validate an existing license (called periodically by the app).
    Allows 7-day grace period if the server is unreachable on the client side.
    """
    valid, tier = validate_key(req.key)
    if not valid:
        return ValidateResponse(valid=False, tier="free", active=False)

    license_row = db.query(License).filter_by(key=req.key).first()
    if license_row is None:
        return ValidateResponse(valid=False, tier="free", active=False)

    license_row.last_validated = datetime.now(timezone.utc)
    db.commit()

    return ValidateResponse(valid=True, tier=tier, active=license_row.active)


@app.post("/deactivate")
def deactivate(req: ValidateRequest, db: Session = Depends(get_db)) -> dict:
    """
    Decrement the activation count for a license key (machine un-registration).
    If the key belongs to a cancelled subscription it is also marked inactive.
    """
    license_row = db.query(License).filter_by(key=req.key).first()
    if license_row:
        license_row.activations = max(0, license_row.activations - 1)
        db.commit()
    return {"deactivated": True}


class ResendKeyRequest(BaseModel):
    email: EmailStr


# ── Account endpoints (Supabase-backed) ──────────────────────────────────────

class AccountLoginRequest(BaseModel):
    email:    str
    password: str

class AccountLoginResponse(BaseModel):
    access_token:  str
    refresh_token: str
    expires_in:    int
    tier:          str
    email:         str

class AccountVerifyRequest(BaseModel):
    access_token: str

class AccountVerifyResponse(BaseModel):
    valid: bool
    tier:  str
    email: str

class AccountRefreshRequest(BaseModel):
    refresh_token: str

class AccountRefreshResponse(BaseModel):
    access_token:  str
    refresh_token: str
    expires_in:    int


def _supabase_available() -> bool:
    return bool(settings.supabase_url and settings.supabase_anon_key)


@app.post("/account/login", response_model=AccountLoginResponse)
def account_login(req: AccountLoginRequest) -> AccountLoginResponse:
    """
    Authenticate a DAW user via Supabase (email + password).
    Returns JWT tokens and the user's current subscription tier.
    """
    if not _supabase_available():
        raise HTTPException(
            status_code=503,
            detail="Account auth not configured on this server.",
        )

    try:
        import supabase_sync as sb
        auth = sb.login_with_password(req.email, req.password)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.error(f"Supabase login error [{type(exc).__name__}]: {exc}")
        raise HTTPException(status_code=502, detail="Auth service unavailable.") from exc

    user_id = auth.get("user", {}).get("id", "")
    try:
        profile = sb.get_profile(user_id) if user_id else {"tier": "free"}
    except Exception as exc:
        logger.warning(f"Could not fetch profile for {user_id}: {exc}")
        profile = {"tier": "free"}

    return AccountLoginResponse(
        access_token=auth["access_token"],
        refresh_token=auth["refresh_token"],
        expires_in=auth.get("expires_in", 3600),
        tier=profile.get("tier", "free"),
        email=req.email,
    )


@app.post("/account/verify", response_model=AccountVerifyResponse)
def account_verify(req: AccountVerifyRequest) -> AccountVerifyResponse:
    """
    Verify a Supabase access token and return the user's current tier.
    Called by the DAW periodically (within the grace period).
    """
    if not _supabase_available():
        raise HTTPException(
            status_code=503,
            detail="Account auth not configured on this server.",
        )

    try:
        import supabase_sync as sb
        user = sb.get_user(req.access_token)
    except Exception:
        return AccountVerifyResponse(valid=False, tier="free", email="")

    user_id = user.get("id", "")
    email   = user.get("email", "")
    try:
        profile = sb.get_profile(user_id) if user_id else {"tier": "free"}
    except Exception as exc:
        logger.warning(f"Could not fetch profile for {user_id}: {exc}")
        profile = {"tier": "free"}

    return AccountVerifyResponse(
        valid=True,
        tier=profile.get("tier", "free"),
        email=email,
    )


@app.post("/account/refresh", response_model=AccountRefreshResponse)
def account_refresh(req: AccountRefreshRequest) -> AccountRefreshResponse:
    """Refresh a Supabase access token using a refresh token."""
    if not _supabase_available():
        raise HTTPException(
            status_code=503,
            detail="Account auth not configured on this server.",
        )

    try:
        import supabase_sync as sb
        data = sb.refresh_access_token(req.refresh_token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Token refresh failed.") from exc

    return AccountRefreshResponse(
        access_token=data["access_token"],
        refresh_token=data["refresh_token"],
        expires_in=data.get("expires_in", 3600),
    )


@app.post("/resend-key")
def resend_key(req: ResendKeyRequest, db: Session = Depends(get_db)) -> dict:
    """Re-send the license key to the customer's email address."""
    customer = db.query(Customer).filter_by(email=req.email).first()
    if customer is None:
        # Return 200 regardless — don't leak whether the email exists.
        return {"sent": True}

    active_licenses = [
        lic for lic in customer.licenses if lic.active
    ]
    for lic in active_licenses:
        send_license_email(req.email, lic.key, lic.tier.value)

    return {"sent": True}


# ── Stripe webhook ────────────────────────────────────────────────────────────

@app.post("/webhooks/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None),
    db: Session = Depends(get_db),
) -> dict:
    """Process Stripe subscription events to issue/revoke licenses."""
    payload = await request.body()

    try:
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, settings.stripe_webhook_secret
        )
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid Stripe signature.")

    event_type = event["type"]
    data = event["data"]["object"]

    if event_type == "checkout.session.completed":
        _handle_checkout_completed(data, db)
    elif event_type in ("customer.subscription.deleted",
                        "customer.subscription.paused"):
        _handle_subscription_cancelled(data, db)
    elif event_type == "customer.subscription.resumed":
        _handle_subscription_resumed(data, db)

    return {"received": True}


def _tier_from_price(price_id: str) -> TierEnum:
    if price_id in settings.studio_price_ids:
        return TierEnum.studio
    if price_id in settings.pro_price_ids:
        return TierEnum.pro
    logger.warning(f"Unknown price_id {price_id!r} — defaulting to pro")
    return TierEnum.pro


def _handle_checkout_completed(session: dict, db: Session) -> None:
    email  = session.get("customer_details", {}).get("email", "")
    sub_id = session.get("subscription")

    # line_items are NOT included in the webhook payload by default —
    # retrieve them via the Stripe API.
    price_id = ""
    session_id = session.get("id")
    if session_id:
        try:
            items = stripe.checkout.Session.list_line_items(session_id, limit=1)
            price_id = (items.data[0].price.id if items.data else "")
        except Exception as exc:
            logger.warning(f"Could not fetch line items for session {session_id}: {exc}")

    tier = _tier_from_price(price_id)

    # Create customer
    customer = db.query(Customer).filter_by(email=email).first()
    if customer is None:
        stripe_cust = session.get("customer")
        customer = Customer(email=email, stripe_customer=stripe_cust)
        db.add(customer)
        db.flush()

    # Generate and store license key
    key = generate_key(tier.value)
    lic = License(
        customer_id=customer.id,
        key=key,
        tier=tier,
        stripe_sub_id=sub_id,
        active=True,
    )
    db.add(lic)
    db.commit()

    logger.info(f"New {tier.value} license issued to {email}: {key}")
    send_license_email(email, key, tier.value)

    # Sync tier to Supabase profile (if configured)
    if _supabase_available() and email:
        try:
            import supabase_sync as sb
            user_id = sb.find_user_id_by_email(email)
            if user_id:
                sb.upsert_profile(
                    user_id=user_id,
                    email=email,
                    tier=tier.value,
                    stripe_customer=customer.stripe_customer or "",
                    stripe_sub_id=sub_id or "",
                    sub_status="active",
                )
                logger.info(f"Synced {tier.value} tier to Supabase for {email}")
            else:
                logger.info(f"No Supabase account found for {email} — skipping sync")
        except Exception as exc:
            logger.warning(f"Supabase profile sync failed for {email}: {exc}")


def _handle_subscription_cancelled(sub: dict, db: Session) -> None:
    sub_id = sub.get("id")
    lic = db.query(License).filter_by(stripe_sub_id=sub_id).first()
    if lic:
        lic.active = False
        db.commit()
        logger.info(f"License deactivated for subscription {sub_id}")

    # Downgrade Supabase profile to free
    if _supabase_available() and lic:
        try:
            import supabase_sync as sb
            cust = db.query(Customer).filter_by(id=lic.customer_id).first()
            if cust:
                user_id = sb.find_user_id_by_email(cust.email)
                if user_id:
                    sb.upsert_profile(
                        user_id=user_id,
                        email=cust.email,
                        tier="free",
                        sub_status="cancelled",
                    )
        except Exception as exc:
            logger.warning(f"Supabase downgrade sync failed: {exc}")


def _handle_subscription_resumed(sub: dict, db: Session) -> None:
    sub_id = sub.get("id")
    lic = db.query(License).filter_by(stripe_sub_id=sub_id).first()
    if lic:
        lic.active = True
        db.commit()
        logger.info(f"License reactivated for subscription {sub_id}")

    # Re-upgrade Supabase profile
    if _supabase_available() and lic:
        try:
            import supabase_sync as sb
            cust = db.query(Customer).filter_by(id=lic.customer_id).first()
            if cust:
                user_id = sb.find_user_id_by_email(cust.email)
                if user_id:
                    sb.upsert_profile(
                        user_id=user_id,
                        email=cust.email,
                        tier=lic.tier.value,
                        sub_status="active",
                    )
        except Exception as exc:
            logger.warning(f"Supabase reactivation sync failed: {exc}")
