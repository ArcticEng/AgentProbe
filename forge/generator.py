"""
Prompt-suite generator.

Uses Claude to bootstrap an eval suite for a given skill:
  - positive prompts: should trigger the skill
  - negative prompts: should NOT trigger the skill (nearby topics, off-topic)
  - edge prompts: ambiguous cases at the decision boundary

This is the meta-magic: Claude writes eval suites for Claude skills.
"""

import os
import json
import re
from typing import Optional


GENERATOR_SYSTEM = """You are a test-suite author for Claude Skills. A "skill" is a capability Claude can use, defined by a name, a short description, and a body of instructions. Your job is to generate evaluation prompts that rigorously test whether Claude triggers and uses the skill correctly.

You produce three classes of prompts:
1. POSITIVE: clearly within the skill's scope — Claude should invoke the skill
2. NEGATIVE: clearly outside the skill's scope — Claude should NOT invoke the skill
3. EDGE: ambiguous cases at the boundary — these test the skill's trigger precision

Rules:
- Prompts are natural user messages, not instructions to Claude
- Vary phrasing, tone, length, and formality
- Negatives should be plausible — similar domain, different task
- Edges should be genuinely ambiguous, not tricks
- No meta-references ("use the skill", "this is a test", etc.)
- Each prompt is self-contained and stands alone

Return ONLY a JSON object, no preamble, no markdown fences. Shape:
{
  "prompts": [
    {"id": "pos_01", "class": "positive", "prompt": "...", "rationale": "..."},
    {"id": "neg_01", "class": "negative", "prompt": "...", "rationale": "..."},
    {"id": "edge_01", "class": "edge", "prompt": "...", "rationale": "..."}
  ]
}"""


def _strip_code_fences(text: str) -> str:
    """Claude sometimes wraps JSON in ```json ... ``` despite instructions."""
    text = text.strip()
    m = re.match(r"^```(?:json)?\s*\n(.*?)\n```\s*$", text, re.DOTALL)
    return m.group(1).strip() if m else text


def generate_prompts(
    skill_name: str,
    skill_description: str,
    skill_body: str,
    api_key: str,
    model: str = "claude-opus-4-7",
    positive_count: int = 8,
    negative_count: int = 8,
    edge_count: int = 4,
) -> dict:
    """
    Call Claude to generate an eval suite. Returns {prompts: [...], token_usage: {...}}.
    Raises ValueError on malformed response.
    """
    try:
        from anthropic import Anthropic
    except ImportError as e:
        raise RuntimeError("anthropic SDK not installed — pip install anthropic") from e

    client = Anthropic(api_key=api_key)

    user_msg = (
        f"Skill name: {skill_name}\n\n"
        f"Skill description: {skill_description}\n\n"
        f"Skill instructions:\n---\n{skill_body[:4000]}\n---\n\n"
        f"Generate exactly {positive_count} POSITIVE prompts, "
        f"{negative_count} NEGATIVE prompts, and {edge_count} EDGE prompts. "
        f"Return only the JSON object."
    )

    resp = client.messages.create(
        model=model,
        max_tokens=4000,
        system=GENERATOR_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )

    # Extract text blocks
    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
    text = _strip_code_fences(text)

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Generator returned non-JSON: {text[:300]}") from e

    prompts = parsed.get("prompts", [])
    if not isinstance(prompts, list) or not prompts:
        raise ValueError("Generator returned empty prompt list")

    # Normalize — ensure every prompt has id, class, prompt fields
    for i, p in enumerate(prompts):
        if not p.get("id"):
            p["id"] = f"{p.get('class', 'x')}_{i:02d}"
        if p.get("class") not in ("positive", "negative", "edge"):
            p["class"] = "positive"
        p.setdefault("rationale", "")

    return {
        "prompts": prompts,
        "token_usage": {
            "input_tokens": getattr(resp.usage, "input_tokens", 0),
            "output_tokens": getattr(resp.usage, "output_tokens", 0),
        },
    }
