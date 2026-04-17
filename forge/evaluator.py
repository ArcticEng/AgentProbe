"""
Forge's core evaluation engine.

Two evaluators, both call Claude via the Anthropic SDK:

  1. evaluate_trigger(skill, prompt, model) -> {triggered: bool, ...}
     Declares the skill as a tool and checks whether Claude invokes it.
     Works today against any Claude API key — no Skills beta access needed.

  2. evaluate_output(skill, prompt, model, rubric) -> {score: float, scores: {...}, ...}
     Injects the skill's instructions into the system prompt, runs Claude,
     then uses Claude-as-judge with the provided rubric to score the output.

And the killer feature:

  3. regression_matrix(skill_version, suite, models) -> diff
     Runs the same suite across N models, returns a structured diff showing
     which prompts changed behavior between models.

Design notes:
  - All Claude calls are wrapped in try/except, surfaced as per-prompt errors.
  - Concurrency is bounded via a thread pool — SQLite writes are fine, but
    the Anthropic API has rate limits we don't want to trip.
  - Token usage is tracked for every call.
  - Judge model defaults to Opus 4.7 for quality; we can make it cheaper later.
"""

import os
import time
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional


# Default regression matrix: the four current public Claude models.
DEFAULT_MODELS = [
    "claude-opus-4-7",
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "claude-haiku-4-5-20251001",
]

DEFAULT_JUDGE_MODEL = "claude-opus-4-7"


# ============================================================
# LOW-LEVEL CLAUDE CALLS
# ============================================================

def _get_client(api_key: str):
    from anthropic import Anthropic
    return Anthropic(api_key=api_key)


def _extract_text(content_blocks) -> str:
    return "".join(
        getattr(b, "text", "") for b in content_blocks if getattr(b, "type", None) == "text"
    )


def _tool_called(content_blocks, tool_name: str) -> bool:
    """Return True if Claude's response includes a tool_use block for tool_name."""
    for b in content_blocks:
        if getattr(b, "type", None) == "tool_use" and getattr(b, "name", "") == tool_name:
            return True
    return False


def _strip_fences(text: str) -> str:
    m = re.match(r"^```(?:json)?\s*\n(.*?)\n```\s*$", text.strip(), re.DOTALL)
    return m.group(1).strip() if m else text.strip()


def _skill_tool_name(skill_name: str) -> str:
    """Normalize a skill name to a valid tool name."""
    n = re.sub(r"[^a-zA-Z0-9_]+", "_", (skill_name or "skill")).strip("_").lower()
    return n[:60] or "skill"


# ============================================================
# EVALUATOR 1 — TRIGGER ACCURACY
# ============================================================

TRIGGER_SYSTEM = (
    "You are Claude. The user may ask for help that matches one of the tools available to you, "
    "or may ask for something unrelated. Use a tool ONLY when the user's request clearly falls "
    "within that tool's described purpose. Otherwise respond normally without calling any tool."
)


def evaluate_trigger(
    skill_name: str,
    skill_description: str,
    prompt: str,
    expected_trigger: bool,
    model: str,
    api_key: str,
    timeout_s: int = 30,
) -> dict:
    """
    Single-prompt trigger evaluation.
    Returns: {triggered, correct, expected, response_text, latency_ms, tokens, error}
    """
    client = _get_client(api_key)
    tool_name = _skill_tool_name(skill_name)
    t0 = time.time()
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=512,
            system=TRIGGER_SYSTEM,
            tools=[{
                "name": tool_name,
                "description": skill_description or "A Claude skill.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "request": {"type": "string", "description": "The user's request to handle."},
                    },
                    "required": ["request"],
                },
            }],
            messages=[{"role": "user", "content": prompt}],
            timeout=timeout_s,
        )
    except Exception as e:
        return {
            "triggered": None,
            "correct": False,
            "expected": expected_trigger,
            "response_text": "",
            "latency_ms": int((time.time() - t0) * 1000),
            "tokens": {"input": 0, "output": 0},
            "error": f"{type(e).__name__}: {str(e)[:200]}",
        }

    latency_ms = int((time.time() - t0) * 1000)
    triggered = _tool_called(resp.content, tool_name)
    return {
        "triggered": triggered,
        "correct": triggered == expected_trigger,
        "expected": expected_trigger,
        "response_text": _extract_text(resp.content)[:800],
        "latency_ms": latency_ms,
        "tokens": {
            "input": getattr(resp.usage, "input_tokens", 0),
            "output": getattr(resp.usage, "output_tokens", 0),
        },
        "error": None,
    }


# ============================================================
# EVALUATOR 2 — OUTPUT QUALITY (LLM-as-judge)
# ============================================================

