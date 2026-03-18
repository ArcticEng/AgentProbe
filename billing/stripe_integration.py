"""
AgentProbe — Stripe Payment Integration

Setup:
  1. Create a Stripe account at https://stripe.com
  2. Get your keys from https://dashboard.stripe.com/apikeys
  3. Add to .env:
       STRIPE_SECRET_KEY=sk_test_...
       STRIPE_WEBHOOK_SECRET=whsec_...
  4. Run: .venv/bin/python billing/setup_stripe.py  (creates products in Stripe)
  5. The webhook URL to add in Stripe Dashboard: https://yourdomain.com/api/billing/webhook
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip()

try:
    import stripe
    stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
    HAS_STRIPE = bool(stripe.api_key)
except ImportError:
    HAS_STRIPE = False
    print("⚠️  stripe package not installed. Run: pip install stripe")

from billing import create_customer, update_plan, get_customer_by_stripe_id, PLANS


def create_stripe_products():
    """One-time setup: Create products and prices in Stripe."""
    if not HAS_STRIPE:
        print("❌ Stripe not configured. Add STRIPE_SECRET_KEY to .env")
        return

    print("Creating AgentProbe products in Stripe...\n")

    # Pro plan
    pro_product = stripe.Product.create(
        name="AgentProbe Pro",
        description="2,000 test runs/month, LLM-judge included, 5 API keys"
    )
    pro_price = stripe.Price.create(
        product=pro_product.id,
        unit_amount=4900,  # $49.00
        currency="usd",
        recurring={"interval": "month"}
    )
    print(f"  ✅ Pro Plan: {pro_price.id}")

    # Enterprise plan
    ent_product = stripe.Product.create(
        name="AgentProbe Enterprise",
        description="Unlimited test runs, LLM-judge, 20 API keys, priority support"
    )
    ent_price = stripe.Price.create(
        product=ent_product.id,
        unit_amount=49900,  # $499.00
        currency="usd",
        recurring={"interval": "month"}
    )
    print(f"  ✅ Enterprise Plan: {ent_price.id}")

    print(f"""
Add these to your .env file:
  STRIPE_PRO_PRICE_ID={pro_price.id}
  STRIPE_ENTERPRISE_PRICE_ID={ent_price.id}
""")
    return {"pro": pro_price.id, "enterprise": ent_price.id}


def create_checkout_session(plan: str, customer_email: str, success_url: str, cancel_url: str) -> str:
    """Create a Stripe Checkout session. Returns the checkout URL."""
    if not HAS_STRIPE:
        raise Exception("Stripe not configured")

    plan_info = PLANS.get(plan)
    if not plan_info or plan == "free":
        raise ValueError(f"Invalid paid plan: {plan}")

    price_id = plan_info.get("stripe_price_id")
    if not price_id:
        raise ValueError(f"No Stripe price ID for plan: {plan}. Run setup_stripe.py first.")

    session = stripe.checkout.Session.create(
        mode="subscription",
        payment_method_types=["card"],
        customer_email=customer_email,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url + "?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=cancel_url,
        metadata={"plan": plan},
    )
    return session.url


def handle_webhook(payload: bytes, sig_header: str) -> dict:
    """Handle Stripe webhook events. Returns action taken."""
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        raise ValueError(f"Webhook verification failed: {e}")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        customer_email = session.get("customer_email") or session.get("customer_details", {}).get("email")
        stripe_customer_id = session.get("customer")
        plan = session.get("metadata", {}).get("plan", "pro")
        
        # Create customer account + API key
        customer, api_key = create_customer(
            email=customer_email,
            plan=plan,
            stripe_customer_id=stripe_customer_id
        )
        
        return {
            "action": "customer_created",
            "customer_id": customer["id"],
            "email": customer_email,
            "plan": plan,
            "api_key": api_key,  # Send this to customer via email
        }

    elif event["type"] == "customer.subscription.updated":
        subscription = event["data"]["object"]
        stripe_customer_id = subscription.get("customer")
        status = subscription.get("status")
        
        customer = get_customer_by_stripe_id(stripe_customer_id)
        if customer:
            if status == "active":
                return {"action": "subscription_active", "customer_id": customer["id"]}
            elif status in ("past_due", "unpaid"):
                return {"action": "subscription_past_due", "customer_id": customer["id"]}
        return {"action": "no_customer_found"}

    elif event["type"] == "customer.subscription.deleted":
        subscription = event["data"]["object"]
        stripe_customer_id = subscription.get("customer")
        
        customer = get_customer_by_stripe_id(stripe_customer_id)
        if customer:
            update_plan(customer["id"], "free")
            return {"action": "downgraded_to_free", "customer_id": customer["id"]}
        return {"action": "no_customer_found"}

    elif event["type"] == "invoice.payment_failed":
        invoice = event["data"]["object"]
        stripe_customer_id = invoice.get("customer")
        customer = get_customer_by_stripe_id(stripe_customer_id)
        if customer:
            return {"action": "payment_failed", "customer_id": customer["id"]}
        return {"action": "no_customer_found"}

    return {"action": "unhandled_event", "type": event["type"]}


if __name__ == "__main__":
    create_stripe_products()
