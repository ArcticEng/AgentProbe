// Forge — Claude Skills production layer, dashboard UI
// Single-file component tree, matches the existing AgentProbe dark theme.
// Touches nothing in App.jsx besides a nav tab and a conditional mount.

import { useState, useEffect, useCallback, useMemo } from "react";

const API = import.meta.env.VITE_API_URL
  ? `${import.meta.env.VITE_API_URL}/api`
  : "/api";

async function forgeFetch(path, opts = {}) {
  const key = localStorage.getItem("ap_key") || "";
  const res = await fetch(`${API}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(key ? { "X-API-Key": key } : {}),
      ...opts.headers,
    },
    ...opts,
  });
  let data = null;
  try { data = await res.json(); } catch { /* non-JSON */ }
  if (!res.ok) throw { status: res.status, ...(data || {}) };
  return data;
}

const MODELS = [
  { id: "claude-opus-4-7",            label: "Opus 4.7",   tone: "emerald" },
  { id: "claude-opus-4-6",            label: "Opus 4.6",   tone: "cyan"    },
  { id: "claude-sonnet-4-6",          label: "Sonnet 4.6", tone: "violet"  },
  { id: "claude-haiku-4-5-20251001",  label: "Haiku 4.5",  tone: "amber"   },
];

const MODEL_LABEL = Object.fromEntries(MODELS.map(m => [m.id, m.label]));

// -----------------------------------------------------------------------------
// UI primitives
// -----------------------------------------------------------------------------

function Spinner({ size = 14 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className="animate-spin text-current">
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" fill="none" opacity="0.2" />
      <path d="M12 2 A10 10 0 0 1 22 12" stroke="currentColor" strokeWidth="3" fill="none" strokeLinecap="round" />
    </svg>
  );
}

function Btn({ children, onClick, variant = "primary", size = "md", disabled, type = "button", className = "" }) {
  const base = "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-all disabled:opacity-40 disabled:cursor-not-allowed";
  const sizes = {
    sm: "text-xs px-3 py-1.5",
    md: "text-sm px-4 py-2",
    lg: "text-sm px-5 py-2.5",
  };
  const variants = {
    primary: "bg-emerald-500 hover:bg-emerald-400 text-black font-semibold",
    ghost:   "bg-white/[0.04] hover:bg-white/[0.07] text-white/80 border border-white/[0.08]",
    danger:  "bg-red-500/15 hover:bg-red-500/25 text-red-400 border border-red-500/20",
    quiet:   "text-white/50 hover:text-white/90 hover:bg-white/[0.03]",
  };
  return (
    <button type={type} onClick={onClick} disabled={disabled} className={`${base} ${sizes[size]} ${variants[variant]} ${className}`}>
      {children}
    </button>
  );
}

function Card({ children, className = "" }) {
  return <div className={`bg-white/[0.02] border border-white/[0.06] rounded-xl ${className}`}>{children}</div>;
}

function Badge({ children, tone = "neutral" }) {
  const tones = {
    neutral:  "bg-white/[0.05] text-white/60 border-white/[0.08]",
    emerald:  "bg-emerald-500/15 text-emerald-400 border-emerald-500/20",
    cyan:     "bg-cyan-500/15 text-cyan-400 border-cyan-500/20",
    violet:   "bg-violet-500/15 text-violet-400 border-violet-500/20",
    amber:    "bg-amber-500/15 text-amber-400 border-amber-500/20",
    red:      "bg-red-500/15 text-red-400 border-red-500/20",
  };
  return <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium border ${tones[tone]}`}>{children}</span>;
}

function Empty({ title, description, cta }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="w-12 h-12 rounded-xl bg-white/[0.03] border border-white/[0.06] flex items-center justify-center mb-4 text-lg">✦</div>
      <div className="text-white/80 font-medium mb-1">{title}</div>
      <div className="text-xs text-white/40 mb-5 max-w-sm">{description}</div>
      {cta}
    </div>
  );
}

function Toast({ kind, message, onDismiss }) {
  if (!message) return null;
  const tones = {
    error:   "bg-red-500/10 border-red-500/30 text-red-400",
    success: "bg-emerald-500/10 border-emerald-500/30 text-emerald-400",
    info:    "bg-cyan-500/10 border-cyan-500/30 text-cyan-400",
  };
  return (
    <div className={`fixed bottom-6 right-6 z-50 max-w-sm rounded-lg border px-4 py-3 text-xs backdrop-blur ${tones[kind]}`}>
      <div className="flex items-start gap-3">
        <div className="flex-1">{message}</div>
        <button onClick={onDismiss} className="text-white/40 hover:text-white/80">×</button>
      </div>
    </div>
  );
}

// -----------------------------------------------------------------------------
// Modal: Create Skill
// -----------------------------------------------------------------------------

const SKILL_MD_PLACEHOLDER = `---
name: My Skill
description: What this skill does, in one sentence.
---

# My Skill

Describe when Claude should invoke this skill and what it should produce.
`;

