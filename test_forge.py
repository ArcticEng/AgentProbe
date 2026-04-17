"""
Forge smoke test — runs without hitting the Anthropic API.

Exercises:
  - DB init (tables exist)
  - SKILL.md parsing (frontmatter + body)
  - Folder import (multi-file)
  - Zip import (base64)
  - Skill + SkillVersion CRUD (including content-hash dedupe)
  - EvalSuite CRUD
  - Run+matrix storage (with stub results)
  - Diff computation on stub results

If this script exits with "OK", the Forge backend is wired correctly and the
only thing between you and a real eval is a valid ANTHROPIC_API_KEY.

Run:
    python test_forge.py
"""

import os, sys, io, base64, zipfile, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Force the DB into a temp file so we don't pollute real data
TMP_DB = "/tmp/forge_smoke.db"
if os.path.exists(TMP_DB):
    os.remove(TMP_DB)
os.environ["AGENTPROBE_DB"] = TMP_DB

from billing import init_db as init_billing_db, create_customer
import forge
from forge.importer import (
    parse_skill_md, slugify, from_folder_dict, from_zip_bytes, from_raw_skill_md,
)
from forge.evaluator import diff_trigger_runs, diff_quality_runs

# ----------------------------------------------------------------------
# DB setup
# ----------------------------------------------------------------------
init_billing_db()
forge.init_db()

customer, api_key = create_customer(email="smoke@test.local", name="Smoke Test", plan="pro")
cid = customer["id"]
print(f"[OK] customer created: {cid}  key={api_key[:14]}...")

# ----------------------------------------------------------------------
# SKILL.md parsing
# ----------------------------------------------------------------------
SAMPLE_SKILL = """---
name: PR Reviewer
description: Reviews pull requests for bugs, style, and missing tests.
tags: [review, git, quality]
---

# PR Reviewer

Use this skill when the user shares a git diff or asks for code review.

## Output format
1. Summary (2 sentences max)
2. Bugs — bulleted, include file:line
3. Style nits — optional
4. Test coverage gaps
"""

fm, body = parse_skill_md(SAMPLE_SKILL)
assert fm["name"] == "PR Reviewer", f"bad name: {fm}"
assert "Reviews pull requests" in fm["description"]
assert "review" in fm.get("tags", [])
print("[OK] SKILL.md parsed:", fm["name"])
print("     description:", fm["description"][:60] + "...")
print("     tags:", fm.get("tags"))

# Description inference from body when frontmatter is empty
inferred_fm, _ = parse_skill_md("# Auto Name\n\nDoes a thing for the user.\n")
assert inferred_fm["name"] == "Auto Name"
assert inferred_fm["description"].startswith("Does a thing")
print("[OK] inference works: name + description from body")

# slugify
assert slugify("PR Reviewer!") == "pr-reviewer"
print("[OK] slugify: 'PR Reviewer!' ->", slugify("PR Reviewer!"))

# ----------------------------------------------------------------------
# Folder import
# ----------------------------------------------------------------------
folder_parsed = from_folder_dict({
    "SKILL.md": SAMPLE_SKILL,
    "templates/review.md": "# Review template\n...",
    "scripts/lint.py": "print('lint')",
})
assert folder_parsed["frontmatter"]["name"] == "PR Reviewer"
assert "templates/review.md" in folder_parsed["files"]
print("[OK] folder import: 3 files ->", len(folder_parsed["files"]), "supporting")

# ----------------------------------------------------------------------
# Zip import
# ----------------------------------------------------------------------
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as zf:
    zf.writestr("my-skill/SKILL.md", SAMPLE_SKILL)
    zf.writestr("my-skill/notes.txt", "notes go here")
zip_parsed = from_zip_bytes(buf.getvalue())
assert zip_parsed["frontmatter"]["name"] == "PR Reviewer"
assert "notes.txt" in zip_parsed["files"]
assert "my-skill/notes.txt" not in zip_parsed["files"], "top-level prefix should be stripped"
print("[OK] zip import: prefix stripped, ", list(zip_parsed["files"].keys()))

# ----------------------------------------------------------------------
# Skill + SkillVersion CRUD with dedupe
# ----------------------------------------------------------------------
skill = forge.create_skill(cid, "pr-reviewer", "PR Reviewer", fm["description"])
sid = skill["id"]
v1 = forge.create_skill_version(sid, "v1", SAMPLE_SKILL, fm, {"t.md": "x"})
v2 = forge.create_skill_version(sid, "v1-dup", SAMPLE_SKILL, fm, {"t.md": "x"})
assert v1["id"] == v2["id"], "content-hash dedupe failed"
print(f"[OK] dedupe: same content -> same version_id {v1['id']}")

v3 = forge.create_skill_version(sid, "v2", SAMPLE_SKILL + "\n\nAdditional step.", fm, {})
assert v3["id"] != v1["id"]
assert v3["content_hash"] != v1["content_hash"]
print(f"[OK] new content -> new version_id {v3['id']}")

versions = forge.list_skill_versions(sid)
assert len(versions) == 2, f"expected 2 versions, got {len(versions)}"
print(f"[OK] list_skill_versions: {len(versions)} versions")

latest = forge.get_skill(sid)["latest_version_id"]
assert latest == v3["id"], "latest_version_id should point to v3"
print(f"[OK] latest pointer updated -> {latest}")

