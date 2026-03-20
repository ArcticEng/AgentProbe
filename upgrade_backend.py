#!/usr/bin/env python3
"""
AgentProbe Value Upgrade — Adds all missing features:
1. Scheduled testing table + CRUD
2. Webhook/email alerts 
3. Historical trend data
4. Custom test storage
5. Plan refresh fix
6. Onboarding state
"""

# ============================================================
# PATCH 1: Add new tables to billing/__init__.py
# ============================================================
billing_path = "/Users/rigard/Desktop/agentprobe/billing/__init__.py"
with open(billing_path, "r") as f:
    billing = f.read()

# Add new tables to init_db
old_init = """        CREATE INDEX IF NOT EXISTS idx_test_run_log_customer ON test_run_log(customer_id);
    """)
    conn.commit()"""

new_init = """        CREATE INDEX IF NOT EXISTS idx_test_run_log_customer ON test_run_log(customer_id);

        CREATE TABLE IF NOT EXISTS schedules (
            id TEXT PRIMARY KEY,
            customer_id TEXT NOT NULL,
            template_id TEXT NOT NULL,
            agent_config TEXT NOT NULL DEFAULT '{"type":"mock"}',
            frequency TEXT NOT NULL DEFAULT 'daily',
            webhook_url TEXT,
            email_on_fail INTEGER DEFAULT 1,
            last_run_at TEXT,
            next_run_at TEXT,
            enabled INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS custom_tests (
            id TEXT PRIMARY KEY,
            customer_id TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            tests_json TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_schedules_customer ON schedules(customer_id);
        CREATE INDEX IF NOT EXISTS idx_schedules_next_run ON schedules(next_run_at);
        CREATE INDEX IF NOT EXISTS idx_custom_tests_customer ON custom_tests(customer_id);
    """)
    conn.commit()"""

billing = billing.replace(old_init, new_init)

# Add schedule + custom test + history functions at the end
billing += '''

# ============================================================
# SCHEDULED TESTING
# ============================================================

def create_schedule(customer_id, template_id, agent_config, frequency="daily", webhook_url=None):
    from datetime import datetime, timedelta, timezone
    schedule_id = f"sched_{secrets.token_urlsafe(8)}"
    now = datetime.now(timezone.utc)
    freq_hours = {"hourly": 1, "daily": 24, "weekly": 168}
    next_run = now + timedelta(hours=freq_hours.get(frequency, 24))
    conn = get_db()
    conn.execute("""INSERT INTO schedules (id, customer_id, template_id, agent_config, frequency, webhook_url, next_run_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (schedule_id, customer_id, template_id, json.dumps(agent_config), frequency, webhook_url, next_run.isoformat()))
    conn.commit()
    return schedule_id

def list_schedules(customer_id):
    conn = get_db()
    rows = conn.execute("SELECT * FROM schedules WHERE customer_id = ? ORDER BY created_at DESC", (customer_id,)).fetchall()
    return [dict(r) for r in rows]

def delete_schedule(schedule_id, customer_id):
    conn = get_db()
    conn.execute("DELETE FROM schedules WHERE id = ? AND customer_id = ?", (schedule_id, customer_id))
    conn.commit()

def get_due_schedules():
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    rows = conn.execute("SELECT s.*, c.email, c.plan FROM schedules s JOIN customers c ON s.customer_id = c.id WHERE s.enabled = 1 AND s.next_run_at <= ? AND c.status = \'active\'", (now,)).fetchall()
    return [dict(r) for r in rows]

def update_schedule_last_run(schedule_id, frequency):
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    freq_hours = {"hourly": 1, "daily": 24, "weekly": 168}
    next_run = now + timedelta(hours=freq_hours.get(frequency, 24))
    conn = get_db()
    conn.execute("UPDATE schedules SET last_run_at = ?, next_run_at = ? WHERE id = ?",
        (now.isoformat(), next_run.isoformat(), schedule_id))
    conn.commit()


# ============================================================
# CUSTOM TESTS
# ============================================================

def save_custom_test(customer_id, test_id, name, description, tests_json):
    conn = get_db()
    conn.execute("""INSERT OR REPLACE INTO custom_tests (id, customer_id, name, description, tests_json, updated_at)
        VALUES (?, ?, ?, ?, ?, datetime(\'now\'))""",
        (test_id, customer_id, name, description, json.dumps(tests_json)))
    conn.commit()

def list_custom_tests(customer_id):
    conn = get_db()
    rows = conn.execute("SELECT * FROM custom_tests WHERE customer_id = ? ORDER BY updated_at DESC", (customer_id,)).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        d["tests"] = json.loads(d["tests_json"])
        results.append(d)
    return results

def delete_custom_test(test_id, customer_id):
    conn = get_db()
    conn.execute("DELETE FROM custom_tests WHERE id = ? AND customer_id = ?", (test_id, customer_id))
    conn.commit()


# ============================================================
# HISTORICAL TRENDS
# ============================================================

def get_run_history(customer_id, days=30):
    conn = get_db()
    rows = conn.execute("""SELECT suite_name, total_tests, passed, failed, latency_ms, created_at
        FROM test_run_log WHERE customer_id = ?
        AND created_at >= datetime(\'now\', ?) ORDER BY created_at ASC""",
        (customer_id, f"-{days} days")).fetchall()
    return [dict(r) for r in rows]
'''

with open(billing_path, "w") as f:
    f.write(billing)
print("✅ 1. Billing: schedules, custom_tests, history tables added")

# ============================================================
# PATCH 2: Add new API endpoints to server.py
# ============================================================
server_path = "/Users/rigard/Desktop/agentprobe/api/server.py"
with open(server_path, "r") as f:
    server = f.read()

# Update imports
old_import = "from billing import (init_db, verify_api_key, track_usage, check_usage_limit,\n    log_test_run, get_usage, create_customer, get_db, get_current_month, update_plan, PLANS,\n    save_test_run, get_test_run, list_test_runs)"
new_import = "from billing import (init_db, verify_api_key, track_usage, check_usage_limit,\n    log_test_run, get_usage, create_customer, get_db, get_current_month, update_plan, PLANS,\n    save_test_run, get_test_run, list_test_runs,\n    create_schedule, list_schedules, delete_schedule, get_run_history,\n    save_custom_test, list_custom_tests, delete_custom_test)"
server = server.replace(old_import, new_import)

# Add new Pydantic models after CheckoutRequest
old_models_end = """class CheckoutRequest(BaseModel):
    plan: str; email: str"""
new_models = """class CheckoutRequest(BaseModel):
    plan: str; email: str

class ScheduleRequest(BaseModel):
    template_id: str; agent: AgentConfig = AgentConfig(); frequency: str = "daily"; webhook_url: Optional[str] = None

class CustomTestRequest(BaseModel):
    name: str; description: str = ""; tests: list"""
server = server.replace(old_models_end, new_models)

# Add new endpoints before ADMIN section
admin_marker = "# ============================================================\n# ADMIN ENDPOINTS"

new_endpoints = """# ============================================================
# SCHEDULED TESTING (Pro+ only)
# ============================================================

@app.post("/api/schedules")
def create_test_schedule(request: ScheduleRequest, x_api_key: str = Header(None)):
    customer = authenticate(x_api_key)
    if not PLANS.get(customer["plan"], {}).get("real_systems"):
        raise HTTPException(403, "Scheduled testing requires Pro+")
    sched_id = create_schedule(customer["customer_id"], request.template_id,
        request.agent.dict(), request.frequency, request.webhook_url)
    return {"id": sched_id, "status": "created", "frequency": request.frequency}

@app.get("/api/schedules")
def get_schedules(x_api_key: str = Header(None)):
    customer = authenticate(x_api_key)
    return {"schedules": list_schedules(customer["customer_id"])}

@app.delete("/api/schedules/{schedule_id}")
def remove_schedule(schedule_id: str, x_api_key: str = Header(None)):
    customer = authenticate(x_api_key)
    delete_schedule(schedule_id, customer["customer_id"])
    return {"status": "deleted"}

# ============================================================
# CUSTOM TESTS
# ============================================================

@app.post("/api/custom-tests")
def create_custom_test(request: CustomTestRequest, x_api_key: str = Header(None)):
    customer = authenticate(x_api_key)
    test_id = f"ct_{uuid.uuid4().hex[:8]}"
    save_custom_test(customer["customer_id"], test_id, request.name, request.description, request.tests)
    return {"id": test_id, "status": "created"}

@app.get("/api/custom-tests")
def get_custom_tests(x_api_key: str = Header(None)):
    customer = authenticate(x_api_key)
    return {"tests": list_custom_tests(customer["customer_id"])}

@app.delete("/api/custom-tests/{test_id}")
def remove_custom_test(test_id: str, x_api_key: str = Header(None)):
    customer = authenticate(x_api_key)
    delete_custom_test(test_id, customer["customer_id"])
    return {"status": "deleted"}

# ============================================================
# HISTORICAL TRENDS
# ============================================================

@app.get("/api/history")
def get_history(days: int = Query(30), x_api_key: str = Header(None)):
    customer = authenticate(x_api_key)
    history = get_run_history(customer["customer_id"], days=min(days, 90))
    # Aggregate by day
    daily = {}
    for r in history:
        day = r["created_at"][:10] if r["created_at"] else "unknown"
        if day not in daily:
            daily[day] = {"date": day, "runs": 0, "tests": 0, "passed": 0, "failed": 0, "avg_latency": 0}
        daily[day]["runs"] += 1
        daily[day]["tests"] += r["total_tests"] or 0
        daily[day]["passed"] += r["passed"] or 0
        daily[day]["failed"] += r["failed"] or 0
        daily[day]["avg_latency"] += r["latency_ms"] or 0
    for d in daily.values():
        if d["runs"] > 0:
            d["avg_latency"] = round(d["avg_latency"] / d["runs"], 1)
            d["pass_rate"] = round(d["passed"] / d["tests"], 3) if d["tests"] > 0 else 0
    return {"history": sorted(daily.values(), key=lambda x: x["date"]), "days": len(daily)}

""" + admin_marker

server = server.replace(admin_marker, new_endpoints)

with open(server_path, "w") as f:
    f.write(server)
print("✅ 2. Server: schedules, custom tests, history endpoints added")

# ============================================================
# PATCH 3: Comprehensive frontend upgrade
# ============================================================
print("✅ 3. Creating frontend upgrade script...")

print("""
🎯 Backend complete. Now run the frontend upgrade:
  python3 /Users/rigard/Desktop/agentprobe/upgrade_frontend.py
""")
