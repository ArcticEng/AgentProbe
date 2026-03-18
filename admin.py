#!/usr/bin/env python3
"""
AgentProbe Admin — View and manage customers, billing, and usage.

Usage:
    .venv/bin/python admin.py                  # Show dashboard
    .venv/bin/python admin.py customers        # List all customers
    .venv/bin/python admin.py usage             # Show usage this month
    .venv/bin/python admin.py revenue           # Revenue summary
    .venv/bin/python admin.py customer EMAIL    # Details for one customer
    .venv/bin/python admin.py upgrade EMAIL pro # Change a customer's plan
    .venv/bin/python admin.py runs              # Recent test runs
"""
import sys, os, sqlite3
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from billing import DB_PATH, get_db, get_current_month, PLANS

def fmt_date(d):
    if not d: return "—"
    try: return datetime.fromisoformat(d).strftime("%b %d, %Y %H:%M")
    except: return d

def header(title):
    w = 60
    print(f"\n{'═'*w}")
    print(f"  {title}")
    print(f"{'═'*w}")

def cmd_dashboard():
    conn = get_db()
    month = get_current_month()
    
    total_customers = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    active_customers = conn.execute("SELECT COUNT(*) FROM customers WHERE status='active'").fetchone()[0]
    free = conn.execute("SELECT COUNT(*) FROM customers WHERE plan='free'").fetchone()[0]
    pro = conn.execute("SELECT COUNT(*) FROM customers WHERE plan='pro'").fetchone()[0]
    enterprise = conn.execute("SELECT COUNT(*) FROM customers WHERE plan='enterprise'").fetchone()[0]
    
    total_runs_month = conn.execute(
        "SELECT COALESCE(SUM(test_runs),0) FROM usage_records WHERE month=?", (month,)
    ).fetchone()[0]
    total_judge_month = conn.execute(
        "SELECT COALESCE(SUM(llm_judge_runs),0) FROM usage_records WHERE month=?", (month,)
    ).fetchone()[0]
    total_runs_all = conn.execute(
        "SELECT COALESCE(SUM(total_tests),0) FROM test_run_log"
    ).fetchone()[0]
    
    mrr = (pro * 49) + (enterprise * 499)
    arr = mrr * 12
    
    header("AgentProbe Admin Dashboard")
    print(f"""
  CUSTOMERS
  ─────────────────────────────────
  Total:        {total_customers}
  Active:       {active_customers}
  Free:         {free}
  Pro ($49):    {pro}
  Enterprise:   {enterprise}

  REVENUE
  ─────────────────────────────────
  MRR:          ${mrr:,}/month
  ARR:          ${arr:,}/year

  USAGE ({month})
  ─────────────────────────────────
  Test runs:    {total_runs_month:,}
  LLM-judge:    {total_judge_month:,}
  All-time:     {total_runs_all:,} total runs
""")
    conn.close()

def cmd_customers():
    conn = get_db()
    rows = conn.execute("""
        SELECT c.*, 
               COALESCE(u.test_runs, 0) as runs_this_month,
               (SELECT COUNT(*) FROM api_keys WHERE customer_id=c.id AND status='active') as active_keys
        FROM customers c
        LEFT JOIN usage_records u ON c.id = u.customer_id AND u.month = ?
        ORDER BY c.created_at DESC
    """, (get_current_month(),)).fetchall()
    conn.close()
    
    header(f"All Customers ({len(rows)})")
    if not rows:
        print("  No customers yet.\n")
        return
    
    print(f"  {'Email':<30s} {'Plan':<12s} {'Status':<10s} {'Runs/Mo':<10s} {'Keys':<5s} {'Signed Up'}")
    print(f"  {'─'*29} {'─'*11} {'─'*9} {'─'*9} {'─'*4} {'─'*20}")
    for r in rows:
        plan_display = f"{r['plan']}" + (" 💰" if r['plan'] in ('pro','enterprise') else "")
        print(f"  {r['email']:<30s} {plan_display:<12s} {r['status']:<10s} {r['runs_this_month']:<10d} {r['active_keys']:<5d} {fmt_date(r['created_at'])}")
    print()

def cmd_usage():
    conn = get_db()
    month = get_current_month()
    rows = conn.execute("""
        SELECT c.email, c.plan, u.test_runs, u.llm_judge_runs,
               CASE WHEN c.plan = 'free' THEN 50
                    WHEN c.plan = 'pro' THEN 2000
                    ELSE -1 END as plan_limit
        FROM usage_records u
        JOIN customers c ON u.customer_id = c.id
        WHERE u.month = ?
        ORDER BY u.test_runs DESC
    """, (month,)).fetchall()
    conn.close()
    
    header(f"Usage — {month}")
    if not rows:
        print("  No usage this month.\n")
        return
    
    print(f"  {'Email':<30s} {'Plan':<10s} {'Runs':<8s} {'Limit':<10s} {'Judge':<8s} {'%Used'}")
    print(f"  {'─'*29} {'─'*9} {'─'*7} {'─'*9} {'─'*7} {'─'*8}")
    for r in rows:
        limit = "∞" if r['plan_limit'] == -1 else str(r['plan_limit'])
        pct = "∞" if r['plan_limit'] == -1 else f"{r['test_runs']/r['plan_limit']*100:.0f}%"
        bar = ""
        if r['plan_limit'] > 0:
            filled = min(10, int(r['test_runs'] / r['plan_limit'] * 10))
            bar = f" [{'█'*filled}{'░'*(10-filled)}]"
        print(f"  {r['email']:<30s} {r['plan']:<10s} {r['test_runs']:<8d} {limit:<10s} {r['llm_judge_runs']:<8d} {pct}{bar}")
    print()

