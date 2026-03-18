#!/usr/bin/env python3
"""Quick Stripe product setup — run with: STRIPE_SECRET_KEY="sk_test_..." .venv/bin/python setup_stripe.py"""
import os, sys

# Get key from environment FIRST, before anything else
KEY = os.environ.get("STRIPE_SECRET_KEY", "")
if not KEY:
    print("Usage: STRIPE_SECRET_KEY=\"sk_test_...\" .venv/bin/python setup_stripe.py")
    sys.exit(1)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import stripe
stripe.api_key = KEY

print(f"Using key: {KEY[:12]}...{KEY[-4:]}")
print("Creating AgentProbe products in Stripe...\n")

try:
    pro_product = stripe.Product.create(name="AgentProbe Pro", description="2,000 test runs/month, LLM-judge included, 5 API keys")
    pro_price = stripe.Price.create(product=pro_product.id, unit_amount=4900, currency="usd", recurring={"interval": "month"})
    print(f"  ✅ Pro Plan: {pro_price.id}")

    ent_product = stripe.Product.create(name="AgentProbe Enterprise", description="Unlimited test runs, LLM-judge, 20 API keys, priority support")
    ent_price = stripe.Price.create(product=ent_product.id, unit_amount=49900, currency="usd", recurring={"interval": "month"})
    print(f"  ✅ Enterprise Plan: {ent_price.id}")

    print(f"\nNow run these commands:\n")
    print(f'fly secrets set STRIPE_SECRET_KEY="{KEY}"')
    print(f'fly secrets set STRIPE_PRO_PRICE_ID="{pro_price.id}"')
    print(f'fly secrets set STRIPE_ENTERPRISE_PRICE_ID="{ent_price.id}"')

except stripe.error.AuthenticationError as e:
    print(f"❌ Auth failed: {e}")
    print("\nMake sure you're using the Secret key (sk_test_...), not the Publishable key (pk_test_...)")
    print("Try creating a brand new key in Stripe Dashboard → Developers → API keys")
except Exception as e:
    print(f"❌ Error: {e}")
