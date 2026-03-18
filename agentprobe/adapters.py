"""
AgentProbe — System Adapters for Non-AI Testing

These adapters extend AgentProbe beyond AI agents to test ANY system:
  - REST APIs (GET/POST/PUT/DELETE, status codes, response validation)
  - Websites (uptime, content, redirects, SSL, performance)
  - GraphQL endpoints
  - Webhooks
  - Database queries
  - Custom TCP/HTTP services

Usage:
    from agentprobe import AgentProbe, TestSuite
    from agentprobe.adapters import RESTAPIAdapter, WebsiteAdapter, GraphQLAdapter

    # Test a REST API
    probe = AgentProbe(adapter=RESTAPIAdapter("https://api.example.com"))
    suite = TestSuite("API Tests")
    suite.add_test("health check", "GET /health").expect_contains("ok").expect_max_latency(1000)
    results = probe.run(suite)

    # Test a website
    probe = AgentProbe(adapter=WebsiteAdapter())
    suite = TestSuite("Website Tests")
    suite.add_test("homepage loads", "https://example.com").expect_contains("<html").expect_max_latency(3000)
    results = probe.run(suite)
"""

import json
import time
import re
import urllib.request
import urllib.error
import urllib.parse
import ssl
import socket
from typing import Optional


class RESTAPIAdapter:
    """Test any REST API endpoint.
    
    Input format: "METHOD /path" or "METHOD /path BODY_JSON"
    Examples:
        "GET /health"
        "GET /users/123"
        "POST /users {\"name\": \"test\", \"email\": \"test@example.com\"}"
        "PUT /users/123 {\"name\": \"updated\"}"
        "DELETE /users/123"
        "GET /products?category=electronics&limit=10"
    """

    def __init__(self, base_url: str, headers: dict = None, auth_token: str = None):
        self.base_url = base_url.rstrip("/")
        self.headers = headers or {"Content-Type": "application/json"}
        if auth_token:
            self.headers["Authorization"] = f"Bearer {auth_token}"

    def send_message(self, message: str, context=None, history=None) -> tuple:
        # Parse input: "METHOD /path [BODY]"
        parts = message.strip().split(" ", 2)
        method = parts[0].upper() if len(parts) >= 1 else "GET"
        path = parts[1] if len(parts) >= 2 else "/"
        body = parts[2] if len(parts) >= 3 else None

        url = f"{self.base_url}{path}" if path.startswith("/") else path

        try:
            data = body.encode() if body else None
            req = urllib.request.Request(url, data=data, headers=self.headers, method=method)
            
            start = time.time()
            with urllib.request.urlopen(req, timeout=30) as resp:
                response_body = resp.read().decode()
                status_code = resp.status
                response_headers = dict(resp.headers)
                latency = (time.time() - start) * 1000
            
            # Build a response string that evaluators can check
            try:
                parsed = json.loads(response_body)
                response_text = json.dumps(parsed, indent=2)
            except (json.JSONDecodeError, ValueError):
                response_text = response_body

            raw = {
                "status_code": status_code,
                "headers": response_headers,
                "body": response_body,
                "latency_ms": latency,
                "url": url,
                "method": method,
            }
            
            # Prefix with status for easy evaluation
            return f"HTTP {status_code}\n{response_text}", raw

        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode()
            except:
                pass
            return f"HTTP {e.code}\n{body}", {"status_code": e.code, "error": str(e), "body": body}
        except urllib.error.URLError as e:
            return f"ERROR: Connection failed — {e.reason}", {"error": str(e.reason)}
        except socket.timeout:
            return "ERROR: Request timed out", {"error": "timeout"}
        except Exception as e:
            return f"ERROR: {str(e)}", {"error": str(e)}


