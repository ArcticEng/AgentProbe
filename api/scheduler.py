"""
AgentProbe Schedule Runner — Background worker that executes due scheduled tests.

Runs as a background thread inside the FastAPI server.
Checks every 60 seconds for schedules whose next_run_at has passed,
executes the tests, stores results, sends webhook/email alerts on failure.
"""

import json
import time
import threading
import traceback
import urllib.request
import urllib.parse
from datetime import datetime, timezone

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def send_webhook(url, payload):
    """POST JSON payload to a webhook URL."""
    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data,
            headers={"Content-Type": "application/json", "User-Agent": "AgentProbe/1.0"},
            method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"[Scheduler] Webhook sent to {url}: {resp.status}")
            return True
    except Exception as e:
        print(f"[Scheduler] Webhook failed for {url}: {e}")
        return False


def send_email_alert(to_email, subject, body):
    """Send email alert via SMTP or external service.
    
    Uses a webhook-to-email approach: POST to a simple endpoint.
    For production, replace with SendGrid/Postmark/SES.
    
    For now, we log and use webhook as fallback.
    """
    smtp_host = os.environ.get("SMTP_HOST", "")
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    smtp_from = os.environ.get("SMTP_FROM", "alerts@agentprobe.dev")

    if smtp_host and smtp_user:
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = smtp_from
            msg["To"] = to_email
            msg.attach(MIMEText(body, "plain"))

            # HTML version
            html_body = f"""<div style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:20px;">
                <div style="background:#06060a;color:#e0e0e8;padding:24px;border-radius:12px;">
                    <h2 style="color:#ef4444;margin:0 0 16px;">{subject}</h2>
                    <pre style="background:#111;padding:16px;border-radius:8px;color:#ccc;font-size:13px;overflow-x:auto;white-space:pre-wrap;">{body}</pre>
                    <p style="color:#666;font-size:12px;margin-top:16px;">— AgentProbe Monitoring</p>
                </div>
            </div>"""
            msg.attach(MIMEText(html_body, "html"))

            port = int(os.environ.get("SMTP_PORT", "587"))
            with smtplib.SMTP(smtp_host, port) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_from, [to_email], msg.as_string())
            print(f"[Scheduler] Email sent to {to_email}: {subject}")
            return True
        except Exception as e:
            print(f"[Scheduler] Email failed for {to_email}: {e}")
            return False
    else:
        print(f"[Scheduler] Email alert (no SMTP configured): to={to_email} subject={subject}")
        print(f"[Scheduler] Body: {body[:200]}...")
        return False


def run_scheduled_test(schedule):
    """Execute a single scheduled test and return results."""
    from agentprobe import AgentProbe, MockAgentAdapter, HTTPAgentAdapter
    from agentprobe import OpenAIAgentAdapter, AnthropicAgentAdapter
    from agentprobe.templates import ExtendedTemplates
    from agentprobe.system_templates import SystemTemplates
    from agentprobe.adapters import RESTAPIAdapter, WebsiteAdapter
    from billing import (track_usage, log_test_run, save_test_run,
                         update_schedule_last_run, check_usage_limit, PLANS)
    import uuid

    template_id = schedule["template_id"]
    agent_config = json.loads(schedule["agent_config"]) if isinstance(schedule["agent_config"], str) else schedule["agent_config"]
    customer_id = schedule["customer_id"]
    frequency = schedule["frequency"]
    schedule_id = schedule["id"]

    # Check usage limits
    plan = schedule.get("plan", "pro")
    limit_info = check_usage_limit(customer_id, plan)
    if not limit_info["allowed"]:
        print(f"[Scheduler] Skipping {schedule_id}: usage limit reached for {customer_id}")
        update_schedule_last_run(schedule_id, frequency)
        return None

    # Build adapter
    agent_type = agent_config.get("type", "mock")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    openai_key = os.environ.get("OPENAI_API_KEY", "")

    if agent_type == "anthropic":
        key = agent_config.get("api_key") or anthropic_key
        adapter = AnthropicAgentAdapter(key,
            model=agent_config.get("model", "claude-haiku-4-5-20251001"),
            system_prompt=agent_config.get("system_prompt"))
    elif agent_type == "openai":
        key = agent_config.get("api_key") or openai_key
        adapter = OpenAIAgentAdapter(key,
            model=agent_config.get("model", "gpt-4o-mini"),
            system_prompt=agent_config.get("system_prompt"))
    elif agent_type == "rest_api" and agent_config.get("endpoint"):
        adapter = RESTAPIAdapter(agent_config["endpoint"],
            auth_token=agent_config.get("auth_token"))
    elif agent_type == "website":
        adapter = WebsiteAdapter()
    elif agent_type == "http" and agent_config.get("endpoint"):
        adapter = HTTPAgentAdapter(agent_config["endpoint"])
    else:
        adapter = MockAgentAdapter({}, "OK")

    # Get template
    suite = None
    try:
        suite = SystemTemplates.get(template_id)
    except (ValueError, KeyError):
        pass
    if not suite:
        try:
            suite = ExtendedTemplates.get(template_id)
        except (ValueError, KeyError):
            print(f"[Scheduler] Unknown template: {template_id}")
            update_schedule_last_run(schedule_id, frequency)
            return None

    # Run tests
    probe = AgentProbe(adapter=adapter)
    result = probe.run(suite)

    # Track usage
    track_usage(customer_id, test_runs=result.total)
    log_test_run(customer_id, f"sched:{schedule_id[:8]}", result.suite_name,
                 result.total, result.passed, result.failed, False, result.avg_latency)

    # Save run
    run_id = str(uuid.uuid4())[:8]
    run_data = result.to_dict()
    run_data["id"] = run_id
    run_data["scheduled"] = True
    run_data["schedule_id"] = schedule_id
    save_test_run(run_id, customer_id, result.suite_name, run_data)

    # Update schedule timing
    update_schedule_last_run(schedule_id, frequency)

    return {
        "run_id": run_id,
        "suite_name": result.suite_name,
        "total": result.total,
        "passed": result.passed,
        "failed": result.failed,
        "pass_rate": result.pass_rate,
        "avg_score": result.avg_score,
        "avg_latency_ms": result.avg_latency,
    }


