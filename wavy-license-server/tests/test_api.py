"""Integration tests for the FastAPI license server endpoints."""

from __future__ import annotations

import json
import hmac
import hashlib
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from database import get_db
from license_utils import generate_key
from models import Customer, License, TierEnum
from tests.conftest import TestingSession


# ── Helpers ───────────────────────────────────────────────────────────────────

def _seed_license(key: str, tier: str = "pro", active: bool = True,
                  activations: int = 0) -> None:
    """Insert a license row directly into the test database."""
    db = TestingSession()
    customer = Customer(email=f"test_{key[:4]}@example.com")
    db.add(customer)
    db.flush()
    lic = License(
        customer_id=customer.id,
        key=key,
        tier=TierEnum(tier),
        active=active,
        activations=activations,
    )
    db.add(lic)
    db.commit()
    db.close()


# ── /health ───────────────────────────────────────────────────────────────────

class TestHealth:
    def test_returns_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


# ── /activate ─────────────────────────────────────────────────────────────────

class TestActivate:
    def test_valid_activation(self, client, pro_key):
        _seed_license(pro_key)
        r = client.post("/activate", json={"key": pro_key, "email": "alice@example.com"})
        assert r.status_code == 200
        data = r.json()
        assert data["valid"] is True
        assert data["tier"] == "pro"

    def test_invalid_key_format(self, client):
        r = client.post("/activate", json={"key": "INVALID-KEY", "email": "x@x.com"})
        assert r.status_code == 400

    def test_key_not_in_db(self, client, pro_key):
        # Key is cryptographically valid but not seeded in the database.
        r = client.post("/activate", json={"key": pro_key, "email": "x@x.com"})
        assert r.status_code == 404

    def test_inactive_key(self, client, pro_key):
        _seed_license(pro_key, active=False)
        r = client.post("/activate", json={"key": pro_key, "email": "x@x.com"})
        assert r.status_code == 403

    def test_seat_limit_enforced(self, client, pro_key):
        _seed_license(pro_key, activations=2)  # already at limit
        r = client.post("/activate", json={"key": pro_key, "email": "x@x.com"})
        assert r.status_code == 403
        assert "2 machines" in r.json()["detail"]

    def test_activation_increments_counter(self, client, pro_key):
        _seed_license(pro_key, activations=0)
        client.post("/activate", json={"key": pro_key, "email": "y@y.com"})
        db = TestingSession()
        lic = db.query(License).filter_by(key=pro_key).first()
        assert lic.activations == 1
        db.close()

    def test_creates_customer_record(self, client, pro_key):
        _seed_license(pro_key)
        client.post("/activate", json={"key": pro_key, "email": "new@example.com"})
        db = TestingSession()
        cust = db.query(Customer).filter_by(email="new@example.com").first()
        assert cust is not None
        db.close()


# ── /validate ─────────────────────────────────────────────────────────────────

class TestValidate:
    def test_valid_key(self, client, pro_key):
        _seed_license(pro_key)
        r = client.post("/validate", json={"key": pro_key})
        assert r.status_code == 200
        data = r.json()
        assert data["valid"] is True
        assert data["tier"] == "pro"
        assert data["active"] is True

    def test_invalid_key_returns_free(self, client):
        r = client.post("/validate", json={"key": "BAD-KEY-XXXXXXXX"})
        assert r.status_code == 200
        data = r.json()
        assert data["valid"] is False
        assert data["tier"] == "free"

    def test_inactive_key(self, client, pro_key):
        _seed_license(pro_key, active=False)
        r = client.post("/validate", json={"key": pro_key})
        assert r.status_code == 200
        assert r.json()["active"] is False

    def test_updates_last_validated(self, client, pro_key):
        _seed_license(pro_key)
        client.post("/validate", json={"key": pro_key})
        db = TestingSession()
        lic = db.query(License).filter_by(key=pro_key).first()
        assert lic.last_validated is not None
        db.close()


# ── /deactivate ───────────────────────────────────────────────────────────────