def _build_skill_system(skill_md: str) -> str:
    """
    Inject SKILL.md contents as the system prompt. This is the 'skill is active'
    simulation for the API — the closest analog to how Skills are invoked
    in claude.ai once triggered.
    """
    return (
        "You are Claude, operating with the following skill loaded. Follow its "
        "instructions precisely when responding to the user.\n\n"
        "=== SKILL ===\n"
        f"{skill_md}\n"
        "=== END SKILL ==="
    )


def _run_skill(prompt: str, skill_md: str, model: str, api_key: str,
               timeout_s: int = 60) -> dict:
    client = _get_client(api_key)
    t0 = time.time()
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=2000,
            system=_build_skill_system(skill_md),
            messages=[{"role": "user", "content": prompt}],
            timeout=timeout_s,
        )
    except Exception as e:
        return {
            "output": "",
            "latency_ms": int((time.time() - t0) * 1000),
            "tokens": {"input": 0, "output": 0},
            "error": f"{type(e).__name__}: {str(e)[:200]}",
        }
    return {
        "output": _extract_text(resp.content),
        "latency_ms": int((time.time() - t0) * 1000),
        "tokens": {
            "input": getattr(resp.usage, "input_tokens", 0),
            "output": getattr(resp.usage, "output_tokens", 0),
        },
        "error": None,
    }


JUDGE_SYSTEM = """You are a rigorous evaluation judge for Claude Skills. You are given:
  - the skill's description and instructions
  - the user prompt
  - the model's output
  - a rubric with scoring criteria

Score each rubric criterion on an integer scale (default 1-5 unless told otherwise).
Be strict. A score of 5 means the output is exemplary; 3 is acceptable; 1 is a failure.
Explain each score in one terse sentence.

Return ONLY a JSON object, no preamble, no markdown fences:
{
  "scores": {"<criterion_key>": <int>, ...},
  "rationale": {"<criterion_key>": "<one sentence>", ...},
  "overall_pass": <bool>
}"""


def _judge_output(
    skill_md: str,
    prompt: str,
    output: str,
    rubric: dict,
    judge_model: str,
    api_key: str,
    timeout_s: int = 60,
) -> dict:
    client = _get_client(api_key)
    criteria = rubric.get("criteria", [])
    scale = rubric.get("scale", {"min": 1, "max": 5, "pass_threshold": 3.5})

    rubric_desc = "\n".join(
        f"- {c['key']} (weight {c.get('weight', 1.0)}): {c['description']}"
        for c in criteria
    )

    user_msg = (
        f"SKILL:\n{skill_md[:3000]}\n\n"
        f"USER PROMPT:\n{prompt}\n\n"
        f"MODEL OUTPUT:\n{output[:3000]}\n\n"
        f"RUBRIC (score {scale['min']}-{scale['max']}, pass threshold {scale['pass_threshold']}):\n"
        f"{rubric_desc}\n\n"
        "Return only the JSON."
    )

    try:
        resp = client.messages.create(
            model=judge_model,
            max_tokens=800,
            system=JUDGE_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
            timeout=timeout_s,
        )
    except Exception as e:
        return {
            "scores": {},
            "rationale": {},
            "weighted_score": 0.0,
            "pass": False,
            "tokens": {"input": 0, "output": 0},
            "error": f"{type(e).__name__}: {str(e)[:200]}",
        }

    text = _strip_fences(_extract_text(resp.content))
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {
            "scores": {},
            "rationale": {},
            "weighted_score": 0.0,
            "pass": False,
            "tokens": {
                "input": getattr(resp.usage, "input_tokens", 0),
                "output": getattr(resp.usage, "output_tokens", 0),
            },
            "error": f"judge returned non-JSON: {text[:200]}",
        }

    scores = parsed.get("scores", {})
    # Weighted aggregate
    total_weight = sum(c.get("weight", 1.0) for c in criteria) or 1.0
    weighted = sum(scores.get(c["key"], 0) * c.get("weight", 1.0) for c in criteria) / total_weight
    pass_threshold = scale.get("pass_threshold", 3.5)

    return {
        "scores": scores,
        "rationale": parsed.get("rationale", {}),
        "weighted_score": round(weighted, 3),
        "pass": weighted >= pass_threshold,
        "tokens": {
            "input": getattr(resp.usage, "input_tokens", 0),
            "output": getattr(resp.usage, "output_tokens", 0),
        },
        "error": None,
    }


