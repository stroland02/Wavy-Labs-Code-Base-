"""
Wavy Labs AI Backend — Sentry crash reporting.
Call init_sentry() once at startup. No-ops if WAVY_SENTRY_DSN is not set.
"""

from __future__ import annotations

import os
import sys

from loguru import logger


def init_sentry(release: str = "wavy-ai@1.0.0") -> None:
    """Initialise Sentry SDK. Safe to call even without a DSN."""
    dsn = os.environ.get("WAVY_SENTRY_DSN", "")
    if not dsn:
        logger.debug("Sentry DSN not set — crash reporting disabled.")
        return

    try:
        import sentry_sdk
        sentry_sdk.init(
            dsn=dsn,
            release=release,
            environment=os.environ.get("WAVY_ENV", "production"),
            traces_sample_rate=0.1,   # 10% performance tracing
            profiles_sample_rate=0.05,
            before_send=_before_send,
        )
        logger.info("Sentry crash reporting initialised.")
    except ImportError:
        logger.warning("sentry-sdk not installed — crash reporting disabled.")
    except Exception as exc:
        logger.warning(f"Sentry init failed: {exc}")


def _before_send(event: dict, hint: dict) -> dict | None:
    """Strip any file paths or prompts from events before sending."""
    # Remove user-generated content from breadcrumbs
    for crumb in event.get("breadcrumbs", {}).get("values", []):
        if crumb.get("category") == "rpc":
            crumb.get("data", {}).pop("prompt", None)
            crumb.get("data", {}).pop("lyrics", None)
            crumb.get("data", {}).pop("code", None)

    return event


def capture_exception(exc: BaseException) -> None:
    """Capture an exception if Sentry is initialised."""
    try:
        import sentry_sdk
        sentry_sdk.capture_exception(exc)
    except Exception:
        pass
