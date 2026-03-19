"""
AgentProbe — PayFast Payment Integration (South Africa)

PayFast flow:
  1. User clicks "Upgrade to Pro" → we return a form-post URL
  2. Frontend redirects to PayFast's hosted checkout
  3. User pays → PayFast sends ITN to our server
  4. We verify signature + upgrade the customer

Sandbox credentials:
  PAYFAST_MERCHANT_ID=10000100
  PAYFAST_MERCHANT_KEY=46f0cd694581a
  PAYFAST_PASSPHRASE=jt7NOE43FZPn  (sandbox passphrase)
"""

import os
import hashlib
import urllib.parse
import urllib.request
import json
import socket
from datetime import datetime
from typing import Optional


PAYFAST_MERCHANT_ID = os.environ.get("PAYFAST_MERCHANT_ID", "10000100")
PAYFAST_MERCHANT_KEY = os.environ.get("PAYFAST_MERCHANT_KEY", "46f0cd694581a")
PAYFAST_PASSPHRASE = os.environ.get("PAYFAST_PASSPHRASE", "")
PAYFAST_SANDBOX = os.environ.get("PAYFAST_SANDBOX", "true").lower() == "true"

PAYFAST_URL = "https://sandbox.payfast.co.za/eng/process" if PAYFAST_SANDBOX else "https://www.payfast.co.za/eng/process"
PAYFAST_VALIDATE_URL = "https://sandbox.payfast.co.za/eng/query/validate" if PAYFAST_SANDBOX else "https://www.payfast.co.za/eng/query/validate"

HAS_PAYFAST = bool(PAYFAST_MERCHANT_ID and PAYFAST_MERCHANT_KEY)

# PayFast REQUIRES this exact field order for signature generation
FIELD_ORDER = [
    "merchant_id", "merchant_key", "return_url", "cancel_url", "notify_url",
    "name_first", "name_last", "email_address", "cell_number",
    "m_payment_id", "amount", "item_name", "item_description",
    "custom_int1", "custom_int2", "custom_int3", "custom_int4", "custom_int5",
    "custom_str1", "custom_str2", "custom_str3", "custom_str4", "custom_str5",
    "email_confirmation", "confirmation_address", "payment_method",
    "subscription_type", "billing_date", "recurring_amount", "frequency", "cycles",
]

PAYFAST_PLANS = {
    "pro": {
        "amount": "880.00",
        "item_name": "AgentProbe Pro Monthly",
        "item_description": "2000 test runs per month with real system testing and LLM Judge",
        "subscription_type": "1",
        "recurring_amount": "880.00",
        "frequency": "3",
        "cycles": "0",
    },
    "enterprise": {
        "amount": "9000.00",
        "item_name": "AgentProbe Enterprise Monthly",
        "item_description": "Unlimited runs with certification and priority support",
        "subscription_type": "1",
        "recurring_amount": "9000.00",
        "frequency": "3",
        "cycles": "0",
    },
}


def get_next_billing_date() -> str:
    """Get the 1st of next month in Y-m-d format (PayFast requirement)."""
    today = datetime.now()
    if today.month == 12:
        return f"{today.year + 1}-01-01"
    return f"{today.year}-{today.month + 1:02d}-01"


def generate_signature(data: dict, passphrase: str = "") -> str:
    """Generate PayFast MD5 signature.
    
    CRITICAL: Fields must be in PayFast's required order.
    Empty values must be excluded. Passphrase only appended if non-empty.
    """
    field_priority = {k: i for i, k in enumerate(FIELD_ORDER)}
    sorted_keys = sorted(data.keys(), key=lambda k: field_priority.get(k, 999))
    
    parts = []
    for key in sorted_keys:
        val = str(data[key]).strip()
        if val and key != "signature":
            parts.append(f"{key}={urllib.parse.quote_plus(val)}")
    
    param_string = "&".join(parts)
    
    if passphrase and passphrase.strip():
        param_string += f"&passphrase={urllib.parse.quote_plus(passphrase.strip())}"
    
    return hashlib.md5(param_string.encode()).hexdigest()


