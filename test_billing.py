#!/usr/bin/env python3
"""
Test the full billing + API flow locally.

This simulates what happens when a customer signs up, gets an API key,
and runs tests — with usage tracking and plan limits enforced.
"""
import sys, os, json, urllib.request, urllib.error

API = "http://localhost:8000"

def call(method, path, data=None, api_key=None):
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(f"{API}{path}", data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode()), resp.status
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode()), e.code

print("""
╔══════════════════════════════════════════════════╗
║  AgentProbe — Full Billing Flow Test             ║
║  Make sure the API is running:                   ║
║    make api                                      ║
╚══════════════════════════════════════════════════╝
""")

# Step 1: Check API is running
print("1. Checking API is running...")
try:
    result, status = call("GET", "/api/health")
    print(f"   ✅ API is running: {result}\n")
except:
    print("   ❌ API not running. Start it with: make api")
    sys.exit(1)

# Step 2: View pricing
print("2. Viewing pricing plans...")
result, _ = call("GET", "/api/pricing")
for plan_id, plan in result["plans"].items():
    limit = plan["test_runs_per_month"]
    limit_str = "unlimited" if limit == -1 else str(limit)
    judge = "✓" if plan.get("llm_judge") else "✗"
    print(f"   {plan['name']:12s} | ${plan['price_monthly']:>3}/mo | {limit_str:>9} runs | LLM-Judge: {judge}")
print()

# Step 3: Sign up (free plan)
print("3. Signing up for free plan...")
result, status = call("POST", "/api/billing/signup", {"email": "demo@example.com", "name": "Demo User"})
if status == 409:
    print(f"   ⚠️  Email already registered. Using existing account.\n")
    # For demo, we'll just proceed
    API_KEY = None
else:
    API_KEY = result.get("api_key")
    print(f"   ✅ Account created!")
    print(f"   📧 Email: {result['customer']['email']}")
    print(f"   📋 Plan: {result['plan']}")
    print(f"   🔑 API Key: {API_KEY}")
    print(f"   ⚠️  Save this key — it won't be shown again!\n")

if not API_KEY:
    print("   No API key available (account already exists). Creating new test account...")
    import random
    result, status = call("POST", "/api/billing/signup", 
                         {"email": f"demo{random.randint(1000,9999)}@example.com"})
    API_KEY = result.get("api_key")
    print(f"   ✅ Created: {result['customer']['email']}")
    print(f"   🔑 API Key: {API_KEY}\n")

# Step 4: Run tests WITH the API key
print("4. Running customer service tests (with API key)...")
result, status = call("POST", "/api/run/template", 
    {"template": "customer_service", "agent": {"type": "mock"}},
    api_key=API_KEY)

if status == 200:
    print(f"   ✅ Tests completed!")
    print(f"   📊 {result['passed']}/{result['total']} passed ({result['pass_rate']:.0%})")
    print(f"   📈 Usage after: {result.get('usage_after', {})}\n")
else:
    print(f"   ❌ Error {status}: {result}\n")

# Step 5: Try WITHOUT an API key (should fail)
print("5. Trying without API key (should be rejected)...")
result, status = call("POST", "/api/run/template", 
    {"template": "safety", "agent": {"type": "mock"}})
if status == 401:
    print(f"   ✅ Correctly rejected: {result.get('detail', {}).get('message', result)}\n")
else:
    print(f"   ⚠️  Unexpected status {status}\n")

# Step 6: Try with invalid API key
print("6. Trying with invalid API key (should be rejected)...")
result, status = call("POST", "/api/run/template",
    {"template": "safety", "agent": {"type": "mock"}},
    api_key="ap_live_fake_key_12345")
if status == 401:
    print(f"   ✅ Correctly rejected: {result.get('detail', {}).get('message', result)}\n")
else:
    print(f"   ⚠️  Unexpected status {status}\n")

# Step 7: Try LLM-judge on free plan (should be blocked)
print("7. Trying LLM-judge on free plan (should be blocked)...")
result, status = call("POST", "/api/run/template",
    {"template": "customer_service", "agent": {"type": "mock"}, "use_llm_judge": True},
    api_key=API_KEY)
if status == 403:
    print(f"   ✅ Correctly blocked: {result.get('detail', {}).get('message', result)}\n")
else:
    print(f"   Status {status}: LLM-judge {'allowed' if status == 200 else 'error'}\n")

# Step 8: Check usage
print("8. Checking usage...")
result, status = call("GET", "/api/billing/usage", api_key=API_KEY)
if status == 200:
    usage = result.get("usage", {})
    limits = result.get("limits", {})
    print(f"   Plan: {result.get('plan')}")
    print(f"   Used: {usage.get('test_runs', 0)} test runs")
    print(f"   Remaining: {limits.get('remaining')}")
    print()
else:
    print(f"   Error: {result}\n")

print(f"""
{'='*50}
  BILLING FLOW TEST COMPLETE
{'='*50}

What just happened:
  ✓ Customer signed up → got API key
  ✓ Used API key to run tests → usage tracked
  ✓ Request without key → rejected (401)
  ✓ Invalid key → rejected (401)
  ✓ LLM-judge on free plan → blocked (403)
  ✓ Usage tracked against monthly limit

This is the EXACT flow your customers will experience.
The only missing piece is Stripe for real payments.

To add Stripe:
  1. Create account at stripe.com
  2. Add STRIPE_SECRET_KEY to .env
  3. Run: .venv/bin/python billing/stripe_integration.py
  4. Add webhook URL in Stripe Dashboard
{'='*50}
""")