def evaluate_output(
    skill_md: str,
    prompt: str,
    model: str,
    rubric: dict,
    api_key: str,
    judge_model: str = DEFAULT_JUDGE_MODEL,
) -> dict:
    """
    Run the skill on the prompt, then judge the output.
    Returns a combined result.
    """
    run = _run_skill(prompt, skill_md, model, api_key)
    if run["error"]:
        return {
            "output": "",
            "scores": {},
            "weighted_score": 0.0,
            "pass": False,
            "latency_ms": run["latency_ms"],
            "tokens": run["tokens"],
            "error": run["error"],
            "judge_error": None,
        }
    judged = _judge_output(skill_md, prompt, run["output"], rubric, judge_model, api_key)
    combined_tokens = {
        "input": run["tokens"]["input"] + judged["tokens"]["input"],
        "output": run["tokens"]["output"] + judged["tokens"]["output"],
    }
    return {
        "output": run["output"][:2000],
        "scores": judged["scores"],
        "rationale": judged["rationale"],
        "weighted_score": judged["weighted_score"],
        "pass": judged["pass"],
        "latency_ms": run["latency_ms"],
        "tokens": combined_tokens,
        "error": None,
        "judge_error": judged["error"],
    }


# ============================================================
# SUITE RUNNERS — parallel across prompts
# ============================================================

def run_trigger_suite(
    skill_name: str,
    skill_description: str,
    prompts: list,
    model: str,
    api_key: str,
    max_workers: int = 5,
) -> dict:
    """Run trigger eval for every prompt in the suite, in parallel."""
    results = []

    def _one(p):
        is_edge = p.get("class") == "edge"
        # Edges have no ground truth. We still run them to observe trigger behaviour,
        # but we mark `expected` as None and do not count them in precision/recall.
        hard_expected = None if is_edge else (p.get("class") == "positive")
        r = evaluate_trigger(
            skill_name, skill_description, p["prompt"],
            hard_expected if hard_expected is not None else True,  # API call still needs a bool
            model, api_key,
        )
        # IMPORTANT: spread `r` FIRST, then override — otherwise `r['expected']`
        # (which is always True for edges because of the fallback) clobbers our None.
        return {
            **r,
            "id": p.get("id"),
            "class": p.get("class"),
            "prompt": p["prompt"],
            "expected": hard_expected,
            "correct": None if is_edge else r.get("correct"),
        }

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_one, p): p for p in prompts}
        for fut in as_completed(futures):
            results.append(fut.result())

    # Summary — precision/recall over non-edge prompts
    scoring = [r for r in results if r["class"] in ("positive", "negative") and r.get("triggered") is not None]
    tp = sum(1 for r in scoring if r["class"] == "positive" and r["triggered"])
    fn = sum(1 for r in scoring if r["class"] == "positive" and not r["triggered"])
    fp = sum(1 for r in scoring if r["class"] == "negative" and r["triggered"])
    tn = sum(1 for r in scoring if r["class"] == "negative" and not r["triggered"])
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    accuracy = (tp + tn) / len(scoring) if scoring else 0.0

    edge_triggered = sum(1 for r in results if r["class"] == "edge" and r.get("triggered"))
    edge_total = sum(1 for r in results if r["class"] == "edge")

    errors = sum(1 for r in results if r.get("error"))
    total_tokens = sum(r.get("tokens", {}).get("input", 0) + r.get("tokens", {}).get("output", 0) for r in results)

    # Sort results deterministically by id for stable storage
    results.sort(key=lambda r: (r.get("class") or "", r.get("id") or ""))

    return {
        "summary": {
            "total": len(results),
            "errors": errors,
            "true_positive": tp, "false_positive": fp,
            "true_negative": tn, "false_negative": fn,
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
            "accuracy": round(accuracy, 3),
            "edge_triggered": edge_triggered,
            "edge_total": edge_total,
            "tokens_total": total_tokens,
        },
        "results": results,
    }


def run_quality_suite(
    skill_md: str,
    prompts: list,
    model: str,
    rubric: dict,
    api_key: str,
    judge_model: str = DEFAULT_JUDGE_MODEL,
    max_workers: int = 3,
) -> dict:
    """Run output-quality eval for every positive + edge prompt."""
    # Only run quality on prompts the skill is supposed to handle.
    targets = [p for p in prompts if p.get("class") in ("positive", "edge")]
    results = []

    def _one(p):
        r = evaluate_output(skill_md, p["prompt"], model, rubric, api_key, judge_model=judge_model)
        return {"id": p.get("id"), "class": p.get("class"), "prompt": p["prompt"], **r}

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_one, p): p for p in targets}
        for fut in as_completed(futures):
            results.append(fut.result())

    scored = [r for r in results if not r.get("error") and r.get("weighted_score") is not None]
    avg = sum(r["weighted_score"] for r in scored) / len(scored) if scored else 0.0
    passed = sum(1 for r in scored if r.get("pass"))
    errors = sum(1 for r in results if r.get("error"))
    total_tokens = sum(r.get("tokens", {}).get("input", 0) + r.get("tokens", {}).get("output", 0) for r in results)

    results.sort(key=lambda r: (r.get("class") or "", r.get("id") or ""))

    return {
        "summary": {
            "total": len(results),
            "scored": len(scored),
            "passed": passed,
            "errors": errors,
            "avg_score": round(avg, 3),
            "pass_rate": round(passed / len(scored), 3) if scored else 0.0,
            "tokens_total": total_tokens,
        },
        "results": results,
    }


