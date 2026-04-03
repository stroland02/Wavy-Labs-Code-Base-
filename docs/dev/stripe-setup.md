# Stripe Setup Guide

This guide walks through creating Stripe products, configuring the webhook, and
wiring everything into the Wavy Labs license server.

---

## Prerequisites

- A [Stripe](https://stripe.com) account (free to create)
- The license server running locally or deployed (see [Railway deployment](#railway-deployment))
- `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRO_PRICE_ID`,
  `STRIPE_STUDIO_PRICE_ID` ready to paste into `.env`

---

## 1. Create Products & Prices

### Wavy Labs Pro

1. Go to **Stripe Dashboard → Product catalog → + Add product**
2. Fill in:
   - **Name**: `Wavy Labs Pro`
   - **Description**: Unlimited AI generation, 6-stem splitting, vocal & mastering
   - **Price**: `$9.99` / month / recurring
3. Click **Save product**
4. Copy the **Price ID** — it looks like `price_1Abc123...`
   → this is `STRIPE_PRO_PRICE_ID`

### Wavy Labs Studio

1. **+ Add product** again
2. Fill in:
   - **Name**: `Wavy Labs Studio`
   - **Description**: Everything in Pro + Prompt Commands and Code to Music
   - **Price**: `$24.99` / month / recurring
3. Click **Save product**
4. Copy the **Price ID**
   → this is `STRIPE_STUDIO_PRICE_ID`

---

## 2. Get Your API Keys

1. **Stripe Dashboard → Developers → API keys**
2. Copy **Secret key** (`sk_live_...` for production, `sk_test_...` for testing)
   → this is `STRIPE_SECRET_KEY`

!!! warning "Use test keys locally"
    Use `sk_test_...` and `price_test_...` IDs during development.
    Swap to live keys only in your production Railway environment.

---

## 3. Configure the Webhook

The license server listens at `/webhooks/stripe` for `checkout.session.completed`
events. Stripe sends this when a customer's payment succeeds.

### Local development (Stripe CLI)

```bash
# Install Stripe CLI: https://stripe.com/docs/stripe-cli
stripe login
stripe listen --forward-to localhost:8000/webhooks/stripe
```

The CLI prints a `whsec_...` signing secret — paste it into `.env` as
`STRIPE_WEBHOOK_SECRET`.

### Production (Railway)

1. **Stripe Dashboard → Developers → Webhooks → + Add endpoint**
2. **Endpoint URL**: `https://your-app.railway.app/webhooks/stripe`
3. **Events to listen**: select `checkout.session.completed`
4. Click **Add endpoint**
5. Click **Reveal** on the **Signing secret** → copy `whsec_...`
   → this is `STRIPE_WEBHOOK_SECRET`

---

## 4. Configure `.env`

```bash
cd wavy-license-server
cp .env.example .env
```

Edit `.env`:

```dotenv
# Stripe
STRIPE_SECRET_KEY=sk_live_...          # or sk_test_... locally
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRO_PRICE_ID=price_...
STRIPE_STUDIO_PRICE_ID=price_...

# HMAC secret — must match WAVY_LICENSE_HMAC_SECRET in your CMake build
LICENSE_HMAC_SECRET=<output of: python -c "import secrets; print(secrets.token_hex(32))">

# Resend (email delivery)
RESEND_API_KEY=re_...
EMAIL_FROM=licenses@wavylabs.io
```

---

## 5. Test the Purchase Flow

With the Stripe CLI forwarding events locally:

```bash
# Start the license server
uvicorn main:app --reload

# In another terminal, trigger a test checkout
stripe trigger checkout.session.completed
```

Check the server logs — you should see:

```
INFO  Stripe webhook: checkout.session.completed  session=cs_test_...
INFO  License key issued  email=test@example.com  tier=pro  key=PRO-...
INFO  Email sent  to=test@example.com
```

---

## 6. Railway Deployment

### First deploy

```bash
# Install Railway CLI
npm install -g @railway/cli
railway login
railway init        # link to your Railway project
railway up          # push Dockerfile
```

### Environment variables

In **Railway Dashboard → your service → Variables**, add every key from `.env`
(do **not** commit `.env` to git):

| Variable | Value |
|----------|-------|
| `DATABASE_URL` | Provided automatically by Railway Postgres plugin |
| `LICENSE_HMAC_SECRET` | Your 64-char hex secret |
| `STRIPE_SECRET_KEY` | `sk_live_...` |
| `STRIPE_WEBHOOK_SECRET` | `whsec_...` |
| `STRIPE_PRO_PRICE_ID` | `price_...` |
| `STRIPE_STUDIO_PRICE_ID` | `price_...` |
| `RESEND_API_KEY` | `re_...` |
| `EMAIL_FROM` | `licenses@wavylabs.io` |
| `APP_ENV` | `production` |

### Add Postgres

In Railway Dashboard → **+ New → Database → Add PostgreSQL**.
The `DATABASE_URL` variable is injected automatically.

### Verify health

```bash
curl https://your-app.railway.app/health
# → {"status": "ok"}
```

---

## 7. Wire the HMAC Secret into the C++ Build

The `LICENSE_HMAC_SECRET` in `.env` **must exactly match** the
`WAVY_LICENSE_HMAC_SECRET` CMake cache variable used to compile `wavy-labs.exe`.

```bash
# Local dev
cmake -B build -DWAVY_LICENSE_HMAC_SECRET="your-64-char-hex-secret" ...

# CI / GitHub Actions — add repository secret WAVY_HMAC_SECRET in:
# Settings → Secrets and variables → Actions → New repository secret
```

The secret is baked into the binary at compile time and used by
`LicenseManager` to verify keys without a network round-trip.

---

## Key Format Reference

| Tier | Key prefix | HMAC input |
|------|-----------|------------|
| Pro | `PRO-` | `"PRO-" + uuid` |
| Studio | `STU-` | `"STU-" + uuid` |

Keys are generated by the license server on successful checkout and emailed to
the purchaser via Resend.
