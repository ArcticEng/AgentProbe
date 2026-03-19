#!/usr/bin/env python3
"""Apply pricing page update to App.jsx"""
import re

filepath = "/Users/rigard/Desktop/agentprobe/dashboard/src/App.jsx"

with open(filepath, "r") as f:
    content = f.read()

# Find and replace the PricingPage function
old_start = "function PricingPage({ setView, user }) {"
old_end_marker = "function SignupPage"

start_idx = content.find(old_start)
end_idx = content.find(old_end_marker)

if start_idx == -1 or end_idx == -1:
    print("ERROR: Could not find PricingPage boundaries")
    exit(1)

new_pricing = '''function PricingPage({ setView, user }) {
  const currentPlan = user?.plan || "none";
  const planRank = {"none": 0, "free": 1, "pro": 2, "enterprise": 3};
  const userRank = planRank[currentPlan] || 0;

  const plans = [
    {id:"free",name:"Free",price:0,features:["25 test runs/month","Mock testing only (demo)","All 33 templates (preview)","Keyword evaluations","1 API key"]},
    {id:"pro",name:"Pro",price:49,popular:true,features:["2,000 test runs/month","Test real AI agents & APIs","LLM-Judge evaluations","All 33 templates","5 API keys","Certification badge"]},
    {id:"enterprise",name:"Enterprise",price:499,features:["Unlimited test runs","Test real AI agents & APIs","LLM-Judge evaluations","All 33 templates","20 API keys","Enterprise certification","Continuous monitoring","Compliance mapping"]},
  ];

  const getCta = (p) => {
    const pRank = planRank[p.id] || 0;
    if (currentPlan === p.id) return "Current plan";
    if (pRank < userRank) return "Current: " + currentPlan.charAt(0).toUpperCase() + currentPlan.slice(1);
    if (!user) return p.id === "free" ? "Get started free" : `Upgrade to ${p.name}`;
    return `Upgrade to ${p.name}`;
  };

  const isDisabled = (p) => {
    const pRank = planRank[p.id] || 0;
    return pRank <= userRank && userRank > 0;
  };

  const handleUpgrade = async (planId) => {
    if (planId === "free") return setView("signup");
    if (!user) return setView("signup");
    try { const data = await apiFetch("/billing/checkout", {method:"POST",body:JSON.stringify({plan:planId,email:user.email})}); if (data.checkout_url) window.location.href = data.checkout_url; } catch (e) { alert(e.message || "Checkout failed."); }
  };
  return (
    <div className="max-w-5xl mx-auto px-6 py-16">
      <div className="text-center mb-12"><h1 className="text-4xl font-bold text-white/90 mb-3">Simple, transparent pricing</h1><p className="text-white/35">Start free. Upgrade when you need LLM-Judge or more runs.</p></div>
      <div className="grid grid-cols-3 gap-4">
        {plans.map(p => {
          const disabled = isDisabled(p);
          const isCurrent = currentPlan === p.id;
          return (<div key={p.id} className={`relative p-6 rounded-2xl border transition-all ${isCurrent ? "bg-emerald-500/[0.06] border-emerald-500/40 ring-1 ring-emerald-500/20" : p.popular && !disabled ? "bg-emerald-500/[0.04] border-emerald-500/30 scale-[1.02]" : "bg-white/[0.02] border-white/[0.06]"}`}>
            {isCurrent && <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-0.5 bg-emerald-500 text-black text-[10px] font-bold rounded-full">YOUR PLAN</div>}
            {p.popular && !isCurrent && <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-0.5 bg-emerald-500 text-black text-[10px] font-bold rounded-full">MOST POPULAR</div>}
            <h3 className="text-lg font-semibold text-white/90 mb-1">{p.name}</h3>
            <div className="flex items-baseline gap-1 mb-4"><span className="text-3xl font-bold text-white/90">${p.price}</span>{p.price > 0 && <span className="text-white/30 text-sm">/month</span>}</div>
            <ul className="space-y-2 mb-6">{p.features.map((f,i) => (<li key={i} className="flex items-center gap-2 text-xs text-white/50"><span className="text-emerald-400">✓</span> {f}</li>))}</ul>
            <button onClick={() => !disabled && handleUpgrade(p.id)} disabled={disabled}
              className={`w-full py-2.5 rounded-xl text-sm font-semibold transition-all ${disabled ? "bg-white/[0.03] text-white/20 cursor-not-allowed border border-white/[0.05]" : p.popular || (!disabled && p.id === "enterprise") ? "bg-emerald-500 hover:bg-emerald-400 text-black" : "bg-white/[0.05] hover:bg-white/[0.08] text-white/70 border border-white/[0.08]"}`}>
              {getCta(p)}
            </button>
          </div>);
        })}
      </div>
    </div>
  );
}

'''

content = content[:start_idx] + new_pricing + content[end_idx:]

with open(filepath, "w") as f:
    f.write(content)

print("✅ PricingPage updated successfully!")
print("   - Current plan shows 'YOUR PLAN' badge + greyed out button")
print("   - Lower plans disabled")
print("   - Enterprise is purchasable via PayFast")
print("   - 'Contact sales' replaced with 'Upgrade to Enterprise'")
