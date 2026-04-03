"""
AgentProbe — Webhook Examples

Shows how to receive AgentProbe webhook alerts in Slack, Discord, or a custom endpoint.
Set the webhook_url when creating a schedule via the API.
"""

# ============================================================
# EXAMPLE 1: Slack Webhook
# ============================================================
# 1. Create a Slack webhook: https://api.slack.com/messaging/webhooks
# 2. Use the webhook URL when creating a schedule:
#
#   curl -X POST https://agentprobe-api.fly.dev/api/schedules \
#     -H "X-API-Key: ap_live_..." \
#     -H "Content-Type: application/json" \
#     -d '{
#       "template_id": "safety_suite",
#       "agent": {"type": "anthropic", "api_key": "sk-ant-...", "system_prompt": "You are a support agent."},
#       "frequency": "daily",
#       "webhook_url": "https://hooks.slack.com/services/T00000/B00000/XXXX"
#     }'
#
# AgentProbe will POST results to your Slack channel when tests run.
# Failed tests trigger an alert automatically.


# ============================================================
# EXAMPLE 2: Custom Python webhook receiver
# ============================================================
# If you want to process webhook payloads yourself:

from fastapi import FastAPI, Request
import json

app = FastAPI()

@app.post("/agentprobe-webhook")
async def receive_agentprobe(request: Request):
    payload = await request.json()
    
    event = payload.get("event")           # "scheduled_test_complete"
    status = payload.get("status")         # "passed", "failed", or "degraded"
    results = payload.get("results", {})
    schedule_id = payload.get("schedule_id")
    
    print(f"AgentProbe: {results.get('suite_name')} — {status}")
    print(f"  Passed: {results.get('passed')}/{results.get('total')}")
    print(f"  Score: {results.get('avg_score', 0):.2f}")
    
    if status in ("failed", "degraded"):
        # Send alert to your team
        # send_slack_message(f"⚠️ {results['suite_name']} failed: {results['failed']} tests")
        # send_pagerduty_alert(...)
        pass
    
    return {"received": True}

# Run: uvicorn webhook_examples:app --port 9000
# Then set webhook_url to: https://your-server.com/agentprobe-webhook


# ============================================================
# EXAMPLE 3: Create a schedule via Python SDK
# ============================================================
# import requests
#
# API = "https://agentprobe-api.fly.dev/api"
# KEY = "ap_live_..."
#
# # Create a daily safety test
# resp = requests.post(f"{API}/schedules",
#     headers={"X-API-Key": KEY, "Content-Type": "application/json"},
#     json={
#         "template_id": "safety_suite",
#         "agent": {
#             "type": "rest_api",
#             "endpoint": "https://your-chatbot-api.com"
#         },
#         "frequency": "daily",
#         "webhook_url": "https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK"
#     })
# print(resp.json())
# # {"id": "sched_abc123", "status": "created", "frequency": "daily"}
#
# # List your schedules
# resp = requests.get(f"{API}/schedules", headers={"X-API-Key": KEY})
# print(resp.json())
#
# # Delete a schedule
# resp = requests.delete(f"{API}/schedules/sched_abc123", headers={"X-API-Key": KEY})
# print(resp.json())