class WebsiteAdapter:
    """Test any website for uptime, content, SSL, redirects, performance.
    
    Input format: just a URL
    Examples:
        "https://example.com"
        "https://example.com/about"
        "https://api.example.com/v1/status"
    """

    def __init__(self, headers: dict = None, follow_redirects: bool = True):
        self.headers = headers or {"User-Agent": "AgentProbe/1.0 (Website Monitor)"}
        self.follow_redirects = follow_redirects

    def send_message(self, message: str, context=None, history=None) -> tuple:
        url = message.strip()
        if not url.startswith("http"):
            url = f"https://{url}"

        try:
            req = urllib.request.Request(url, headers=self.headers)
            
            start = time.time()
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode(errors="replace")
                status = resp.status
                headers = dict(resp.headers)
                final_url = resp.url
                latency = (time.time() - start) * 1000

            # Check SSL
            ssl_info = self._check_ssl(url)
            
            # Extract title
            title_match = re.search(r"<title[^>]*>(.*?)</title>", body, re.IGNORECASE | re.DOTALL)
            title = title_match.group(1).strip() if title_match else "No title"

            # Build response
            response_text = f"HTTP {status} | {title} | {latency:.0f}ms | {len(body)} bytes"
            if final_url != url:
                response_text += f" | Redirected to: {final_url}"

            raw = {
                "status_code": status,
                "title": title,
                "headers": headers,
                "body_length": len(body),
                "body_preview": body[:2000],
                "latency_ms": latency,
                "url": url,
                "final_url": final_url,
                "redirected": final_url != url,
                "ssl": ssl_info,
                "content_type": headers.get("Content-Type", "unknown"),
            }

            return response_text, raw

        except urllib.error.HTTPError as e:
            return f"HTTP {e.code} | Error: {e.reason}", {"status_code": e.code, "error": str(e)}
        except urllib.error.URLError as e:
            return f"ERROR: {e.reason}", {"error": str(e.reason)}
        except Exception as e:
            return f"ERROR: {str(e)}", {"error": str(e)}

    def _check_ssl(self, url: str) -> dict:
        """Check SSL certificate details."""
        if not url.startswith("https"):
            return {"valid": False, "reason": "Not HTTPS"}
        try:
            hostname = urllib.parse.urlparse(url).hostname
            ctx = ssl.create_default_context()
            with ctx.wrap_socket(socket.socket(), server_hostname=hostname) as s:
                s.settimeout(10)
                s.connect((hostname, 443))
                cert = s.getpeercert()
                return {
                    "valid": True,
                    "issuer": dict(x[0] for x in cert.get("issuer", [])).get("organizationName", "Unknown"),
                    "expires": cert.get("notAfter", "Unknown"),
                    "subject": dict(x[0] for x in cert.get("subject", [])).get("commonName", "Unknown"),
                }
        except Exception as e:
            return {"valid": False, "reason": str(e)}


class GraphQLAdapter:
    """Test GraphQL endpoints.
    
    Input format: GraphQL query string
    Examples:
        "{ users { id name email } }"
        "mutation { createUser(name: \"test\") { id } }"
        "{ product(id: \"123\") { name price inStock } }"
    """

    def __init__(self, endpoint: str, headers: dict = None, auth_token: str = None):
        self.endpoint = endpoint
        self.headers = headers or {"Content-Type": "application/json"}
        if auth_token:
            self.headers["Authorization"] = f"Bearer {auth_token}"

    def send_message(self, message: str, context=None, history=None) -> tuple:
        query = message.strip()
        payload = json.dumps({"query": query}).encode()

        try:
            req = urllib.request.Request(self.endpoint, data=payload, headers=self.headers, method="POST")
            
            start = time.time()
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode())
                latency = (time.time() - start) * 1000

            has_errors = "errors" in body
            response_text = json.dumps(body, indent=2)

            return response_text, {
                "status_code": resp.status,
                "data": body.get("data"),
                "errors": body.get("errors"),
                "has_errors": has_errors,
                "latency_ms": latency,
            }
        except Exception as e:
            return f"ERROR: {str(e)}", {"error": str(e)}


