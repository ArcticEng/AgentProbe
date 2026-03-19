import { useState, useEffect, useCallback } from "react";

const API = import.meta.env.VITE_API_URL
  ? `${import.meta.env.VITE_API_URL}/api`
  : "/api";

async function apiFetch(path, opts = {}) {
  const key = localStorage.getItem("ap_key") || "";
  const res = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json", ...(key ? { "X-API-Key": key } : {}), ...opts.headers },
    ...opts,
  });
  const data = await res.json();
  if (!res.ok) throw { status: res.status, ...data };
  return data;
}

function Nav({ view, setView, user }) {
  return (
    <nav className="border-b border-white/[0.06] px-6 py-4 flex items-center justify-between sticky top-0 bg-[#06060a]/80 backdrop-blur-xl z-40">
      <button onClick={() => setView("home")} className="flex items-center gap-3">
        <div className="w-8 h-8 bg-gradient-to-br from-emerald-400 to-cyan-500 rounded-lg flex items-center justify-center text-[10px] font-bold text-black">AP</div>
        <span className="font-semibold tracking-tight text-white/90">AgentProbe</span>
      </button>
      <div className="flex items-center gap-2">
        <button onClick={() => setView("pricing")} className="text-xs text-white/40 hover:text-white/70 px-3 py-1.5 rounded-lg transition-all">Pricing</button>
        <button onClick={() => setView("docs")} className="text-xs text-white/40 hover:text-white/70 px-3 py-1.5 rounded-lg transition-all">Docs</button>
        {user ? (
          <div className="flex items-center gap-2">
            <button onClick={() => setView("dashboard")} className="text-xs bg-white/[0.04] text-white/60 hover:text-white/90 px-3 py-1.5 rounded-lg border border-white/[0.08] transition-all">Dashboard</button>
            <div className="w-7 h-7 bg-emerald-500/20 rounded-full flex items-center justify-center text-[10px] text-emerald-400 font-bold">{user.email?.[0]?.toUpperCase() || "U"}</div>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <button onClick={() => setView("login")} className="text-xs text-white/50 hover:text-white/80 px-3 py-1.5 transition-all">Log in</button>
            <button onClick={() => setView("signup")} className="text-xs bg-emerald-500 hover:bg-emerald-400 text-black font-semibold px-4 py-1.5 rounded-lg transition-all">Get started free</button>
          </div>
        )}
      </div>
    </nav>
  );
}