# ============================================================
# REGRESSION MATRIX
# ============================================================

def diff_trigger_runs(runs_by_model: dict) -> dict:
    """
    Given {model: trigger_suite_result}, produce a diff.
      - per-prompt: which models triggered vs not, flagged when inconsistent
      - per-model: summary metrics, delta vs baseline (first model in dict)
    """
    models = list(runs_by_model.keys())
    if not models:
        return {"per_prompt": [], "per_model": {}, "prompts_with_disagreement": 0}

    # Index results by prompt id
    by_prompt = {}
    for model in models:
        for r in runs_by_model[model].get("results", []):
            pid = r.get("id") or r.get("prompt", "")[:40]
            by_prompt.setdefault(pid, {
                "id": pid,
                "class": r.get("class"),
                "prompt": r.get("prompt"),
                "expected": r.get("expected"),
                "by_model": {},
            })
            by_prompt[pid]["by_model"][model] = {
                "triggered": r.get("triggered"),
                "correct": r.get("correct"),
                "error": r.get("error"),
            }

    per_prompt = []
    disagreements = 0
    for pid, entry in by_prompt.items():
        triggers = {m: d.get("triggered") for m, d in entry["by_model"].items()}
        distinct = set(v for v in triggers.values() if v is not None)
        disagree = len(distinct) > 1
        if disagree:
            disagreements += 1
        per_prompt.append({**entry, "disagreement": disagree})

    per_model = {}
    baseline = models[0]
    baseline_summary = runs_by_model[baseline].get("summary", {})
    for m in models:
        s = runs_by_model[m].get("summary", {})
        per_model[m] = {
            **s,
            "delta_accuracy_vs_baseline": round(
                s.get("accuracy", 0) - baseline_summary.get("accuracy", 0), 3
            ) if m != baseline else 0.0,
            "delta_f1_vs_baseline": round(
                s.get("f1", 0) - baseline_summary.get("f1", 0), 3
            ) if m != baseline else 0.0,
        }

    per_prompt.sort(key=lambda r: (not r["disagreement"], r.get("class") or "", r.get("id") or ""))

    return {
        "per_prompt": per_prompt,
        "per_model": per_model,
        "prompts_with_disagreement": disagreements,
        "baseline_model": baseline,
    }


def diff_quality_runs(runs_by_model: dict) -> dict:
    """Same shape as diff_trigger_runs but for quality scores."""
    models = list(runs_by_model.keys())
    if not models:
        return {"per_prompt": [], "per_model": {}, "prompts_with_drift": 0}

    by_prompt = {}
    for model in models:
        for r in runs_by_model[model].get("results", []):
            pid = r.get("id") or r.get("prompt", "")[:40]
            by_prompt.setdefault(pid, {
                "id": pid,
                "class": r.get("class"),
                "prompt": r.get("prompt"),
                "by_model": {},
            })
            by_prompt[pid]["by_model"][model] = {
                "weighted_score": r.get("weighted_score"),
                "pass": r.get("pass"),
                "error": r.get("error"),
            }

    per_prompt = []
    drift_threshold = 0.5  # one full score point weighted
    drifts = 0
    for pid, entry in by_prompt.items():
        scores = [d.get("weighted_score") for d in entry["by_model"].values()
                  if d.get("weighted_score") is not None]
        spread = max(scores) - min(scores) if scores else 0
        drift = spread >= drift_threshold
        if drift:
            drifts += 1
        per_prompt.append({**entry, "score_spread": round(spread, 3), "drift": drift})

    per_model = {}
    baseline = models[0]
    baseline_summary = runs_by_model[baseline].get("summary", {})
    for m in models:
        s = runs_by_model[m].get("summary", {})
        per_model[m] = {
            **s,
            "delta_avg_score_vs_baseline": round(
                s.get("avg_score", 0) - baseline_summary.get("avg_score", 0), 3
            ) if m != baseline else 0.0,
            "delta_pass_rate_vs_baseline": round(
                s.get("pass_rate", 0) - baseline_summary.get("pass_rate", 0), 3
            ) if m != baseline else 0.0,
        }

    per_prompt.sort(key=lambda r: (-r["score_spread"], r.get("id") or ""))

    return {
        "per_prompt": per_prompt,
        "per_model": per_model,
        "prompts_with_drift": drifts,
        "drift_threshold": drift_threshold,
        "baseline_model": baseline,
    }
