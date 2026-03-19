"""
AgentProbe — PayFast Payment Integration (South Africa)

PayFast flow:
  1. User clicks "Upgrade to Pro" on pricing page
  2. We generate a PayFast checkout URL with signed parameters
  3. User pays on PayFast's hosted page
  4. PayFast sends ITN (Instant Transaction Notification) to our server
  5. We verify the ITN signature and upgrade the customer's plan

Setup:
  1. Register at https://www.payfast.co.za
  2. Add to .env or Fly secrets:
       PAYFAST_MERCHANT_ID=10000100
       PAYFAST_MERCHANT_KEY=46f0cd694581a
       PAYFAST_PASSPHRASE=          (empty for sandbox, set for live)
       PAYFAST_SANDBOX=true         (set to false for production)
  3. Set ITN callback URL in PayFast dashboard:
       https://agentprobe-api.fly.dev/api/billing/payfast/itn

Sandbox test cards:
  - Any card number works in sandbox mode
  - Use merchant ID 10000100 and key 46f0cd694581a for testing
"""

import os
import hashlib
import urllib.parse
import urllib.request
import json
import socket
from typing import Optional

# Configuration
PAYFAST_MERCHANT_ID = os.environ.get("PAYFAST_MERCHANT_ID", "10000100")
PAYFAST_MERCHANT_KEY = os.environ.get("PAYFAST_MERCHANT_KEY", "46f0cd694581a")
PAYFAST_PASSPHRASE = os.environ.get("PAYFAST_PASSPHRASE", "")
PAYFAST_SANDBOX = os.environ.get("PAYFAST_SANDBOX", "true").lower() == "true"

PAYFAST_URL = "https://sandbox.payfast.co.za/eng/process" if PAYFAST_SANDBOX else "https://www.payfast.co.za/eng/process"
PAYFAST_VALIDATE_URL = "https://sandbox.payfast.co.za/eng/query/validate" if PAYFAST_SANDBOX else "https://www.payfast.co.za/eng/query/validate"

HAS_PAYFAST = bool(PAYFAST_MERCHANT_ID and PAYFAST_MERCHANT_KEY)

# PayFast subscription billing — amounts in ZAR
# At ~R18/USD, $49 ≈ R880, $499 ≈ R9000
PAYFAST_PLANS = {
    "pro": {
        "amount": "880.00",
        "item_name": "AgentProbe Pro — Monthly",
        "item_description": "2,000 test runs/month, real system testing, LLM-Judge",
        "subscription_type": "1",  # 1 = subscription
        "billing_date": "1",       # 1st of month
        "recurring_amount": "880.00",
        "frequency": "3",          # 3 = monthly
        "cycles": "0",             # 0 = indefinite
    },
    "enterprise": {
        "amount": "9000.00",
        "item_name": "AgentProbe Enterprise — Monthly",
        "item_description": "Unlimited runs, certification, priority support",
        "subscription_type": "1",
        "billing_date": "1",
        "recurring_amount": "9000.00",
        "frequency": "3",
        "cycles": "0",
    },
}


def generate_signature(data: dict, passphrase: str = "") -> str:
    """Generate PayFast MD5 signature from parameter dict."""
    # Build the string: key=value pairs in order, URL-encoded
    payload_parts = []
    for key, value in data.items():
        if value is not None and value != "":
            payload_parts.append(f"{key}={urllib.parse.quote_plus(str(value).strip())}")
    
    payload_string = "&".join(payload_parts)
    
    if passphrase:
        payload_string += f"&passphrase={urllib.parse.quote_plus(passphrase.strip())}"
    
    return hashlib.md5(payload_string.encode()).hexdigest()


def create_payfast_checkout(plan: str, email: str, return_url: str, cancel_url: str, notify_url: str) -> str:
    """Generate a PayFast checkout URL that redirects the user to PayFast's payment page.
    
    Returns the full URL with all parameters that the frontend should redirect to.
    """
    if plan not in PAYFAST_PLANS:
        raise ValueError(f"Unknown plan: {plan}. Available: {list(PAYFAST_PLANS.keys())}")
    
    plan_info = PAYFAST_PLANS[plan]
    
    # Build PayFast parameters (ORDER MATTERS for signature)
    data = {
        "merchant_id": PAYFAST_MERCHANT_ID,
        "merchant_key": PAYFAST_MERCHANT_KEY,
        "return_url": return_url,
        "cancel_url": cancel_url,
        "notify_url": notify_url,
        "email_address": email,
        "amount": plan_info["amount"],
        "item_name": plan_info["item_name"],
        "item_description": plan_info["item_description"],
        # Custom field to identify the plan + customer email on ITN callback
        "custom_str1": plan,
        "custom_str2": email,
        # Subscription fields
        "subscription_type": plan_info["subscription_type"],
        "recurring_amount": plan_info["recurring_amount"],
        "frequency": plan_info["frequency"],
        "cycles": plan_info["cycles"],
    }
    
    # Generate signature
    signature = generate_signature(data, PAYFAST_PASSPHRASE)
    data["signature"] = signature
    
    # Build the redirect URL
    query_string = urllib.parse.urlencode(data)
    checkout_url = f"{PAYFAST_URL}?{query_string}"
    
    return checkout_url


