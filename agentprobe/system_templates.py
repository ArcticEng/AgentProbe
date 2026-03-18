"""
AgentProbe — System Testing Templates (Non-AI)

Test ANY API, website, or service — not just AI agents.

Usage:
    from agentprobe import AgentProbe
    from agentprobe.adapters import RESTAPIAdapter, WebsiteAdapter
    from agentprobe.system_templates import SystemTemplates

    # Test any REST API
    probe = AgentProbe(adapter=RESTAPIAdapter("https://jsonplaceholder.typicode.com"))
    results = probe.run(SystemTemplates.rest_api_health())
    results.summary()

    # Test any website
    probe = AgentProbe(adapter=WebsiteAdapter())
    results = probe.run(SystemTemplates.website_uptime(["https://google.com", "https://github.com"]))
    results.summary()
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agentprobe import TestSuite


class SystemTemplates:
    """Templates for testing non-AI systems: APIs, websites, services."""

    # ================================================================
    # REST API TEMPLATES
    # ================================================================

    @staticmethod
    def rest_api_health(name="REST API Health Check") -> TestSuite:
        """Basic health checks for any REST API."""
        suite = TestSuite(name, "Verify API is responsive and returning valid data", tags=["api", "health"])
        suite.add_test("GET /health responds", "GET /health").expect_contains("200").expect_max_latency(2000)
        suite.add_test("GET / root responds", "GET /").expect_max_latency(3000)
        suite.add_test("404 for missing route", "GET /this-route-does-not-exist-xyz").expect_contains("404")
        suite.add_test("handles bad method", "PATCH /health").expect_max_latency(5000)
        return suite

    @staticmethod
    def rest_api_crud(resource="/users", name="REST API CRUD Operations") -> TestSuite:
        """Test Create/Read/Update/Delete on a resource."""
        suite = TestSuite(name, f"Full CRUD testing for {resource}", tags=["api", "crud"])
        suite.add_test(f"LIST {resource}", f"GET {resource}").expect_contains("200").expect_max_latency(3000)
        suite.add_test(f"GET {resource}/1", f"GET {resource}/1").expect_contains("200").expect_max_latency(2000)
        suite.add_test(f"POST {resource}", f'POST {resource} {{"name":"AgentProbe Test","email":"test@agentprobe.dev"}}').expect_max_latency(5000)
        suite.add_test(f"GET invalid ID", f"GET {resource}/99999999").expect_max_latency(3000)
        return suite

    @staticmethod
    def rest_api_security(name="REST API Security") -> TestSuite:
        """Test API for common security vulnerabilities."""
        suite = TestSuite(name, "Security testing for REST APIs", tags=["api", "security"])
        suite.add_test("SQL injection attempt", "GET /users?id=1' OR '1'='1").expect_not_contains("error", "syntax", "mysql", "postgresql", "sqlite")
        suite.add_test("XSS in parameter", 'GET /search?q=<script>alert("xss")</script>').expect_not_contains("<script>")
        suite.add_test("path traversal", "GET /files/../../../etc/passwd").expect_not_contains("root:")
        suite.add_test("unauthorized access", "GET /admin/users").expect_contains("401", "403", "unauthorized", "forbidden")
        suite.add_test("CORS headers present", "GET /api/data").expect_max_latency(5000)
        suite.add_test("no sensitive headers leaked", "GET /").expect_not_contains("X-Powered-By", "Server: Apache", "Server: nginx")
        return suite

    @staticmethod
    def rest_api_performance(name="REST API Performance", num_requests=20) -> TestSuite:
        """Latency and throughput testing."""
        suite = TestSuite(name, "API performance benchmarks", tags=["api", "performance"])
        for i in range(num_requests):
            suite.add_test(f"request_{i+1}", "GET /").expect_max_latency(3000)
        return suite

    @staticmethod
    def rest_api_pagination(resource="/posts", name="REST API Pagination") -> TestSuite:
        """Test pagination works correctly."""
        suite = TestSuite(name, "Pagination validation", tags=["api", "pagination"])
        suite.add_test("page 1", f"GET {resource}?_page=1&_limit=5").expect_contains("200").expect_max_latency(3000)
        suite.add_test("page 2", f"GET {resource}?_page=2&_limit=5").expect_contains("200").expect_max_latency(3000)
        suite.add_test("large page size", f"GET {resource}?_page=1&_limit=100").expect_max_latency(5000)
        suite.add_test("invalid page", f"GET {resource}?_page=-1").expect_max_latency(3000)
        suite.add_test("page 0", f"GET {resource}?_page=0&_limit=5").expect_max_latency(3000)
        return suite

    # ================================================================
    # WEBSITE TEMPLATES
    # ================================================================

    @staticmethod
    def website_uptime(urls: list = None, name="Website Uptime Monitor") -> TestSuite:
        """Monitor multiple websites for uptime."""
        urls = urls or ["https://google.com", "https://github.com", "https://cloudflare.com"]
        suite = TestSuite(name, "Check that websites are reachable and responding", tags=["website", "uptime"])
        for url in urls:
            domain = url.replace("https://", "").replace("http://", "").split("/")[0]
            suite.add_test(f"{domain} is up", url).expect_contains("200").expect_max_latency(5000)
        return suite

    @staticmethod
    def website_seo(url: str, name="Website SEO Check") -> TestSuite:
        """Basic SEO checks for a website."""
        suite = TestSuite(name, f"SEO checks for {url}", tags=["website", "seo"])
        suite.add_test("has title tag", url).expect_contains("title")
        suite.add_test("loads under 3s", url).expect_max_latency(3000)
        suite.add_test("returns 200", url).expect_contains("200")
        return suite

    @staticmethod
    def website_ssl(urls: list = None, name="SSL Certificate Check") -> TestSuite:
        """Check SSL certificates are valid."""
        urls = urls or ["https://google.com", "https://github.com"]
        suite = TestSuite(name, "Verify SSL certificates", tags=["website", "ssl", "security"])
        for url in urls:
            domain = url.replace("https://", "").split("/")[0]
            suite.add_test(f"{domain} SSL valid", url).expect_contains("200").expect_max_latency(5000)
        return suite

    # ================================================================
    # USER JOURNEY TEMPLATES
    # ================================================================

    @staticmethod
    def ecommerce_journey(name="E-Commerce User Journey") -> TestSuite:
        """Test a typical e-commerce flow: browse → add to cart → checkout."""
        suite = TestSuite(name, "End-to-end e-commerce flow", tags=["journey", "ecommerce"])
        suite.add_test("browse products", "GET /products").expect_contains("200").expect_max_latency(3000)
        suite.add_test("search products", "GET /products?q=laptop").expect_max_latency(3000)
        suite.add_test("view product detail", "GET /products/1").expect_contains("200").expect_max_latency(2000)
        suite.add_test("add to cart", 'POST /cart {"product_id": 1, "quantity": 1}').expect_max_latency(3000)
        suite.add_test("view cart", "GET /cart").expect_contains("200").expect_max_latency(2000)
        suite.add_test("checkout", 'POST /checkout {"cart_id": 1}').expect_max_latency(5000)
        return suite

    @staticmethod
    def auth_flow(name="Authentication Flow") -> TestSuite:
        """Test login/signup/token flow."""
        suite = TestSuite(name, "Authentication and authorization testing", tags=["journey", "auth"])
        suite.add_test("signup", 'POST /auth/signup {"email":"test@agentprobe.dev","password":"Test123!"}').expect_max_latency(5000)
        suite.add_test("login", 'POST /auth/login {"email":"test@agentprobe.dev","password":"Test123!"}').expect_max_latency(3000)
        suite.add_test("access protected route without token", "GET /auth/me").expect_contains("401", "403", "unauthorized")
        suite.add_test("invalid login", 'POST /auth/login {"email":"fake@nope.com","password":"wrong"}').expect_contains("401", "invalid", "unauthorized")
        suite.add_test("password validation", 'POST /auth/signup {"email":"test2@test.com","password":"1"}').expect_max_latency(3000)
        return suite

    # ================================================================
    # TEMPLATE REGISTRY
    # ================================================================

    @classmethod
    def list_all(cls) -> list:
        return [
            {"id": "rest_api_health", "name": "REST API Health Check", "tests": 4, "category": "API Testing", "tags": ["api", "health"]},
            {"id": "rest_api_crud", "name": "REST API CRUD", "tests": 4, "category": "API Testing", "tags": ["api", "crud"]},
            {"id": "rest_api_security", "name": "REST API Security", "tests": 6, "category": "API Testing", "tags": ["api", "security"]},
            {"id": "rest_api_performance", "name": "REST API Performance", "tests": 20, "category": "API Testing", "tags": ["api", "performance"]},
            {"id": "rest_api_pagination", "name": "REST API Pagination", "tests": 5, "category": "API Testing", "tags": ["api", "pagination"]},
            {"id": "website_uptime", "name": "Website Uptime", "tests": 3, "category": "Website Testing", "tags": ["website", "uptime"]},
            {"id": "website_seo", "name": "Website SEO Check", "tests": 3, "category": "Website Testing", "tags": ["website", "seo"]},
            {"id": "website_ssl", "name": "SSL Certificate Check", "tests": 2, "category": "Website Testing", "tags": ["ssl", "security"]},
            {"id": "ecommerce_journey", "name": "E-Commerce Journey", "tests": 6, "category": "User Journeys", "tags": ["journey", "ecommerce"]},
            {"id": "auth_flow", "name": "Authentication Flow", "tests": 5, "category": "User Journeys", "tags": ["journey", "auth"]},
        ]

    @classmethod
    def get(cls, template_id: str, **kwargs) -> TestSuite:
        method = getattr(cls, template_id, None)
        if method and callable(method):
            return method(**kwargs) if kwargs else method()
        raise ValueError(f"Unknown system template: {template_id}")
