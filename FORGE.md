# Forge

**The production layer for Claude Skills.** Built on top of AgentProbe.

Forge turns a `SKILL.md` folder into a versioned, evaluated, regression-tested artifact you can ship with confidence.

- **Authoring:** import a skill via paste / folder / zip / git (coming soon).
- **Generation:** one call produces an eval suite (positives, negatives, edges).
- **Evaluation:** two dimensions — *trigger accuracy* (did Claude invoke the skill?) and *output quality* (did Claude follow the skill's instructions?).
- **Regression matrix:** run the same suite across every Claude model, get a diff of what changed.

Forge shares AgentProbe's database, auth, rate limiting, and billing. All Forge routes live under `/api/skills/*`.

---

## 1. Prerequisites

```bash
# From the agentprobe repo root
pip install -e '.[api,anthropic]'

# Ensure .env has an Anthropic key — Forge needs it server-side
echo 'ANTHROPIC_API_KEY=sk-ant-...' >> .env
```

Run the server:

```bash
uvicorn api.server:app --reload --port 8000
```

You should see `forge.init_db()` run once on boot, and `GET /` should return `{"forge": "online", ...}`.

---

## 2. Data model (one-liner each)

- **Skill** — a container. Has a slug, name, description, and many versions.
- **SkillVersion** — an immutable snapshot of `SKILL.md` + supporting files. Content-hashed.
- **EvalSuite** — a list of prompts (positive/negative/edge) + a rubric. Attached to a skill.
- **EvalRun** — evaluating one suite against one `SkillVersion` on one model. Reproducible forever.
- **RegressionMatrix** — N EvalRuns across M models, diffed. This is the headline feature.

---

## 3. End-to-end walkthrough

### Create a skill from raw SKILL.md

```bash
curl -X POST http://localhost:8000/api/skills \
  -H "X-API-Key: $AP_KEY" -H "Content-Type: application/json" \
  -d '{
    "slug": "pr-reviewer",
    "version_tag": "v1",
    "skill_md": "---\nname: PR Reviewer\ndescription: Reviews pull requests for bugs, style, and test coverage.\n---\n\n# PR Reviewer\n\nWhen given a git diff, produce a review with:\n1. Summary of changes (2 sentences)\n2. Bugs (bulleted, with file:line)\n3. Style nits (optional)\n4. Test coverage gaps\n\nAlways use this exact section order."
  }'
```

### Create a skill from a folder (JSON shape)

```json
POST /api/skills
{
  "slug": "meal-planner",
  "folder": {
    "SKILL.md": "---\nname: Meal Planner\n...",
    "templates/weekly_plan.md": "Mon: ...",
    "scripts/shopping_list.py": "def build(..):\n  ..."
  }
}
```

### Create a skill from a zip

Base64-encode the zip on the client, POST it as `zip_base64`. Max 5 MB total, 500 KB per file.

### Auto-generate an eval suite

```bash
curl -X POST http://localhost:8000/api/skills/$SKILL_ID/generate-prompts \
  -H "X-API-Key: $AP_KEY" -H "Content-Type: application/json" \
  -d '{"positive_count": 8, "negative_count": 8, "edge_count": 4}'
```

Returns `{prompts: [...]}`. Save them as a suite:

```bash
curl -X POST http://localhost:8000/api/skills/$SKILL_ID/suites \
  -H "X-API-Key: $AP_KEY" -H "Content-Type: application/json" \
  -d '{"name": "v1-auto", "prompts": <paste the returned prompts>}'
```

### Run a single-model evaluation

```bash
curl -X POST http://localhost:8000/api/skills/$SKILL_ID/runs \
  -H "X-API-Key: $AP_KEY" -H "Content-Type: application/json" \
  -d '{"suite_id": "suite_...", "model": "claude-opus-4-7", "run_type": "both"}'
```

`run_type` is one of `trigger`, `quality`, `both`. Returns a full EvalRun object with summary + per-prompt results.

### Run a regression matrix across all Claude models

```bash
curl -X POST http://localhost:8000/api/skills/$SKILL_ID/regression \
  -H "X-API-Key: $AP_KEY" -H "Content-Type: application/json" \
  -d '{"suite_id": "suite_...", "run_type": "both"}'
```

Default models: `claude-opus-4-7`, `claude-opus-4-6`, `claude-sonnet-4-6`, `claude-haiku-4-5-20251001`.

The response includes `diff.trigger` and `diff.quality`. Each has:
- `per_prompt`: every prompt with `by_model` showing what each model did, flagged if they disagree
- `per_model`: summary metrics plus delta vs baseline (the first model in the list)
- `prompts_with_disagreement` / `prompts_with_drift`: the headline numbers

---

## 4. How evaluation actually works

### Trigger accuracy

The skill is declared to Claude as a **tool** — name + description + minimal input schema. A prompt is sent. If Claude responds with a `tool_use` block naming that tool, we count it as "triggered." Positive prompts should trigger; negative prompts should not; edge prompts are observed but not counted in precision/recall.

This is not exactly how `claude.ai` runs skills today — but it's the closest analog we can measure through the API, and the trigger signal correlates well with skill-invocation behavior.

### Output quality

The skill's full `SKILL.md` body is injected into the system prompt. Claude is called with the user prompt. The output is then judged by Claude (default: Opus 4.7) against the suite's rubric. The rubric is weighted; each criterion gets a 1-5 score; the weighted average decides pass/fail.

You can customize the rubric per suite. The default rubric scores `correctness`, `format_adherence`, and `instruction_following`.

### Regression matrix

Runs both evaluators across every listed model, then diffs:
- **Trigger diff**: for each prompt, compare `triggered` across models. Flag disagreements.
- **Quality diff**: for each prompt, compare `weighted_score` across models. Flag drift > 0.5 points.

---

## 5. Usage & billing

Forge evaluation calls count against the customer's monthly `test_runs` quota:
- `generate-prompts`: 1 run
- single-model eval: `prompt_count * phases` (phases=2 for `both`)
- regression matrix: `prompt_count * models * phases`

Real-model evaluation requires **Pro+** (same gate as AgentProbe's `real_systems` flag).

Free-tier users can create skills, import them, and generate prompt suites — but not run evaluations against real Claude models.

---

## 6. Next phases

**Phase 2 (CLI):** `forge init / test / push / diff` — a thin Node wrapper on top of these endpoints, published as `@arcticeng/forge` on npm. Distribution wedge and OSS brand.

**Phase 3 (Dashboard):** new "Skills" tab in the existing AgentProbe dashboard — list skills, inspect runs, visualize the regression matrix as a heatmap.

**Phase 4 (Launch artifact):** public "SkillBench" — run a set of public skills across every Claude model and publish the matrix. This is what gets Anthropic's attention.

---

## 7. File map

```
forge/
├── __init__.py     # Schema + storage (shares billing DB)
├── importer.py     # SKILL.md parser, folder/zip ingestion
├── generator.py    # Claude-generated eval suites
├── evaluator.py    # Trigger + quality + regression matrix
└── routes.py       # FastAPI router — /api/skills/*

api/server.py       # 4 additive lines — imports, init_db, mount router, status
```

Nothing in `billing/`, `agentprobe/`, or existing AgentProbe routes was changed. If you kill `forge/` and revert 4 lines in `api/server.py`, AgentProbe is exactly as it was.