def verify_itn_signature(post_data: dict) -> bool:
    """Verify the ITN callback signature from PayFast."""
    received_signature = post_data.pop("signature", "")
    
    # Rebuild signature from remaining data
    expected_signature = generate_signature(post_data, PAYFAST_PASSPHRASE)
    
    # Restore signature to dict
    post_data["signature"] = received_signature
    
    return received_signature == expected_signature


def verify_itn_source(request_ip: str) -> bool:
    """Verify the ITN came from PayFast's servers."""
    valid_hosts = [
        "www.payfast.co.za",
        "sandbox.payfast.co.za",
        "w1w.payfast.co.za",
        "w2w.payfast.co.za",
    ]
    
    valid_ips = set()
    for host in valid_hosts:
        try:
            ips = socket.getaddrinfo(host, None)
            for ip_info in ips:
                valid_ips.add(ip_info[4][0])
        except socket.gaierror:
            pass
    
    # In sandbox mode, be more permissive
    if PAYFAST_SANDBOX:
        return True
    
    return request_ip in valid_ips


def verify_itn_with_payfast(post_data: dict) -> bool:
    """Server-to-server verification with PayFast."""
    try:
        # Rebuild the parameter string
        params = []
        for key, value in post_data.items():
            if key != "signature" and value is not None and value != "":
                params.append(f"{key}={urllib.parse.quote_plus(str(value).strip())}")
        
        param_string = "&".join(params)
        
        req = urllib.request.Request(
            PAYFAST_VALIDATE_URL,
            data=param_string.encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST"
        )
        
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = resp.read().decode().strip()
            return result == "VALID"
    except Exception as e:
        print(f"PayFast validation error: {e}")
        # In sandbox mode, allow through on validation failure
        return PAYFAST_SANDBOX


def handle_itn(post_data: dict, request_ip: str) -> dict:
    """Process an ITN callback from PayFast.
    
    Called when PayFast POSTs to /api/billing/payfast/itn
    
    Returns: {"status": "ok"} or raises ValueError
    """
    from billing import create_customer, update_plan, get_db
    
    # Step 1: Verify signature
    data_copy = dict(post_data)
    if not verify_itn_signature(data_copy):
        raise ValueError("Invalid ITN signature")
    
    # Step 2: Verify source IP
    if not verify_itn_source(request_ip):
        raise ValueError(f"ITN from unauthorized IP: {request_ip}")
    
    # Step 3: Verify with PayFast server
    if not verify_itn_with_payfast(post_data):
        raise ValueError("PayFast server validation failed")
    
    # Step 4: Process the payment
    payment_status = post_data.get("payment_status", "")
    plan = post_data.get("custom_str1", "")
    email = post_data.get("custom_str2", "")
    pf_payment_id = post_data.get("pf_payment_id", "")
    amount = post_data.get("amount_gross", "0")
    
    if not plan or not email:
        raise ValueError("Missing plan or email in ITN data")
    
    print(f"[PayFast ITN] status={payment_status} plan={plan} email={email} amount=R{amount} pf_id={pf_payment_id}")
    
    if payment_status == "COMPLETE":
        # Payment successful — upgrade the customer
        conn = get_db()
        customer = conn.execute("SELECT * FROM customers WHERE email = ?", (email,)).fetchone()
        
        if customer:
            # Existing customer — upgrade plan
            update_plan(customer["id"], plan)
            print(f"[PayFast] Upgraded {email} to {plan}")
        else:
            # New customer from PayFast — create account
            # They'll need to sign up on the dashboard to get their API key
            cust, api_key = create_customer(email=email, plan=plan)
            print(f"[PayFast] Created new customer {email} on {plan} plan")
            # TODO: Email them their API key
        
        return {"status": "ok", "action": "upgraded", "plan": plan, "email": email}
    
    elif payment_status == "CANCELLED":
        # Subscription cancelled — downgrade to free
        conn = get_db()
        customer = conn.execute("SELECT * FROM customers WHERE email = ?", (email,)).fetchone()
        if customer:
            update_plan(customer["id"], "free")
            print(f"[PayFast] Downgraded {email} to free (cancelled)")
        
        return {"status": "ok", "action": "downgraded", "email": email}
    
    else:
        print(f"[PayFast] Unhandled payment status: {payment_status}")
        return {"status": "ok", "action": "ignored", "payment_status": payment_status}