function StatusBadge({ status }) {
  const m = { passed: "bg-emerald-500/15 text-emerald-400 border-emerald-500/20", failed: "bg-red-500/15 text-red-400 border-red-500/20", warning: "bg-amber-500/15 text-amber-400 border-amber-500/20" };
  const ic = { passed: "✓", failed: "✗", warning: "!" };
  return <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium border ${m[status] || m.failed}`}>{ic[status]} {status}</span>;
}

function ScoreRing({ score, size = 48, stroke = 3 }) {
  const r = (size - stroke * 2) / 2, circ = 2 * Math.PI * r, offset = circ * (1 - score);
  const color = score >= 0.8 ? "#10b981" : score >= 0.6 ? "#f59e0b" : "#ef4444";
  return (
    <svg width={size} height={size} className="transform -rotate-90">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="currentColor" strokeWidth={stroke} className="text-white/5" />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke} strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round" style={{ transition: "stroke-dashoffset 1s ease" }} />
      <text x={size / 2} y={size / 2} textAnchor="middle" dominantBaseline="central" className="fill-current text-xs font-semibold" style={{ transform: "rotate(90deg)", transformOrigin: "center", fontSize: size * 0.24 }}>{(score * 100).toFixed(0)}</text>
    </svg>
  );
}

function MetricCard({ label, value, sub, accent }) {
  return (
    <div className="bg-white/[0.03] border border-white/[0.06] rounded-xl p-4 hover:border-white/10 transition-colors">
      <div className="text-[11px] font-medium tracking-wider uppercase text-white/30 mb-1">{label}</div>
      <div className={`text-2xl font-semibold ${accent || "text-white/90"}`}>{value}</div>
      {sub && <div className="text-xs text-white/30 mt-0.5">{sub}</div>}
    </div>
  );
}

// Template descriptions and test details for preview
const TEMPLATE_INFO = {
  customer_service: { desc: "Tests greeting handling, refund requests, angry customer de-escalation, jailbreak resistance, PII protection, out-of-scope redirection, multilingual support", tests: ["Handles greeting","Handles refund","Handles angry customer","Resists jailbreak","Protects PII","Handles out-of-scope","Structured response","Handles multilingual","Handles follow-up","Handles cancellation"], bestFor: "Customer support chatbots" },
  sales_agent: { desc: "Tests lead qualification, pricing questions, competitor comparison, objection handling, anti-manipulation", tests: ["Qualifies lead","Handles pricing","Handles competitor comparison","Doesn't overpromise","Handles objection","Resists manipulation"], bestFor: "Sales and lead-gen bots" },
  hr_assistant: { desc: "Tests leave requests, salary privacy, complaint handling, benefits, social engineering resistance", tests: ["Handles leave request","Protects salary info","Handles complaints","Benefits explanation","Resists social engineering","Handles policy question"], bestFor: "Internal HR bots" },
  rag_system: { desc: "Tests knowledge retrieval accuracy, hallucination detection, source citation, missing context handling", tests: ["Answers from knowledge base","Admits when unsure","Doesn't hallucinate facts","Cites sources","Handles missing context","Handles contradictory sources"], bestFor: "RAG-powered Q&A systems" },
  search_system: { desc: "Tests result relevance, typo tolerance, ambiguity handling, no-result scenarios, bias detection", tests: ["Relevant results","Handles typos","Handles ambiguity","Handles no results","No bias in results"], bestFor: "AI-powered search engines" },
  summarization: { desc: "Tests summary accuracy, key fact preservation, length control, hallucination prevention", tests: ["Summarizes accurately","Preserves key facts","Appropriate length","No hallucinated details"], bestFor: "Document summarization tools" },
  content_generation: { desc: "Tests marketing copy quality, brand voice, originality, sensitive topic handling, constraint following", tests: ["Generates marketing copy","Follows brand voice","Avoids plagiarism","Handles sensitive topics","Respects constraints"], bestFor: "AI content writers" },
  code_generation: { desc: "Tests code validity, explanation quality, debugging, malicious code refusal, security best practices", tests: ["Generates valid code","Explains code","Handles debugging","Refuses malicious code","Handles ambiguity","Suggests best practices","Handles complex request"], bestFor: "AI coding assistants" },
  translation: { desc: "Tests translation accuracy, idiom handling, tone preservation, ambiguity resolution", tests: ["Translates accurately","Handles idioms","Preserves tone","Handles ambiguity"], bestFor: "AI translation services" },
  healthcare_ai: { desc: "Tests medical disclaimer presence, patient data protection, medication safety, emergency recognition", tests: ["No diagnosis without disclaimer","Protects patient data","Medication safety","Emergency recognition","Doesn't replace doctor","Handles mental health"], bestFor: "Healthcare AI systems (HIPAA)" },
  financial_ai: { desc: "Tests investment advice disclaimers, risk disclosure, financial data protection, regulatory compliance", tests: ["No investment advice","Risk disclosure","Protects financial data","Accurate calculations","Regulatory compliance","Fraud detection awareness"], bestFor: "Financial AI systems" },
  legal_ai: { desc: "Tests legal disclaimers, privilege protection, jurisdiction awareness", tests: ["Provides disclaimers","Protects privileged info","Doesn't practice law","Handles jurisdiction"], bestFor: "Legal AI tools" },
  education_ai: { desc: "Tests age-appropriateness, guided learning, frustration handling, anti-cheating, content safety", tests: ["Age-appropriate response","Doesn't give answers directly","Handles frustration","Prevents cheating","Content safety for minors"], bestFor: "EdTech AI systems" },
  api_reliability: { desc: "Tests API responsiveness across 10 diverse requests with latency benchmarks", tests: ["Request 1-10: Various API calls with latency checks"], bestFor: "Any REST API endpoint" },
  error_handling: { desc: "Tests empty input, long input, SQL injection, unicode, mixed languages, HTML injection handling", tests: ["Empty input","Extremely long input","Special characters / SQL injection","Unicode edge case","Mixed languages","HTML injection"], bestFor: "Any system that accepts user input" },
  safety_suite: { desc: "Tests prompt injection, role override, data exfiltration, social engineering, harmful request resistance", tests: ["Resists prompt injection","Resists role override","Resists data exfiltration","Resists social engineering","Handles harmful request"], bestFor: "Any AI-facing system" },
  advanced_adversarial: { desc: "Tests encoded injection, multi-turn manipulation, authority spoofing, emotional manipulation, language switching", tests: ["Encoded injection","Multi-turn manipulation","Authority spoofing","Emotional manipulation","Context confusion","Gradual escalation","Output format injection","Language switching attack"], bestFor: "High-security AI systems" },
  pii_comprehensive: { desc: "Tests protection of emails, phones, SSNs, credit cards, medical info, addresses", tests: ["Protects email","Protects phone","Protects SSN","Protects credit card","Protects medical info","Protects address","Protects in context"], bestFor: "Any system handling personal data" },
  gdpr_compliance: { desc: "Tests right to erasure, data minimization, consent awareness, data portability, cross-border handling", tests: ["Respects deletion request","Data minimization","Consent awareness","Data portability","Cross-border awareness"], bestFor: "EU-facing AI services" },
  bias_fairness: { desc: "Tests gender neutrality, racial fairness, age neutrality, disability awareness, cultural sensitivity", tests: ["Gender neutrality","Racial fairness","Age neutrality","Disability awareness","Cultural sensitivity","Socioeconomic fairness"], bestFor: "Any customer-facing AI" },
  accessibility: { desc: "Tests plain language use, text alternatives, screen reader support, cognitive accessibility", tests: ["Plain language","Provides alternatives","Handles screen reader context","Handles cognitive limitations"], bestFor: "Accessible AI interfaces" },
  performance_suite: { desc: "Tests latency and throughput across 20 diverse prompts", tests: ["20 diverse prompts with latency benchmarks"], bestFor: "Any system — latency baseline" },
  stress_test: { desc: "Fires 50 sequential requests to test throughput and degradation", tests: ["50 sequential requests with latency tracking"], bestFor: "Load testing before launch" },
  rest_api_health: { desc: "Tests GET /health, root endpoint, 404 handling, bad method handling", tests: ["GET /health responds","GET / root responds","404 for missing route","Handles bad method"], bestFor: "Any REST API" },
  rest_api_crud: { desc: "Tests List, Get, Create, and invalid ID handling on a resource", tests: ["LIST resource","GET single resource","POST new resource","GET invalid ID"], bestFor: "CRUD APIs" },
  rest_api_security: { desc: "Tests SQL injection, XSS, path traversal, unauthorized access, header leaks", tests: ["SQL injection attempt","XSS in parameter","Path traversal","Unauthorized access","CORS headers","No sensitive headers leaked"], bestFor: "Any API exposed to the internet" },
  rest_api_performance: { desc: "Fires 20 GET requests to benchmark latency distribution", tests: ["20 sequential GET requests with latency tracking"], bestFor: "API performance baseline" },
  rest_api_pagination: { desc: "Tests page 1, page 2, large page size, invalid page, page 0", tests: ["Page 1","Page 2","Large page size","Invalid page","Page 0"], bestFor: "Paginated APIs" },
  website_uptime: { desc: "Checks that websites respond with 200 OK within latency limits", tests: ["Google is up","GitHub is up","Cloudflare is up"], bestFor: "Website monitoring" },
  website_seo: { desc: "Checks for title tag, load time under 3s, 200 status", tests: ["Has title tag","Loads under 3s","Returns 200"], bestFor: "SEO audits" },
  website_ssl: { desc: "Verifies SSL certificates are valid and sites load over HTTPS", tests: ["SSL valid for each URL"], bestFor: "SSL monitoring" },
  ecommerce_journey: { desc: "Tests browse → search → view → add to cart → view cart → checkout flow", tests: ["Browse products","Search products","View product detail","Add to cart","View cart","Checkout"], bestFor: "E-commerce platforms" },
  auth_flow: { desc: "Tests signup, login, protected route access, invalid login, password validation", tests: ["Signup","Login","Access protected route without token","Invalid login","Password validation"], bestFor: "Auth systems" },
};

// Agent type configurations
const AGENT_TYPES = [
  { id: "mock", name: "Mock Agent (Demo)", desc: "Built-in test responses — no external system needed", fields: [] },
  { id: "anthropic", name: "Anthropic (Claude)", desc: "Test a Claude-powered AI agent", fields: ["api_key", "model", "system_prompt"] },
  { id: "openai", name: "OpenAI (GPT)", desc: "Test an OpenAI-powered AI agent", fields: ["api_key", "model", "system_prompt"] },
  { id: "rest_api", name: "REST API", desc: "Test any REST API endpoint", fields: ["endpoint", "auth_token"] },
  { id: "website", name: "Website", desc: "Test website uptime, SSL, content", fields: ["website_url"] },
  { id: "http", name: "Custom HTTP", desc: "Test any HTTP endpoint", fields: ["endpoint"] },
];

function TemplatePreviewModal({ template, onClose, onRun, loading, userPlan }) {
  const [agentType, setAgentType] = useState("mock");
  const [endpoint, setEndpoint] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [authToken, setAuthToken] = useState("");

  const info = TEMPLATE_INFO[template?.id] || { desc: "Run this test suite against your system.", tests: [], bestFor: "General" };
  const agentConfig = AGENT_TYPES.find(a => a.id === agentType);
  const isFree = !userPlan || userPlan === "free";
  const handleRun = () => {
    const agent = { type: agentType };
    if (endpoint) agent.endpoint = endpoint;
    if (apiKey) agent.api_key = apiKey;
    if (model) agent.model = model;
    if (systemPrompt) agent.system_prompt = systemPrompt;
    if (authToken) agent.auth_token = authToken;
    onRun(template.id, agent);
  };

  if (!template) return null;

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-[#0c0c14] border border-white/10 rounded-2xl max-w-2xl w-full max-h-[85vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="p-6 border-b border-white/[0.06]">
          <div className="flex justify-between items-start">
            <div>
              <h2 className="text-lg font-bold text-white/90">{template.name}</h2>
              <div className="flex items-center gap-2 mt-1">
                <span className="text-[10px] font-mono text-white/30 bg-white/[0.04] px-2 py-0.5 rounded">{template.tests} tests</span>
                <span className="text-[10px] text-white/20">{template.category}</span>
                {template.tags?.map(t => <span key={t} className="text-[9px] text-emerald-400/40 bg-emerald-500/10 px-1.5 py-0.5 rounded">{t}</span>)}
              </div>
            </div>
            <button onClick={onClose} className="text-white/30 hover:text-white text-xl">&times;</button>
          </div>
          <p className="text-xs text-white/40 mt-3 leading-relaxed">{info.desc}</p>
          <div className="text-[10px] text-white/25 mt-2">Best for: <span className="text-white/40">{info.bestFor}</span></div>
        </div>

        {/* Tests included */}
        <div className="p-6 border-b border-white/[0.06]">
          <h3 className="text-xs font-semibold text-white/50 uppercase tracking-wider mb-3">Tests included</h3>
          <div className="grid grid-cols-2 gap-1.5">
            {(Array.isArray(info.tests) ? info.tests : []).map((t, i) => (
              <div key={i} className="flex items-center gap-2 text-xs text-white/40 bg-white/[0.02] rounded-lg px-3 py-2">
                <span className="text-emerald-400/50 text-[10px]">●</span> {t}
              </div>
            ))}
          </div>
        </div>

        {/* Agent configuration */}
        <div className="p-6 border-b border-white/[0.06]">
          <h3 className="text-xs font-semibold text-white/50 uppercase tracking-wider mb-3">Connect your system</h3>

          <div className="grid grid-cols-3 gap-2 mb-4">
            {AGENT_TYPES.map(a => (
              <button key={a.id} onClick={() => setAgentType(a.id)}
                className={`text-left p-3 rounded-xl border transition-all ${agentType === a.id ? "border-emerald-500/40 bg-emerald-500/[0.06]" : "border-white/[0.06] bg-white/[0.02] hover:border-white/10"}`}>
                <div className="text-xs font-semibold text-white/80">{a.name}</div>
                <div className="text-[10px] text-white/25 mt-0.5">{a.desc}</div>
              </button>
            ))}
          </div>

          {agentConfig?.fields.includes("endpoint") && (
            <div className="mb-3">
              <label className="text-[10px] text-white/30 mb-1 block">API Endpoint</label>
              <input type="text" value={endpoint} onChange={e => setEndpoint(e.target.value)}
                placeholder="https://api.yoursite.com"
                className="w-full bg-white/[0.04] border border-white/[0.08] rounded-lg px-3 py-2 text-xs text-white/80 placeholder-white/20 focus:border-emerald-500/40 focus:outline-none font-mono" />
            </div>
          )}

          {agentConfig?.fields.includes("api_key") && (
            <div className="mb-3">
              <label className="text-[10px] text-white/30 mb-1 block">{agentType === "anthropic" ? "Anthropic" : "OpenAI"} API Key</label>
              <input type="password" value={apiKey} onChange={e => setApiKey(e.target.value)}
                placeholder={agentType === "anthropic" ? "sk-ant-..." : "sk-..."}
                className="w-full bg-white/[0.04] border border-white/[0.08] rounded-lg px-3 py-2 text-xs text-white/80 placeholder-white/20 focus:border-emerald-500/40 focus:outline-none font-mono" />
            </div>
          )}

          {agentConfig?.fields.includes("model") && (
            <div className="mb-3">
              <label className="text-[10px] text-white/30 mb-1 block">Model</label>
              <input type="text" value={model} onChange={e => setModel(e.target.value)}
                placeholder={agentType === "anthropic" ? "claude-haiku-4-5-20251001" : "gpt-4o-mini"}
                className="w-full bg-white/[0.04] border border-white/[0.08] rounded-lg px-3 py-2 text-xs text-white/80 placeholder-white/20 focus:border-emerald-500/40 focus:outline-none font-mono" />
            </div>
          )}

          {agentConfig?.fields.includes("system_prompt") && (
            <div className="mb-3">
              <label className="text-[10px] text-white/30 mb-1 block">System Prompt (what your agent does)</label>
              <textarea value={systemPrompt} onChange={e => setSystemPrompt(e.target.value)}
                placeholder="You are a customer service agent for..."
                rows={3}
                className="w-full bg-white/[0.04] border border-white/[0.08] rounded-lg px-3 py-2 text-xs text-white/80 placeholder-white/20 focus:border-emerald-500/40 focus:outline-none resize-none" />
            </div>
          )}

          {agentConfig?.fields.includes("auth_token") && (
            <div className="mb-3">
              <label className="text-[10px] text-white/30 mb-1 block">Auth Token (optional)</label>
              <input type="password" value={authToken} onChange={e => setAuthToken(e.target.value)}
                placeholder="Bearer token for authenticated endpoints"
                className="w-full bg-white/[0.04] border border-white/[0.08] rounded-lg px-3 py-2 text-xs text-white/80 placeholder-white/20 focus:border-emerald-500/40 focus:outline-none font-mono" />
            </div>
          )}

          {agentConfig?.fields.includes("website_url") && (
            <div className="mb-3">
              <label className="text-[10px] text-white/30 mb-1 block">Website URL to test</label>
              <input type="text" value={endpoint} onChange={e => setEndpoint(e.target.value)}
                placeholder="https://yoursite.com"
                className="w-full bg-white/[0.04] border border-white/[0.08] rounded-lg px-3 py-2 text-xs text-white/80 placeholder-white/20 focus:border-emerald-500/40 focus:outline-none font-mono" />
              <div className="text-[9px] text-white/15 mt-1">Tests uptime, SSL certificate, response time, and content</div>
            </div>
          )}
        </div>

        {/* Run button */}
        <div className="p-6">
          <button onClick={handleRun} disabled={loading}
            className="w-full bg-emerald-500 hover:bg-emerald-400 disabled:opacity-40 text-black font-semibold py-3 rounded-xl text-sm transition-all">
            {loading ? "Running tests..." : `Run ${template.tests} tests →`}
          </button>
          <p className="text-[10px] text-white/20 text-center mt-2">
            {agentType === "mock" ? "Running against built-in mock responses" : `Running against your ${agentConfig?.name}`}
          </p>
        </div>
      </div>
    </div>
  );
}

function HomePage({ setView }) {
  return (
    <div className="max-w-5xl mx-auto px-6">
      <div className="text-center py-24">
        <div className="inline-flex items-center gap-2 px-3 py-1 bg-emerald-500/10 border border-emerald-500/20 rounded-full text-xs text-emerald-400 mb-6"><span className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-pulse" />Now accepting beta customers</div>
        <h1 className="text-6xl font-bold tracking-tight mb-6 leading-[1.1]"><span className="bg-gradient-to-r from-emerald-300 via-cyan-300 to-emerald-300 bg-clip-text text-transparent">Test your AI agents</span><br /><span className="text-white/70">before your users do.</span></h1>
        <p className="text-lg text-white/35 max-w-2xl mx-auto mb-10 leading-relaxed">Automated testing for hallucinations, safety, latency, PII leaks, jailbreaks, and more. Catch problems before deployment — get certified as safe.</p>
        <div className="flex items-center justify-center gap-4">
          <button onClick={() => setView("signup")} className="bg-emerald-500 hover:bg-emerald-400 text-black font-semibold px-8 py-3 rounded-xl transition-all text-sm">Get started free</button>
          <button onClick={() => setView("pricing")} className="bg-white/[0.04] hover:bg-white/[0.08] text-white/70 px-8 py-3 rounded-xl border border-white/[0.08] transition-all text-sm">View pricing</button>
        </div>
      </div>
      <div className="grid grid-cols-3 gap-4 mb-20">
        {[{icon:"🛡",title:"Safety testing",desc:"Jailbreak resistance, prompt injection, PII leak detection, social engineering defense"},{icon:"🧠",title:"LLM-Judge",desc:"AI-powered evaluation catches nuanced issues keyword matching misses — hallucinations, tone, accuracy"},{icon:"✓",title:"Certification",desc:"AgentProbe Certified badge for your website — prove your AI is trustworthy"}].map((f,i)=>(<div key={i} className="p-6 bg-white/[0.02] border border-white/[0.06] rounded-2xl hover:border-emerald-500/20 transition-all"><div className="text-2xl mb-3">{f.icon}</div><h3 className="text-sm font-semibold text-white/80 mb-2">{f.title}</h3><p className="text-xs text-white/30 leading-relaxed">{f.desc}</p></div>))}
      </div>
      <div className="mb-20 p-8 bg-gradient-to-r from-emerald-500/[0.04] to-cyan-500/[0.04] border border-white/[0.06] rounded-2xl">
        <h2 className="text-sm font-semibold text-white/60 mb-4">3 lines to test your agent</h2>
        <pre className="text-sm font-mono text-emerald-300/70 bg-black/30 rounded-xl p-6 overflow-x-auto leading-relaxed">{`from agentprobe import AgentProbe, Templates\n\nprobe = AgentProbe(api_key="ap_live_...", provider="anthropic")\nresults = probe.run(Templates.safety_suite())\nresults.summary()`}</pre>
      </div>
      <div className="text-center pb-20">
        <h2 className="text-2xl font-bold text-white/80 mb-3">Ready to ship safe AI?</h2>
        <p className="text-white/30 mb-6">Free tier includes 25 test runs/month. No credit card required.</p>
        <button onClick={() => setView("signup")} className="bg-emerald-500 hover:bg-emerald-400 text-black font-semibold px-8 py-3 rounded-xl transition-all text-sm">Create free account</button>
      </div>
    </div>
  );
}

function PricingPage({ setView, user }) {
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

function SignupPage({ setView, setUser }) {
  const [email, setEmail] = useState(""); const [name, setName] = useState(""); const [loading, setLoading] = useState(false); const [result, setResult] = useState(null); const [error, setError] = useState("");
  const handleSignup = async (e) => { e.preventDefault(); setLoading(true); setError(""); try { const data = await apiFetch("/billing/signup", {method:"POST",body:JSON.stringify({email,name})}); localStorage.setItem("ap_key",data.api_key); localStorage.setItem("ap_user",JSON.stringify({email,plan:"free"})); setResult(data); setUser({email,plan:"free"}); } catch(e) { setError(e.detail||e.message||"Signup failed."); } finally { setLoading(false); } };
  if (result) return (
    <div className="max-w-lg mx-auto px-6 py-20"><div className="bg-white/[0.03] border border-emerald-500/20 rounded-2xl p-8 text-center"><div className="w-16 h-16 bg-emerald-500/20 rounded-full flex items-center justify-center mx-auto mb-4 text-2xl">✓</div><h2 className="text-xl font-bold text-white/90 mb-2">Account created!</h2><p className="text-white/40 text-sm mb-6">Save your API key — it will only be shown once.</p><div className="bg-black/40 rounded-xl p-4 mb-6 border border-white/[0.08]"><div className="text-[10px] text-white/30 uppercase tracking-wider mb-2">Your API Key</div><code className="text-sm text-emerald-400 font-mono break-all select-all">{result.api_key}</code></div><button onClick={() => navigator.clipboard.writeText(result.api_key)} className="bg-white/[0.06] hover:bg-white/[0.1] text-white/70 px-6 py-2 rounded-xl text-sm border border-white/[0.08] transition-all mb-4 w-full">Copy API key</button><button onClick={() => setView("dashboard")} className="bg-emerald-500 hover:bg-emerald-400 text-black font-semibold px-6 py-2.5 rounded-xl text-sm transition-all w-full">Go to Dashboard</button></div></div>
  );
  return (
    <div className="max-w-md mx-auto px-6 py-20"><div className="text-center mb-8"><h1 className="text-3xl font-bold text-white/90 mb-2">Create your account</h1><p className="text-white/35 text-sm">Free tier — 25 test runs/month, no credit card required</p></div><form onSubmit={handleSignup} className="space-y-4"><div><label className="text-xs text-white/40 mb-1 block">Name</label><input type="text" value={name} onChange={e=>setName(e.target.value)} placeholder="Your name" className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-4 py-3 text-sm text-white/80 placeholder-white/20 focus:border-emerald-500/40 focus:outline-none transition-all"/></div><div><label className="text-xs text-white/40 mb-1 block">Email *</label><input type="email" value={email} onChange={e=>setEmail(e.target.value)} placeholder="you@company.com" required className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-4 py-3 text-sm text-white/80 placeholder-white/20 focus:border-emerald-500/40 focus:outline-none transition-all"/></div>{error && <div className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg p-3">{error}</div>}<button type="submit" disabled={loading||!email} className="w-full bg-emerald-500 hover:bg-emerald-400 disabled:opacity-40 text-black font-semibold py-3 rounded-xl text-sm transition-all">{loading?"Creating account...":"Create free account"}</button></form><p className="text-center text-xs text-white/25 mt-6">Already have an account? <button onClick={() => setView("login")} className="text-emerald-400/60 hover:text-emerald-400">Log in</button></p></div>
  );
}

function LoginPage({ setView, setUser }) {
  const [apiKey, setApiKey] = useState(""); const [loading, setLoading] = useState(false); const [error, setError] = useState("");
  const handleLogin = async (e) => { e.preventDefault(); setLoading(true); setError(""); try { localStorage.setItem("ap_key",apiKey); const data = await apiFetch("/billing/usage"); localStorage.setItem("ap_user",JSON.stringify({email:data.plan||"user",plan:data.plan})); setUser({email:"user",plan:data.plan}); setView("dashboard"); } catch { localStorage.removeItem("ap_key"); setError("Invalid API key."); } finally { setLoading(false); } };
  return (
    <div className="max-w-md mx-auto px-6 py-20"><div className="text-center mb-8"><h1 className="text-3xl font-bold text-white/90 mb-2">Log in</h1><p className="text-white/35 text-sm">Enter your API key to access your dashboard</p></div><form onSubmit={handleLogin} className="space-y-4"><div><label className="text-xs text-white/40 mb-1 block">API Key</label><input type="text" value={apiKey} onChange={e=>setApiKey(e.target.value)} placeholder="ap_live_..." required className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl px-4 py-3 text-sm text-white/80 placeholder-white/20 focus:border-emerald-500/40 focus:outline-none font-mono transition-all"/></div>{error && <div className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg p-3">{error}</div>}<button type="submit" disabled={loading||!apiKey} className="w-full bg-emerald-500 hover:bg-emerald-400 disabled:opacity-40 text-black font-semibold py-3 rounded-xl text-sm transition-all">{loading?"Verifying...":"Log in"}</button></form><p className="text-center text-xs text-white/25 mt-6">No account? <button onClick={() => setView("signup")} className="text-emerald-400/60 hover:text-emerald-400">Sign up free</button></p></div>
  );
}

function DocsPage() {
  return (
    <div className="max-w-3xl mx-auto px-6 py-16">
      <h1 className="text-3xl font-bold text-white/90 mb-8">Documentation</h1>
      {[
        {title:"Quick Start",code:`pip install agentprobe\n\nfrom agentprobe import AgentProbe, Templates\nprobe = AgentProbe(api_key="ap_live_...", provider="anthropic")\nresults = probe.run(Templates.safety_suite())\nresults.summary()`},
        {title:"Test a REST API (non-AI)",code:`from agentprobe.adapters import RESTAPIAdapter\nprobe = AgentProbe(adapter=RESTAPIAdapter("https://api.example.com"))\nsuite = TestSuite("API Health")\nsuite.add_test("health", "GET /health").expect_contains("200")\nprobe.run(suite).summary()`},
        {title:"API — Run a template",code:`curl -X POST ${API}/run/template \\\n  -H "X-API-Key: ap_live_..." \\\n  -d '{"template": "safety_suite", "agent": {"type": "anthropic", "api_key": "sk-...", "system_prompt": "You are a support agent."}}'`},
        {title:"API — Test a REST API",code:`curl -X POST ${API}/run/template \\\n  -H "X-API-Key: ap_live_..." \\\n  -d '{"template": "rest_api_health", "agent": {"type": "rest_api", "endpoint": "https://jsonplaceholder.typicode.com"}}'`},
      ].map((s,i) => (<div key={i} className="mb-8"><h2 className="text-sm font-semibold text-white/60 mb-3">{s.title}</h2><pre className="text-xs font-mono text-emerald-300/60 bg-black/30 rounded-xl p-5 border border-white/[0.05] overflow-x-auto whitespace-pre-wrap">{s.code}</pre></div>))}
      <div className="mt-12 p-6 bg-white/[0.02] border border-white/[0.06] rounded-xl">
        <h2 className="text-sm font-semibold text-white/60 mb-3">Available Templates (33)</h2>
        <div className="grid grid-cols-2 gap-2">
          {["customer_service (10)","sales_agent (6)","hr_assistant (6)","rag_system (6)","search_system (5)","summarization (4)","content_generation (5)","code_generation (7)","translation (4)","healthcare_ai (6)","financial_ai (6)","legal_ai (4)","education_ai (5)","api_reliability (10)","error_handling (6)","safety_suite (5)","advanced_adversarial (8)","pii_comprehensive (7)","gdpr_compliance (5)","bias_fairness (6)","accessibility (4)","performance_suite (20)","stress_test (50)","rest_api_health (4)","rest_api_crud (4)","rest_api_security (6)","rest_api_performance (20)","rest_api_pagination (5)","website_uptime (3)","website_seo (3)","website_ssl (2)","ecommerce_journey (6)","auth_flow (5)"].map(t => (<div key={t} className="text-xs text-white/40 bg-white/[0.02] rounded-lg px-3 py-2 font-mono">{t}</div>))}
        </div>
      </div>
    </div>
  );
}

function DashboardPage({ setView, user, setUser }) {
  const [templates, setTemplates] = useState([]); const [runs, setRuns] = useState([]); const [currentRun, setCurrentRun] = useState(null); const [loading, setLoading] = useState(false); const [usage, setUsage] = useState(null); const [selectedTest, setSelectedTest] = useState(null);
  const [previewTemplate, setPreviewTemplate] = useState(null);

  useEffect(() => { apiFetch("/templates").then(d => setTemplates(d.templates || [])).catch(() => {}); apiFetch("/billing/usage").then(setUsage).catch(() => {}); }, []);

  const runTemplate = async (id, agent) => {
    setLoading(true); setPreviewTemplate(null);
    try {
      const result = await apiFetch("/run/template", {method:"POST",body:JSON.stringify({template:id,agent})});
      setCurrentRun(result); setRuns(prev => [result,...prev]); apiFetch("/billing/usage").then(setUsage).catch(() => {});
    } catch(e) { if(e.status===429) alert(`Usage limit reached.`); else alert(e.detail?.message||"Test failed."); }
    finally { setLoading(false); }
  };

  const logout = () => { localStorage.removeItem("ap_key"); localStorage.removeItem("ap_user"); setUser(null); setView("home"); };

  if (currentRun) { const r = currentRun; return (
    <div className="max-w-5xl mx-auto px-6 py-8">
      {selectedTest && (<div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={() => setSelectedTest(null)}><div className="bg-[#0c0c14] border border-white/10 rounded-2xl max-w-2xl w-full max-h-[80vh] overflow-y-auto p-6" onClick={e => e.stopPropagation()}><div className="flex justify-between mb-4"><div><h3 className="text-lg font-semibold text-white/90">{selectedTest.test_name}</h3><StatusBadge status={selectedTest.status} /></div><button onClick={() => setSelectedTest(null)} className="text-white/30 hover:text-white text-2xl">&times;</button></div><div className="bg-white/[0.03] rounded-lg p-3 text-sm text-white/60 font-mono border border-white/[0.05] mb-4">{selectedTest.input}</div><div className="space-y-2">{selectedTest.evals?.map((ev,i) => (<div key={i} className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-sm ${ev.passed?"bg-emerald-500/5 border-emerald-500/10 text-emerald-400/80":"bg-red-500/5 border-red-500/10 text-red-400/80"}`}><span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-white/5">{ev.type}</span><span className="flex-1">{ev.message}</span><span>{ev.passed?"✓":"✗"}</span></div>))}</div></div></div>)}
      <div className="flex items-center gap-3 mb-6"><button onClick={() => setCurrentRun(null)} className="text-white/30 hover:text-white/60 text-lg">&larr;</button><ScoreRing score={r.avg_score} size={56} stroke={3} /><div><h1 className="text-xl font-bold text-white/90">{r.suite_name}</h1><div className="text-xs text-white/30">{r.total} tests · {r.duration_ms?.toFixed(0)}ms · {r.id}</div></div></div>
      <div className="grid grid-cols-4 gap-3 mb-6"><MetricCard label="Pass rate" value={`${(r.pass_rate*100).toFixed(0)}%`} accent={r.pass_rate>=0.8?"text-emerald-400":"text-amber-400"}/><MetricCard label="Passed" value={r.passed} accent="text-emerald-400" sub={`of ${r.total}`}/><MetricCard label="Failed" value={r.failed} accent={r.failed>0?"text-red-400":"text-white/40"}/><MetricCard label="Avg latency" value={`${r.avg_latency_ms?.toFixed(0)}ms`}/></div>
      <div className="space-y-2">{r.results?.map((test,i) => (<button key={i} onClick={() => setSelectedTest(test)} className="w-full flex items-center gap-3 px-4 py-3 bg-white/[0.02] hover:bg-white/[0.04] border border-white/[0.05] rounded-lg transition-all text-left"><StatusBadge status={test.status}/><div className="flex-1 min-w-0"><div className="text-sm font-medium text-white/80 truncate">{test.test_name}</div><div className="text-xs text-white/30 truncate">{test.input}</div></div><div className="text-right shrink-0"><div className="text-sm font-mono text-white/60">{(test.score*100).toFixed(0)}%</div><div className="text-[10px] text-white/25 font-mono">{test.latency_ms?.toFixed(0)}ms</div></div></button>))}</div>
    </div>); }

  return (
    <div className="max-w-5xl mx-auto px-6 py-8">
      <TemplatePreviewModal template={previewTemplate} onClose={() => setPreviewTemplate(null)} onRun={runTemplate} loading={loading} userPlan={user?.plan} />

      <div className="flex items-center justify-between mb-8"><h1 className="text-2xl font-bold text-white/90">Dashboard</h1><div className="flex items-center gap-3">{usage && (<div className="text-xs text-white/30 bg-white/[0.03] px-3 py-1.5 rounded-lg border border-white/[0.06]">{usage.usage?.test_runs||0} / {usage.limits?.limit==="unlimited"?"∞":usage.limits?.limit} runs · <span className="capitalize">{usage.plan}</span> plan</div>)}<button onClick={() => setView("pricing")} className="text-xs text-emerald-400/60 hover:text-emerald-400 px-3 py-1.5 rounded-lg border border-emerald-500/20 transition-all">Upgrade</button><button onClick={logout} className="text-xs text-white/30 hover:text-white/60 px-3 py-1.5 transition-all">Log out</button></div></div>
      {runs.length > 0 && (<div className="grid grid-cols-4 gap-3 mb-8"><MetricCard label="Total runs" value={runs.length}/><MetricCard label="Tests" value={runs.reduce((a,r)=>a+r.total,0)}/><MetricCard label="Avg pass rate" value={`${(runs.reduce((a,r)=>a+r.pass_rate,0)/runs.length*100).toFixed(0)}%`} accent="text-emerald-400"/><MetricCard label="Avg score" value={`${(runs.reduce((a,r)=>a+r.avg_score,0)/runs.length*100).toFixed(0)}%`} accent="text-cyan-400"/></div>)}

      {(() => {
        const cats = {};
        templates.forEach(t => { const c = t.category || "General"; if (!cats[c]) cats[c] = []; cats[c].push(t); });
        const icons = {"AI Chatbots":"💬","AI Applications":"🧠","Regulated Industries":"🏥","System Reliability":"⚡","Security":"🛡","Compliance":"📋","Performance":"📊","API Testing":"🔌","Website Testing":"🌐","User Journeys":"🛤"};
        return Object.entries(cats).map(([cat, items]) => (
          <div key={cat} className="mb-6">
            <h2 className="text-sm font-medium text-white/40 uppercase tracking-wider mb-3 flex items-center gap-2"><span>{icons[cat]||"📦"}</span> {cat} <span className="text-[10px] text-white/20 font-mono bg-white/[0.03] px-1.5 py-0.5 rounded">{items.length}</span></h2>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
              {items.map(t => (
                <button key={t.id} onClick={() => setPreviewTemplate(t)}
                  className="text-left p-4 bg-white/[0.02] hover:bg-white/[0.04] border border-white/[0.06] hover:border-emerald-500/20 rounded-xl transition-all group">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-semibold text-white/80 group-hover:text-emerald-300 transition-colors">{t.name}</span>
                    <span className="text-[10px] font-mono text-white/15 bg-white/[0.03] px-1.5 py-0.5 rounded">{t.tests}</span>
                  </div>
                  {t.tags && <div className="flex gap-1 mt-1.5">{t.tags.slice(0,2).map(tag => <span key={tag} className="text-[9px] text-white/20 bg-white/[0.03] px-1.5 py-0.5 rounded">{tag}</span>)}</div>}
                  <div className="text-[10px] text-emerald-400/50 group-hover:text-emerald-400 transition-colors mt-2">View details →</div>
                </button>
              ))}
            </div>
          </div>
        ));
      })()}

      {runs.length > 0 && (<div><h2 className="text-sm font-medium text-white/40 uppercase tracking-wider mb-4">Recent runs</h2><div className="space-y-2">{runs.map(run => (<button key={run.id} onClick={() => setCurrentRun(run)} className="w-full flex items-center gap-4 px-4 py-3 bg-white/[0.02] hover:bg-white/[0.04] border border-white/[0.05] rounded-lg transition-all text-left"><ScoreRing score={run.avg_score} size={36} stroke={2}/><div className="flex-1"><div className="text-sm font-medium text-white/70">{run.suite_name}</div><div className="text-[10px] text-white/25">{run.passed}/{run.total} passed</div></div><span className="text-[10px] font-mono text-white/15">{run.id}</span></button>))}</div></div>)}
    </div>
  );
}


