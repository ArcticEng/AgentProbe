# AgentProbe — DEPLOYMENT & LAUNCH GUIDE
## Go live in 30 minutes, get first customers this week

---

## STEP 1: Push to GitHub (5 min)

```bash
cd ~/Desktop/agentprobe

# Fix App.jsx for production (one-line change)
sed -i '' 's|const API_BASE = "/api";|import API_BASE from "./config.js";|' dashboard/src/App.jsx

# Init git and push
git init
git add .
git commit -m "AgentProbe v0.1.0 - AI agent testing and certification platform"

# Create repo on GitHub (install gh CLI first: brew install gh)
gh auth login
gh repo create agentprobe --public --source=. --push
```

---

## STEP 2: Deploy Backend to Fly.io (10 min)

```bash
# Install Fly CLI
brew install flyctl

# Login
fly auth login

# Create the app (first time only)
fly apps create agentprobe-api

# Create persistent storage for the database
fly volumes create agentprobe_data --region jnb --size 1

# Set your secrets (DON'T put these in code)
fly secrets set ANTHROPIC_API_KEY="sk-ant-your-key-here"
fly secrets set ADMIN_SECRET="your-admin-secret"
fly secrets set CERT_SIGNING_SECRET="your-signing-secret"
# Add Stripe keys when ready:
# fly secrets set STRIPE_SECRET_KEY="sk_live_..."
# fly secrets set STRIPE_WEBHOOK_SECRET="whsec_..."

# Deploy
fly deploy

# Verify it's running
curl https://agentprobe-api.fly.dev/api/health
```

Your API is now live at: **https://agentprobe-api.fly.dev**

---

## STEP 3: Deploy Frontend to Vercel (5 min)

```bash
# Install Vercel CLI
npm i -g vercel

# Deploy the dashboard
cd ~/Desktop/agentprobe/dashboard
vercel

# When prompted:
#   Set up and deploy? Y
#   Which scope? (your account)
#   Link to existing project? N
#   Project name: agentprobe
#   Directory: ./
#   Override settings? N

# Set the API URL environment variable
vercel env add VITE_API_URL
# Enter: https://agentprobe-api.fly.dev
# Select: Production, Preview, Development

# Redeploy with the env var
vercel --prod
```

Your dashboard is now live at: **https://agentprobe.vercel.app**

---

## STEP 4: Set Up Stripe (10 min)

1. Go to https://stripe.com and create an account
2. Go to https://dashboard.stripe.com/apikeys
3. Copy your **Secret key** (starts with sk_live_ or sk_test_ for testing)
4. Set it on Fly.io:
   ```bash
   fly secrets set STRIPE_SECRET_KEY="sk_test_your_key"
   ```
5. Create your products — run locally:
   ```bash
   cd ~/Desktop/agentprobe
   STRIPE_SECRET_KEY="sk_test_your_key" .venv/bin/python billing/stripe_integration.py
   ```
6. Copy the Price IDs it outputs and set them:
   ```bash
   fly secrets set STRIPE_PRO_PRICE_ID="price_xxx"
   fly secrets set STRIPE_ENTERPRISE_PRICE_ID="price_xxx"
   ```
7. Set up the webhook in Stripe Dashboard:
   - Go to https://dashboard.stripe.com/webhooks
   - Add endpoint: `https://agentprobe-api.fly.dev/api/billing/webhook`
   - Select events: `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.payment_failed`
   - Copy the webhook signing secret
   ```bash
   fly secrets set STRIPE_WEBHOOK_SECRET="whsec_xxx"
   ```

**Stripe is now live. Customers can pay.**

---

## STEP 5: Custom Domain (Optional, 5 min)

Buy `agentprobe.dev` from Namecheap, Google Domains, or Cloudflare (~$12/year).

For the dashboard:
```bash
vercel domains add agentprobe.dev
# Add the DNS records Vercel tells you to add
```

For the API:
```bash
fly certs create api.agentprobe.dev
# Add CNAME record: api.agentprobe.dev -> agentprobe-api.fly.dev
```

Then update Fly.io:
```bash
fly secrets set DOMAIN="https://agentprobe.dev"
```

---

## MARKETING: GET YOUR FIRST 100 CUSTOMERS

### Week 1: Launch Week