class WebhookTestAdapter:
    """Test webhook delivery by sending payloads to webhook URLs.
    
    Input format: "URL PAYLOAD_JSON"
    Examples:
        "https://hooks.example.com/webhook {\"event\": \"order.created\", \"data\": {\"id\": 123}}"
    """

    def __init__(self, headers: dict = None):
        self.headers = headers or {"Content-Type": "application/json"}

    def send_message(self, message: str, context=None, history=None) -> tuple:
        parts = message.strip().split(" ", 1)
        url = parts[0]
        payload = parts[1] if len(parts) > 1 else "{}"

        try:
            data = payload.encode()
            req = urllib.request.Request(url, data=data, headers=self.headers, method="POST")
            
            start = time.time()
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode()
                latency = (time.time() - start) * 1000

            return f"HTTP {resp.status} | {latency:.0f}ms | {body[:500]}", {
                "status_code": resp.status,
                "body": body,
                "latency_ms": latency,
                "delivered": resp.status < 400,
            }
        except Exception as e:
            return f"ERROR: {str(e)}", {"error": str(e), "delivered": False}


class MultiEndpointAdapter:
    """Test multiple API endpoints in sequence — simulates user journeys.
    
    Input format: JSON array of requests
    Example:
        '[{"method":"POST","path":"/auth/login","body":{"email":"test@test.com","password":"test"}},
          {"method":"GET","path":"/users/me"},
          {"method":"PUT","path":"/users/me","body":{"name":"Updated"}}]'
    """

    def __init__(self, base_url: str, headers: dict = None):
        self.base_url = base_url.rstrip("/")
        self.headers = headers or {"Content-Type": "application/json"}
        self._session_headers = dict(self.headers)

    def send_message(self, message: str, context=None, history=None) -> tuple:
        try:
            steps = json.loads(message)
        except json.JSONDecodeError:
            return "ERROR: Input must be a JSON array of request objects", {"error": "invalid_json"}

        results = []
        total_latency = 0

        for i, step in enumerate(steps):
            method = step.get("method", "GET").upper()
            path = step.get("path", "/")
            body = step.get("body")
            url = f"{self.base_url}{path}"

            try:
                data = json.dumps(body).encode() if body else None
                req = urllib.request.Request(url, data=data, headers=self._session_headers, method=method)
                
                start = time.time()
                with urllib.request.urlopen(req, timeout=30) as resp:
                    resp_body = resp.read().decode()
                    latency = (time.time() - start) * 1000
                    total_latency += latency

                    # Capture auth tokens from response
                    try:
                        parsed = json.loads(resp_body)
                        if "token" in parsed:
                            self._session_headers["Authorization"] = f"Bearer {parsed['token']}"
                        elif "access_token" in parsed:
                            self._session_headers["Authorization"] = f"Bearer {parsed['access_token']}"
                    except:
                        pass

                    results.append({
                        "step": i + 1, "method": method, "path": path,
                        "status": resp.status, "latency_ms": latency, "passed": resp.status < 400,
                    })
            except urllib.error.HTTPError as e:
                results.append({
                    "step": i + 1, "method": method, "path": path,
                    "status": e.code, "error": str(e), "passed": False,
                })
            except Exception as e:
                results.append({
                    "step": i + 1, "method": method, "path": path,
                    "error": str(e), "passed": False,
                })

        passed = sum(1 for r in results if r.get("passed"))
        response_text = f"Journey: {passed}/{len(results)} steps passed | {total_latency:.0f}ms total\n"
        for r in results:
            status = r.get("status", "ERR")
            response_text += f"  Step {r['step']}: {r['method']} {r['path']} → {status} ({r.get('latency_ms', 0):.0f}ms)\n"

        return response_text, {"results": results, "total_latency_ms": total_latency, "passed": passed, "total": len(results)}
