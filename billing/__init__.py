"""
AgentProbe Billing — Production-grade database layer

Handles: customers, API keys, usage tracking, plan enforcement
SQLite with WAL mode + connection pooling + API key caching
"""

import os
import json
import time
import sqlite3
import hashlib
import secrets
import threading
from datetime import datetime, timezone
from typing import Optional
from functools import lru_cache

DB_PATH = os.environ.get("AGENTPROBE_DB", os.path.join(os.path.dirname(__file__), "agentprobe.db"))


# ============================================================
# CONNECTION POOL — reuse connections, don't open/close per request
# ============================================================
_local = threading.local()

def get_db() -> sqlite3.Connection:
    """Get a thread-local database connection (reused across requests)."""
    if not hasattr(_local, "conn") or _local.conn is None:
        conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
        conn.execute("PRAGMA temp_store=MEMORY")
        _local.conn = conn
    return _local.conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS customers (
            id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT,
            stripe_customer_id TEXT, plan TEXT DEFAULT 'free',
            status TEXT DEFAULT 'active', created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS api_keys (
            key_hash TEXT PRIMARY KEY, key_prefix TEXT NOT NULL,
            customer_id TEXT NOT NULL REFERENCES customers(id),
            name TEXT DEFAULT 'Default', status TEXT DEFAULT 'active',
            last_used_at TEXT, created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(customer_id, name)
        );
        CREATE TABLE IF NOT EXISTS usage_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id TEXT NOT NULL REFERENCES customers(id),
            test_runs INTEGER DEFAULT 0, llm_judge_runs INTEGER DEFAULT 0,
            month TEXT NOT NULL, created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(customer_id, month)
        );
        CREATE TABLE IF NOT EXISTS test_run_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id TEXT NOT NULL,
            api_key_prefix TEXT, suite_name TEXT, total_tests INTEGER,
            passed INTEGER, failed INTEGER, used_llm_judge INTEGER DEFAULT 0,
            latency_ms REAL, created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS test_runs (
            id TEXT PRIMARY KEY, customer_id TEXT NOT NULL,
            suite_name TEXT, data TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);
        CREATE INDEX IF NOT EXISTS idx_customers_email ON customers(email);
        CREATE INDEX IF NOT EXISTS idx_usage_customer_month ON usage_records(customer_id, month);
        CREATE INDEX IF NOT EXISTS idx_test_runs_customer ON test_runs(customer_id);
        CREATE INDEX IF NOT EXISTS idx_test_run_log_customer ON test_run_log(customer_id);
    """)
    conn.commit()


# ============================================================
# API KEY CACHE — avoid DB lookup on every request
# ============================================================
_key_cache = {}
_key_cache_ttl = 300  # 5 minutes
_key_cache_lock = threading.Lock()


def _cache_key(key_hash: str, data: dict):
    with _key_cache_lock:
        _key_cache[key_hash] = {"data": data, "ts": time.time()}

def _get_cached_key(key_hash: str) -> Optional[dict]:
    with _key_cache_lock:
        entry = _key_cache.get(key_hash)
        if entry and (time.time() - entry["ts"]) < _key_cache_ttl:
            return entry["data"]
        if entry:
            del _key_cache[key_hash]
    return None

def invalidate_key_cache(key_hash: str = None):
    with _key_cache_lock:
        if key_hash:
            _key_cache.pop(key_hash, None)
        else:
            _key_cache.clear()


# ============================================================
# PRICING PLANS
# ============================================================

PLANS = {
    "free": {
        "name": "Free",
        "price_monthly": 0,
        "test_runs_per_month": 25,
        "llm_judge": False,
        "real_systems": False,
        "api_keys": 1,
        "support": "community",
    },
    "pro": {
        "name": "Pro",
        "price_monthly": 49,
        "test_runs_per_month": 2000,
        "llm_judge": True,
        "real_systems": True,
        "api_keys": 5,
        "support": "email",
        "stripe_price_id": os.environ.get("STRIPE_PRO_PRICE_ID", ""),
    },
    "enterprise": {
        "name": "Enterprise",
        "price_monthly": 499,
        "test_runs_per_month": -1,
        "llm_judge": True,
        "real_systems": True,
        "api_keys": 20,
        "support": "priority",
        "stripe_price_id": os.environ.get("STRIPE_ENTERPRISE_PRICE_ID", ""),
    },
}


# ============================================================
# API KEY MANAGEMENT
# ============================================================

def generate_api_key() -> tuple[str, str, str]:
    raw = secrets.token_urlsafe(32)
    full_key = f"ap_live_{raw}"
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()
    prefix = full_key[:12] + "..."
    return full_key, key_hash, prefix

def verify_api_key(key: str) -> Optional[dict]:
    key_hash = hashlib.sha256(key.encode()).hexdigest()

    # Check cache first
    cached = _get_cached_key(key_hash)
    if cached:
        return cached

    conn = get_db()
    row = conn.execute("""
        SELECT ak.key_hash, ak.customer_id, ak.status as key_status,
               c.email, c.plan, c.status as customer_status, c.stripe_customer_id
        FROM api_keys ak JOIN customers c ON ak.customer_id = c.id
        WHERE ak.key_hash = ? AND ak.status = 'active' AND c.status = 'active'
    """, (key_hash,)).fetchone()
    if not row:
        return None

    # Update last_used (non-blocking, skip if it fails)
    try:
        conn.execute("UPDATE api_keys SET last_used_at = datetime('now') WHERE key_hash = ?", (key_hash,))
        conn.commit()
    except:
        pass

    result = dict(row)
    _cache_key(key_hash, result)
    return result


# ============================================================
# USAGE TRACKING
# ============================================================

def get_current_month():
    return datetime.now(timezone.utc).strftime("%Y-%m")

def track_usage(customer_id: str, test_runs: int = 0, llm_judge_runs: int = 0):
    month = get_current_month()
    conn = get_db()
    conn.execute("""INSERT INTO usage_records (customer_id, test_runs, llm_judge_runs, month) VALUES (?, ?, ?, ?)
        ON CONFLICT(customer_id, month) DO UPDATE SET test_runs = test_runs + excluded.test_runs,
        llm_judge_runs = llm_judge_runs + excluded.llm_judge_runs""", (customer_id, test_runs, llm_judge_runs, month))
    conn.commit()

def get_usage(customer_id: str, month: str = None) -> dict:
    month = month or get_current_month()
    conn = get_db()
    row = conn.execute("SELECT * FROM usage_records WHERE customer_id = ? AND month = ?", (customer_id, month)).fetchone()
    return dict(row) if row else {"customer_id": customer_id, "test_runs": 0, "llm_judge_runs": 0, "month": month}

def check_usage_limit(customer_id: str, plan: str) -> dict:
    usage = get_usage(customer_id)
    plan_info = PLANS.get(plan, PLANS["free"])
    limit = plan_info["test_runs_per_month"]
    if limit == -1:
        return {"allowed": True, "used": usage["test_runs"], "limit": "unlimited", "remaining": "unlimited"}
    remaining = max(0, limit - usage["test_runs"])
    return {"allowed": usage["test_runs"] < limit, "used": usage["test_runs"], "limit": limit, "remaining": remaining}

def log_test_run(customer_id, api_key_prefix, suite_name, total, passed, failed, used_judge, latency_ms):
    conn = get_db()
    conn.execute("""INSERT INTO test_run_log (customer_id, api_key_prefix, suite_name, total_tests, passed, failed, used_llm_judge, latency_ms)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", (customer_id, api_key_prefix, suite_name, total, passed, failed, int(used_judge), latency_ms))
    conn.commit()


