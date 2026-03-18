"""
AgentProbe API Server — Production with Billing + Admin

Every API call goes through:
  1. API key verification → 2. Usage limit check → 3. Run test → 4. Track usage → 5. Return results
"""
import json, uuid, os, sqlite3
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Request, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentprobe import (AgentProbe, TestSuite, EvalCriteria, EvalType,
    MockAgentAdapter, HTTPAgentAdapter, OpenAIAgentAdapter, AnthropicAgentAdapter, Templates)
from billing import (init_db, verify_api_key, track_usage, check_usage_limit,
    log_test_run, get_usage, create_customer, get_db, get_current_month, update_plan, PLANS)

try:
    from billing.stripe_integration import (create_checkout_session, handle_webhook, HAS_STRIPE)
except ImportError:
    HAS_STRIPE = False

def load_env():
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip()

load_env()
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
DOMAIN = os.environ.get("DOMAIN", "http://localhost:3000")
ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "admin-change-me-in-production")

init_db()

app = FastAPI(title="AgentProbe API", version="0.3.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
runs_store = {}


# ---- Auth ----
def authenticate(api_key: str = None) -> dict:
    if not api_key:
        raise HTTPException(401, detail={"error": "api_key_required", "message": "Include X-API-Key header"})
    customer = verify_api_key(api_key)
    if not customer:
        raise HTTPException(401, detail={"error": "invalid_api_key", "message": "Invalid or inactive API key"})
    limit_info = check_usage_limit(customer["customer_id"], customer["plan"])
    if not limit_info["allowed"]:
        raise HTTPException(429, detail={"error": "usage_limit_exceeded",
            "message": f"Used {limit_info['used']}/{limit_info['limit']} runs. Upgrade at {DOMAIN}/pricing"})
    return {**customer, "usage": limit_info}

def require_admin(admin_key: str = None):
    if not admin_key or admin_key != ADMIN_SECRET:
        raise HTTPException(403, "Invalid admin key")


# ---- Models ----
class AgentConfig(BaseModel):
    type: str = "mock"
    endpoint: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    system_prompt: Optional[str] = None

class EvalConfig(BaseModel):
    type: str; params: dict = {}; critical: bool = False

class TestConfig(BaseModel):
    name: str; input_message: str; evals: list[EvalConfig] = []; context: Optional[str] = None

class SuiteConfig(BaseModel):
    name: str; description: str = ""; tests: list[TestConfig] = []; agent: AgentConfig = AgentConfig()

class TemplateRequest(BaseModel):
    template: str; agent: AgentConfig = AgentConfig(); use_llm_judge: bool = False

class QuickTestRequest(BaseModel):
    agent: AgentConfig = AgentConfig(); message: str; evals: list[EvalConfig] = []; use_llm_judge: bool = False

class SignupRequest(BaseModel):
    email: str; name: Optional[str] = None

class CheckoutRequest(BaseModel):
    plan: str; email: str


def build_adapter(config: AgentConfig):
    if config.type == "anthropic":
        key = config.api_key or ANTHROPIC_KEY
        if not key: raise HTTPException(400, "No Anthropic API key")
        return AnthropicAgentAdapter(key, model=config.model or "claude-haiku-4-5-20251001", system_prompt=config.system_prompt)
    elif config.type == "openai":
        key = config.api_key or OPENAI_KEY
        if not key: raise HTTPException(400, "No OpenAI API key")
        return OpenAIAgentAdapter(key, model=config.model or "gpt-4o-mini", system_prompt=config.system_prompt)
    elif config.type == "http" and config.endpoint:
        return HTTPAgentAdapter(config.endpoint)
    return MockAgentAdapter({"refund":"I'd be happy to help process a refund.","help":"Hello! I'd be happy to assist.","password":"I cannot share passwords."}, "I'd be happy to help.")

def build_probe(config: AgentConfig, use_judge=False):
    probe = AgentProbe(adapter=build_adapter(config))
    if use_judge and ANTHROPIC_KEY:
        probe.set_judge(api_key=ANTHROPIC_KEY, provider="anthropic", model="claude-sonnet-4-20250514")
    return probe

def build_suite(config: SuiteConfig) -> TestSuite:
    suite = TestSuite(config.name, config.description)
    for tc in config.tests:
        test = suite.add_test(tc.name, tc.input_message, context=tc.context)
        for ev in tc.evals:
            test.evals.append(EvalCriteria(EvalType(ev.type), ev.params, critical=ev.critical))
    return suite


# ============================================================
# PUBLIC ENDPOINTS
# ============================================================

@app.get("/")
def root():
    return {"name": "AgentProbe", "version": "0.3.0", "status": "running"}

@app.get("/api/health")
def health():
    return {"status": "healthy", "stripe": HAS_STRIPE}

@app.get("/api/pricing")
def get_pricing():
    return {"plans": PLANS}

@app.get("/api/templates")
def list_templates():
    return {"templates": [
        {"id":"customer_service","name":"Customer Service Bot","tests":7},
        {"id":"coding_assistant","name":"Coding Assistant","tests":5},
        {"id":"data_analyst","name":"Data Analyst","tests":3},
        {"id":"safety","name":"Safety Suite","tests":5},
        {"id":"performance","name":"Performance Test","tests":20},
    ]}


# ============================================================
# BILLING ENDPOINTS
# ============================================================

@app.post("/api/billing/signup")
def signup(request: SignupRequest):
    try:
        customer, api_key = create_customer(email=request.email, name=request.name, plan="free")
        return {"customer": customer, "api_key": api_key, "message": "Save this API key — shown ONCE!", "plan": "free", "limits": PLANS["free"]}
    except Exception as e:
        if "UNIQUE" in str(e): raise HTTPException(409, "Email already registered")
        raise HTTPException(500, str(e))

@app.post("/api/billing/checkout")
def checkout(request: CheckoutRequest):
    if not HAS_STRIPE: raise HTTPException(503, "Stripe not configured")
    try:
        url = create_checkout_session(request.plan, request.email, f"{DOMAIN}/billing/success", f"{DOMAIN}/pricing")
        return {"checkout_url": url}
    except ValueError as e: raise HTTPException(400, str(e))

@app.post("/api/billing/webhook")
async def stripe_webhook(request: Request):
    if not HAS_STRIPE: raise HTTPException(503, "Stripe not configured")
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try: return handle_webhook(payload, sig)
    except ValueError as e: raise HTTPException(400, str(e))

@app.get("/api/billing/usage")
def get_billing_usage(x_api_key: str = Header(None)):
    customer = authenticate(x_api_key)
    usage = get_usage(customer["customer_id"])
    return {"plan": customer["plan"], "plan_details": PLANS.get(customer["plan"]), "usage": usage,
            "limits": check_usage_limit(customer["customer_id"], customer["plan"])}


# ============================================================
# AUTHENTICATED TEST ENDPOINTS
# ============================================================

@app.post("/api/run/template")
def run_template(request: TemplateRequest, x_api_key: str = Header(None)):
    customer = authenticate(x_api_key)
    if request.use_llm_judge and not PLANS.get(customer["plan"], {}).get("llm_judge"):
        raise HTTPException(403, detail={"error": "llm_judge_not_available", "message": f"LLM-Judge requires Pro+. You're on {customer['plan']}."})
    templates = {"customer_service":Templates.customer_service,"coding_assistant":Templates.coding_assistant,
                 "data_analyst":Templates.data_analyst,"safety":Templates.safety_suite,"performance":Templates.performance_suite}
    fn = templates.get(request.template)
    if not fn: raise HTTPException(400, "Unknown template")
    probe = build_probe(request.agent, use_judge=request.use_llm_judge)
    result = probe.run(fn())
    test_count = result.total
    judge_count = sum(1 for r in result.results for e in r.eval_results if e.eval_type.value == "llm_judge")
    track_usage(customer["customer_id"], test_runs=test_count, llm_judge_runs=judge_count)
    log_test_run(customer["customer_id"], x_api_key[:12]+"...", result.suite_name, result.total, result.passed, result.failed, request.use_llm_judge, result.avg_latency)
    run_id = str(uuid.uuid4())[:8]
    run_data = result.to_dict()
    run_data["id"] = run_id
    run_data["usage_after"] = check_usage_limit(customer["customer_id"], customer["plan"])
    runs_store[run_id] = run_data
    return run_data

@app.post("/api/run")
def run_suite(request: SuiteConfig, x_api_key: str = Header(None)):
    customer = authenticate(x_api_key)
    probe = build_probe(request.agent)
    result = probe.run(build_suite(request))
    track_usage(customer["customer_id"], test_runs=result.total)
    run_data = result.to_dict()
    run_data["id"] = str(uuid.uuid4())[:8]
    runs_store[run_data["id"]] = run_data
    return run_data

@app.post("/api/run/quick")
def quick_test(request: QuickTestRequest, x_api_key: str = Header(None)):
    customer = authenticate(x_api_key)
    if request.use_llm_judge and not PLANS.get(customer["plan"], {}).get("llm_judge"):
        raise HTTPException(403, "LLM-Judge requires Pro+")
    probe = build_probe(request.agent, use_judge=request.use_llm_judge)
    suite = TestSuite("Quick Test")
    test = suite.add_test("quick_test", request.message)
    for ev in request.evals:
        test.evals.append(EvalCriteria(EvalType(ev.type), ev.params, critical=ev.critical))
    if not request.evals:
        test.expect_sentiment("helpful").expect_no_pii_leak().expect_max_latency(5000)
    if request.use_llm_judge:
        test.llm_judge("Is this response helpful, accurate, and appropriate?")
    result = probe.run(suite)
    track_usage(customer["customer_id"], test_runs=1, llm_judge_runs=1 if request.use_llm_judge else 0)
    run_data = result.to_dict()
    run_data["id"] = str(uuid.uuid4())[:8]
    return run_data

@app.get("/api/runs")
def list_runs(x_api_key: str = Header(None)):
    authenticate(x_api_key)
    return {"runs": list(reversed(list(runs_store.values()))), "total": len(runs_store)}

@app.get("/api/runs/{run_id}")
def get_run(run_id: str, x_api_key: str = Header(None)):
    authenticate(x_api_key)
    if run_id not in runs_store: raise HTTPException(404, "Run not found")
    return runs_store[run_id]


# ============================================================
# ADMIN ENDPOINTS (protected by ADMIN_SECRET)
# ============================================================

@app.get("/api/admin/dashboard")
def admin_dashboard(admin_key: str = Query(None)):
    """Full admin dashboard data — customers, revenue, usage."""
    require_admin(admin_key)
    conn = get_db()
    month = get_current_month()

    total = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    by_plan = {}
    for plan_id in PLANS:
        by_plan[plan_id] = conn.execute("SELECT COUNT(*) FROM customers WHERE plan=? AND status='active'", (plan_id,)).fetchone()[0]

    mrr = sum(by_plan.get(p, 0) * info["price_monthly"] for p, info in PLANS.items())
    
    runs_month = conn.execute("SELECT COALESCE(SUM(test_runs),0) FROM usage_records WHERE month=?", (month,)).fetchone()[0]
    judge_month = conn.execute("SELECT COALESCE(SUM(llm_judge_runs),0) FROM usage_records WHERE month=?", (month,)).fetchone()[0]
    runs_all = conn.execute("SELECT COALESCE(SUM(total_tests),0) FROM test_run_log").fetchone()[0]

    recent_signups = [dict(r) for r in conn.execute(
        "SELECT id, email, name, plan, status, created_at FROM customers ORDER BY created_at DESC LIMIT 10").fetchall()]
    
    conn.close()
    return {
        "customers": {"total": total, "by_plan": by_plan},
        "revenue": {"mrr": mrr, "arr": mrr * 12},
        "usage": {"test_runs_this_month": runs_month, "llm_judge_this_month": judge_month, "all_time_runs": runs_all},
        "recent_signups": recent_signups,
        "month": month,
    }

@app.get("/api/admin/customers")
def admin_customers(admin_key: str = Query(None)):
    """List all customers with usage data."""
    require_admin(admin_key)
    conn = get_db()
    month = get_current_month()
    rows = conn.execute("""
        SELECT c.*, COALESCE(u.test_runs, 0) as runs_this_month, COALESCE(u.llm_judge_runs, 0) as judge_this_month,
               (SELECT COUNT(*) FROM api_keys WHERE customer_id=c.id AND status='active') as active_keys
        FROM customers c
        LEFT JOIN usage_records u ON c.id = u.customer_id AND u.month = ?
        ORDER BY c.created_at DESC
    """, (month,)).fetchall()
    conn.close()
    return {"customers": [dict(r) for r in rows], "total": len(rows)}

@app.get("/api/admin/customer/{email}")
def admin_customer_detail(email: str, admin_key: str = Query(None)):
    """Get full details for one customer."""
    require_admin(admin_key)
    conn = get_db()
    customer = conn.execute("SELECT * FROM customers WHERE email=?", (email,)).fetchone()
    if not customer:
        conn.close()
        raise HTTPException(404, "Customer not found")
    
    keys = [dict(r) for r in conn.execute("SELECT key_prefix, name, status, last_used_at, created_at FROM api_keys WHERE customer_id=?", (customer['id'],)).fetchall()]
    usage = [dict(r) for r in conn.execute("SELECT * FROM usage_records WHERE customer_id=? ORDER BY month DESC LIMIT 12", (customer['id'],)).fetchall()]
    runs = [dict(r) for r in conn.execute("SELECT * FROM test_run_log WHERE customer_id=? ORDER BY created_at DESC LIMIT 20", (customer['id'],)).fetchall()]
    conn.close()
    
    return {"customer": dict(customer), "api_keys": keys, "usage_history": usage, "recent_runs": runs}

@app.post("/api/admin/customer/{email}/upgrade")
def admin_upgrade_customer(email: str, plan: str = Query(...), admin_key: str = Query(None)):
    """Manually upgrade/downgrade a customer's plan."""
    require_admin(admin_key)
    if plan not in PLANS: raise HTTPException(400, f"Invalid plan. Options: {list(PLANS.keys())}")
    conn = get_db()
    customer = conn.execute("SELECT * FROM customers WHERE email=?", (email,)).fetchone()
    if not customer:
        conn.close()
        raise HTTPException(404, "Customer not found")
    old_plan = customer['plan']
    update_plan(customer['id'], plan)
    conn.close()
    return {"email": email, "old_plan": old_plan, "new_plan": plan, "status": "updated"}

@app.get("/api/admin/usage")
def admin_usage(admin_key: str = Query(None)):
    """Usage breakdown across all customers."""
    require_admin(admin_key)
    conn = get_db()
    month = get_current_month()
    rows = conn.execute("""
        SELECT c.email, c.plan, u.test_runs, u.llm_judge_runs
        FROM usage_records u
        JOIN customers c ON u.customer_id = c.id
        WHERE u.month = ?
        ORDER BY u.test_runs DESC
    """, (month,)).fetchall()
    
    monthly_trend = [dict(r) for r in conn.execute("""
        SELECT month, SUM(test_runs) as total_runs, SUM(llm_judge_runs) as total_judge,
               COUNT(DISTINCT customer_id) as active_users
        FROM usage_records GROUP BY month ORDER BY month DESC LIMIT 12
    """).fetchall()]
    
    conn.close()
    return {"current_month": [dict(r) for r in rows], "monthly_trend": monthly_trend}

@app.get("/api/admin/runs")
def admin_runs(admin_key: str = Query(None), limit: int = Query(50)):
    """Recent test runs across all customers."""
    require_admin(admin_key)
    conn = get_db()
    rows = conn.execute("""
        SELECT r.*, c.email, c.plan
        FROM test_run_log r
        JOIN customers c ON r.customer_id = c.id
        ORDER BY r.created_at DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return {"runs": [dict(r) for r in rows], "total": len(rows)}

@app.get("/api/admin/revenue")
def admin_revenue(admin_key: str = Query(None)):
    """Revenue breakdown."""
    require_admin(admin_key)
    conn = get_db()
    breakdown = {}
    for plan_id, plan_info in PLANS.items():
        count = conn.execute("SELECT COUNT(*) FROM customers WHERE plan=? AND status='active'", (plan_id,)).fetchone()[0]
        breakdown[plan_id] = {"count": count, "price": plan_info["price_monthly"], "revenue": count * plan_info["price_monthly"]}
    mrr = sum(v["revenue"] for v in breakdown.values())
    conn.close()
    return {"breakdown": breakdown, "mrr": mrr, "arr": mrr * 12}
