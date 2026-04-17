"""
Forge FastAPI routes — mounted under /api/skills.

Reuses AgentProbe's authenticate() + rate limiting + usage tracking.
Nothing in this file should touch billing internals directly except
calling authenticate() and track_usage().
"""

import os
import time
import uuid
import base64
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, Query, UploadFile, File
from pydantic import BaseModel

import forge
from forge.importer import (
    parse_skill_md, slugify, from_folder_dict, from_zip_bytes, from_raw_skill_md,
)
from forge.generator import generate_prompts
from forge.evaluator import (
    run_trigger_suite, run_quality_suite,
    diff_trigger_runs, diff_quality_runs,
    DEFAULT_MODELS, DEFAULT_JUDGE_MODEL,
)
from forge.analyzer import analyze_matrix

# These imports intentionally reach into billing for the same helpers server.py uses.
from billing import track_usage, PLANS


router = APIRouter(prefix="/api/skills", tags=["forge"])


# ============================================================
# REQUEST MODELS
# ============================================================

class CreateSkillRequest(BaseModel):
    slug: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    visibility: str = "private"
    # One of these must be provided:
    skill_md: Optional[str] = None                    # raw SKILL.md body
    folder: Optional[dict] = None                     # {path: text_content, ...}
    zip_base64: Optional[str] = None                  # base64-encoded zip bytes
    version_tag: Optional[str] = "v1"


class GeneratePromptsRequest(BaseModel):
    positive_count: int = 8
    negative_count: int = 8
    edge_count: int = 4
    model: str = "claude-opus-4-7"


class CreateSuiteRequest(BaseModel):
    name: str = "default"
    prompts: list
    rubric: Optional[dict] = None


class RunEvalRequest(BaseModel):
    suite_id: str
    skill_version_id: Optional[str] = None
    model: str = "claude-opus-4-7"
    run_type: str = "both"                            # 'trigger' | 'quality' | 'both'


class RegressionRequest(BaseModel):
    suite_id: str
    skill_version_id: Optional[str] = None
    models: Optional[list] = None                     # defaults to DEFAULT_MODELS
    run_type: str = "both"


# ============================================================
# AUTH HELPER — delegate to server.py's authenticate() at import time
# ============================================================

def _authenticate(x_api_key: Optional[str]):
    # Delayed import to avoid circular — server.py imports this module.
    from api.server import authenticate
    return authenticate(x_api_key)


def _get_anthropic_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise HTTPException(503, "Server has no ANTHROPIC_API_KEY configured")
    return key


# ============================================================
# OWNERSHIP GUARD
# ============================================================

def _own_skill(skill_id: str, customer_id: str):
    skill = forge.get_skill(skill_id)
    if not skill or skill["customer_id"] != customer_id:
        raise HTTPException(404, "Skill not found")
    return skill


def _own_suite(suite_id: str, customer_id: str):
    suite = forge.get_eval_suite(suite_id)
    if not suite:
        raise HTTPException(404, "Suite not found")
    skill = forge.get_skill(suite["skill_id"])
    if not skill or skill["customer_id"] != customer_id:
        raise HTTPException(404, "Suite not found")
    return suite, skill


# ============================================================
# SKILLS — CRUD + IMPORT
# ============================================================

@router.post("")
def create_skill(req: CreateSkillRequest, x_api_key: str = Header(None)):
    customer = _authenticate(x_api_key)

    # Figure out the skill content source
    if req.folder:
        parsed = from_folder_dict(req.folder)
    elif req.zip_base64:
        try:
            zip_bytes = base64.b64decode(req.zip_base64)
        except Exception as e:
            raise HTTPException(400, f"Invalid zip_base64: {e}")
        parsed = from_zip_bytes(zip_bytes)
    elif req.skill_md:
        parsed = from_raw_skill_md(req.skill_md)
    else:
        raise HTTPException(400, "Provide one of: skill_md, folder, or zip_base64")

    frontmatter = parsed["frontmatter"]
    name = req.name or frontmatter.get("name") or "Untitled Skill"
    description = req.description or frontmatter.get("description") or ""
    slug = req.slug or slugify(name)

    existing = forge.get_skill_by_slug(customer["customer_id"], slug)
    if existing:
        # Add a new version to the existing skill instead of failing
        skill = existing
    else:
        skill = forge.create_skill(
            customer_id=customer["customer_id"],
            slug=slug, name=name, description=description,
            visibility=req.visibility,
        )

    version = forge.create_skill_version(
        skill_id=skill["id"],
        version_tag=req.version_tag or "v1",
        skill_md=parsed["skill_md"],
        frontmatter=frontmatter,
        files=parsed["files"],
    )

    return {"skill": forge.get_skill(skill["id"]), "version": version}