# ============================================================
# TEST RUN PERSISTENCE — no more in-memory dict!
# ============================================================

def save_test_run(run_id: str, customer_id: str, suite_name: str, data: dict):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO test_runs (id, customer_id, suite_name, data) VALUES (?, ?, ?, ?)",
                 (run_id, customer_id, suite_name, json.dumps(data)))
    conn.commit()

def get_test_run(run_id: str) -> Optional[dict]:
    conn = get_db()
    row = conn.execute("SELECT data FROM test_runs WHERE id = ?", (run_id,)).fetchone()
    return json.loads(row["data"]) if row else None

def list_test_runs(customer_id: str, limit: int = 50) -> list:
    conn = get_db()
    rows = conn.execute("SELECT id, suite_name, created_at, data FROM test_runs WHERE customer_id = ? ORDER BY created_at DESC LIMIT ?",
                        (customer_id, limit)).fetchall()
    results = []
    for r in rows:
        try:
            d = json.loads(r["data"])
            d["id"] = r["id"]
            results.append(d)
        except:
            pass
    return results


# ============================================================
# CUSTOMER MANAGEMENT
# ============================================================

def create_customer(email, name=None, plan="free", stripe_customer_id=None):
    customer_id = f"cust_{secrets.token_urlsafe(12)}"
    full_key, key_hash, key_prefix = generate_api_key()
    conn = get_db()
    conn.execute("INSERT INTO customers (id, email, name, plan, stripe_customer_id) VALUES (?, ?, ?, ?, ?)",
                 (customer_id, email, name, plan, stripe_customer_id))
    conn.execute("INSERT INTO api_keys (key_hash, key_prefix, customer_id, name) VALUES (?, ?, ?, 'Default')",
                 (key_hash, key_prefix, customer_id))
    conn.commit()
    return {"id": customer_id, "email": email, "plan": plan}, full_key

def get_customer(customer_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
    return dict(row) if row else None

def update_plan(customer_id, new_plan):
    conn = get_db()
    conn.execute("UPDATE customers SET plan = ?, updated_at = datetime('now') WHERE id = ?", (new_plan, customer_id))
    conn.commit()
    # Invalidate cache for this customer's keys
    rows = conn.execute("SELECT key_hash FROM api_keys WHERE customer_id = ?", (customer_id,)).fetchall()
    for r in rows:
        invalidate_key_cache(r["key_hash"])

def get_customer_by_stripe_id(stripe_customer_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM customers WHERE stripe_customer_id = ?", (stripe_customer_id,)).fetchone()
    return dict(row) if row else None