def cmd_revenue():
    conn = get_db()
    
    header("Revenue Breakdown")
    
    for plan_id, plan in PLANS.items():
        count = conn.execute("SELECT COUNT(*) FROM customers WHERE plan=? AND status='active'",
                            (plan_id,)).fetchone()[0]
        revenue = count * plan["price_monthly"]
        print(f"  {plan['name']:<15s} {count:>3d} customers × ${plan['price_monthly']:>3d}/mo = ${revenue:>6,}/mo")
    
    total_mrr = sum(
        conn.execute("SELECT COUNT(*) FROM customers WHERE plan=? AND status='active'",
                    (p,)).fetchone()[0] * info["price_monthly"]
        for p, info in PLANS.items()
    )
    print(f"  {'─'*55}")
    print(f"  {'TOTAL MRR':<15s} {'':>18s} ${total_mrr:>6,}/mo")
    print(f"  {'TOTAL ARR':<15s} {'':>18s} ${total_mrr*12:>6,}/yr")
    
    # Month over month
    print(f"\n  Monthly Usage Trends:")
    rows = conn.execute("""
        SELECT month, SUM(test_runs) as total_runs, COUNT(DISTINCT customer_id) as active_users
        FROM usage_records
        GROUP BY month
        ORDER BY month DESC
        LIMIT 6
    """).fetchall()
    for r in rows:
        print(f"    {r['month']}  |  {r['total_runs']:>6,} runs  |  {r['active_users']} active users")
    
    conn.close()
    print()

def cmd_customer_detail(email):
    conn = get_db()
    customer = conn.execute("SELECT * FROM customers WHERE email=?", (email,)).fetchone()
    if not customer:
        print(f"  ❌ Customer not found: {email}")
        conn.close()
        return
    
    keys = conn.execute("SELECT * FROM api_keys WHERE customer_id=?", (customer['id'],)).fetchall()
    usage = conn.execute("SELECT * FROM usage_records WHERE customer_id=? ORDER BY month DESC LIMIT 6",
                        (customer['id'],)).fetchall()
    runs = conn.execute("SELECT * FROM test_run_log WHERE customer_id=? ORDER BY created_at DESC LIMIT 10",
                       (customer['id'],)).fetchall()
    conn.close()
    
    header(f"Customer: {email}")
    print(f"""
  ID:             {customer['id']}
  Name:           {customer['name'] or '—'}
  Plan:           {customer['plan']}
  Status:         {customer['status']}
  Stripe ID:      {customer['stripe_customer_id'] or '—'}
  Signed up:      {fmt_date(customer['created_at'])}
  Last updated:   {fmt_date(customer['updated_at'])}

  API Keys ({len(keys)}):""")
    for k in keys:
        print(f"    {k['key_prefix']:<16s} status: {k['status']}  last used: {fmt_date(k['last_used_at'])}")
    
    print(f"\n  Usage History:")
    for u in usage:
        print(f"    {u['month']}  |  {u['test_runs']} runs  |  {u['llm_judge_runs']} judge calls")
    
    print(f"\n  Recent Test Runs:")
    for r in runs:
        print(f"    {fmt_date(r['created_at'])}  |  {r['suite_name']:<25s}  |  {r['passed']}/{r['total_tests']} passed  |  {r['latency_ms']:.0f}ms")
    print()

def cmd_upgrade(email, new_plan):
    if new_plan not in PLANS:
        print(f"  ❌ Invalid plan: {new_plan}. Options: {list(PLANS.keys())}")
        return
    conn = get_db()
    customer = conn.execute("SELECT * FROM customers WHERE email=?", (email,)).fetchone()
    if not customer:
        print(f"  ❌ Customer not found: {email}")
        conn.close()
        return
    old_plan = customer['plan']
    conn.execute("UPDATE customers SET plan=?, updated_at=datetime('now') WHERE email=?", (new_plan, email))
    conn.commit()
    conn.close()
    print(f"  ✅ {email}: {old_plan} → {new_plan}")

def cmd_runs():
    conn = get_db()
    rows = conn.execute("""
        SELECT r.*, c.email
        FROM test_run_log r
        JOIN customers c ON r.customer_id = c.id
        ORDER BY r.created_at DESC
        LIMIT 20
    """).fetchall()
    conn.close()
    
    header(f"Recent Test Runs ({len(rows)})")
    if not rows:
        print("  No runs yet.\n")
        return
    print(f"  {'When':<20s} {'Email':<25s} {'Suite':<20s} {'Result':<12s} {'Judge':<6s} {'Latency'}")
    print(f"  {'─'*19} {'─'*24} {'─'*19} {'─'*11} {'─'*5} {'─'*8}")
    for r in rows:
        result = f"{r['passed']}/{r['total_tests']}"
        judge = "✓" if r['used_llm_judge'] else "—"
        print(f"  {fmt_date(r['created_at']):<20s} {r['email']:<25s} {(r['suite_name'] or '?'):<20s} {result:<12s} {judge:<6s} {r['latency_ms']:.0f}ms")
    print()


# ---- CLI ----
if __name__ == "__main__":
    args = sys.argv[1:]
    
    if not args or args[0] == "dashboard":
        cmd_dashboard()
    elif args[0] == "customers":
        cmd_customers()
    elif args[0] == "usage":
        cmd_usage()
    elif args[0] == "revenue":
        cmd_revenue()
    elif args[0] == "customer" and len(args) >= 2:
        cmd_customer_detail(args[1])
    elif args[0] == "upgrade" and len(args) >= 3:
        cmd_upgrade(args[1], args[2])
    elif args[0] == "runs":
        cmd_runs()
    else:
        print(__doc__)