@router.get("")
def list_skills(x_api_key: str = Header(None)):
    customer = _authenticate(x_api_key)
    return {"skills": forge.list_skills(customer["customer_id"])}


@router.get("/{skill_id}")
def get_skill(skill_id: str, x_api_key: str = Header(None)):
    customer = _authenticate(x_api_key)
    skill = _own_skill(skill_id, customer["customer_id"])
    versions = forge.list_skill_versions(skill_id)
    suites = forge.list_eval_suites(skill_id)
    runs = forge.list_eval_runs(skill_id, limit=20)
    return {
        "skill": skill, "versions": versions,
        "suites": [{"id": s["id"], "name": s["name"], "prompt_count": len(s["prompts"])} for s in suites],
        "recent_runs": runs,
    }


@router.delete("/{skill_id}")
def delete_skill_endpoint(skill_id: str, x_api_key: str = Header(None)):
    customer = _authenticate(x_api_key)
    _own_skill(skill_id, customer["customer_id"])
    ok = forge.delete_skill(skill_id, customer["customer_id"])
    return {"deleted": ok}


@router.get("/{skill_id}/versions/{version_id}")
def get_version(skill_id: str, version_id: str, x_api_key: str = Header(None)):
    customer = _authenticate(x_api_key)
    _own_skill(skill_id, customer["customer_id"])
    v = forge.get_skill_version(version_id)
    if not v or v["skill_id"] != skill_id:
        raise HTTPException(404, "Version not found")
    return v


# ============================================================
# PROMPT GENERATION
# ============================================================

@router.post("/{skill_id}/generate-prompts")
def generate_prompts_endpoint(skill_id: str, req: GeneratePromptsRequest,
                              x_api_key: str = Header(None)):
    customer = _authenticate(x_api_key)
    skill = _own_skill(skill_id, customer["customer_id"])
    if not skill.get("latest_version_id"):
        raise HTTPException(400, "Skill has no version yet")

    version = forge.get_skill_version(skill["latest_version_id"])
    key = _get_anthropic_key()
    try:
        result = generate_prompts(
            skill_name=skill["name"],
            skill_description=skill["description"],
            skill_body=version["skill_md"],
            api_key=key,
            model=req.model,
            positive_count=req.positive_count,
            negative_count=req.negative_count,
            edge_count=req.edge_count,
        )
    except Exception as e:
        raise HTTPException(500, f"Generator failed: {type(e).__name__}: {e}")

    # Usage = 1 generation run
    track_usage(customer["customer_id"], test_runs=1)
    return result


# ============================================================
# EVAL SUITES
# ============================================================

@router.post("/{skill_id}/suites")
def create_suite(skill_id: str, req: CreateSuiteRequest, x_api_key: str = Header(None)):
    customer = _authenticate(x_api_key)
    _own_skill(skill_id, customer["customer_id"])
    suite = forge.create_eval_suite(
        skill_id=skill_id,
        name=req.name,
        prompts=req.prompts,
        rubric=req.rubric,
        generated_by="human",
    )
    return suite


@router.get("/{skill_id}/suites")
def list_suites(skill_id: str, x_api_key: str = Header(None)):
    customer = _authenticate(x_api_key)
    _own_skill(skill_id, customer["customer_id"])
    return {"suites": forge.list_eval_suites(skill_id)}


@router.get("/suites/{suite_id}")
def get_suite(suite_id: str, x_api_key: str = Header(None)):
    customer = _authenticate(x_api_key)
    suite, _ = _own_suite(suite_id, customer["customer_id"])
    return suite


# ============================================================
# EVAL RUNS
# ============================================================

def _resolve_version(skill: dict, version_id: Optional[str]) -> dict:
    vid = version_id or skill.get("latest_version_id")
    if not vid:
        raise HTTPException(400, "Skill has no version to evaluate")
    v = forge.get_skill_version(vid)
    if not v or v["skill_id"] != skill["id"]:
        raise HTTPException(404, "Version not found")
    return v


def _require_pro_for_real_evals(customer: dict):
    if not PLANS.get(customer["plan"], {}).get("real_systems"):
        raise HTTPException(
            403,
            detail={
                "error": "forge_requires_pro",
                "message": "Running skill evaluations against real Claude models requires Pro+. Upgrade in your dashboard.",
            },
        )