def create_payfast_checkout(plan: str, email: str, return_url: str, cancel_url: str, notify_url: str) -> str:
    """Generate a PayFast checkout URL."""
    if plan not in PAYFAST_PLANS:
        raise ValueError(f"Unknown plan: {plan}. Available: {list(PAYFAST_PLANS.keys())}")
    
    plan_info = PAYFAST_PLANS[plan]
    
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
        "custom_str1": plan,
        "custom_str2": email,
        "subscription_type": plan_info["subscription_type"],
        "billing_date": get_next_billing_date(),
        "recurring_amount": plan_info["recurring_amount"],
        "frequency": plan_info["frequency"],
        "cycles": plan_info["cycles"],
    }
    
    signature = generate_signature(data, PAYFAST_PASSPHRASE)
    data["signature"] = signature
    
    field_priority = {k: i for i, k in enumerate(FIELD_ORDER)}
    sorted_keys = sorted(data.keys(), key=lambda k: field_priority.get(k, 998 if k != "signature" else 999))
    
    query_parts = []
    for key in sorted_keys:
        val = str(data[key]).strip()
        if val:
            query_parts.append(f"{key}={urllib.parse.quote_plus(val)}")
    
    return f"{PAYFAST_URL}?{'&'.join(query_parts)}"


def verify_itn_signature(post_data: dict) -> bool:
    """Verify ITN callback signature."""
    received_signature = post_data.get("signature", "")
    data_copy = {k: v for k, v in post_data.items() if k != "signature"}
    expected_signature = generate_signature(data_copy, PAYFAST_PASSPHRASE)
    return received_signature == expected_signature


def verify_itn_source(request_ip: str) -> bool:
    """Verify ITN came from PayFast servers."""
    if PAYFAST_SANDBOX:
        return True
    valid_hosts = ["www.payfast.co.za", "sandbox.payfast.co.za", "w1w.payfast.co.za", "w2w.payfast.co.za"]
    valid_ips = set()
    for host in valid_hosts:
        try:
            for info in socket.getaddrinfo(host, None):
                valid_ips.add(info[4][0])
        except socket.gaierror:
            pass
    return request_ip in valid_ips


def verify_itn_with_payfast(post_data: dict) -> bool:
    """Server-to-server verification."""
    try:
        params = []
        for key, value in post_data.items():
            if key != "signature" and value is not None and str(value).strip():
                params.append(f"{key}={urllib.parse.quote_plus(str(value).strip())}")
        param_string = "&".join(params)
        req = urllib.request.Request(PAYFAST_VALIDATE_URL, data=param_string.encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode().strip() == "VALID"
    except Exception as e:
        print(f"PayFast validation error: {e}")
        return PAYFAST_SANDBOX


def handle_itn(post_data: dict, request_ip: str) -> dict:
    """Process ITN callback from PayFast."""
    from billing import create_customer, update_plan, get_db
    
    if not verify_itn_signature(post_data):
        raise ValueError("Invalid ITN signature")
    if not verify_itn_source(request_ip):
        raise ValueError(f"ITN from unauthorized IP: {request_ip}")
    if not verify_itn_with_payfast(post_data):
        raise ValueError("PayFast server validation failed")
    
    payment_status = post_data.get("payment_status", "")
    plan = post_data.get("custom_str1", "")
    email = post_data.get("custom_str2", "")
    pf_payment_id = post_data.get("pf_payment_id", "")
    amount = post_data.get("amount_gross", "0")
    
    print(f"[PayFast ITN] status={payment_status} plan={plan} email={email} amount=R{amount} pf_id={pf_payment_id}")
    
    if payment_status == "COMPLETE":
        conn = get_db()
        customer = conn.execute("SELECT * FROM customers WHERE email = ?", (email,)).fetchone()
        if customer:
            update_plan(customer["id"], plan)
            print(f"[PayFast] Upgraded {email} to {plan}")
        else:
            cust, api_key = create_customer(email=email, plan=plan)
            print(f"[PayFast] Created {email} on {plan}")
        return {"status": "ok", "action": "upgraded", "plan": plan, "email": email}
    
    elif payment_status == "CANCELLED":
        conn = get_db()
        customer = conn.execute("SELECT * FROM customers WHERE email = ?", (email,)).fetchone()
        if customer:
            update_plan(customer["id"], "free")
            print(f"[PayFast] Downgraded {email} to free")
        return {"status": "ok", "action": "downgraded", "email": email}
    
    return {"status": "ok", "action": "ignored", "payment_status": payment_status}