**Day 1 — Hacker News "Show HN" post:**
```
Show HN: AgentProbe — The Selenium for AI Agents (test for jailbreaks, PII leaks, hallucinations)

I built an automated testing framework for AI agents. Before you deploy 
your chatbot/agent to production, AgentProbe tests it for:

- Jailbreak resistance (prompt injection, role override)
- PII leaks (emails, phone numbers, SSNs in responses)
- Hallucination detection (LLM-judge catches made-up facts)
- Safety evaluation (harmful content, social engineering)
- Latency benchmarks (P95, degradation under load)
- Quality scoring (is the response actually helpful?)

It caught our test agent confidently inventing a return policy that 
didn't exist — keyword matching would have scored that as "helpful."
The LLM-judge caught it as a hallucination.

Python SDK: pip install agentprobe
Dashboard: https://agentprobe.dev
3 lines to test your agent:
  probe = AgentProbe(api_key="sk-...", provider="anthropic")
  results = probe.run(Templates.safety_suite())
  assert results.pass_rate >= 0.95

Free tier: 50 test runs/month. We also offer certification badges 
for companies that want to prove their AI is safe.

https://agentprobe.dev
```

**Day 1 — Twitter/X post:**
```
I built the "SOC 2 for AI agents."

Before you deploy your AI chatbot, AgentProbe tests it for:
→ Jailbreak resistance
→ PII leaks
→ Hallucination detection
→ Safety evaluation
→ Latency benchmarks

It caught our test agent inventing a fake return policy.
Keyword matching scored it as "helpful."
Our LLM-judge scored it 0.0 for hallucination.

That's the difference between a free tool and a $500/month product.

Free: agentprobe.dev
```

**Day 1 — Reddit:**
Post in r/artificial, r/MachineLearning, r/SaaS, r/startups, r/ChatGPT:
"I built an automated testing framework for AI agents — catches jailbreaks, hallucinations, and PII leaks before your users do"

**Day 2-3 — Direct outreach:**
Find 50 companies on Twitter/LinkedIn that have launched AI chatbots in the last 3 months. DM/email them:

```
Subject: Found 3 security issues in [their chatbot name]

Hi [name],

I ran your [product] chatbot through AgentProbe (an AI agent testing 
tool I built) and found:

1. [Specific finding — e.g., "it echoes back the word 'password' 
   when refusing jailbreak attempts"]
2. [Specific finding — e.g., "response latency exceeded 5s on 
   complex queries"]
3. [Specific finding — e.g., "it can be tricked into breaking 
   character with a DAN prompt"]

I'm offering free evaluations for early users. Want me to run a full 
safety audit and send you the report?

— Rigard
agentprobe.dev
```

This works because you're offering VALUE first, not asking for money.

**Day 4-5 — Content:**
- Write a blog post: "We tested 10 popular AI chatbots for safety — here's what we found"
- Post the anonymized results on Twitter (no company names without permission)
- The data itself is the marketing

### Week 2-4: Build Pipeline

**Dev community:**
- Post Python package to PyPI: `pip install agentprobe`
- Add GitHub Actions example to popular AI agent repos
- Answer StackOverflow questions about AI testing
- Create a GitHub discussion/issue template: "Test your agent with AgentProbe"

**LinkedIn (B2B goldmine):**
- Post 3x/week about AI safety findings
- Connect with CTOs, VP Engineering, AI leads at companies deploying agents
- Share specific (anonymized) test results that demonstrate value

**Product Hunt launch:**
- Schedule for a Tuesday (highest traffic)
- Prep: tagline, screenshots, demo video (record a Loom of the production test running)
- Get 10 people to upvote at launch

### Month 2-3: Convert Free to Paid

- Free users hit the 50-run limit → auto-email: "You've used 48/50 runs. Upgrade to Pro for 2,000 runs + LLM-judge"
- Offer annual discount: $39/mo (billed annually) vs $49/mo
- Enterprise: offer a free 30-day pilot → convert to $499/mo
- Certification: approach 10 companies for charter "AgentProbe Certified" program at 50% off first year

---

## KEY METRICS TO TRACK

| Metric | Target (Month 1) | Target (Month 3) |
|--------|------------------|------------------|
| Signups | 100 | 500 |
| Active users (ran ≥1 test) | 30 | 150 |
| Paying customers | 3 | 20 |
| MRR | $147 | $2,000 |
| Hacker News upvotes | 50+ | — |
| GitHub stars | 100 | 500 |

---

## QUICK REFERENCE: ALL YOUR URLS

| What | URL |
|------|-----|
| Dashboard | https://agentprobe.vercel.app |
| API | https://agentprobe-api.fly.dev |
| API Docs | https://agentprobe-api.fly.dev/docs |
| Admin Dashboard | https://agentprobe-api.fly.dev/api/admin/dashboard?admin_key=YOUR_SECRET |
| Stripe Dashboard | https://dashboard.stripe.com |
| GitHub | https://github.com/YOUR_USERNAME/agentprobe |
| Fly.io Dashboard | https://fly.io/apps/agentprobe-api |
| Vercel Dashboard | https://vercel.com/dashboard |
