"""Shared fixtures for the license server test suite."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Use an in-memory SQLite database for every test run — fast, isolated, no cleanup needed.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LICENSE_HMAC_SECRET", "test-secret-do-not-use-in-prod")
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_fake")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_fake")
os.environ.setdefault("STRIPE_PRO_PRICE_ID", "price_pro_test")
os.environ.setdefault("STRIPE_STUDIO_PRICE_ID", "price_studio_test")
os.environ.setdefault("RESEND_API_KEY", "")  # empty = dev mode, no actual emails sent
# Keep Supabase empty in tests — prevents real .env from enabling live auth calls
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_ANON_KEY"] = ""
os.environ["SUPABASE_SERVICE_KEY"] = ""

from database import Base, get_db  # noqa: E402 (must come after env vars are set)
from main import app                # noqa: E402


TEST_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSession = sessionmaker(bind=TEST_ENGINE, autocommit=False, autoflush=False)


def _get_test_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def fresh_db():
    """Create all tables before each test and drop them after."""
    Base.metadata.create_all(bind=TEST_ENGINE)
    app.dependency_overrides[get_db] = _get_test_db
    yield
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=TEST_ENGINE)


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def pro_key() -> str:
    """Return a freshly generated valid Pro license key."""
    from license_utils import generate_key
    return generate_key("pro")


@pytest.fixture()
def studio_key() -> str:
    from license_utils import generate_key
    return generate_key("studio")