# ----------------------------------------------------------------------
# EvalSuite
# ----------------------------------------------------------------------
prompts = [
    {"id": "pos_01", "class": "positive", "prompt": "Review this diff: @@ ..."},
    {"id": "pos_02", "class": "positive", "prompt": "What bugs are in this PR?"},
    {"id": "neg_01", "class": "negative", "prompt": "What's the capital of Botswana?"},
    {"id": "neg_02", "class": "negative", "prompt": "Write me a haiku about rain."},
    {"id": "edge_01", "class": "edge", "prompt": "Should I use async here?"},
]
suite = forge.create_eval_suite(sid, "smoke", prompts)
assert len(suite["prompts"]) == 5
assert suite["rubric"]["scale"]["pass_threshold"] == 3.5
print(f"[OK] suite created: {suite['id']} with {len(suite['prompts'])} prompts")

# ----------------------------------------------------------------------
# EvalRun storage
# ----------------------------------------------------------------------
run_id = forge.create_eval_run(cid, sid, v3["id"], suite["id"], "claude-opus-4-7", "both")
forge.finish_eval_run(
    run_id, "completed",
    summary={"trigger": {"precision": 1.0, "recall": 0.75, "f1": 0.86, "accuracy": 0.9},
             "quality": {"avg_score": 4.1, "pass_rate": 0.8}},
    results=[{"id": "pos_01", "triggered": True, "correct": True}],
    duration_ms=12_345,
    token_usage={"input": 1200, "output": 800},
)
run = forge.get_eval_run(run_id)
assert run["status"] == "completed"
assert run["summary"]["trigger"]["f1"] == 0.86
print(f"[OK] eval run stored: {run_id}, f1={run['summary']['trigger']['f1']}")

# ----------------------------------------------------------------------
# Diff computation (stubbed results, no Claude calls)
# ----------------------------------------------------------------------
trigger_stubs = {
    "claude-opus-4-7": {
        "summary": {"accuracy": 0.9, "f1": 0.86},
        "results": [
            {"id": "pos_01", "class": "positive", "prompt": "...", "expected": True,  "triggered": True,  "correct": True},
            {"id": "pos_02", "class": "positive", "prompt": "...", "expected": True,  "triggered": True,  "correct": True},
            {"id": "neg_01", "class": "negative", "prompt": "...", "expected": False, "triggered": False, "correct": True},
        ],
    },
    "claude-haiku-4-5-20251001": {
        "summary": {"accuracy": 0.67, "f1": 0.67},
        "results": [
            {"id": "pos_01", "class": "positive", "prompt": "...", "expected": True,  "triggered": True,  "correct": True},
            {"id": "pos_02", "class": "positive", "prompt": "...", "expected": True,  "triggered": False, "correct": False},  # flip!
            {"id": "neg_01", "class": "negative", "prompt": "...", "expected": False, "triggered": True,  "correct": False},  # flip!
        ],
    },
}
tdiff = diff_trigger_runs(trigger_stubs)
assert tdiff["prompts_with_disagreement"] == 2, f"expected 2 flips, got {tdiff['prompts_with_disagreement']}"
assert tdiff["baseline_model"] == "claude-opus-4-7"
assert tdiff["per_model"]["claude-haiku-4-5-20251001"]["delta_accuracy_vs_baseline"] < 0
print(f"[OK] trigger diff: {tdiff['prompts_with_disagreement']} disagreements, "
      f"haiku delta={tdiff['per_model']['claude-haiku-4-5-20251001']['delta_accuracy_vs_baseline']}")

quality_stubs = {
    "claude-opus-4-7": {
        "summary": {"avg_score": 4.5, "pass_rate": 1.0},
        "results": [
            {"id": "pos_01", "class": "positive", "weighted_score": 4.6, "pass": True},
            {"id": "pos_02", "class": "positive", "weighted_score": 4.4, "pass": True},
        ],
    },
    "claude-haiku-4-5-20251001": {
        "summary": {"avg_score": 3.5, "pass_rate": 0.5},
        "results": [
            {"id": "pos_01", "class": "positive", "weighted_score": 4.1, "pass": True},
            {"id": "pos_02", "class": "positive", "weighted_score": 2.8, "pass": False},  # drift > 0.5
        ],
    },
}
qdiff = diff_quality_runs(quality_stubs)
assert qdiff["prompts_with_drift"] >= 1
print(f"[OK] quality diff: {qdiff['prompts_with_drift']} drift, threshold={qdiff['drift_threshold']}")

# Regression matrix storage
matrix_id = forge.create_regression_matrix(
    cid, sid, v3["id"],
    models=list(trigger_stubs.keys()),
    run_ids=[run_id],
    diff={"trigger": tdiff, "quality": qdiff},
)
m = forge.get_regression_matrix(matrix_id)
assert m["diff"]["trigger"]["prompts_with_disagreement"] == 2
print(f"[OK] regression matrix stored: {matrix_id}")

# ----------------------------------------------------------------------
print("\n" + "=" * 50)
print("OK — Forge backend is correctly wired.")
print("=" * 50)
print("Next: set ANTHROPIC_API_KEY in .env and hit /api/skills/... endpoints.")
