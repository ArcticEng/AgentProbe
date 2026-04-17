"""
Finding analyzer — Claude generates a prescriptive analysis of cross-model disagreements.

Takes a completed regression matrix diff, extracts disagreements/drift, and asks Claude
Opus to explain WHY the models differ and WHAT to do about it. Returns structured
recommendations keyed to four categories:

  - description: tighten the SKILL.md wording
  - routing:     pin a specific model in production
  - guardrail:   add an app-layer pre-filter or post-check
  - accept:      the difference is acceptable, no action needed

Output is strict JSON so the UI can render it as a clean panel.
"""

import json
import re


ANALYZER_SYSTEM = """You are a senior evaluation engineer analyzing cross-model behavioral drift in Claude Skills.

You are given:
  - A skill (name, description, full instructions)
  - A set of prompts where different Claude models made different decisions
  - Each model's trigger decision or quality score
  - Summary statistics per model

Your job: explain WHY the models likely differ and WHAT the skill author should do about it.

Be specific. Reference exact phrases from the skill's description or instructions where relevant. Don't hand-wave. If the finding genuinely doesn't matter, say so plainly.

Rules:
  - Keep the summary to 2-3 sentences, no filler
  - Provide 2-4 concrete recommendations, most-actionable first
  - Each recommendation has a category:
    * "description" — edit SKILL.md to tighten or clarify trigger conditions
    * "routing"     — pin a specific model in production for this skill
    * "guardrail"   — add an app-layer pre-filter or post-check
    * "accept"      — difference is acceptable, no action needed
  - Each recommendation has a priority: "high", "medium", or "low"

Return ONLY a JSON object, no preamble, no markdown fences:
{
  "summary": "2-3 sentence TLDR of what's happening and what it means",
  "likely_cause": "one paragraph on why the models probably differ",
  "recommendations": [
    {
      "category": "description|routing|guardrail|accept",
      "priority": "high|medium|low",
      "title": "short action label (<60 chars)",
      "detail": "2-4 sentence explanation of the action and why it helps"
    }
  ]
}"""


def _strip_fences(text: str) -> str:
    m = re.match(r"^```(?:json)?\s*\n(.*?)\n```\s*$", text.strip(), re.DOTALL)
    return m.group(1).strip() if m else text.strip()


def analyze_matrix(
    skill_name: str,
    skill_description: str,
    skill_md: str,
    diff: dict,
    api_key: str,
    model: str = "claude-opus-4-7",
) -> dict:
    """
    Given a matrix diff, produce structured recommendations.

    If there are no disagreements or drifts, returns a canned "ship with confidence"
    result without calling Claude — saves money when everything's green.
    """
    try:
        from anthropic import Anthropic
    except ImportError as e:
        raise RuntimeError("anthropic SDK not installed") from e

    # Extract disagreement / drift rows
    trigger_disagreements = []
    quality_drifts = []

    if diff.get("trigger"):
        for p in diff["trigger"].get("per_prompt", []):
            if p.get("disagreement"):
                trigger_disagreements.append({
                    "class": p.get("class"),
                    "prompt": (p.get("prompt") or "")[:500],
                    "by_model": {
                        m: {
                            "triggered": r.get("triggered"),
                            "response_preview": (r.get("response_text") or "")[:250]
                                if r.get("response_text") else None,
                        }
                        for m, r in p.get("by_model", {}).items()
                    },
                })

    if diff.get("quality"):
        for p in diff["quality"].get("per_prompt", []):
            if p.get("drift"):
                quality_drifts.append({
                    "class": p.get("class"),
                    "prompt": (p.get("prompt") or "")[:500],
                    "score_spread": p.get("score_spread"),
                    "by_model": {
                        m: {"weighted_score": r.get("weighted_score"), "pass": r.get("pass")}
                        for m, r in p.get("by_model", {}).items()
                    },
                })

    # Nothing to analyze — return a free, instant, canned result
    if not trigger_disagreements and not quality_drifts:
        return {
            "summary": "No disagreements or drift detected — all tested Claude models agreed across the eval suite.",
            "likely_cause": "The skill's description is unambiguous enough that every tested Claude model makes the same decision on every prompt. This is the desired state.",
            "recommendations": [{
                "category": "accept",
                "priority": "low",
                "title": "Ship with confidence on any tested model",
                "detail": "Cross-model behavior is consistent for this skill on the current eval suite. Consider expanding the suite with harder edge cases or adversarial prompts to probe further, but no action is required before production.",
            }],
            "token_usage": {"input_tokens": 0, "output_tokens": 0},
            "cached": False,
        }

    # Build analysis context
    per_model_summary = {}
    if diff.get("trigger", {}).get("per_model"):
        per_model_summary["trigger"] = diff["trigger"]["per_model"]
    if diff.get("quality", {}).get("per_model"):
        per_model_summary["quality"] = diff["quality"]["per_model"]

    parts = [
        f"SKILL NAME: {skill_name}",
        f"SKILL DESCRIPTION: {skill_description}",
        f"SKILL INSTRUCTIONS:\n---\n{skill_md[:3000]}\n---",
        f"PER-MODEL SUMMARY:\n{json.dumps(per_model_summary, indent=2)}",
    ]
    if trigger_disagreements:
        parts.append(
            f"TRIGGER DISAGREEMENTS ({len(trigger_disagreements)} prompts where models "
            f"differed on whether to invoke the skill):\n"
            f"{json.dumps(trigger_disagreements, indent=2)[:4000]}"
        )
    if quality_drifts:
        parts.append(
            f"QUALITY DRIFTS ({len(quality_drifts)} prompts where output scores varied by >0.5):\n"
            f"{json.dumps(quality_drifts, indent=2)[:4000]}"
        )
    parts.append("Analyze this finding. Return only the JSON object.")

    client = Anthropic(api_key=api_key)
    resp = client.messages.create(
        model=model,
        max_tokens=2000,
        system=ANALYZER_SYSTEM,
        messages=[{"role": "user", "content": "\n\n".join(parts)}],
    )

    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
    text = _strip_fences(text)

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Analyzer returned non-JSON: {text[:300]}") from e

    # Normalize — defensive against malformed model output
    parsed.setdefault("summary", "")
    parsed.setdefault("likely_cause", "")
    parsed.setdefault("recommendations", [])
    for r in parsed["recommendations"]:
        r.setdefault("category", "description")
        r.setdefault("priority", "medium")
        r.setdefault("title", "")
        r.setdefault("detail", "")

    parsed["token_usage"] = {
        "input_tokens": getattr(resp.usage, "input_tokens", 0),
        "output_tokens": getattr(resp.usage, "output_tokens", 0),
    }
    parsed["cached"] = False
    return parsed