class TestDeactivate:
    def test_decrements_activation_count(self, client, pro_key):
        _seed_license(pro_key, activations=2)
        r = client.post("/deactivate", json={"key": pro_key})
        assert r.status_code == 200
        db = TestingSession()
        lic = db.query(License).filter_by(key=pro_key).first()
        assert lic.activations == 1
        db.close()

    def test_does_not_go_below_zero(self, client, pro_key):
        _seed_license(pro_key, activations=0)
        client.post("/deactivate", json={"key": pro_key})
        db = TestingSession()
        lic = db.query(License).filter_by(key=pro_key).first()
        assert lic.activations == 0
        db.close()

    def test_unknown_key_still_200(self, client, pro_key):
        r = client.post("/deactivate", json={"key": pro_key})
        assert r.status_code == 200


# ── /resend-key ───────────────────────────────────────────────────────────────

class TestResendKey:
    def test_sends_email_to_known_customer(self, client, pro_key):
        _seed_license(pro_key)
        # Retrieve the email the seed helper used
        db = TestingSession()
        lic = db.query(License).filter_by(key=pro_key).first()
        email = lic.customer.email
        db.close()

        with patch("main.send_license_email") as mock_send:
            r = client.post("/resend-key", json={"email": email})
            assert r.status_code == 200
            mock_send.assert_called_once_with(email, pro_key, "pro")

    def test_unknown_email_returns_200(self, client):
        """Should return 200 even for unknown emails (no info leakage)."""
        r = client.post("/resend-key", json={"email": "nobody@example.com"})
        assert r.status_code == 200

    def test_inactive_license_not_resent(self, client, pro_key):
        _seed_license(pro_key, active=False)
        db = TestingSession()
        lic = db.query(License).filter_by(key=pro_key).first()
        email = lic.customer.email
        db.close()
        with patch("main.send_license_email") as mock_send:
            client.post("/resend-key", json={"email": email})
            mock_send.assert_not_called()


# ── /webhooks/stripe ──────────────────────────────────────────────────────────

