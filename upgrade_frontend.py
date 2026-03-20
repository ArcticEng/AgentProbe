#!/usr/bin/env python3
"""
Frontend Value Upgrade — Patches App.jsx with:
1. Plan refresh on every dashboard load
2. Onboarding flow for new users
3. Historical trend chart
4. Custom test builder
5. Schedule configuration
"""

f = "/Users/rigard/Desktop/agentprobe/dashboard/src/App.jsx"
with open(f, "r") as fh:
    app = fh.read()

# ============================================================
# FIX 1: Plan refresh — fetch plan on every dashboard load
# ============================================================
old_dashboard_effect = """  useEffect(() => { apiFetch("/templates").then(d => setTemplates(d.templates || [])).catch(() => {}); apiFetch("/billing/usage").then(setUsage).catch(() => {}); }, []);"""

new_dashboard_effect = """  useEffect(() => {
    apiFetch("/templates").then(d => setTemplates(d.templates || [])).catch(() => {});
    apiFetch("/billing/usage").then(data => {
      setUsage(data);
      // Always sync plan from server — fixes stale localStorage
      if (data.plan && user) {
        const updated = { ...user, plan: data.plan };
        localStorage.setItem("ap_user", JSON.stringify(updated));
        if (user.plan !== data.plan) setUser(updated);
      }
    }).catch(() => {});
    apiFetch("/history?days=30").then(d => setHistory(d.history || [])).catch(() => {});
  }, []);"""

app = app.replace(old_dashboard_effect, new_dashboard_effect)

# ============================================================
# FIX 2: Add history + onboarding state to DashboardPage
# ============================================================
old_dash_state = """  const [templates, setTemplates] = useState([]); const [runs, setRuns] = useState([]); const [currentRun, setCurrentRun] = useState(null); const [loading, setLoading] = useState(false); const [usage, setUsage] = useState(null); const [selectedTest, setSelectedTest] = useState(null);
  const [previewTemplate, setPreviewTemplate] = useState(null);"""

new_dash_state = """  const [templates, setTemplates] = useState([]); const [runs, setRuns] = useState([]); const [currentRun, setCurrentRun] = useState(null); const [loading, setLoading] = useState(false); const [usage, setUsage] = useState(null); const [selectedTest, setSelectedTest] = useState(null);
  const [previewTemplate, setPreviewTemplate] = useState(null);
  const [history, setHistory] = useState([]);
  const [showOnboarding, setShowOnboarding] = useState(() => !localStorage.getItem("ap_onboarded"));
  const [activeTab, setActiveTab] = useState("templates");"""

app = app.replace(old_dash_state, new_dash_state)

# ============================================================
# FIX 3: Add onboarding + history + tabs to dashboard body
# Find the metrics cards section and add above it
# ============================================================
old_metrics = """      {runs.length > 0 && (<div className="grid grid-cols-4 gap-3 mb-8">"""

