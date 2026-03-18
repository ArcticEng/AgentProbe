"""
AgentProbe Billing — Database, API Keys, Usage Tracking, Stripe Integration

Pricing:
  Free:       25 test runs/month, mock agent only (demo mode)
  Pro:        2,000 test runs/month, real systems, LLM-judge    $49/month
  Enterprise: Unlimited, real systems, priority support          $499/month
"""

import os
import json
import time
import sqlite3
import hashlib
import secrets
from datetime import datetime, timezone
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Optional

DB_PATH = os.environ.get("AGENTPROBE_DB", os.path.join(os.path.dirname(__file__), "agentprobe.db"))


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS customers (
            id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT,
            stripe_customer_id TEXT UNIQUE, plan TEXT DEFAULT 'free',
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
    """)
    conn.commit()
    conn.close()


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


def generate_api_key() -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    full_key = f"ap_live_{raw}"
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()
    prefix = full_key[:12] + "..."
    return full_key, key_hash, prefix

def verify_api_key(key: str) -> Optional[dict]:
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    conn = get_db()
    row = conn.execute("""
        SELECT ak.key_hash, ak.customer_id, ak.status as key_status,
               c.email, c.plan, c.status as customer_status, c.stripe_customer_id
        FROM api_keys ak JOIN customers c ON ak.customer_id = c.id
        WHERE ak.key_hash = ? AND ak.status = 'active' AND c.status = 'active'
    """, (key_hash,)).fetchone()
    if not row: conn.close(); return None
    conn.execute("UPDATE api_keys SET last_used_at = datetime('now') WHERE key_hash = ?", (key_hash,))
    conn.commit(); conn.close()
    return dict(row)

def get_current_month():
    return datetime.now(timezone.utc).strftime("%Y-%m")

def track_usage(customer_id: str, test_runs: int = 0, llm_judge_runs: int = 0):
    month = get_current_month()
    conn = get_db()
    conn.execute("""INSERT INTO usage_records (customer_id, test_runs, llm_judge_runs, month) VALUES (?, ?, ?, ?)
        ON CONFLICT(customer_id, month) DO UPDATE SET test_runs = test_runs + excluded.test_runs,
        llm_judge_runs = llm_judge_runs + excluded.llm_judge_runs""", (customer_id, test_runs, llm_judge_runs, month))
    conn.commit(); conn.close()

def get_usage(customer_id: str, month: str = None) -> dict:
    month = month or get_current_month()
    conn = get_db()
    row = conn.execute("SELECT * FROM usage_records WHERE customer_id = ? AND month = ?", (customer_id, month)).fetchone()
    conn.close()
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
    conn.commit(); conn.close()

def create_customer(email, name=None, plan="free", stripe_customer_id=None):
    customer_id = f"cust_{secrets.token_urlsafe(12)}"
    full_key, key_hash, key_prefix = generate_api_key()
    conn = get_db()
    conn.execute("INSERT INTO customers (id, email, name, plan, stripe_customer_id) VALUES (?, ?, ?, ?, ?)",
                 (customer_id, email, name, plan, stripe_customer_id))
    conn.execute("INSERT INTO api_keys (key_hash, key_prefix, customer_id, name) VALUES (?, ?, ?, 'Default')",
                 (key_hash, key_prefix, customer_id))
    conn.commit(); conn.close()
    return {"id": customer_id, "email": email, "plan": plan}, full_key

def get_customer(customer_id):
    conn = get_db(); row = conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone(); conn.close()
    return dict(row) if row else None

def update_plan(customer_id, new_plan):
    conn = get_db(); conn.execute("UPDATE customers SET plan = ?, updated_at = datetime('now') WHERE id = ?", (new_plan, customer_id)); conn.commit(); conn.close()

def get_customer_by_stripe_id(stripe_customer_id):
    conn = get_db(); row = conn.execute("SELECT * FROM customers WHERE stripe_customer_id = ?", (stripe_customer_id,)).fetchone(); conn.close()
    return dict(row) if row else None
