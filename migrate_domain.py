#!/usr/bin/env python3
"""
Domain Migration Script
Run: python3 migrate_domain.py agentprobe.dev

Updates all references from agent-probe-eight.vercel.app to your custom domain.
"""
import sys, os, glob

if len(sys.argv) < 2:
    print("Usage: python3 migrate_domain.py <your-domain>")
    print("Example: python3 migrate_domain.py agentprobe.dev")
    sys.exit(1)

NEW_DOMAIN = sys.argv[1].strip().replace("https://", "").replace("http://", "").rstrip("/")
OLD_DOMAIN = "agent-probe-eight.vercel.app"
BASE = "/Users/rigard/Desktop/agentprobe"

files_to_check = [
    "fly.toml",
    "api/server.py",
    "billing/payfast_integration.py",
    "certification/__init__.py",
    "dashboard/src/App.jsx",
    "DEPLOY.md",
    "VISION.md",
    "README.md",
    ".env",
    ".env.example",
    "pyproject.toml",
]

total_replacements = 0

for rel_path in files_to_check:
    full_path = os.path.join(BASE, rel_path)
    if not os.path.exists(full_path):
        continue
    with open(full_path, "r") as f:
        content = f.read()
    count = content.count(OLD_DOMAIN)
    if count > 0:
        content = content.replace(OLD_DOMAIN, NEW_DOMAIN)
        with open(full_path, "w") as f:
            f.write(content)
        print(f"  ✅ {rel_path}: {count} replacement(s)")
        total_replacements += count
    # Also replace agentprobe.dev references if they exist and differ
    old_cert = "agentprobe.dev"
    if old_cert != NEW_DOMAIN and old_cert in content:
        count2 = content.count(old_cert)
        content = content.replace(old_cert, NEW_DOMAIN)
        with open(full_path, "w") as f:
            f.write(content)
        print(f"  ✅ {rel_path}: {count2} cert URL replacement(s)")
        total_replacements += count2

print(f"\n🎯 Done! {total_replacements} total replacements across all files.")
print(f"\nYour new domain: https://{NEW_DOMAIN}")
print(f"""
Next steps:
  1. Add {NEW_DOMAIN} in Vercel: Settings → Domains → Add Domain
  2. Point DNS records as Vercel instructs (CNAME or A record)
  3. Update Fly.io:
     fly secrets set DOMAIN="https://{NEW_DOMAIN}"
  4. Update PayFast ITN URL in your PayFast dashboard:
     https://agentprobe-api.fly.dev/api/billing/payfast/itn
     (this stays the same — only the frontend domain changes)
  5. Deploy:
     git add . && git commit -m "Migrate to {NEW_DOMAIN}" && git push && fly deploy
  6. Update Vercel env var: VITE_API_URL stays as https://agentprobe-api.fly.dev
""")
