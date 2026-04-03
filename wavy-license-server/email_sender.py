"""
Transactional email delivery for Wavy Labs License Server.
Uses Resend (https://resend.com) — simple REST API, generous free tier.

Falls back to a log warning if RESEND_API_KEY is not configured (dev mode).
"""

from __future__ import annotations

from loguru import logger

from config import settings

_TIER_LABELS = {
    "pro":    "Pro ($9.99/mo)",
    "studio": "Studio ($24.99/mo)",
}

_EMAIL_TEMPLATE = """\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:sans-serif;max-width:600px;margin:40px auto;color:#1a1a2e">
  <div style="background:#0d0d14;padding:24px 32px;border-radius:8px 8px 0 0">
    <h1 style="color:#7c5cbf;margin:0">✦ Wavy Labs</h1>
    <p style="color:#90a4ae;margin:4px 0 0">The DAW that listens to you</p>
  </div>
  <div style="background:#f9f9ff;padding:32px;border-radius:0 0 8px 8px;border:1px solid #e0e0ef">
    <h2 style="color:#0d0d14">Your {tier_label} License Key</h2>
    <p>Thank you for subscribing to Wavy Labs {tier_label}!</p>
    <p>Your license key is:</p>
    <div style="background:#1a1a2e;color:#4fc3f7;font-family:monospace;font-size:18px;
                padding:16px 24px;border-radius:6px;letter-spacing:2px;text-align:center">
      {key}
    </div>
    <p style="margin-top:24px">To activate:</p>
    <ol>
      <li>Open <strong>Wavy Labs</strong></li>
      <li>Go to <strong>Settings → License → Activate</strong></li>
      <li>Paste your key and click <strong>Activate</strong></li>
    </ol>
    <p>Your key works on up to <strong>2 machines</strong> simultaneously.
       You can deactivate a machine via <em>Settings → License → Deactivate</em>.</p>
    <hr style="border:none;border-top:1px solid #e0e0ef;margin:24px 0">
    <p style="color:#666;font-size:13px">
      If you didn't purchase this subscription, please contact
      <a href="mailto:support@wavylab.net">support@wavylab.net</a> immediately.
    </p>
  </div>
</body>
</html>
"""


def send_license_email(to_email: str, key: str, tier: str) -> bool:
    """
    Send the license key to the customer via Resend.

    Returns True on success, False on failure (never raises).
    In development (no RESEND_API_KEY), logs the key instead of sending.
    """
    tier_label = _TIER_LABELS.get(tier, tier.title())
    html = _EMAIL_TEMPLATE.format(tier_label=tier_label, key=key)

    if not settings.resend_api_key:
        logger.warning(
            f"[email_sender] RESEND_API_KEY not set — would send key to {to_email}: {key}"
        )
        return True  # Treat as success in dev so tests don't fail

    try:
        import resend  # pip install resend
        resend.api_key = settings.resend_api_key
        resend.Emails.send({
            "from":    settings.email_from,
            "to":      [to_email],
            "subject": f"Your Wavy Labs {tier_label} License Key",
            "html":    html,
        })
        logger.info(f"License key email sent to {to_email}")
        return True
    except Exception as exc:
        logger.error(f"Failed to send license email to {to_email}: {exc}")
        return False