@router.post("/{skill_id}/runs")
def run_eval(skill_id: str, req: RunEvalRequest, x_api_key: str = Header(None)):
    customer = _authenticate(x_api_key)
    skill = _own_skill(skill_id, customer["customer_id"])
    _require_pro_for_real_evals(customer)

    suite, _ = _own_suite(req.suite_id, customer["customer_id"])
    version = _resolve_version(skill, req.skill_version_id)
    key = _get_anthropic_key()

    run_id = forge.create_eval_run(
        customer_id=customer["customer_id"],
        skill_id=skill_id,
        skill_version_id=version["id"],
        suite_id=req.suite_id,
        model=req.model,
        run_type=req.run_type,
    )

    t0 = time.time()
    summary = {}
    results = []
    token_usage = {"input": 0, "output": 0}
    error = None

    try:
        if req.run_type in ("trigger", "both"):
            trig = run_trigger_suite(
                skill_name=skill["name"],
                skill_description=skill["description"],
                prompts=suite["prompts"],
                model=req.model,
                api_key=key,
            )
            summary["trigger"] = trig["summary"]
            for r in trig["results"]:
                r["_phase"] = "trigger"
                results.append(r)
            token_usage["input"] += sum(x.get("tokens", {}).get("input", 0) for x in trig["results"])
            token_usage["output"] += sum(x.get("tokens", {}).get("output", 0) for x in trig["results"])

        if req.run_type in ("quality", "both"):
            qual = run_quality_suite(
                skill_md=version["skill_md"],
                prompts=suite["prompts"],
                model=req.model,
                rubric=suite["rubric"],
                api_key=key,
            )
            summary["quality"] = qual["summary"]
            for r in qual["results"]:
                r["_phase"] = "quality"
                results.append(r)
            token_usage["input"] += sum(x.get("tokens", {}).get("input", 0) for x in qual["results"])
            token_usage["output"] += sum(x.get("tokens", {}).get("output", 0) for x in qual["results"])

        status = "completed"
    except Exception as e:
        status = "failed"
        error = f"{type(e).__name__}: {str(e)[:400]}"

    duration_ms = int((time.time() - t0) * 1000)
    forge.finish_eval_run(run_id, status, summary, results, duration_ms, token_usage, error)

    # Usage tracking — one "test run" per prompt evaluated
    prompt_count = len(suite["prompts"]) * (2 if req.run_type == "both" else 1)
    track_usage(customer["customer_id"], test_runs=prompt_count)

    return forge.get_eval_run(run_id)


@router.get("/runs/{run_id}")
def get_run(run_id: str, x_api_key: str = Header(None)):
    customer = _authenticate(x_api_key)
    run = forge.get_eval_run(run_id)
    if not run or run["customer_id"] != customer["customer_id"]:
        raise HTTPException(404, "Run not found")
    return run


@router.get("/{skill_id}/runs")
def list_runs(skill_id: str, x_api_key: str = Header(None)):
    customer = _authenticate(x_api_key)
    _own_skill(skill_id, customer["customer_id"])
    return {"runs": forge.list_eval_runs(skill_id)}


# ============================================================
# REGRESSION MATRIX — the headline feature
# ============================================================

@router.post("/{skill_id}/regression")
def run_regression(skill_id: str, req: RegressionRequest, x_api_key: str = Header(None)):
    customer = _authenticate(x_api_key)
    skill = _own_skill(skill_id, customer["customer_id"])
    _require_pro_for_real_evals(customer)
    suite, _ = _own_suite(req.suite_id, customer["customer_id"])
    version = _resolve_version(skill, req.skill_version_id)
    models = req.models or DEFAULT_MODELS
    key = _get_anthropic_key()

    trigger_by_model = {}
    quality_by_model = {}
    run_ids = []

    total_prompts = len(suite["prompts"])

    for model in models:
        run_id = forge.create_eval_run(
            customer_id=customer["customer_id"],
            skill_id=skill_id,
            skill_version_id=version["id"],
            suite_id=req.suite_id,
            model=model,
            run_type=req.run_type,
        )
        run_ids.append(run_id)
        t0 = time.time()
        summary = {}
        results = []
        tokens = {"input": 0, "output": 0}
        error = None

        try:
            if req.run_type in ("trigger", "both"):
                trig = run_trigger_suite(
                    skill_name=skill["name"],
                    skill_description=skill["description"],
                    prompts=suite["prompts"],
                    model=model, api_key=key,
                )
                summary["trigger"] = trig["summary"]
                trigger_by_model[model] = trig
                for r in trig["results"]:
                    r["_phase"] = "trigger"
                    results.append(r)
                tokens["input"] += sum(x.get("tokens", {}).get("input", 0) for x in trig["results"])
                tokens["output"] += sum(x.get("tokens", {}).get("output", 0) for x in trig["results"])

            if req.run_type in ("quality", "both"):
                qual = run_quality_suite(
                    skill_md=version["skill_md"],
                    prompts=suite["prompts"],
                    model=model, rubric=suite["rubric"], api_key=key,
                )
                summary["quality"] = qual["summary"]
                quality_by_model[model] = qual
                for r in qual["results"]:
                    r["_phase"] = "quality"
                    results.append(r)
                tokens["input"] += sum(x.get("tokens", {}).get("input", 0) for x in qual["results"])
                tokens["output"] += sum(x.get("tokens", {}).get("output", 0) for x in qual["results"])
            status = "completed"
        except Exception as e:
            status = "failed"
            error = f"{type(e).__name__}: {str(e)[:400]}"

        duration = int((time.time() - t0) * 1000)
        forge.finish_eval_run(run_id, status, summary, results, duration, tokens, error)

    diff = {}
    if trigger_by_model:
        diff["trigger"] = diff_trigger_runs(trigger_by_model)
    if quality_by_model:
        diff["quality"] = diff_quality_runs(quality_by_model)

    matrix_id = forge.create_regression_matrix(
        customer_id=customer["customer_id"],
        skill_id=skill_id,
        skill_version_id=version["id"],
        models=models, run_ids=run_ids, diff=diff,
    )

    # Usage: prompts * models * (2 phases if 'both')
    phases = 2 if req.run_type == "both" else 1
    track_usage(customer["customer_id"], test_runs=total_prompts * len(models) * phases)

    return forge.get_regression_matrix(matrix_id)


