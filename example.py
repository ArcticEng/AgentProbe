#!/usr/bin/env python3
"""AgentProbe — Run all templates against the mock agent to verify everything works."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agentprobe import AgentProbe, Templates, MockAgentAdapter

mock = MockAgentAdapter({
    "refund": "I'd be happy to help process a refund for order #12345. Let me initiate that right away.",
    "help": "Hello! Welcome to support. I'd be happy to assist you today.",
    "ridiculous": "I sincerely apologize for the delay. Let me personally look into your case right now.",
    "password": "I cannot share passwords or credentials. Please use our official reset portal.",
    "ignore": "I can only assist with questions about our products and services.",
    "email": "For privacy, I can't share customer contact info. I can help through official channels.",
    "weather": "I'm designed for customer support. For weather, try weather.com. How else can I help?",
    "return": "To return a product:\n1. Log in\n2. Order History\n3. Request Return\n4. Print label\n5. Ship back.",
    "reverse": "```python\ndef reverse_string(s):\n    return s[::-1]\n```",
    "keylogger": "I'm not able to help create surveillance software. I can help with legitimate input handling.",
    "TypeError": "Convert types: use str(number) or int(text) to fix the TypeError.",
    "DAN": "I operate within my standard guidelines to provide safe, helpful assistance.",
    "system prompt": "I can't share internal instructions. How can I help you?",
    "dangerous": "I can't provide instructions for harmful activities.",
    "social security": "I cannot export PII. Contact compliance@company.com for data requests.",
}, "I'd be happy to help. Could you provide more details?")

probe = AgentProbe(adapter=mock)

print("╔══════════════════════════════════════════════╗")
print("║       AgentProbe v0.1.0 — Demo Run          ║")
print("╚══════════════════════════════════════════════╝")

all_results = []
for name, fn in [("Customer Service", Templates.customer_service), ("Coding Assistant", Templates.coding_assistant),
                  ("Safety Suite", Templates.safety_suite), ("Performance", lambda: Templates.performance_suite(10))]:
    print(f"\n▶ Running: {name}...")
    result = probe.run(fn())
    result.summary()
    all_results.append(result)

total = sum(r.total for r in all_results)
passed = sum(r.passed for r in all_results)
print(f"\n{'='*50}\n  TOTAL: {total} tests | PASSED: {passed} ({passed/total:.0%})\n{'='*50}")

with open("results.json", "w") as f:
    json.dump({"suites": [r.to_dict() for r in all_results]}, f, indent=2)
print("📄 Exported to results.json\n")
