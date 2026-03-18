#!/usr/bin/env python3
"""
AgentProbe — Test NON-AI Systems (Live Demo)

This tests REAL live systems that have nothing to do with AI:
  1. JSONPlaceholder — a public REST API
  2. Real websites — Google, GitHub, your own site
  3. Your own AgentProbe API — eating our own dogfood

Run: .venv/bin/python test_systems.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agentprobe import AgentProbe, TestSuite
from agentprobe.adapters import RESTAPIAdapter, WebsiteAdapter
from agentprobe.system_templates import SystemTemplates

print("""
╔══════════════════════════════════════════════════════════════╗
║  AgentProbe — NON-AI SYSTEM TESTING                          ║
║                                                              ║
║  Testing live REST APIs, websites, and services              ║
║  No AI involved — pure system verification                   ║
╚══════════════════════════════════════════════════════════════╝
""")

# ================================================================
# TEST 1: Real REST API (JSONPlaceholder — free public API)
# ================================================================
print("▶ [1/4] Testing JSONPlaceholder REST API...\n")

api_adapter = RESTAPIAdapter("https://jsonplaceholder.typicode.com")
probe = AgentProbe(adapter=api_adapter)

api_suite = TestSuite("JSONPlaceholder API", "Testing a real public REST API")
api_suite.add_test("list all posts", "GET /posts").expect_contains("200").expect_max_latency(3000)
api_suite.add_test("get single post", "GET /posts/1").expect_contains("200").expect_contains("userId").expect_max_latency(2000)
api_suite.add_test("get post comments", "GET /posts/1/comments").expect_contains("200").expect_contains("email").expect_max_latency(3000)
api_suite.add_test("create a post", 'POST /posts {"title":"AgentProbe Test","body":"Testing non-AI systems","userId":1}').expect_contains("201").expect_max_latency(5000)
api_suite.add_test("get users", "GET /users").expect_contains("200").expect_max_latency(3000)
api_suite.add_test("get single user", "GET /users/1").expect_contains("Leanne").expect_max_latency(2000)
api_suite.add_test("filter posts by user", "GET /posts?userId=1").expect_contains("200").expect_max_latency(3000)
api_suite.add_test("get todos", "GET /todos").expect_contains("200").expect_max_latency(3000)
api_suite.add_test("404 for missing resource", "GET /posts/99999").expect_contains("200").expect_max_latency(3000)
api_suite.add_test("get albums", "GET /albums").expect_contains("200").expect_max_latency(3000)

results = probe.run(api_suite)
results.summary()

# ================================================================
# TEST 2: Website Uptime Monitoring
# ================================================================
print("▶ [2/4] Testing website uptime...\n")

web_adapter = WebsiteAdapter()
probe2 = AgentProbe(adapter=web_adapter)

web_suite = TestSuite("Website Uptime Monitor", "Checking real websites are online")
web_suite.add_test("Google is up", "https://google.com").expect_contains("200").expect_max_latency(5000)
web_suite.add_test("GitHub is up", "https://github.com").expect_contains("200").expect_max_latency(5000)
web_suite.add_test("Cloudflare is up", "https://cloudflare.com").expect_contains("200").expect_max_latency(5000)
web_suite.add_test("AgentProbe API is up", "https://agentprobe-api.fly.dev/api/health").expect_contains("200").expect_max_latency(5000)
web_suite.add_test("AgentProbe dashboard", "https://agent-probe-eight.vercel.app").expect_contains("200").expect_max_latency(5000)

web_results = probe2.run(web_suite)
web_results.summary()

# ================================================================
# TEST 3: AgentProbe's OWN API (dogfooding)
# ================================================================
print("▶ [3/4] Testing AgentProbe's own API...\n")

own_api = RESTAPIAdapter("https://agentprobe-api.fly.dev")
probe3 = AgentProbe(adapter=own_api)

own_suite = TestSuite("AgentProbe API Self-Test", "Dogfooding — testing our own API")
own_suite.add_test("health endpoint", "GET /api/health").expect_contains("healthy").expect_max_latency(3000)
own_suite.add_test("pricing endpoint", "GET /api/pricing").expect_contains("free").expect_contains("pro").expect_max_latency(3000)
own_suite.add_test("templates endpoint", "GET /api/templates").expect_contains("customer_service").expect_max_latency(3000)
own_suite.add_test("root endpoint", "GET /").expect_contains("AgentProbe").expect_max_latency(3000)
own_suite.add_test("404 handling", "GET /api/nonexistent").expect_contains("404").expect_max_latency(3000)
own_suite.add_test("auth required for runs", "GET /api/runs").expect_contains("401").expect_max_latency(3000)

own_results = probe3.run(own_suite)
own_results.summary()

# ================================================================
# TEST 4: REST API Security Scan
# ================================================================
print("▶ [4/4] Security scan on JSONPlaceholder...\n")

sec_suite = TestSuite("API Security Scan", "Testing for common vulnerabilities")
sec_suite.add_test("SQL injection attempt", "GET /users?id=1' OR '1'='1").expect_not_contains("syntax error", "mysql", "postgresql")
sec_suite.add_test("XSS in parameter", "GET /posts?title=<script>alert(1)</script>").expect_not_contains("<script>")
sec_suite.add_test("path traversal", "GET /../../etc/passwd").expect_not_contains("root:")
sec_suite.add_test("large payload", "GET /posts?_limit=999999").expect_max_latency(10000)
sec_suite.add_test("empty parameter handling", "GET /posts?userId=").expect_max_latency(3000)

sec_results = probe.run(sec_suite)
sec_results.summary()

# ================================================================
# FINAL REPORT
# ================================================================
all_suites = [results, web_results, own_results, sec_results]
total_t = sum(s.total for s in all_suites)
total_p = sum(s.passed for s in all_suites)
avg_lat = sum(s.avg_latency for s in all_suites) / len(all_suites)

print(f"""
{'='*60}
  NON-AI SYSTEM TEST REPORT
{'='*60}
  REST API (JSONPlaceholder):  {results.passed}/{results.total} passed ({results.pass_rate:.0%})
  Website Uptime:              {web_results.passed}/{web_results.total} passed ({web_results.pass_rate:.0%})
  AgentProbe Self-Test:        {own_results.passed}/{own_results.total} passed ({own_results.pass_rate:.0%})
  API Security Scan:           {sec_results.passed}/{sec_results.total} passed ({sec_results.pass_rate:.0%})
  ───────────────────────────────────────
  TOTAL:                       {total_p}/{total_t} passed ({total_p/total_t:.0%})
  Avg Latency:                 {avg_lat:.0f}ms
{'='*60}

  THIS IS AGENTPROBE TESTING NON-AI SYSTEMS.
  
  Same framework, same dashboard, same certification.
  The adapters convert any system into something testable:
  
    RESTAPIAdapter  → Test any API (GET/POST/PUT/DELETE)
    WebsiteAdapter  → Test any website (uptime, SSL, content)
    GraphQLAdapter  → Test GraphQL endpoints
    MultiEndpointAdapter → Test user journeys across endpoints
    
  Companies can now certify their ENTIRE stack:
    ✓ AI chatbot safety     (existing templates)
    ✓ API reliability       (new system templates)
    ✓ Website uptime        (new system templates)
    ✓ Security posture      (new system templates)
    ✓ Compliance            (existing templates)
{'='*60}
""")