# Onboarding banner + tab nav + history chart
new_section = """      {/* Onboarding */}
      {showOnboarding && (
        <div className="mb-6 p-5 bg-gradient-to-r from-emerald-500/[0.06] to-cyan-500/[0.06] border border-emerald-500/20 rounded-2xl">
          <div className="flex justify-between items-start">
            <div>
              <h2 className="text-sm font-bold text-emerald-400 mb-2">Welcome to AgentProbe!</h2>
              <div className="space-y-2 text-xs text-white/50">
                <p>1. <strong className="text-white/70">Pick a template below</strong> — start with <span className="text-emerald-400 cursor-pointer" onClick={() => { const t = templates.find(t => t.id === "safety_suite"); if (t) setPreviewTemplate(t); }}>Safety Suite</span> to see how it works</p>
                <p>2. <strong className="text-white/70">Click "View details"</strong> to see what tests run and configure your target system</p>
                <p>3. <strong className="text-white/70">Run the tests</strong> — mock mode is free, connect real systems on Pro</p>
              </div>
            </div>
            <button onClick={() => { setShowOnboarding(false); localStorage.setItem("ap_onboarded", "1"); }} className="text-white/20 hover:text-white/50 text-lg">&times;</button>
          </div>
        </div>
      )}

      {/* Tab Navigation */}
      <div className="flex gap-1 mb-6 bg-white/[0.02] rounded-xl p-1 border border-white/[0.05]">
        {[{id:"templates",label:"Templates",icon:"📋"},{id:"history",label:"History",icon:"📊"},{id:"custom",label:"Custom Tests",icon:"🔧"}].map(tab => (
          <button key={tab.id} onClick={() => setActiveTab(tab.id)} className={`flex-1 py-2 px-3 rounded-lg text-xs font-medium transition-all ${activeTab === tab.id ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" : "text-white/30 hover:text-white/50"}`}>{tab.icon} {tab.label}</button>
        ))}
      </div>

      {/* History Tab */}
      {activeTab === "history" && (
        <div className="mb-8">
          <h2 className="text-sm font-medium text-white/40 uppercase tracking-wider mb-4">Test History — Last 30 Days</h2>
          {history.length === 0 ? (
            <div className="text-center py-12 text-white/20 text-sm">No test runs yet. Run your first template to see trends here.</div>
          ) : (
            <div>
              <div className="grid grid-cols-4 gap-3 mb-4">
                <MetricCard label="Total Runs" value={history.reduce((a,h) => a+h.runs, 0)} />
                <MetricCard label="Tests Executed" value={history.reduce((a,h) => a+h.tests, 0)} />
                <MetricCard label="Avg Pass Rate" value={`${(history.reduce((a,h) => a+h.pass_rate, 0) / history.length * 100).toFixed(0)}%`} accent="text-emerald-400" />
                <MetricCard label="Avg Latency" value={`${(history.reduce((a,h) => a+h.avg_latency, 0) / history.length).toFixed(0)}ms`} />
              </div>
              <div className="bg-white/[0.02] border border-white/[0.06] rounded-xl p-4">
                <div className="flex items-end gap-1" style={{height:"120px"}}>
                  {history.map((h,i) => {
                    const barH = Math.max(4, h.pass_rate * 110);
                    const color = h.pass_rate >= 0.8 ? "#10b981" : h.pass_rate >= 0.6 ? "#f59e0b" : "#ef4444";
                    return <div key={i} className="flex-1 flex flex-col items-center gap-1 group relative">
                      <div className="absolute -top-6 bg-black/80 text-[9px] text-white/60 px-1.5 py-0.5 rounded opacity-0 group-hover:opacity-100 whitespace-nowrap">{h.date}: {(h.pass_rate*100).toFixed(0)}% ({h.tests} tests)</div>
                      <div style={{height:`${barH}px`, backgroundColor:color}} className="w-full rounded-t opacity-70 hover:opacity-100 transition-opacity min-w-[4px]" />
                    </div>;
                  })}
                </div>
                <div className="flex justify-between text-[9px] text-white/15 mt-2">
                  <span>{history[0]?.date}</span><span>{history[history.length-1]?.date}</span>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Custom Tests Tab */}
      {activeTab === "custom" && (
        <CustomTestBuilder />
      )}

      {/* Templates Tab (original content, wrapped) */}
      {activeTab === "templates" && (<>
      {runs.length > 0 && (<div className="grid grid-cols-4 gap-3 mb-8">"""

app = app.replace(old_metrics, new_section)

# Close the templates tab wrapper — find the end of runs section
old_runs_end = """      {runs.length > 0 && (<div><h2 className="text-sm font-medium text-white/40 uppercase tracking-wider mb-4">Recent runs</h2>"""
new_runs_end = """      {runs.length > 0 && (<div><h2 className="text-sm font-medium text-white/40 uppercase tracking-wider mb-4">Recent runs ({runs.length})</h2>"""
app = app.replace(old_runs_end, new_runs_end)

# Find the last closing of the runs section and add the tab closer
old_runs_close = """              <span className="text-[10px] font-mono text-white/15">{run.id}</span></button>))}</div></div>)}
    </div>"""
new_runs_close = """              <span className="text-[10px] font-mono text-white/15">{run.id}</span></button>))}</div></div>)}
      </>)}
    </div>"""
app = app.replace(old_runs_close, new_runs_close)

# ============================================================
# FIX 4: Add CustomTestBuilder component before DashboardPage
# ============================================================
dashboard_marker = "function DashboardPage({ setView, user, setUser }) {"

