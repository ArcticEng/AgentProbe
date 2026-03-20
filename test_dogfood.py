#!/usr/bin/env python3
"""
AgentProbe Dogfood Test — Testing ourselves through our own system.

Tests AgentProbe's own API as if it were a customer's system:
  1. REST API health & reliability
  2. API security scan
  3. Error handling
  4. Authentication flow
  5. Performance under load

Run: .venv/bin/python test_dogfood.py
"""
import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agentprobe import AgentProbe, TestSuite
from agentprobe.adapters import RESTAPIAdapter, WebsiteAdapter
from agentprobe.system_templates import SystemTemplates

API_URL = "https://agentprobe-api.fly.dev"
DASHBOARD_URL = "https://agent-probe-eight.vercel.app"

print("""
╔══════════════════════════════════════════════════════════════╗
║  AgentProbe DOGFOOD — Testing Our Own Platform               ║
║  Running AgentProbe's test suites against AgentProbe         ║
╚══════════════════════════════════════════════════════════════╝
""")

results_all = []

# ================================================================
# TEST 1: API Health & Endpoints
# ================================================================
print("▶ [1/6] API Health & Endpoints...\n")

api = RESTAPIAdapter(API_URL)
probe = AgentProbe(adapter=api)

suite1 = TestSuite("AgentProbe API Health", "Core endpoint availability")
suite1.add_test("root endpoint", "GET /").expect_contains("AgentProbe").expect_contains("0.7").expect_max_latency(3000)
suite1.add_test("health check", "GET /api/health").expect_contains("healthy").expect_max_latency(2000)
suite1.add_test("pricing endpoint", "GET /api/pricing").expect_contains("free").expect_contains("pro").expect_contains("enterprise").expect_max_latency(2000)
suite1.add_test("templates endpoint", "GET /api/templates").expect_contains("customer_service").expect_contains("safety_suite").expect_contains("rest_api_health").expect_max_latency(3000)
suite1.add_test("templates by category", "GET /api/templates/Security").expect_contains("safety").expect_max_latency(3000)
suite1.add_test("404 handling", "GET /api/this-does-not-exist").expect_contains("404").expect_max_latency(2000)

r1 = probe.run(suite1)
r1.summary()
results_all.append({"name": "API Health", "passed": r1.passed, "total": r1.total, "score": r1.avg_score, "pass_rate": r1.pass_rate})

# ================================================================
# TEST 2: Authentication & Authorization
# ================================================================
print("\n▶ [2/6] Authentication & Authorization...\n")

suite2 = TestSuite("AgentProbe Auth", "Authentication enforcement")
suite2.add_test("runs require auth", "GET /api/runs").expect_contains("401").expect_max_latency(2000)
suite2.add_test("run/template requires auth", 'POST /api/run/template {"template":"safety_suite"}').expect_contains("401").expect_max_latency(2000)
suite2.add_test("run/quick requires auth", 'POST /api/run/quick {"message":"test"}').expect_contains("401").expect_max_latency(2000)
suite2.add_test("usage requires auth", "GET /api/billing/usage").expect_contains("401").expect_max_latency(2000)
suite2.add_test("invalid key rejected", "GET /api/runs").expect_contains("401").expect_max_latency(2000)
suite2.add_test("admin requires key", "GET /api/admin/dashboard").expect_contains("403").expect_max_latency(2000)
suite2.add_test("signup works", 'POST /api/billing/signup {"email":"dogfood-test-' + str(int(time.time())) + '@agentprobe.dev","name":"Dogfood Test"}').expect_contains("api_key").expect_max_latency(5000)

r2 = probe.run(suite2)
r2.summary()
results_all.append({"name": "Auth", "passed": r2.passed, "total": r2.total, "score": r2.avg_score, "pass_rate": r2.pass_rate})

# ================================================================
# TEST 3: API Security Scan
# ================================================================
print("\n▶ [3/6] Security Scan...\n")

suite3 = TestSuite("AgentProbe Security", "Common vulnerability checks")
suite3.add_test("SQL injection in path", "GET /api/templates/' OR '1'='1").expect_not_contains("syntax error", "sqlite", "mysql")
suite3.add_test("XSS in query", "GET /api/templates/<script>alert(1)</script>").expect_not_contains("<script>")
suite3.add_test("path traversal", "GET /../../etc/passwd").expect_not_contains("root:")
suite3.add_test("no server header leak", "GET /api/health").expect_not_contains("Server: uvicorn", "X-Powered-By")
suite3.add_test("large payload handling", 'POST /api/billing/signup {"email":"' + 'x'*10000 + '@test.com"}').expect_max_latency(5000)

r3 = probe.run(suite3)
r3.summary()
results_all.append({"name": "Security", "passed": r3.passed, "total": r3.total, "score": r3.avg_score, "pass_rate": r3.pass_rate})

# ================================================================
# TEST 4: Error Handling
# ================================================================
print("\n▶ [4/6] Error Handling...\n")

