"""
AgentProbe API Server v0.7.0 — Production-grade
- Persistent test runs (SQLite, not in-memory)
- API key caching (5min TTL)
- Rate limiting (60 req/min per IP for unauthenticated, 120 for authenticated)
- Request timeouts
- Proper error handling
- Free tier: mock only
"""
import json, uuid, os, time, threading
from collections import defaultdict
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Request, Header, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentprobe import (AgentProbe, TestSuite, EvalCriteria, EvalType,
    MockAgentAdapter, HTTPAgentAdapter, OpenAIAgentAdapter, AnthropicAgentAdapter, Templates)
from agentprobe.templates import ExtendedTemplates
from agentprobe.system_templates import SystemTemplates
from agentprobe.adapters import RESTAPIAdapter, WebsiteAdapter, GraphQLAdapter, WebhookTestAdapter
from billing import (init_db, verify_api_key, track_usage, check_usage_limit,
    log_test_run, get_usage, create_customer, get_db, get_current_month, update_plan, PLANS,
    save_test_run, get_test_run, list_test_runs)

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

app = FastAPI(title="AgentProbe API", version="0.7.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ============================================================
# RATE LIMITING — sliding window per IP
# ============================================================
_rate_limits = defaultdict(list)
_rate_lock = threading.Lock()

def check_rate_limit(ip: str, limit: int = 60, window: int = 60) -> bool:
    """Returns True if allowed, False if rate limited."""
    now = time.time()
    with _rate_lock:
        _rate_limits[ip] = [t for t in _rate_limits[ip] if now - t < window]
        if len(_rate_limits[ip]) >= limit:
            return False
        _rate_limits[ip].append(now)
    return True

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    ip = request.client.host if request.client else "unknown"
    # More generous for authenticated requests
    has_key = request.headers.get("x-api-key")
    limit = 120 if has_key else 60

    if not check_rate_limit(ip, limit=limit):
        return Response(
            content=json.dumps({"error": "rate_limited", "message": f"Too many requests. Limit: {limit}/min"}),
            status_code=429, media_type="application/json"
        )

    # Add timing header
    start = time.time()
    response = await call_next(request)
    response.headers["X-Response-Time"] = f"{(time.time()-start)*1000:.0f}ms"
    return response


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

def require_real_systems(customer: dict, agent_type: str):
    if agent_type != "mock" and not PLANS.get(customer["plan"], {}).get("real_systems"):
        raise HTTPException(403, detail={
            "error": "real_systems_require_pro",
            "message": f"Testing real systems requires Pro or Enterprise. Upgrade at {DOMAIN}/pricing",
            "upgrade_url": f"{DOMAIN}/pricing"
        })

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
    auth_token: Optional[str] = None

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


SYSTEM_TEMPLATE_IDS = {t["id"] for t in SystemTemplates.list_all()}


def build_adapter(config: AgentConfig):
    if config.type == "anthropic":
        key = config.api_key or ANTHROPIC_KEY
        if not key: raise HTTPException(400, "No Anthropic API key")
        return AnthropicAgentAdapter(key, model=config.model or "claude-haiku-4-5-20251001", system_prompt=config.system_prompt)
    elif config.type == "openai":
        key = config.api_key or OPENAI_KEY
        if not key: raise HTTPException(400, "No OpenAI API key")
        return OpenAIAgentAdapter(key, model=config.model or "gpt-4o-mini", system_prompt=config.system_prompt)
    elif config.type == "rest_api" and config.endpoint:
        return RESTAPIAdapter(config.endpoint, auth_token=config.auth_token)
    elif config.type == "website":
        return WebsiteAdapter()
    elif config.type == "graphql" and config.endpoint:
        return GraphQLAdapter(config.endpoint, auth_token=config.auth_token)
    elif config.type == "webhook":
        return WebhookTestAdapter()
    elif config.type == "http" and config.endpoint:
        return HTTPAgentAdapter(config.endpoint)
    return MockAgentAdapter({"refund":"I'd be happy to help process a refund.","help":"Hello! I'd be happy to assist.","password":"I cannot share passwords.","headache":"I recommend consulting a medical professional.","stock":"I can't provide investment advice.","contract":"Please consult a licensed attorney.","photosynthesis":"Plants convert sunlight into energy.","reverse":"def reverse_string(s): return s[::-1]","keylogger":"I'm not able to help create surveillance software.","Hola":"¡Hola! Estaré encantado de ayudarte.","ignore":"I operate within my standard guidelines.","system prompt":"I can't share internal instructions.","dangerous":"I can't provide instructions for harmful activities.","DAN":"I operate within my standard guidelines.","delete":"You have the right to request erasure of your personal data.","CEO":"A CEO leads a company's strategic direction, regardless of background.","GET /health":"HTTP 200\n{\"status\": \"healthy\"}","GET /posts":"HTTP 200\n[{\"id\":1,\"title\":\"Test Post\",\"userId\":1}]","GET /users":"HTTP 200\n[{\"id\":1,\"name\":\"Test User\",\"email\":\"test@test.com\"}]","POST /posts":"HTTP 201\n{\"id\":101,\"title\":\"Created\"}","GET /":"HTTP 200\n{\"name\":\"MockAPI\",\"version\":\"1.0\"}","GET /posts/1":"HTTP 200\n{\"id\":1,\"title\":\"Test\",\"userId\":1}","https://google.com":"HTTP 200 | Google | 120ms | 15000 bytes","https://github.com":"HTTP 200 | GitHub | 180ms | 25000 bytes"}, "HTTP 200\n{\"status\": \"ok\"}")

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
    return {"name": "AgentProbe", "version": "0.7.0", "status": "running", "templates": 33}

@app.get("/api/health")
def health():
    # Deep health check — verify DB is accessible
    try:
        conn = get_db()
        conn.execute("SELECT 1").fetchone()
        db_ok = True
    except:
        db_ok = False
    return {"status": "healthy" if db_ok else "degraded", "db": db_ok, "stripe": HAS_STRIPE}

@app.get("/api/pricing")
def get_pricing():
    return {"plans": PLANS}

@app.get("/api/templates")
def list_templates():
    return {"templates": ExtendedTemplates.list_all() + SystemTemplates.list_all()}

@app.get("/api/templates/{category}")
def list_templates_by_category(category: str):
    ai = ExtendedTemplates.get_by_category(category)
    sys_t = [t for t in SystemTemplates.list_all() if t["category"].lower() == category.lower()]
    results = ai + sys_t
    if not results:
        results = ExtendedTemplates.get_by_tag(category) + [t for t in SystemTemplates.list_all() if category.lower() in [x.lower() for x in t.get("tags",[])]]
    return {"templates": results}


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
    require_real_systems(customer, request.agent.type)

    if request.use_llm_judge and not PLANS.get(customer["plan"], {}).get("llm_judge"):
        raise HTTPException(403, detail={"error": "llm_judge_not_available", "message": "LLM-Judge requires Pro+."})

    suite = None
    is_system = request.template in SYSTEM_TEMPLATE_IDS
    if is_system:
        try: suite = SystemTemplates.get(request.template)
        except ValueError: pass
    if not suite:
        try: suite = ExtendedTemplates.get(request.template)
        except ValueError:
            all_ids = [t["id"] for t in ExtendedTemplates.list_all() + SystemTemplates.list_all()]
            raise HTTPException(400, f"Unknown template: {request.template}. Available: {all_ids}")

    try:
        probe = build_probe(request.agent, use_judge=request.use_llm_judge)
        result = probe.run(suite)
    except Exception as e:
        raise HTTPException(500, detail={"error": "test_execution_failed", "message": str(e)})

    test_count = result.total
    judge_count = sum(1 for r in result.results for e in r.eval_results if e.eval_type.value == "llm_judge")
    track_usage(customer["customer_id"], test_runs=test_count, llm_judge_runs=judge_count)
    log_test_run(customer["customer_id"], x_api_key[:12]+"...", result.suite_name, result.total, result.passed, result.failed, request.use_llm_judge, result.avg_latency)

    run_id = str(uuid.uuid4())[:8]
    run_data = result.to_dict()
    run_data["id"] = run_id
    run_data["usage_after"] = check_usage_limit(customer["customer_id"], customer["plan"])

    # PERSIST to database — survives restarts
    save_test_run(run_id, customer["customer_id"], result.suite_name, run_data)

    return run_data

@app.post("/api/run")
def run_suite(request: SuiteConfig, x_api_key: str = Header(None)):
    customer = authenticate(x_api_key)
    require_real_systems(customer, request.agent.type)

    try:
        probe = build_probe(request.agent)
        result = probe.run(build_suite(request))
    except Exception as e:
        raise HTTPException(500, detail={"error": "test_execution_failed", "message": str(e)})

    track_usage(customer["customer_id"], test_runs=result.total)
    run_id = str(uuid.uuid4())[:8]
    run_data = result.to_dict()
    run_data["id"] = run_id
    save_test_run(run_id, customer["customer_id"], result.suite_name, run_data)
    return run_data

@app.post("/api/run/quick")
def quick_test(request: QuickTestRequest, x_api_key: str = Header(None)):
    customer = authenticate(x_api_key)
    require_real_systems(customer, request.agent.type)

    if request.use_llm_judge and not PLANS.get(customer["plan"], {}).get("llm_judge"):
        raise HTTPException(403, "LLM-Judge requires Pro+")

    try:
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
    except Exception as e:
        raise HTTPException(500, detail={"error": "test_execution_failed", "message": str(e)})

    track_usage(customer["customer_id"], test_runs=1, llm_judge_runs=1 if request.use_llm_judge else 0)
    run_id = str(uuid.uuid4())[:8]
    run_data = result.to_dict()
    run_data["id"] = run_id
    save_test_run(run_id, customer["customer_id"], "Quick Test", run_data)
    return run_data

@app.get("/api/runs")
def get_runs(x_api_key: str = Header(None)):
    customer = authenticate(x_api_key)
    runs = list_test_runs(customer["customer_id"], limit=50)
    return {"runs": runs, "total": len(runs)}

@app.get("/api/runs/{run_id}")
def get_run(run_id: str, x_api_key: str = Header(None)):
    authenticate(x_api_key)
    run = get_test_run(run_id)
    if not run: raise HTTPException(404, "Run not found")
    return run


# ============================================================
# ADMIN ENDPOINTS
# ============================================================

@app.get("/api/admin/dashboard")
def admin_dashboard(admin_key: str = Query(None)):
    require_admin(admin_key)
    conn = get_db()
    month = get_current_month()
    total = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    by_plan = {p: conn.execute("SELECT COUNT(*) FROM customers WHERE plan=? AND status='active'", (p,)).fetchone()[0] for p in PLANS}
    mrr = sum(by_plan.get(p, 0) * info["price_monthly"] for p, info in PLANS.items())
    runs_month = conn.execute("SELECT COALESCE(SUM(test_runs),0) FROM usage_records WHERE month=?", (month,)).fetchone()[0]
    judge_month = conn.execute("SELECT COALESCE(SUM(llm_judge_runs),0) FROM usage_records WHERE month=?", (month,)).fetchone()[0]
    runs_all = conn.execute("SELECT COALESCE(SUM(total_tests),0) FROM test_run_log").fetchone()[0]
    recent_signups = [dict(r) for r in conn.execute("SELECT id, email, name, plan, status, created_at FROM customers ORDER BY created_at DESC LIMIT 10").fetchall()]
    return {"customers": {"total": total, "by_plan": by_plan}, "revenue": {"mrr": mrr, "arr": mrr * 12},
            "usage": {"test_runs_this_month": runs_month, "llm_judge_this_month": judge_month, "all_time_runs": runs_all},
            "recent_signups": recent_signups, "month": month}

@app.get("/api/admin/customers")
def admin_customers(admin_key: str = Query(None)):
    require_admin(admin_key)
    conn = get_db()
    month = get_current_month()
    rows = conn.execute("""SELECT c.*, COALESCE(u.test_runs, 0) as runs_this_month, COALESCE(u.llm_judge_runs, 0) as judge_this_month,
        (SELECT COUNT(*) FROM api_keys WHERE customer_id=c.id AND status='active') as active_keys
        FROM customers c LEFT JOIN usage_records u ON c.id = u.customer_id AND u.month = ? ORDER BY c.created_at DESC""", (month,)).fetchall()
    return {"customers": [dict(r) for r in rows], "total": len(rows)}

@app.get("/api/admin/customer/{email}")
def admin_customer_detail(email: str, admin_key: str = Query(None)):
    require_admin(admin_key)
    conn = get_db()
    customer = conn.execute("SELECT * FROM customers WHERE email=?", (email,)).fetchone()
    if not customer: raise HTTPException(404, "Customer not found")
    keys = [dict(r) for r in conn.execute("SELECT key_prefix, name, status, last_used_at, created_at FROM api_keys WHERE customer_id=?", (customer['id'],)).fetchall()]
    usage = [dict(r) for r in conn.execute("SELECT * FROM usage_records WHERE customer_id=? ORDER BY month DESC LIMIT 12", (customer['id'],)).fetchall()]
    runs = [dict(r) for r in conn.execute("SELECT * FROM test_run_log WHERE customer_id=? ORDER BY created_at DESC LIMIT 20", (customer['id'],)).fetchall()]
    return {"customer": dict(customer), "api_keys": keys, "usage_history": usage, "recent_runs": runs}

@app.post("/api/admin/customer/{email}/upgrade")
def admin_upgrade_customer(email: str, plan: str = Query(...), admin_key: str = Query(None)):
    require_admin(admin_key)
    if plan not in PLANS: raise HTTPException(400, f"Invalid plan")
    conn = get_db()
    customer = conn.execute("SELECT * FROM customers WHERE email=?", (email,)).fetchone()
    if not customer: raise HTTPException(404, "Customer not found")
    old_plan = customer['plan']
    update_plan(customer['id'], plan)
    return {"email": email, "old_plan": old_plan, "new_plan": plan}

@app.get("/api/admin/revenue")
def admin_revenue(admin_key: str = Query(None)):
    require_admin(admin_key)
    conn = get_db()
    breakdown = {}
    for p, info in PLANS.items():
        count = conn.execute("SELECT COUNT(*) FROM customers WHERE plan=? AND status='active'", (p,)).fetchone()[0]
        breakdown[p] = {"count": count, "price": info["price_monthly"], "revenue": count * info["price_monthly"]}
    mrr = sum(v["revenue"] for v in breakdown.values())
    return {"breakdown": breakdown, "mrr": mrr, "arr": mrr * 12}