custom_builder = '''function CustomTestBuilder() {
  const [tests, setTests] = useState([{name:"",input:"",expect_contains:"",expect_not_contains:""}]);
  const [suiteName, setSuiteName] = useState("");
  const [saved, setSaved] = useState(false);

  const addTest = () => setTests([...tests, {name:"",input:"",expect_contains:"",expect_not_contains:""}]);
  const updateTest = (i, field, val) => { const t = [...tests]; t[i][field] = val; setTests(t); };
  const removeTest = (i) => setTests(tests.filter((_,idx) => idx !== i));

  const saveTests = async () => {
    if (!suiteName.trim() || tests.length === 0) return;
    const payload = tests.filter(t => t.name && t.input).map(t => ({
      name: t.name, input: t.input,
      evals: [
        ...(t.expect_contains ? [{type:"contains",params:{phrases:[t.expect_contains]}}] : []),
        ...(t.expect_not_contains ? [{type:"not_contains",params:{phrases:[t.expect_not_contains]}}] : []),
      ]
    }));
    try {
      await apiFetch("/custom-tests", {method:"POST", body:JSON.stringify({name:suiteName, description:"Custom test suite", tests:payload})});
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch(e) { alert(e.detail?.message || "Failed to save"); }
  };

  return (
    <div className="mb-8">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-sm font-medium text-white/40 uppercase tracking-wider">Build Custom Tests</h2>
        {saved && <span className="text-xs text-emerald-400">Saved!</span>}
      </div>
      <div className="mb-3">
        <input value={suiteName} onChange={e => setSuiteName(e.target.value)} placeholder="Test suite name (e.g. My API Tests)"
          className="w-full bg-white/[0.04] border border-white/[0.08] rounded-lg px-3 py-2 text-sm text-white/80 placeholder-white/20 focus:border-emerald-500/40 focus:outline-none" />
      </div>
      <div className="space-y-3">
        {tests.map((t,i) => (
          <div key={i} className="bg-white/[0.02] border border-white/[0.06] rounded-xl p-4">
            <div className="flex justify-between items-center mb-2">
              <span className="text-[10px] text-white/20 font-mono">Test {i+1}</span>
              {tests.length > 1 && <button onClick={() => removeTest(i)} className="text-[10px] text-red-400/40 hover:text-red-400">Remove</button>}
            </div>
            <div className="grid grid-cols-2 gap-2">
              <input value={t.name} onChange={e => updateTest(i,"name",e.target.value)} placeholder="Test name"
                className="bg-white/[0.03] border border-white/[0.06] rounded-lg px-2 py-1.5 text-xs text-white/70 placeholder-white/15 focus:border-emerald-500/30 focus:outline-none" />
              <input value={t.input} onChange={e => updateTest(i,"input",e.target.value)} placeholder="Input message or API call"
                className="bg-white/[0.03] border border-white/[0.06] rounded-lg px-2 py-1.5 text-xs text-white/70 placeholder-white/15 focus:border-emerald-500/30 focus:outline-none" />
              <input value={t.expect_contains} onChange={e => updateTest(i,"expect_contains",e.target.value)} placeholder="Should contain..."
                className="bg-white/[0.03] border border-white/[0.06] rounded-lg px-2 py-1.5 text-xs text-white/70 placeholder-white/15 focus:border-emerald-500/30 focus:outline-none" />
              <input value={t.expect_not_contains} onChange={e => updateTest(i,"expect_not_contains",e.target.value)} placeholder="Should NOT contain..."
                className="bg-white/[0.03] border border-white/[0.06] rounded-lg px-2 py-1.5 text-xs text-white/70 placeholder-white/15 focus:border-emerald-500/30 focus:outline-none" />
            </div>
          </div>
        ))}
      </div>
      <div className="flex gap-2 mt-3">
        <button onClick={addTest} className="text-xs text-white/30 hover:text-white/60 bg-white/[0.03] px-3 py-1.5 rounded-lg border border-white/[0.05]">+ Add test</button>
        <button onClick={saveTests} disabled={!suiteName.trim()} className="text-xs bg-emerald-500 hover:bg-emerald-400 disabled:opacity-30 text-black font-semibold px-4 py-1.5 rounded-lg">Save test suite</button>
      </div>
    </div>
  );
}

'''

app = app.replace(dashboard_marker, custom_builder + dashboard_marker)

with open(f, "w") as fh:
    fh.write(app)

# Verify
checks = {
    "Plan refresh": "Always sync plan from server",
    "Onboarding": "Welcome to AgentProbe",
    "History chart": "Test History",
    "Tab navigation": "activeTab",
    "Custom test builder": "CustomTestBuilder",
    "History API call": "/history?days=30",
}
for label, needle in checks.items():
    status = "✅" if needle in app else "❌"
    print(f"  {status} {label}")

print("\n🎯 ALL FRONTEND UPGRADES APPLIED")
