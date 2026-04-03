#!/usr/bin/env python3
"""
setup_stripe.py — create Wavy Labs Stripe products and prices.

Run ONCE against your live Stripe account to set up the Pro and Studio
subscription products. Prints the price IDs to paste into Railway env vars.

Usage:
    STRIPE_SECRET_KEY=sk_live_... python setup_stripe.py

Or with a .env file:
    python setup_stripe.py
"""

from __future__ import annotations

import os
import sys

try:
    import stripe
except ImportError:
    sys.exit("stripe not installed — run: pip install stripe")

# ── Load key ──────────────────────────────────────────────────────────────────
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
if not stripe.api_key:
    try:
        from dotenv import load_dotenv
        load_dotenv()
        stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
    except ImportError:
        pass

if not stripe.api_key:
    sys.exit("Set STRIPE_SECRET_KEY env var before running this script.")

if stripe.api_key.startswith("sk_test_"):
    print("⚠️  Using TEST mode Stripe key. Switch to sk_live_... for production.")


# ── Products ──────────────────────────────────────────────────────────────────

PRODUCTS = [
    {
        "name":        "Wavy Labs Pro",
        "description": "Unlimited AI generations, 6-stem split, vocal synthesis, mastering.",
        "metadata":    {"tier": "pro"},
        "price_usd":   999,   # $9.99 / month
        "env_var":     "STRIPE_PRO_PRICE_ID",
    },
    {
        "name":        "Wavy Labs Studio",
        "description": "Everything in Pro plus Prompt Commands and Code-to-Music DSL.",
        "metadata":    {"tier": "studio"},
        "price_usd":   2499,  # $24.99 / month
        "env_var":     "STRIPE_STUDIO_PRICE_ID",
    },
]


def create_product_and_price(spec: dict) -> tuple[str, str]:
    """Create (or reuse) a Stripe Product + monthly recurring Price. Returns (product_id, price_id)."""

    # Check if product already exists (idempotent by metadata)
    existing = stripe.Product.list(active=True, limit=100)
    for p in existing.auto_paging_iter():
        if p.metadata.get("tier") == spec["metadata"]["tier"]:
            print(f"  Product already exists: {p.id} ({p.name})")
            product_id = p.id
            break
    else:
        product = stripe.Product.create(
            name=spec["name"],
            description=spec["description"],
            metadata=spec["metadata"],
        )
        product_id = product.id
        print(f"  Created product: {product_id} ({spec['name']})")

    # Check if price already exists for this product
    prices = stripe.Price.list(product=product_id, active=True, limit=10)
    for pr in prices.auto_paging_iter():
        if pr.unit_amount == spec["price_usd"] and pr.recurring and pr.recurring.interval == "month":
            print(f"  Price already exists: {pr.id} (${spec['price_usd']/100:.2f}/mo)")
            return product_id, pr.id

    price = stripe.Price.create(
        product=product_id,
        unit_amount=spec["price_usd"],
        currency="usd",
        recurring={"interval": "month"},
    )
    print(f"  Created price: {price.id} (${spec['price_usd']/100:.2f}/mo)")
    return product_id, price.id


def main() -> None:
    print("Wavy Labs — Stripe product setup")
    print("=" * 50)

    results: dict[str, str] = {}

    for spec in PRODUCTS:
        print(f"\n{spec['name']}:")
        _, price_id = create_product_and_price(spec)
        results[spec["env_var"]] = price_id

    print("\n" + "=" * 50)
    print("✅  Setup complete! Set these Railway environment variables:\n")
    for var, val in results.items():
        print(f"   {var}={val}")

    print("\nThen configure the Stripe webhook:")
    print("  URL: https://<your-railway-url>/webhooks/stripe")
    print("  Events to subscribe:")
    print("    - checkout.session.completed")
    print("    - customer.subscription.deleted")
    print("    - customer.subscription.paused")
    print("    - customer.subscription.resumed")
    print("\nPaste the webhook signing secret as STRIPE_WEBHOOK_SECRET in Railway.")


if __name__ == "__main__":
    main()