suite4 = TestSuite("AgentProbe Error Handling", "Graceful error responses")
suite4.add_test("invalid template", 'POST /api/run/template {"template":"nonexistent_template_xyz"}').expect_contains("401").expect_max_latency(3000)
suite4.add_test("empty body POST", "POST /api/billing/signup").expect_max_latency(3000)
suite4.add_test("invalid JSON", "POST /api/billing/signup NOTJSON").expect_max_latency(3000)
suite4.add_test("missing required fields", 'POST /api/billing/signup {"name":"no email"}').expect_max_latency(3000)
suite4.add_test("duplicate signup", 'POST /api/billing/signup {"email":"duplicate-test@test.com"}').expect_max_latency(5000)
suite4.add_test("duplicate signup again", 'POST /api/billing/signup {"email":"duplicate-test@test.com"}').expect_contains("409").expect_max_latency(3000)

r4 = probe.run(suite4)
r4.summary()
results_all.append({"name": "Error Handling", "passed": r4.passed, "total": r4.total, "score": r4.avg_score, "pass_rate": r4.pass_rate})

# ================================================================
# TEST 5: Website / Dashboard Uptime
# ================================================================
print("\n▶ [5/6] Dashboard & Website Uptime...\n")

web = WebsiteAdapter()
probe_web = AgentProbe(adapter=web)

suite5 = TestSuite("AgentProbe Dashboard", "Website availability checks")
suite5.add_test("Dashboard loads", DASHBOARD_URL).expect_contains("200").expect_max_latency(5000)
suite5.add_test("API root accessible", f"{API_URL}/").expect_contains("200").expect_max_latency(3000)
suite5.add_test("Health endpoint web", f"{API_URL}/api/health").expect_contains("200").expect_max_latency(3000)

r5 = probe_web.run(suite5)
r5.summary()
results_all.append({"name": "Website Uptime", "passed": r5.passed, "total": r5.total, "score": r5.avg_score, "pass_rate": r5.pass_rate})

# ================================================================
# TEST 6: API Performance (10 rapid requests)
# ================================================================
print("\n▶ [6/6] Performance Benchmark...\n")

suite6 = TestSuite("AgentProbe Performance", "Latency benchmarks")
for i in range(10):
    suite6.add_test(f"health_req_{i+1}", "GET /api/health").expect_contains("healthy").expect_max_latency(2000)

r6 = probe.run(suite6)
r6.summary()
results_all.append({"name": "Performance", "passed": r6.passed, "total": r6.total, "score": r6.avg_score, "pass_rate": r6.pass_rate})

# ================================================================
# CERTIFICATION EVALUATION
# ================================================================
total_passed = sum(r["passed"] for r in results_all)
total_tests = sum(r["total"] for r in results_all)
overall_score = sum(r["score"] for r in results_all) / len(results_all)
safety_score = results_all[2]["score"]  # Security scan

print(f"""
{'='*60}
  AGENTPROBE DOGFOOD REPORT
{'='*60}""")
for r in results_all:
    status = "✅" if r["pass_rate"] >= 0.8 else "⚠️" if r["pass_rate"] >= 0.6 else "❌"
    print(f"  {status} {r['name']:20s}  {r['passed']}/{r['total']} passed ({r['pass_rate']:.0%})  score: {r['score']:.2f}")

print(f"""  {'─'*50}
  TOTAL:                 {total_passed}/{total_tests} passed ({total_passed/total_tests:.0%})
  Overall Score:         {overall_score:.2f}
  Security Score:        {safety_score:.2f}
{'='*60}

  CERTIFICATION ELIGIBILITY:
""")

# Check each tier
from certification import TIERS, evaluate_for_certification

suite_results = [
    {"suite_name": "API Health", "total": r1.total, "passed": r1.passed, "avg_score": r1.avg_score, "avg_latency_ms": r1.avg_latency},
    {"suite_name": "Auth Security", "total": r2.total, "passed": r2.passed, "avg_score": r2.avg_score, "avg_latency_ms": r2.avg_latency},
    {"suite_name": "Safety Security Scan", "total": r3.total, "passed": r3.passed, "avg_score": r3.avg_score, "avg_latency_ms": r3.avg_latency},
    {"suite_name": "Error Handling", "total": r4.total, "passed": r4.passed, "avg_score": r4.avg_score, "avg_latency_ms": r4.avg_latency},
    {"suite_name": "Website Uptime", "total": r5.total, "passed": r5.passed, "avg_score": r5.avg_score, "avg_latency_ms": r5.avg_latency},
    {"suite_name": "Performance", "total": r6.total, "passed": r6.passed, "avg_score": r6.avg_score, "avg_latency_ms": r6.avg_latency},
]

for tier_id, tier_info in TIERS.items():
    eval_result = evaluate_for_certification(suite_results, tier_id)
    if eval_result["eligible"]:
        print(f"  ✅ {tier_info['name']:35s}  ELIGIBLE  (safety: {eval_result['safety_score']:.0%}, overall: {eval_result['overall_score']:.0%})")
    else:
        print(f"  ❌ {tier_info['name']:35s}  NOT ELIGIBLE")
        for issue in eval_result.get("issues", []):
            print(f"     → {issue}")

print(f"""
{'='*60}
  Run this test regularly to ensure AgentProbe stays certifiable.
  
  If AgentProbe can't certify itself, it can't certify anyone else.
{'='*60}
""")

# Save results
with open("dogfood_results.json", "w") as f:
    json.dump({"timestamp": time.time(), "results": results_all, "total_passed": total_passed, "total_tests": total_tests, "overall_score": overall_score}, f, indent=2)
print("Results saved to dogfood_results.json")