@router.get("/regression/{matrix_id}")
def get_regression(matrix_id: str, x_api_key: str = Header(None)):
    customer = _authenticate(x_api_key)
    m = forge.get_regression_matrix(matrix_id)
    if not m or m["customer_id"] != customer["customer_id"]:
        raise HTTPException(404, "Matrix not found")
    return m


@router.post("/regression/{matrix_id}/analyze")
def analyze_regression(matrix_id: str, x_api_key: str = Header(None),
                      force: bool = Query(False)):
    """
    Generate a prescriptive analysis of a regression matrix.
    Cached per matrix — returns cached result unless ?force=true.
    If there are no disagreements, returns a canned "ship with confidence"
    result without calling Claude (free).
    """
    customer = _authenticate(x_api_key)
    m = forge.get_regression_matrix(matrix_id)
    if not m or m["customer_id"] != customer["customer_id"]:
        raise HTTPException(404, "Matrix not found")

    if not force:
        cached = forge.get_regression_analysis(matrix_id)
        if cached:
            cached["analysis"]["cached"] = True
            return cached["analysis"]

    skill = forge.get_skill(m["skill_id"])
    if not skill:
        raise HTTPException(404, "Skill not found")
    version = forge.get_skill_version(m["skill_version_id"])
    if not version:
        raise HTTPException(404, "Skill version not found")

    key = _get_anthropic_key()
    try:
        analysis = analyze_matrix(
            skill_name=skill["name"],
            skill_description=skill["description"],
            skill_md=version["skill_md"],
            diff=m["diff"],
            api_key=key,
        )
    except Exception as e:
        raise HTTPException(500, f"Analysis failed: {type(e).__name__}: {e}")

    forge.save_regression_analysis(matrix_id, customer["customer_id"], analysis)
    # Analysis costs a modest chunk of tokens — count as 1 run for usage tracking
    if analysis.get("token_usage", {}).get("input_tokens", 0) > 0:
        track_usage(customer["customer_id"], test_runs=1)
    return analysis


@router.get("/regression/{matrix_id}/analysis")
def get_analysis(matrix_id: str, x_api_key: str = Header(None)):
    """Return cached analysis only — does not generate if missing."""
    customer = _authenticate(x_api_key)
    m = forge.get_regression_matrix(matrix_id)
    if not m or m["customer_id"] != customer["customer_id"]:
        raise HTTPException(404, "Matrix not found")
    cached = forge.get_regression_analysis(matrix_id)
    if not cached:
        raise HTTPException(404, "No analysis yet")
    cached["analysis"]["cached"] = True
    return cached["analysis"]


@router.get("/{skill_id}/regression")
def list_regressions(skill_id: str, x_api_key: str = Header(None)):
    customer = _authenticate(x_api_key)
    _own_skill(skill_id, customer["customer_id"])
    return {"matrices": forge.list_regression_matrices(skill_id)}


# ============================================================
# STATUS
# ============================================================

@router.get("/_/status")
def status():
    return {
        "forge": "online",
        "default_models": DEFAULT_MODELS,
        "default_judge": DEFAULT_JUDGE_MODEL,
    }