def _stripe_sig(payload: bytes, secret: str) -> str:
    """Compute a Stripe-compatible webhook signature for testing."""
    timestamp = "1700000000"
    signed = f"{timestamp}.{payload.decode()}"
    mac = hmac.new(secret.encode(), signed.encode(), hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={mac}"


WEBHOOK_SECRET = "whsec_fake"

CHECKOUT_PAYLOAD = {
    "type": "checkout.session.completed",
    "data": {
        "object": {
            "id": "cs_test_123",
            "customer": "cus_test_456",
            "subscription": "sub_test_789",
            "customer_details": {"email": "buyer@example.com"},
        }
    },
}

CANCEL_PAYLOAD = {
    "type": "customer.subscription.deleted",
    "data": {"object": {"id": "sub_test_789"}},
}


class TestStripeWebhook:
    def _post_webhook(self, client, payload: dict):
        body = json.dumps(payload).encode()
        sig = _stripe_sig(body, WEBHOOK_SECRET)
        return client.post(
            "/webhooks/stripe",
            content=body,
            headers={"stripe-signature": sig, "content-type": "application/json"},
        )

    def test_invalid_signature_rejected(self, client):
        body = json.dumps(CHECKOUT_PAYLOAD).encode()
        r = client.post(
            "/webhooks/stripe",
            content=body,
            headers={"stripe-signature": "t=0,v1=bad", "content-type": "application/json"},
        )
        assert r.status_code == 400

    def test_checkout_creates_license(self, client):
        with (
            patch("stripe.Webhook.construct_event") as mock_event,
            patch("stripe.checkout.Session.list_line_items") as mock_items,
            patch("main.send_license_email"),
        ):
            mock_event.return_value = CHECKOUT_PAYLOAD
            mock_item = MagicMock()
            mock_item.price.id = "price_pro_test"
            mock_items.return_value = MagicMock(data=[mock_item])

            r = self._post_webhook(client, CHECKOUT_PAYLOAD)
            assert r.status_code == 200

            db = TestingSession()
            lic = db.query(License).filter_by(stripe_sub_id="sub_test_789").first()
            assert lic is not None
            assert lic.tier == TierEnum.pro
            assert lic.active is True
            db.close()

    def test_subscription_cancelled_deactivates_license(self, client, pro_key):
        _seed_license(pro_key)
        db = TestingSession()
        lic = db.query(License).filter_by(key=pro_key).first()
        lic.stripe_sub_id = "sub_test_789"
        db.commit()
        db.close()

        with patch("stripe.Webhook.construct_event") as mock_event:
            mock_event.return_value = CANCEL_PAYLOAD
            r = self._post_webhook(client, CANCEL_PAYLOAD)
            assert r.status_code == 200

        db = TestingSession()
        lic = db.query(License).filter_by(key=pro_key).first()
        assert lic.active is False
        db.close()

    def test_subscription_paused_deactivates_license(self, client, pro_key):
        """customer.subscription.paused should mark the license inactive."""
        _seed_license(pro_key)
        db = TestingSession()
        lic = db.query(License).filter_by(key=pro_key).first()
        lic.stripe_sub_id = "sub_paused_001"
        db.commit()
        db.close()

        pause_payload = {
            "type": "customer.subscription.paused",
            "data": {"object": {"id": "sub_paused_001"}},
        }
        with patch("stripe.Webhook.construct_event") as mock_event:
            mock_event.return_value = pause_payload
            r = self._post_webhook(client, pause_payload)
            assert r.status_code == 200

        db = TestingSession()
        lic = db.query(License).filter_by(key=pro_key).first()
        assert lic.active is False
        db.close()

    def test_subscription_resumed_reactivates_license(self, client, pro_key):
        """customer.subscription.resumed should mark the license active again."""
        _seed_license(pro_key, active=False)
        db = TestingSession()
        lic = db.query(License).filter_by(key=pro_key).first()
        lic.stripe_sub_id = "sub_resumed_001"
        db.commit()
        db.close()

        resume_payload = {
            "type": "customer.subscription.resumed",
            "data": {"object": {"id": "sub_resumed_001"}},
        }
        with patch("stripe.Webhook.construct_event") as mock_event:
            mock_event.return_value = resume_payload
            r = self._post_webhook(client, resume_payload)
            assert r.status_code == 200

        db = TestingSession()
        lic = db.query(License).filter_by(key=pro_key).first()
        assert lic.active is True
        db.close()

    def test_unknown_event_type_ignored(self, client):
        """Unrecognised event types should return 200 without error."""
        unknown_payload = {
            "type": "customer.subscription.trial_will_end",
            "data": {"object": {"id": "sub_trial_001"}},
        }
        with patch("stripe.Webhook.construct_event") as mock_event:
            mock_event.return_value = unknown_payload
            r = self._post_webhook(client, unknown_payload)
        assert r.status_code == 200
        assert r.json() == {"received": True}

    def test_checkout_sends_license_email(self, client):
        """Completing checkout must send a license key email to the buyer."""
        with (
            patch("stripe.Webhook.construct_event") as mock_event,
            patch("stripe.checkout.Session.list_line_items") as mock_items,
            patch("main.send_license_email") as mock_send,
        ):
            mock_event.return_value = CHECKOUT_PAYLOAD
            mock_item = MagicMock()
            mock_item.price.id = "price_pro_test"
            mock_items.return_value = MagicMock(data=[mock_item])

            self._post_webhook(client, CHECKOUT_PAYLOAD)

        assert mock_send.called
        call_args = mock_send.call_args
        assert call_args[0][0] == "buyer@example.com"  # email
        assert call_args[0][2] == "pro"                # tier


# ── /account/* endpoints ──────────────────────────────────────────────────────

class TestAccountEndpoints:
    """
    Tests for the Supabase-backed account auth endpoints.

    When SUPABASE_URL is empty (default in tests), all endpoints return 503.
    With SUPABASE_URL set, supabase_sync is mocked to verify the routing logic.
    """

    def test_login_returns_503_when_supabase_not_configured(self, client):
        r = client.post("/account/login",
                        json={"email": "user@example.com", "password": "pass"})
        assert r.status_code == 503
        assert "not configured" in r.json()["detail"]

    def test_verify_returns_503_when_supabase_not_configured(self, client):
        r = client.post("/account/verify", json={"access_token": "fake.jwt.token"})
        assert r.status_code == 503

    def test_refresh_returns_503_when_supabase_not_configured(self, client):
        r = client.post("/account/refresh", json={"refresh_token": "fake_refresh"})
        assert r.status_code == 503

    def test_login_returns_tokens_and_tier(self, client):
        sb_auth = {
            "access_token": "access.jwt.here",
            "refresh_token": "refresh.token.here",
            "expires_in": 3600,
            "user": {"id": "uuid-1234", "email": "user@example.com"},
        }
        sb_profile = {"tier": "pro"}

        with (
            patch("main.settings.supabase_url", "https://fake.supabase.co"),
            patch("main.settings.supabase_anon_key", "anon-key"),
            patch("main._supabase_available", return_value=True),
            patch("supabase_sync.login_with_password", return_value=sb_auth),
            patch("supabase_sync.get_profile", return_value=sb_profile),
        ):
            r = client.post("/account/login",
                            json={"email": "user@example.com", "password": "secret"})

        assert r.status_code == 200
        data = r.json()
        assert data["access_token"] == "access.jwt.here"
        assert data["tier"] == "pro"
        assert data["email"] == "user@example.com"
        assert data["expires_in"] == 3600

    def test_login_returns_401_on_bad_credentials(self, client):
        with (
            patch("main._supabase_available", return_value=True),
            patch("supabase_sync.login_with_password",
                  side_effect=ValueError("Invalid email or password.")),
        ):
            r = client.post("/account/login",
                            json={"email": "x@x.com", "password": "wrong"})

        assert r.status_code == 401
        assert "Invalid" in r.json()["detail"]

    def test_verify_valid_token_returns_tier(self, client):
        sb_user = {"id": "uuid-5678", "email": "pro@example.com"}
        sb_profile = {"tier": "studio"}

        with (
            patch("main._supabase_available", return_value=True),
            patch("supabase_sync.get_user", return_value=sb_user),
            patch("supabase_sync.get_profile", return_value=sb_profile),
        ):
            r = client.post("/account/verify",
                            json={"access_token": "valid.jwt.token"})

        assert r.status_code == 200
        data = r.json()
        assert data["valid"] is True
        assert data["tier"] == "studio"
        assert data["email"] == "pro@example.com"

    def test_verify_invalid_token_returns_free(self, client):
        with (
            patch("main._supabase_available", return_value=True),
            patch("supabase_sync.get_user", side_effect=Exception("Unauthorized")),
        ):
            r = client.post("/account/verify",
                            json={"access_token": "bad.token"})

        assert r.status_code == 200
        data = r.json()
        assert data["valid"] is False
        assert data["tier"] == "free"

    def test_refresh_returns_new_tokens(self, client):
        new_tokens = {
            "access_token": "new.access.token",
            "refresh_token": "new.refresh.token",
            "expires_in": 3600,
        }

        with (
            patch("main._supabase_available", return_value=True),
            patch("supabase_sync.refresh_access_token", return_value=new_tokens),
        ):
            r = client.post("/account/refresh",
                            json={"refresh_token": "old.refresh.token"})

        assert r.status_code == 200
        data = r.json()
        assert data["access_token"] == "new.access.token"
        assert data["refresh_token"] == "new.refresh.token"

    def test_refresh_returns_401_on_failure(self, client):
        with (
            patch("main._supabase_available", return_value=True),
            patch("supabase_sync.refresh_access_token",
                  side_effect=Exception("Invalid refresh token")),
        ):
            r = client.post("/account/refresh",
                            json={"refresh_token": "expired.token"})

        assert r.status_code == 401