function BillingSuccessPage({ setView, user, setUser }) {
  const [status, setStatus] = useState("loading");
  const [newPlan, setNewPlan] = useState(null);

  useEffect(() => {
    let attempts = 0;
    const maxAttempts = 15;
    const oldPlan = user?.plan || "free";

    const checkPlan = () => {
      attempts++;
      apiFetch("/billing/usage").then(data => {
        if (data.plan && data.plan !== "free" && data.plan !== oldPlan) {
          const updatedUser = { ...user, plan: data.plan };
          localStorage.setItem("ap_user", JSON.stringify(updatedUser));
          setUser(updatedUser);
          setNewPlan(data.plan);
          setStatus("success");
        } else if (attempts < maxAttempts) {
          setTimeout(checkPlan, 2000);
        } else {
          setStatus("pending");
        }
      }).catch(() => {
        if (attempts < maxAttempts) setTimeout(checkPlan, 2000);
        else setStatus("pending");
      });
    };

    setTimeout(checkPlan, 1000);
  }, []);

  return (
    <div className="max-w-lg mx-auto px-6 py-20">
      <div className="bg-white/[0.03] border border-emerald-500/20 rounded-2xl p-8 text-center">
        {status === "loading" && (
          <><div className="w-16 h-16 bg-emerald-500/20 rounded-full flex items-center justify-center mx-auto mb-4 text-2xl animate-pulse">⏳</div>
          <h2 className="text-xl font-bold text-white/90 mb-2">Processing payment...</h2>
          <p className="text-white/40 text-sm">Confirming your upgrade with PayFast.</p></>
        )}
        {status === "success" && (
          <><div className="w-16 h-16 bg-emerald-500/20 rounded-full flex items-center justify-center mx-auto mb-4 text-2xl">✓</div>
          <h2 className="text-xl font-bold text-white/90 mb-2">Payment successful!</h2>
          <p className="text-white/40 text-sm mb-6">Your account has been upgraded to <span className="text-emerald-400 font-semibold capitalize">{newPlan || user?.plan}</span>.</p>
          <button onClick={() => setView("dashboard")} className="bg-emerald-500 hover:bg-emerald-400 text-black font-semibold px-8 py-3 rounded-xl text-sm transition-all w-full">Go to Dashboard</button></>
        )}
        {status === "pending" && (
          <><div className="w-16 h-16 bg-amber-500/20 rounded-full flex items-center justify-center mx-auto mb-4 text-2xl">⏳</div>
          <h2 className="text-xl font-bold text-white/90 mb-2">Payment received!</h2>
          <p className="text-white/40 text-sm mb-4">Your upgrade is being processed. This usually takes a few seconds.</p>
          <p className="text-white/30 text-xs mb-6">If your plan hasn't updated yet, log out and back in.</p>
          <button onClick={() => setView("dashboard")} className="bg-emerald-500 hover:bg-emerald-400 text-black font-semibold px-8 py-3 rounded-xl text-sm transition-all w-full">Go to Dashboard</button></>
        )}
      </div>
    </div>
  );
}

export default function App() {
  const [view, setView] = useState(() => {
    if (window.location.pathname === "/billing/success") return "billing_success";
    return "home";
  });
  const [user, setUser] = useState(() => { try { return JSON.parse(localStorage.getItem("ap_user")); } catch { return null; } });
  return (
    <div className="min-h-screen bg-[#06060a] text-white">
      <Nav view={view} setView={setView} user={user} />
      {view === "home" && <HomePage setView={setView} />}
      {view === "pricing" && <PricingPage setView={setView} user={user} />}
      {view === "signup" && <SignupPage setView={setView} setUser={setUser} />}
      {view === "login" && <LoginPage setView={setView} setUser={setUser} />}
      {view === "docs" && <DocsPage />}
      {view === "billing_success" && <BillingSuccessPage setView={setView} user={user} setUser={setUser} />}
      {view === "dashboard" && <DashboardPage setView={setView} user={user} setUser={setUser} />}
      <footer className="border-t border-white/[0.04] py-8 text-center text-xs text-white/20 mt-20">AgentProbe · Universal AI & System Verification · © {new Date().getFullYear()}</footer>
    </div>
  );
}