function CreateSkillModal({ onClose, onCreated, setToast }) {
  const [skillMd, setSkillMd] = useState(SKILL_MD_PLACEHOLDER);
  const [slug, setSlug] = useState("");
  const [versionTag, setVersionTag] = useState("v1");
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    try {
      const body = { skill_md: skillMd, version_tag: versionTag };
      if (slug) body.slug = slug;
      const result = await forgeFetch("/skills", {
        method: "POST",
        body: JSON.stringify(body),
      });
      onCreated(result.skill);
      setToast({ kind: "success", message: `Imported "${result.skill.name}"` });
    } catch (e) {
      setToast({ kind: "error", message: e.detail || e.message || "Import failed" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-6">
      <div className="bg-[#0a0a0f] border border-white/[0.08] rounded-2xl w-full max-w-3xl max-h-[90vh] flex flex-col">
        <div className="px-6 py-4 border-b border-white/[0.06] flex items-center justify-between">
          <div>
            <div className="text-white/90 font-semibold text-sm">Import a Skill</div>
            <div className="text-xs text-white/40">Paste the contents of your SKILL.md below</div>
          </div>
          <button onClick={onClose} className="text-white/40 hover:text-white/80 text-xl leading-none">×</button>
        </div>
        <div className="p-6 flex-1 overflow-auto flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <div className="text-[11px] font-medium uppercase tracking-wider text-white/40 mb-1.5">Slug (optional)</div>
              <input
                value={slug}
                onChange={e => setSlug(e.target.value)}
                placeholder="auto from name"
                className="w-full bg-white/[0.03] border border-white/[0.08] rounded-lg px-3 py-2 text-sm text-white/90 placeholder:text-white/25 focus:outline-none focus:border-emerald-500/50"
              />
            </div>
            <div>
              <div className="text-[11px] font-medium uppercase tracking-wider text-white/40 mb-1.5">Version tag</div>
              <input
                value={versionTag}
                onChange={e => setVersionTag(e.target.value)}
                className="w-full bg-white/[0.03] border border-white/[0.08] rounded-lg px-3 py-2 text-sm text-white/90 focus:outline-none focus:border-emerald-500/50"
              />
            </div>
          </div>
          <div className="flex-1 flex flex-col">
            <div className="text-[11px] font-medium uppercase tracking-wider text-white/40 mb-1.5">SKILL.md contents</div>
            <textarea
              value={skillMd}
              onChange={e => setSkillMd(e.target.value)}
              spellCheck={false}
              className="flex-1 min-h-[320px] bg-white/[0.03] border border-white/[0.08] rounded-lg p-3 text-xs text-white/90 font-mono focus:outline-none focus:border-emerald-500/50 resize-none leading-relaxed"
            />
          </div>
        </div>
        <div className="px-6 py-4 border-t border-white/[0.06] flex items-center justify-end gap-2">
          <Btn variant="ghost" onClick={onClose}>Cancel</Btn>
          <Btn onClick={submit} disabled={busy || !skillMd.trim()}>
            {busy ? <><Spinner /> Importing…</> : "Import skill"}
          </Btn>
        </div>
      </div>
    </div>
  );
}

// -----------------------------------------------------------------------------
// Skills home: list + create CTA
// -----------------------------------------------------------------------------

function ForgeHome({ onOpen, onCreate, refreshKey }) {
  const [skills, setSkills] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    let cancelled = false;
    setSkills(null);
    forgeFetch("/skills")
      .then(d => { if (!cancelled) setSkills(d.skills || []); })
      .catch(e => { if (!cancelled) setErr(e.detail || e.message || "Failed to load skills"); });
    return () => { cancelled = true; };
  }, [refreshKey]);

  return (
    <div className="max-w-5xl mx-auto px-6 py-10">
      <div className="flex items-start justify-between mb-8">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <div className="w-8 h-8 bg-gradient-to-br from-amber-400 to-rose-500 rounded-lg flex items-center justify-center text-[10px] font-bold text-black">F</div>
            <div className="text-xl font-semibold text-white/90">Forge</div>
            <Badge tone="amber">beta</Badge>
          </div>
          <div className="text-sm text-white/50 max-w-xl">
            Import a Claude skill, auto-generate an eval suite, and run it across every Claude model to catch regressions before they ship.
          </div>
        </div>
        <Btn onClick={onCreate}>+ Import skill</Btn>
      </div>

      {err && <div className="text-xs text-red-400 mb-4">{err}</div>}

      {skills === null && (
        <div className="flex items-center gap-2 text-xs text-white/40 py-12 justify-center"><Spinner /> Loading skills…</div>
      )}

      {skills && skills.length === 0 && (
        <Card className="p-0">
          <Empty
            title="No skills yet"
            description="Paste a SKILL.md to import your first skill. Forge will version it, let you auto-generate an eval suite, and run it across every Claude model."
            cta={<Btn onClick={onCreate}>+ Import your first skill</Btn>}
          />
        </Card>
      )}

      {skills && skills.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {skills.map(s => (
            <button
              key={s.id}
              onClick={() => onOpen(s.id)}
              className="text-left bg-white/[0.02] border border-white/[0.06] rounded-xl p-5 hover:border-white/[0.15] hover:bg-white/[0.04] transition-all"
            >
              <div className="flex items-start justify-between mb-2">
                <div className="text-white/90 font-semibold truncate">{s.name}</div>
                <Badge tone="neutral">{s.visibility}</Badge>
              </div>
              <div className="text-xs text-white/40 mb-3">{s.slug}</div>
              <div className="text-xs text-white/50 line-clamp-2 min-h-[2.5em]">{s.description || "No description."}</div>
              <div className="mt-4 text-[11px] text-white/30 font-mono truncate">
                {s.latest_version_id ? `latest: ${s.latest_version_id}` : "no version yet"}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// -----------------------------------------------------------------------------
// Suite generation flow
// -----------------------------------------------------------------------------

function GenerateSuiteFlow({ skill, onSaved, setToast }) {
  const [pos, setPos] = useState(4);
  const [neg, setNeg] = useState(4);
  const [edge, setEdge] = useState(2);
  const [busy, setBusy] = useState(false);
  const [generated, setGenerated] = useState(null);
  const [name, setName] = useState("auto");

  async function generate() {
    setBusy(true);
    setGenerated(null);
    try {
      const d = await forgeFetch(`/skills/${skill.id}/generate-prompts`, {
        method: "POST",
        body: JSON.stringify({ positive_count: pos, negative_count: neg, edge_count: edge }),
      });
      setGenerated(d);
    } catch (e) {
      setToast({ kind: "error", message: e.detail || e.message || "Generation failed" });
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    if (!generated) return;
    setBusy(true);
    try {
      const suite = await forgeFetch(`/skills/${skill.id}/suites`, {
        method: "POST",
        body: JSON.stringify({ name, prompts: generated.prompts }),
      });
      setToast({ kind: "success", message: `Saved suite "${suite.name}"` });
      setGenerated(null);
      onSaved(suite);
    } catch (e) {
      setToast({ kind: "error", message: e.detail || e.message || "Save failed" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="p-5">
      <div className="text-white/90 font-medium text-sm mb-1">Auto-generate prompt suite</div>
      <div className="text-xs text-white/40 mb-4">
        Claude writes {pos + neg + edge} prompts for you — {pos} positive, {neg} negative, {edge} edge. ≈1 generator call, 10–20s.
      </div>

      <div className="grid grid-cols-3 gap-3 mb-4">
        {[
          ["Positive", pos, setPos, "emerald"],
          ["Negative", neg, setNeg, "red"],
          ["Edge",     edge, setEdge, "amber"],
        ].map(([label, val, set, tone]) => (
          <label key={label} className="block">
            <div className="text-[11px] font-medium uppercase tracking-wider text-white/40 mb-1.5">{label}</div>
            <input
              type="number" min={0} max={20} value={val}
              onChange={e => set(parseInt(e.target.value || "0"))}
              className={`w-full bg-white/[0.03] border border-white/[0.08] rounded-lg px-3 py-2 text-sm text-white/90 focus:outline-none focus:border-${tone}-500/50`}
            />
          </label>
        ))}
      </div>

      <Btn onClick={generate} disabled={busy || (pos + neg + edge) === 0} size="sm">
        {busy && !generated ? <><Spinner /> Generating…</> : "Generate prompts"}
      </Btn>

      {generated && (
        <div className="mt-5 pt-5 border-t border-white/[0.06]">
          <div className="flex items-center justify-between mb-3">
            <div className="text-xs text-white/60">
              {generated.prompts.length} prompts · {generated.token_usage?.input_tokens || 0}→{generated.token_usage?.output_tokens || 0} tokens
            </div>
            <div className="flex items-center gap-2">
              <input
                value={name}
                onChange={e => setName(e.target.value)}
                placeholder="suite name"
                className="bg-white/[0.03] border border-white/[0.08] rounded-lg px-3 py-1.5 text-xs text-white/90 focus:outline-none focus:border-emerald-500/50"
              />
              <Btn size="sm" onClick={save} disabled={busy || !name.trim()}>Save suite</Btn>
            </div>
          </div>
          <div className="space-y-2 max-h-96 overflow-auto pr-1">
            {generated.prompts.map(p => (
              <div key={p.id} className="bg-white/[0.02] border border-white/[0.06] rounded-lg p-3">
                <div className="flex items-center gap-2 mb-1.5">
                  <Badge tone={p.class === "positive" ? "emerald" : p.class === "negative" ? "red" : "amber"}>{p.class}</Badge>
                  <div className="text-[11px] font-mono text-white/30">{p.id}</div>
                </div>
                <div className="text-xs text-white/80 whitespace-pre-wrap">{p.prompt}</div>
                {p.rationale && <div className="text-[11px] text-white/40 mt-2 italic">{p.rationale}</div>}
              </div>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}

// -----------------------------------------------------------------------------
// Regression runner
// -----------------------------------------------------------------------------

function RegressionRunner({ skill, suites, onCompleted, setToast }) {
  const [suiteId, setSuiteId] = useState(suites[0]?.id || "");
  const [selectedModels, setSelectedModels] = useState(MODELS.map(m => m.id));
  const [runType, setRunType] = useState("trigger");
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState("");

  useEffect(() => {
    if (!suiteId && suites[0]) setSuiteId(suites[0].id);
  }, [suites]);

  const promptCount = suites.find(s => s.id === suiteId)?.prompt_count || 0;
  const callCount = promptCount * selectedModels.length * (runType === "both" ? 2 : 1);
  const eta = Math.max(15, Math.round(callCount * 2.5));

  async function run() {
    if (!suiteId) return;
    setBusy(true);
    setProgress(`Running ${callCount} Claude calls across ${selectedModels.length} model${selectedModels.length === 1 ? "" : "s"}…`);
    try {
      const d = await forgeFetch(`/skills/${skill.id}/regression`, {
        method: "POST",
        body: JSON.stringify({ suite_id: suiteId, models: selectedModels, run_type: runType }),
      });
      setToast({ kind: "success", message: `Matrix ${d.id} completed` });
      onCompleted(d);
    } catch (e) {
      setToast({ kind: "error", message: e.detail || e.message || "Matrix run failed" });
    } finally {
      setBusy(false);
      setProgress("");
    }
  }

  function toggleModel(id) {
    setSelectedModels(prev => prev.includes(id) ? prev.filter(m => m !== id) : [...prev, id]);
  }

  if (suites.length === 0) {
    return (
      <Card className="p-5">
        <div className="text-sm text-white/60">Create an evaluation suite first, then you can run a regression matrix.</div>
      </Card>
    );
  }

  return (
    <Card className="p-5">
      <div className="text-white/90 font-medium text-sm mb-1">Run regression matrix</div>
      <div className="text-xs text-white/40 mb-4">
        Evaluate the same suite across selected models, then diff the results to find cross-model behavioral differences.
      </div>

      <div className="grid grid-cols-2 gap-3 mb-4">
        <label>
          <div className="text-[11px] font-medium uppercase tracking-wider text-white/40 mb-1.5">Suite</div>
          <select
            value={suiteId}
            onChange={e => setSuiteId(e.target.value)}
            className="w-full bg-white/[0.03] border border-white/[0.08] rounded-lg px-3 py-2 text-sm text-white/90 focus:outline-none focus:border-emerald-500/50"
          >
            {suites.map(s => (
              <option key={s.id} value={s.id}>{s.name} ({s.prompt_count} prompts)</option>
            ))}
          </select>
        </label>
        <label>
          <div className="text-[11px] font-medium uppercase tracking-wider text-white/40 mb-1.5">Run type</div>
          <select
            value={runType}
            onChange={e => setRunType(e.target.value)}
            className="w-full bg-white/[0.03] border border-white/[0.08] rounded-lg px-3 py-2 text-sm text-white/90 focus:outline-none focus:border-emerald-500/50"
          >
            <option value="trigger">Trigger accuracy only (fast)</option>
            <option value="quality">Output quality only</option>
            <option value="both">Both (thorough)</option>
          </select>
        </label>
      </div>

      <div className="mb-4">
        <div className="text-[11px] font-medium uppercase tracking-wider text-white/40 mb-2">Models</div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          {MODELS.map(m => {
            const on = selectedModels.includes(m.id);
            return (
              <button
                key={m.id}
                onClick={() => toggleModel(m.id)}
                className={`px-3 py-2 rounded-lg border text-xs text-left transition-all ${on ? "bg-white/[0.05] border-white/[0.15] text-white/90" : "bg-white/[0.02] border-white/[0.06] text-white/40"}`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium">{m.label}</span>
                  <span className={`w-3 h-3 rounded-sm ${on ? `bg-${m.tone}-400` : "bg-white/10"}`} />
                </div>
                <div className="text-[10px] text-white/30 mt-0.5 font-mono truncate">{m.id}</div>
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex items-center justify-between">
        <div className="text-[11px] text-white/40">
          ≈{callCount} Claude calls · est {eta}s · runs in parallel
        </div>
        <Btn onClick={run} disabled={busy || !suiteId || selectedModels.length === 0}>
          {busy ? <><Spinner /> {progress || "Running…"}</> : "Run matrix"}
        </Btn>
      </div>
    </Card>
  );
}

// -----------------------------------------------------------------------------
// The hero: regression matrix heatmap
// -----------------------------------------------------------------------------

function MatrixCell({ data, row, runType, onClick }) {
  if (!data || data.error) {
    return <div className="w-full h-full flex items-center justify-center text-red-400/70 text-[11px]">err</div>;
  }
  if (runType === "quality") {
    const s = data.weighted_score;
    if (s == null) return <div className="text-white/20 text-[11px]">—</div>;
    const tone = s >= 4 ? "emerald" : s >= 3 ? "amber" : "red";
    return (
      <button onClick={onClick} className={`w-full h-full flex items-center justify-center font-mono text-[11px] text-${tone}-400 hover:bg-white/[0.04]`}>
        {s.toFixed(2)}
      </button>
    );
  }
  // trigger view
  const trig = data.triggered;
  // For edges we intentionally have no ground truth — always render a neutral marker,
  // regardless of what `expected` / `correct` say in legacy rows.
  const isEdge = row.class === "edge";
  let icon, cls;
  if (trig === null || trig === undefined) {
    icon = "?"; cls = "text-white/30";
  } else if (isEdge) {
    // Edge prompts — show behaviour, not correctness
    icon = trig ? "●" : "○";
    cls = trig ? "text-violet-400" : "text-white/40";
  } else if (data.correct) {
    icon = "✓"; cls = "text-emerald-400";
  } else {
    icon = "✗"; cls = "text-red-400";
  }
  return (
    <button onClick={onClick} className={`w-full h-full flex items-center justify-center text-lg font-semibold hover:bg-white/[0.04] ${cls}`}>
      {icon}
    </button>
  );
}

function classToTone(cls) {
  return cls === "positive" ? "emerald" : cls === "negative" ? "red" : "amber";
}

function AnalysisPanel({ matrixId, diff, setToast }) {
  const [analysis, setAnalysis] = useState(null);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(false);

  const hasFindings =
    (diff?.trigger?.prompts_with_disagreement ?? 0) > 0 ||
    (diff?.quality?.prompts_with_drift ?? 0) > 0;

  // Try to load cached analysis on mount
  useEffect(() => {
    let cancelled = false;
    forgeFetch(`/skills/regression/${matrixId}/analysis`)
      .then(a => { if (!cancelled) { setAnalysis(a); setExpanded(true); } })
      .catch(() => {}); // 404 is normal for un-analyzed matrices
    return () => { cancelled = true; };
  }, [matrixId]);

  async function run(force = false) {
    setLoading(true);
    try {
      const a = await forgeFetch(
        `/skills/regression/${matrixId}/analyze${force ? "?force=true" : ""}`,
        { method: "POST" }
      );
      setAnalysis(a);
      setExpanded(true);
    } catch (e) {
      setToast({ kind: "error", message: e.detail || e.message || "Analysis failed" });
    } finally {
      setLoading(false);
    }
  }

  const catTones = {
    description: "cyan",
    routing:     "violet",
    guardrail:   "amber",
    accept:      "emerald",
  };
  const catIcons = {
    description: "✏",
    routing:     "→",
    guardrail:   "□",
    accept:      "✓",
  };
  const prioTones = { high: "red", medium: "amber", low: "neutral" };

  if (!analysis) {
    return (
      <Card className="p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-white/90 font-medium text-sm mb-1">
              {hasFindings ? "You have findings. What should you do about them?" : "Everything looks clean. Want a second opinion?"}
            </div>
            <div className="text-xs text-white/40 max-w-md">
              Claude Opus reads the skill, the disagreements, and each model's response, then returns a structured analysis with specific recommendations.
            </div>
          </div>
          <Btn onClick={() => run(false)} disabled={loading}>
            {loading ? <><Spinner /> Analyzing…</> : "Analyze findings"}
          </Btn>
        </div>
      </Card>
    );
  }

  return (
    <Card className="p-5">
      <div className="flex items-start justify-between gap-4 mb-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <div className="text-white/90 font-semibold">Analysis</div>
            {analysis.cached && <Badge tone="neutral">cached</Badge>}
          </div>
          <div className="text-sm text-white/80 leading-relaxed">{analysis.summary}</div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Btn size="sm" variant="ghost" onClick={() => setExpanded(!expanded)}>
            {expanded ? "Collapse" : "Expand"}
          </Btn>
          <Btn size="sm" variant="ghost" onClick={() => run(true)} disabled={loading}>
            {loading ? <><Spinner /> …</> : "Re-analyze"}
          </Btn>
        </div>
      </div>

      {expanded && (
        <div className="space-y-4">
          {analysis.likely_cause && (
            <div>
              <div className="text-[11px] font-medium uppercase tracking-wider text-white/40 mb-1.5">Likely cause</div>
              <div className="text-xs text-white/70 leading-relaxed">{analysis.likely_cause}</div>
            </div>
          )}

          <div>
            <div className="text-[11px] font-medium uppercase tracking-wider text-white/40 mb-2">
              Recommendations ({analysis.recommendations?.length || 0})
            </div>
            <div className="space-y-2">
              {(analysis.recommendations || []).map((r, i) => {
                const tone = catTones[r.category] || "neutral";
                return (
                  <div key={i} className="bg-white/[0.02] border border-white/[0.06] rounded-lg p-3">
                    <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                      <Badge tone={tone}>{catIcons[r.category] || "•"} {r.category}</Badge>
                      <Badge tone={prioTones[r.priority] || "neutral"}>{r.priority} priority</Badge>
                      <div className="text-sm text-white/90 font-medium">{r.title}</div>
                    </div>
                    <div className="text-xs text-white/60 leading-relaxed">{r.detail}</div>
                  </div>
                );
              })}
            </div>
          </div>

          {analysis.token_usage?.input_tokens > 0 && (
            <div className="text-[11px] text-white/30 font-mono pt-2 border-t border-white/[0.04]">
              {analysis.token_usage.input_tokens.toLocaleString()}→{analysis.token_usage.output_tokens.toLocaleString()} tokens · Opus 4.7
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

function MatrixView({ matrix, setToast }) {
  const [phase, setPhase] = useState(matrix.diff?.trigger ? "trigger" : "quality");
  const [expandedId, setExpandedId] = useState(null);
  const [cellDetail, setCellDetail] = useState(null); // {rowId, model, data}

  const diff = matrix.diff?.[phase];
  if (!diff) return <div className="text-white/40 text-sm">No diff available for this matrix.</div>;

  // Order: disagreements first, then by class (pos, neg, edge), then by id.
  const rows = [...(diff.per_prompt || [])].sort((a, b) => {
    const aDis = (a.disagreement || a.drift) ? 0 : 1;
    const bDis = (b.disagreement || b.drift) ? 0 : 1;
    if (aDis !== bDis) return aDis - bDis;
    const order = { positive: 0, negative: 1, edge: 2 };
    const ca = order[a.class] ?? 3, cb = order[b.class] ?? 3;
    if (ca !== cb) return ca - cb;
    return (a.id || "").localeCompare(b.id || "");
  });

  const models = matrix.models || Object.keys(diff.per_model || {});

  const stats = phase === "trigger"
    ? {
        label: "disagreements",
        value: diff.prompts_with_disagreement ?? 0,
        total: rows.length,
      }
    : {
        label: "prompts with drift",
        value: diff.prompts_with_drift ?? 0,
        total: rows.length,
      };

  return (
    <div className="space-y-4">
      <Card className="p-5">
        <div className="flex items-start justify-between gap-4 mb-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <div className="text-white/90 font-semibold">Regression matrix</div>
              <div className="text-[11px] font-mono text-white/30">{matrix.id}</div>
            </div>
            <div className="text-xs text-white/40">
              {models.length} models · {rows.length} prompts · baseline: {MODEL_LABEL[diff.baseline_model] || diff.baseline_model}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {(matrix.diff?.trigger && matrix.diff?.quality) ? (
              <>
                <button onClick={() => setPhase("trigger")}
                  className={`text-xs px-3 py-1.5 rounded-lg border transition-all ${phase === "trigger" ? "bg-white/[0.06] border-white/[0.15] text-white/90" : "bg-white/[0.02] border-white/[0.06] text-white/40"}`}>
                  Trigger
                </button>
                <button onClick={() => setPhase("quality")}
                  className={`text-xs px-3 py-1.5 rounded-lg border transition-all ${phase === "quality" ? "bg-white/[0.06] border-white/[0.15] text-white/90" : "bg-white/[0.02] border-white/[0.06] text-white/40"}`}>
                  Quality
                </button>
              </>
            ) : (
              <Badge tone="neutral">{phase === "trigger" ? "Trigger accuracy" : "Output quality"}</Badge>
            )}
          </div>
        </div>

        <div className="grid grid-cols-3 gap-3 mb-5">
          <div className="bg-white/[0.02] border border-white/[0.06] rounded-lg p-3">
            <div className="text-[11px] uppercase tracking-wider text-white/40">{stats.label}</div>
            <div className={`text-2xl font-semibold ${stats.value > 0 ? "text-amber-400" : "text-emerald-400"}`}>
              {stats.value}<span className="text-white/30 text-sm font-normal"> / {stats.total}</span>
            </div>
          </div>
          {Object.entries(diff.per_model).slice(0, 2).map(([m, s]) => (
            <div key={m} className="bg-white/[0.02] border border-white/[0.06] rounded-lg p-3">
              <div className="text-[11px] uppercase tracking-wider text-white/40 truncate">{MODEL_LABEL[m] || m}</div>
              <div className="text-2xl font-semibold text-white/90">
                {phase === "trigger" ? s.f1?.toFixed(2) : s.avg_score?.toFixed(2)}
                <span className="text-xs font-normal text-white/40 ml-1">{phase === "trigger" ? "F1" : "avg"}</span>
              </div>
            </div>
          ))}
        </div>

        {/* Heatmap */}
        <div className="border border-white/[0.06] rounded-lg overflow-hidden">
          <div className="grid" style={{ gridTemplateColumns: `minmax(240px, 2fr) repeat(${models.length}, 1fr)` }}>
            {/* Header */}
            <div className="bg-white/[0.03] px-3 py-2 text-[11px] font-medium uppercase tracking-wider text-white/40 border-b border-white/[0.06]">Prompt</div>
            {models.map(m => {
              const tone = MODELS.find(x => x.id === m)?.tone || "neutral";
              return (
                <div key={m} className="bg-white/[0.03] px-3 py-2 text-[11px] font-medium text-center border-b border-l border-white/[0.06]">
                  <div className={`text-${tone}-400`}>{MODEL_LABEL[m] || m}</div>
                  {diff.per_model[m] && (
                    <div className="text-white/30 font-mono mt-0.5">
                      {phase === "trigger"
                        ? `acc ${(diff.per_model[m].accuracy ?? 0).toFixed(2)}`
                        : `avg ${(diff.per_model[m].avg_score ?? 0).toFixed(2)}`}
                    </div>
                  )}
                </div>
              );
            })}

            {/* Rows */}
            {rows.map(row => {
              const flagged = row.disagreement || row.drift;
              const isExpanded = expandedId === row.id;
              return (
                <div key={row.id} className="contents">
                  <button
                    onClick={() => setExpandedId(isExpanded ? null : row.id)}
                    className={`text-left px-3 py-2 border-t border-white/[0.06] hover:bg-white/[0.03] transition-colors ${flagged ? "border-l-2 border-l-amber-500" : ""}`}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <Badge tone={classToTone(row.class)}>{row.class}</Badge>
                      {flagged && <Badge tone="amber">⚠ {row.disagreement ? "disagreement" : "drift"}</Badge>}
                      <span className="text-[11px] font-mono text-white/30">{row.id}</span>
                    </div>
                    <div className={`text-xs text-white/70 ${isExpanded ? "whitespace-pre-wrap" : "truncate"}`}>
                      {row.prompt}
                    </div>
                  </button>
                  {models.map(m => {
                    const data = row.by_model?.[m];
                    return (
                      <div key={m} className="border-t border-l border-white/[0.06] min-h-[44px]">
                        <MatrixCell
                          data={data}
                          row={row}
                          runType={phase}
                          onClick={() => setCellDetail({ rowId: row.id, model: m, prompt: row.prompt, cls: row.class, data })}
                        />
                      </div>
                    );
                  })}
                </div>
              );
            })}
          </div>
        </div>

        <div className="mt-3 text-[11px] text-white/30 flex items-center gap-4">
          <span className="flex items-center gap-1"><span className="text-emerald-400">✓</span> correct</span>
          <span className="flex items-center gap-1"><span className="text-red-400">✗</span> incorrect</span>
          <span className="flex items-center gap-1"><span className="text-violet-400">●</span> edge triggered</span>
          <span className="flex items-center gap-1"><span className="text-white/30">○</span> edge declined</span>
          <span className="ml-auto">Click a row to expand · click a cell to see Claude's response</span>
        </div>
      </Card>

      {cellDetail && <CellDetailModal detail={cellDetail} onClose={() => setCellDetail(null)} />}

      <AnalysisPanel matrixId={matrix.id} diff={matrix.diff} setToast={setToast} />
    </div>
  );
}

function CellDetailModal({ detail, onClose }) {
  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-6" onClick={onClose}>
      <div onClick={e => e.stopPropagation()} className="bg-[#0a0a0f] border border-white/[0.08] rounded-2xl w-full max-w-2xl max-h-[85vh] flex flex-col">
        <div className="px-6 py-4 border-b border-white/[0.06] flex items-center justify-between">
          <div>
            <div className="text-white/90 font-semibold text-sm flex items-center gap-2">
              <Badge tone={classToTone(detail.cls)}>{detail.cls}</Badge>
              {MODEL_LABEL[detail.model] || detail.model}
              <span className="text-[11px] font-mono text-white/30">{detail.rowId}</span>
            </div>
          </div>
          <button onClick={onClose} className="text-white/40 hover:text-white/80 text-xl">×</button>
        </div>
        <div className="p-6 overflow-auto space-y-4">
          <div>
            <div className="text-[11px] font-medium uppercase tracking-wider text-white/40 mb-1.5">Prompt</div>
            <div className="bg-white/[0.02] border border-white/[0.06] rounded-lg p-3 text-xs text-white/80 whitespace-pre-wrap">{detail.prompt}</div>
          </div>
          {detail.data?.triggered !== undefined && (
            <div>
              <div className="text-[11px] font-medium uppercase tracking-wider text-white/40 mb-1.5">Triggered</div>
              <div className={detail.data.triggered ? "text-violet-400" : "text-white/60"}>
                {detail.data.triggered ? "Yes — Claude invoked the skill as a tool" : "No — Claude declined to invoke the skill"}
              </div>
            </div>
          )}
          {detail.data?.weighted_score !== undefined && (
            <div>
              <div className="text-[11px] font-medium uppercase tracking-wider text-white/40 mb-1.5">Quality score</div>
              <div className="text-white/80 font-mono">{detail.data.weighted_score?.toFixed(3)}</div>
            </div>
          )}
          {detail.data?.error && (
            <div>
              <div className="text-[11px] font-medium uppercase tracking-wider text-red-400/70 mb-1.5">Error</div>
              <div className="bg-red-500/5 border border-red-500/20 rounded-lg p-3 text-xs text-red-300 font-mono">{detail.data.error}</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// -----------------------------------------------------------------------------
// Skill detail: tabs, runs, matrices
// -----------------------------------------------------------------------------

function SkillDetail({ skillId, onBack, setToast }) {
  const [detail, setDetail] = useState(null);
  const [err, setErr] = useState("");
  const [tab, setTab] = useState("overview");
  const [matrix, setMatrix] = useState(null);
  const [matrixList, setMatrixList] = useState([]);
  const [refreshKey, setRefreshKey] = useState(0);

  const loadDetail = useCallback(async () => {
    setErr("");
    try {
      const d = await forgeFetch(`/skills/${skillId}`);
      setDetail(d);
      // Load matrix list
      const ms = await forgeFetch(`/skills/${skillId}/regression`);
      setMatrixList(ms.matrices || []);
    } catch (e) {
      setErr(e.detail || e.message || "Failed to load");
    }
  }, [skillId]);

  useEffect(() => { loadDetail(); }, [loadDetail, refreshKey]);

  async function deleteSkill() {
    if (!confirm(`Delete skill "${detail.skill.name}"? This is permanent.`)) return;
    try {
      await forgeFetch(`/skills/${skillId}`, { method: "DELETE" });
      setToast({ kind: "success", message: "Skill deleted" });
      onBack();
    } catch (e) {
      setToast({ kind: "error", message: e.detail || e.message || "Delete failed" });
    }
  }

  async function openMatrix(id) {
    try {
      const m = await forgeFetch(`/skills/regression/${id}`);
      setMatrix(m);
      setTab("matrix");
    } catch (e) {
      setToast({ kind: "error", message: e.detail || e.message || "Failed to load matrix" });
    }
  }

  if (err) return <div className="max-w-5xl mx-auto px-6 py-10 text-red-400 text-sm">{err}</div>;
  if (!detail) return <div className="max-w-5xl mx-auto px-6 py-10 text-white/40 text-sm flex items-center gap-2"><Spinner /> Loading…</div>;

  const { skill, versions, suites, recent_runs } = detail;

  return (
    <div className="max-w-6xl mx-auto px-6 py-8">
      <button onClick={onBack} className="text-xs text-white/40 hover:text-white/80 mb-4">← All skills</button>

      <div className="flex items-start justify-between gap-4 mb-6">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <div className="text-2xl font-semibold text-white/90">{skill.name}</div>
            <Badge tone="neutral">{skill.slug}</Badge>
            <Badge tone="amber">{skill.visibility}</Badge>
          </div>
          <div className="text-sm text-white/50 max-w-2xl">{skill.description || "No description."}</div>
          <div className="text-[11px] font-mono text-white/30 mt-2">
            {versions.length} version{versions.length !== 1 ? "s" : ""} · latest {skill.latest_version_id}
          </div>
        </div>
        <Btn variant="danger" size="sm" onClick={deleteSkill}>Delete</Btn>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 border-b border-white/[0.06] mb-6">
        {[
          ["overview",   "Overview"],
          ["suites",     `Suites (${suites.length})`],
          ["runs",       "Run regression"],
          ["matrices",   `Matrices (${matrixList.length})`],
          matrix && ["matrix", "Current matrix"],
        ].filter(Boolean).map(([id, label]) => (
          <button key={id}
            onClick={() => setTab(id)}
            className={`px-4 py-2.5 text-sm border-b-2 transition-all ${tab === id ? "border-emerald-500 text-white/90" : "border-transparent text-white/40 hover:text-white/70"}`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "overview" && (
        <div className="space-y-4">
          <Card className="p-5">
            <div className="text-[11px] uppercase tracking-wider text-white/40 mb-2">SKILL.md</div>
            <pre className="text-xs text-white/80 whitespace-pre-wrap font-mono bg-black/30 border border-white/[0.05] rounded-lg p-4 max-h-96 overflow-auto">
{versions[0] ? "(load version to view)" : "No versions yet."}
            </pre>
          </Card>

          <Card className="p-5">
            <div className="flex items-center justify-between mb-3">
              <div className="text-white/90 font-medium text-sm">Recent runs</div>
              {recent_runs.length > 0 && <div className="text-[11px] text-white/40">{recent_runs.length} in this skill</div>}
            </div>
            {recent_runs.length === 0 ? (
              <div className="text-xs text-white/40">No runs yet. Create a suite and run a regression matrix to populate this.</div>
            ) : (
              <div className="space-y-2">
                {recent_runs.slice(0, 6).map(r => (
                  <div key={r.id} className="flex items-center gap-3 px-3 py-2 bg-white/[0.02] rounded-lg">
                    <Badge tone={r.status === "completed" ? "emerald" : r.status === "failed" ? "red" : "neutral"}>{r.status}</Badge>
                    <span className="text-xs text-white/80">{MODEL_LABEL[r.model] || r.model}</span>
                    <span className="text-[11px] text-white/40">{r.run_type}</span>
                    {r.summary?.trigger?.f1 !== undefined && (
                      <span className="text-[11px] font-mono text-white/60">F1 {r.summary.trigger.f1.toFixed(2)}</span>
                    )}
                    {r.summary?.quality?.avg_score !== undefined && (
                      <span className="text-[11px] font-mono text-white/60">avg {r.summary.quality.avg_score.toFixed(2)}</span>
                    )}
                    <span className="text-[11px] text-white/30 ml-auto font-mono">{r.id}</span>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      )}

      {tab === "suites" && (
        <div className="space-y-4">
          <GenerateSuiteFlow skill={skill} setToast={setToast} onSaved={() => setRefreshKey(k => k + 1)} />

          <Card className="p-5">
            <div className="text-white/90 font-medium text-sm mb-3">Existing suites</div>
            {suites.length === 0 ? (
              <div className="text-xs text-white/40">No suites yet. Generate one above, or POST to /api/skills/:id/suites.</div>
            ) : (
              <div className="space-y-2">
                {suites.map(s => (
                  <div key={s.id} className="flex items-center gap-3 px-3 py-2 bg-white/[0.02] rounded-lg">
                    <span className="text-white/80 text-sm">{s.name}</span>
                    <span className="text-[11px] text-white/40">{s.prompt_count} prompts</span>
                    <span className="text-[11px] text-white/30 ml-auto font-mono">{s.id}</span>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      )}

      {tab === "runs" && (
        <RegressionRunner
          skill={skill}
          suites={suites}
          setToast={setToast}
          onCompleted={(m) => { setMatrix(m); setTab("matrix"); setRefreshKey(k => k + 1); }}
        />
      )}

      {tab === "matrices" && (
        <Card className="p-5">
          <div className="text-white/90 font-medium text-sm mb-3">Past regression runs</div>
          {matrixList.length === 0 ? (
            <div className="text-xs text-white/40">No matrices yet.</div>
          ) : (
            <div className="space-y-2">
              {matrixList.map(m => (
                <button key={m.id} onClick={() => openMatrix(m.id)}
                  className="w-full flex items-center gap-3 px-3 py-2 bg-white/[0.02] hover:bg-white/[0.05] rounded-lg text-left transition-colors">
                  <span className="text-[11px] font-mono text-white/40">{m.id}</span>
                  <span className="text-xs text-white/70">{m.models.length} models</span>
                  <span className="text-[11px] text-white/40 ml-auto">{m.created_at}</span>
                </button>
              ))}
            </div>
          )}
        </Card>
      )}

      {tab === "matrix" && matrix && (
        <MatrixView matrix={matrix} setToast={setToast} />
      )}
    </div>
  );
}

// -----------------------------------------------------------------------------
// Public entry
// -----------------------------------------------------------------------------

export default function ForgeView() {
  const [screen, setScreen] = useState("home");
  const [showCreate, setShowCreate] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [toast, setToast] = useState(null);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 4500);
    return () => clearTimeout(t);
  }, [toast]);

  return (
    <div className="min-h-[calc(100vh-56px)]">
      {screen === "home"
        ? <ForgeHome onOpen={setScreen} onCreate={() => setShowCreate(true)} refreshKey={refreshKey} />
        : <SkillDetail skillId={screen} onBack={() => setScreen("home")} setToast={setToast} />
      }
      {showCreate && (
        <CreateSkillModal
          onClose={() => setShowCreate(false)}
          setToast={setToast}
          onCreated={(skill) => {
            setShowCreate(false);
            setRefreshKey(k => k + 1);
            setScreen(skill.id);
          }}
        />
      )}
      <Toast kind={toast?.kind} message={toast?.message} onDismiss={() => setToast(null)} />
    </div>
  );
}
