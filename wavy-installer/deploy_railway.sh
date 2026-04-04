#!/usr/bin/env bash
# =============================================================================
# Wavy Labs — Railway + Stripe Deploy Runbook
# Run this script once from the wavy-license-server/ directory.
# Prerequisites: railway CLI installed, Stripe CLI installed, .env configured.
# =============================================================================
set -euo pipefail

cd "$(dirname "$0")/../wavy-license-server"

echo "=== Wavy Labs License Server Deploy ==="
echo

# ── Step 1: Verify .env is configured ─────────────────────────────────────
if [ ! -f ".env" ]; then
    echo "ERROR: .env not found. Copy .env.example and fill in the values."
    echo "  cp .env.example .env && nano .env"
    exit 1
fi

# Source env for validation
set -a; source .env; set +a

REQUIRED_VARS=(LICENSE_HMAC_SECRET STRIPE_SECRET_KEY STRIPE_WEBHOOK_SECRET \
               STRIPE_PRO_PRICE_ID STRIPE_STUDIO_PRICE_ID)
MISSING=0
for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var:-}" ]; then
        echo "  MISSING: $var"
        MISSING=1
    fi
done
if [ "$MISSING" = "1" ]; then
    echo
    echo "Fill in all required vars in .env, then re-run."
    exit 1
fi
echo "✓ All required env vars present"

# ── Step 2: Run tests ──────────────────────────────────────────────────────
echo
echo "--- Running license server tests ---"
python -m pytest tests/ -q --tb=short
echo "✓ All tests passing"

# ── Step 3: Railway deploy ─────────────────────────────────────────────────
echo
echo "--- Deploying to Railway ---"
echo "If this is your first deploy, run: railway login && railway link"
echo

railway up --detach
echo "✓ Deployed to Railway"

# ── Step 4: Set Railway environment variables ──────────────────────────────
echo
echo "--- Pushing env vars to Railway ---"
railway variables set \
    LICENSE_HMAC_SECRET="$LICENSE_HMAC_SECRET" \
    STRIPE_SECRET_KEY="$STRIPE_SECRET_KEY" \
    STRIPE_WEBHOOK_SECRET="$STRIPE_WEBHOOK_SECRET" \
    STRIPE_PRO_PRICE_ID="$STRIPE_PRO_PRICE_ID" \
    STRIPE_STUDIO_PRICE_ID="$STRIPE_STUDIO_PRICE_ID" \
    ${RESEND_API_KEY:+RESEND_API_KEY="$RESEND_API_KEY"} \
    ${SENTRY_DSN:+SENTRY_DSN="$SENTRY_DSN"}

echo "✓ Env vars pushed"

# ── Step 5: Run DB migrations ──────────────────────────────────────────────
echo
echo "--- Running Alembic migrations ---"
railway run -- alembic upgrade head
echo "✓ Database migrated"

# ── Step 6: Stripe setup ───────────────────────────────────────────────────
echo
echo "--- Creating Stripe products (idempotent) ---"
python setup_stripe.py
echo "✓ Stripe products created"

# ── Step 7: Configure Stripe webhook ──────────────────────────────────────
echo
echo "--- Stripe Webhook Setup ---"
RAILWAY_URL=$(railway domain 2>/dev/null || echo "")
if [ -n "$RAILWAY_URL" ]; then
    WEBHOOK_URL="https://${RAILWAY_URL}/webhook/stripe"
    echo "  Webhook URL: $WEBHOOK_URL"
    echo
    echo "  Run this command to create the Stripe webhook:"
    echo "  stripe webhooks create \\"
    echo "    --url $WEBHOOK_URL \\"
    echo "    --events checkout.session.completed,customer.subscription.deleted,customer.subscription.paused,customer.subscription.resumed"
    echo
    echo "  Then copy the webhook signing secret into .env and Railway vars:"
    echo "    STRIPE_WEBHOOK_SECRET=whsec_..."
else
    echo "  Could not determine Railway domain automatically."
    echo "  Set webhook URL to: https://<your-railway-domain>/webhook/stripe"
fi

echo
echo "=== Deploy complete ==="
echo
echo "Health check: curl https://<your-railway-domain>/health"
echo "License server docs: https://<your-railway-domain>/docs"