def process_due_schedules():
    """Find and execute all due scheduled tests."""
    from billing import get_due_schedules

    due = get_due_schedules()
    if not due:
        return

    print(f"[Scheduler] Processing {len(due)} due schedule(s)")

    for schedule in due:
        schedule_id = schedule["id"]
        email = schedule.get("email", "")
        webhook_url = schedule.get("webhook_url", "")

        try:
            result = run_scheduled_test(schedule)
            if result is None:
                continue

            print(f"[Scheduler] {schedule_id}: {result['suite_name']} — "
                  f"{result['passed']}/{result['total']} passed ({result['pass_rate']:.0%})")

            # Check for failures
            has_failures = result["failed"] > 0
            is_degraded = result["pass_rate"] < 0.8

            # Build alert payload
            alert_payload = {
                "event": "scheduled_test_complete",
                "schedule_id": schedule_id,
                "template": schedule["template_id"],
                "status": "failed" if has_failures else "degraded" if is_degraded else "passed",
                "results": result,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "dashboard_url": f"{os.environ.get('DOMAIN', '')}/dashboard",
            }

            # Send webhook (always, if configured)
            if webhook_url:
                send_webhook(webhook_url, alert_payload)

            # Send email alert on failure/degradation
            if (has_failures or is_degraded) and email and schedule.get("email_on_fail", 1):
                subject = f"AgentProbe Alert: {result['suite_name']} — {result['failed']} test(s) failed"
                body = (
                    f"Scheduled test results for: {result['suite_name']}\n"
                    f"Schedule: {schedule_id}\n"
                    f"Template: {schedule['template_id']}\n"
                    f"Frequency: {schedule['frequency']}\n\n"
                    f"Results:\n"
                    f"  Total tests:  {result['total']}\n"
                    f"  Passed:       {result['passed']}\n"
                    f"  Failed:       {result['failed']}\n"
                    f"  Pass rate:    {result['pass_rate']:.0%}\n"
                    f"  Avg score:    {result['avg_score']:.2f}\n"
                    f"  Avg latency:  {result['avg_latency_ms']:.0f}ms\n\n"
                    f"View details: {os.environ.get('DOMAIN', '')}\n\n"
                    f"— AgentProbe Monitoring"
                )
                send_email_alert(email, subject, body)

        except Exception as e:
            print(f"[Scheduler] Error running schedule {schedule_id}: {e}")
            traceback.print_exc()


def scheduler_loop():
    """Background loop that checks for due schedules every 60 seconds."""
    print("[Scheduler] Background scheduler started (60s interval)")
    # Wait 30s after startup before first check
    time.sleep(30)

    while True:
        try:
            process_due_schedules()
        except Exception as e:
            print(f"[Scheduler] Loop error: {e}")
            traceback.print_exc()
        time.sleep(60)


def start_scheduler():
    """Launch the scheduler as a daemon thread."""
    t = threading.Thread(target=scheduler_loop, daemon=True, name="agentprobe-scheduler")
    t.start()
    print("[Scheduler] Daemon thread launched")
    return t
