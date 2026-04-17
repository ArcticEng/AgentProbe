"""
Forge — the production layer for Claude Skills.

Sits alongside AgentProbe's billing layer, shares the same SQLite database
and customer auth, but introduces skills as first-class objects:
  - Skill:        the container (name, description, owner)
  - SkillVersion: immutable snapshot of SKILL.md + files (content-hashed)
  - EvalSuite:    a bundle of prompts (positive / negative / edge) attached to a skill
  - EvalRun:      an immutable record of evaluating (SkillVersion x Model x SuiteSnapshot)
  - RegressionMatrix: N runs across M Claude models, diffed for drift

Design principle: every eval run is reproducible forever. Hash everything.
"""

import os
import json
import hashlib
import secrets
from datetime import datetime, timezone
from typing import Optional

# Share the billing DB connection pool — one file, multiple logical schemas.
from billing import get_db


# ============================================================
# SCHEMA
# ============================================================

def init_db():
    """Create Forge tables. Safe to call repeatedly."""
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS skills (
            id TEXT PRIMARY KEY,
            customer_id TEXT NOT NULL,
            slug TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            latest_version_id TEXT,
            visibility TEXT DEFAULT 'private',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            UNIQUE(customer_id, slug)
        );

        CREATE TABLE IF NOT EXISTS skill_versions (
            id TEXT PRIMARY KEY,
            skill_id TEXT NOT NULL,
            version_tag TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            skill_md TEXT NOT NULL,
            frontmatter_json TEXT NOT NULL DEFAULT '{}',
            files_json TEXT NOT NULL DEFAULT '{}',
            token_estimate INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(skill_id, version_tag)
        );

        CREATE TABLE IF NOT EXISTS eval_suites (
            id TEXT PRIMARY KEY,
            skill_id TEXT NOT NULL,
            name TEXT NOT NULL DEFAULT 'default',
            prompts_json TEXT NOT NULL DEFAULT '[]',
            rubric_json TEXT NOT NULL DEFAULT '{}',
            generated_by TEXT DEFAULT 'human',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS eval_runs (
            id TEXT PRIMARY KEY,
            customer_id TEXT NOT NULL,
            skill_id TEXT NOT NULL,
            skill_version_id TEXT NOT NULL,
            suite_id TEXT NOT NULL,
            model TEXT NOT NULL,
            run_type TEXT NOT NULL,        -- 'trigger' | 'quality' | 'both'
            status TEXT NOT NULL DEFAULT 'pending',
            summary_json TEXT DEFAULT '{}',
            results_json TEXT DEFAULT '[]',
            started_at TEXT DEFAULT (datetime('now')),
            completed_at TEXT,
            duration_ms INTEGER,
            token_usage_json TEXT DEFAULT '{}',
            error TEXT
        );

        CREATE TABLE IF NOT EXISTS regression_matrices (
            id TEXT PRIMARY KEY,
            customer_id TEXT NOT NULL,
            skill_id TEXT NOT NULL,
            skill_version_id TEXT NOT NULL,
            models_json TEXT NOT NULL,
            run_ids_json TEXT NOT NULL,
            diff_json TEXT DEFAULT '{}',
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_skills_customer ON skills(customer_id);
        CREATE INDEX IF NOT EXISTS idx_skill_versions_skill ON skill_versions(skill_id);
        CREATE INDEX IF NOT EXISTS idx_eval_suites_skill ON eval_suites(skill_id);
        CREATE INDEX IF NOT EXISTS idx_eval_runs_skill_version ON eval_runs(skill_version_id);
        CREATE INDEX IF NOT EXISTS idx_eval_runs_customer ON eval_runs(customer_id);
        CREATE INDEX IF NOT EXISTS idx_regression_skill ON regression_matrices(skill_id);
    """)
    conn.commit()


# ============================================================
# ID HELPERS
# ============================================================

def _mk_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(10)}"

def compute_content_hash(skill_md: str, files: dict) -> str:
    """Deterministic hash of the SKILL.md + all supporting file contents."""
    hasher = hashlib.sha256()
    hasher.update(skill_md.encode("utf-8"))
    for filename in sorted(files.keys()):
        hasher.update(filename.encode("utf-8"))
        hasher.update(b"\x00")
        content = files[filename]
        if isinstance(content, str):
            hasher.update(content.encode("utf-8"))
        else:
            hasher.update(content)
        hasher.update(b"\x00")
    return hasher.hexdigest()[:16]


# ============================================================
# SKILLS — CRUD
# ============================================================

def create_skill(customer_id: str, slug: str, name: str, description: str = "",
                 visibility: str = "private") -> dict:
    skill_id = _mk_id("skill")
    conn = get_db()
    conn.execute(
        "INSERT INTO skills (id, customer_id, slug, name, description, visibility) VALUES (?, ?, ?, ?, ?, ?)",
        (skill_id, customer_id, slug, name, description, visibility),
    )
    conn.commit()
    return get_skill(skill_id)


def get_skill(skill_id: str) -> Optional[dict]:
    conn = get_db()
    row = conn.execute("SELECT * FROM skills WHERE id = ?", (skill_id,)).fetchone()
    return dict(row) if row else None


def get_skill_by_slug(customer_id: str, slug: str) -> Optional[dict]:
    conn = get_db()
    row = conn.execute("SELECT * FROM skills WHERE customer_id = ? AND slug = ?",
                       (customer_id, slug)).fetchone()
    return dict(row) if row else None


def list_skills(customer_id: str, limit: int = 100) -> list:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM skills WHERE customer_id = ? ORDER BY updated_at DESC LIMIT ?",
        (customer_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def delete_skill(skill_id: str, customer_id: str) -> bool:
    conn = get_db()
    cur = conn.execute("DELETE FROM skills WHERE id = ? AND customer_id = ?",
                       (skill_id, customer_id))
    conn.execute("DELETE FROM skill_versions WHERE skill_id = ?", (skill_id,))
    conn.execute("DELETE FROM eval_suites WHERE skill_id = ?", (skill_id,))
    conn.execute("DELETE FROM eval_runs WHERE skill_id = ?", (skill_id,))
    conn.commit()
    return cur.rowcount > 0


def set_latest_version(skill_id: str, version_id: str):
    conn = get_db()
    conn.execute(
        "UPDATE skills SET latest_version_id = ?, updated_at = datetime('now') WHERE id = ?",
        (version_id, skill_id),
    )
    conn.commit()


# ============================================================
# SKILL VERSIONS — immutable, content-hashed
# ============================================================

def create_skill_version(skill_id: str, version_tag: str, skill_md: str,
                         frontmatter: dict, files: dict) -> dict:
    """
    Store an immutable snapshot. If the content hash matches an existing version
    for this skill, reuse it rather than duplicating.
    """
    conn = get_db()
    content_hash = compute_content_hash(skill_md, files)

    existing = conn.execute(
        "SELECT * FROM skill_versions WHERE skill_id = ? AND content_hash = ?",
        (skill_id, content_hash),
    ).fetchone()
    if existing:
        return get_skill_version(existing["id"])

    version_id = _mk_id("sv")
    token_estimate = max(1, (len(skill_md) + sum(len(str(v)) for v in files.values())) // 4)
    conn.execute(
        """INSERT INTO skill_versions
           (id, skill_id, version_tag, content_hash, skill_md, frontmatter_json, files_json, token_estimate)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            version_id,
            skill_id,
            version_tag,
            content_hash,
            skill_md,
            json.dumps(frontmatter),
            json.dumps(files),
            token_estimate,
        ),
    )
    conn.commit()
    set_latest_version(skill_id, version_id)
    return get_skill_version(version_id)


def get_skill_version(version_id: str) -> Optional[dict]:
    conn = get_db()
    row = conn.execute("SELECT * FROM skill_versions WHERE id = ?", (version_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["frontmatter"] = json.loads(d.pop("frontmatter_json") or "{}")
    d["files"] = json.loads(d.pop("files_json") or "{}")
    return d


def list_skill_versions(skill_id: str) -> list:
    conn = get_db()
    rows = conn.execute(
        """SELECT id, skill_id, version_tag, content_hash, token_estimate, created_at
           FROM skill_versions WHERE skill_id = ? ORDER BY created_at DESC""",
        (skill_id,),
    ).fetchall()
    return [dict(r) for r in rows]


# ============================================================
# EVAL SUITES
# ============================================================

DEFAULT_RUBRIC = {
    "criteria": [
        {"key": "correctness", "description": "Does the output correctly address the prompt using the skill's instructions?", "weight": 0.4},
        {"key": "format_adherence", "description": "Does the output follow any format rules defined in the skill?", "weight": 0.3},
        {"key": "instruction_following", "description": "Does the output follow every explicit instruction in the skill?", "weight": 0.3},
    ],
    "scale": {"min": 1, "max": 5, "pass_threshold": 3.5},
}


def create_eval_suite(skill_id: str, name: str, prompts: list,
                      rubric: Optional[dict] = None, generated_by: str = "human") -> dict:
    suite_id = _mk_id("suite")
    conn = get_db()
    conn.execute(
        """INSERT INTO eval_suites (id, skill_id, name, prompts_json, rubric_json, generated_by)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            suite_id,
            skill_id,
            name,
            json.dumps(prompts),
            json.dumps(rubric or DEFAULT_RUBRIC),
            generated_by,
        ),
    )
    conn.commit()
    return get_eval_suite(suite_id)


def get_eval_suite(suite_id: str) -> Optional[dict]:
    conn = get_db()
    row = conn.execute("SELECT * FROM eval_suites WHERE id = ?", (suite_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["prompts"] = json.loads(d.pop("prompts_json") or "[]")
    d["rubric"] = json.loads(d.pop("rubric_json") or "{}")
    return d


def list_eval_suites(skill_id: str) -> list:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM eval_suites WHERE skill_id = ? ORDER BY updated_at DESC",
        (skill_id,),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["prompts"] = json.loads(d.pop("prompts_json") or "[]")
        d["rubric"] = json.loads(d.pop("rubric_json") or "{}")
        out.append(d)
    return out


def update_eval_suite(suite_id: str, prompts: Optional[list] = None,
                      rubric: Optional[dict] = None) -> Optional[dict]:
    conn = get_db()
    sets, vals = [], []
    if prompts is not None:
        sets.append("prompts_json = ?")
        vals.append(json.dumps(prompts))
    if rubric is not None:
        sets.append("rubric_json = ?")
        vals.append(json.dumps(rubric))
    if not sets:
        return get_eval_suite(suite_id)
    sets.append("updated_at = datetime('now')")
    vals.append(suite_id)
    conn.execute(f"UPDATE eval_suites SET {', '.join(sets)} WHERE id = ?", vals)
    conn.commit()
    return get_eval_suite(suite_id)


# ============================================================
# EVAL RUNS
# ============================================================

def create_eval_run(customer_id: str, skill_id: str, skill_version_id: str,
                    suite_id: str, model: str, run_type: str = "both") -> str:
    run_id = _mk_id("run")
    conn = get_db()
    conn.execute(
        """INSERT INTO eval_runs
           (id, customer_id, skill_id, skill_version_id, suite_id, model, run_type, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')""",
        (run_id, customer_id, skill_id, skill_version_id, suite_id, model, run_type),
    )
    conn.commit()
    return run_id


def finish_eval_run(run_id: str, status: str, summary: dict, results: list,
                    duration_ms: int, token_usage: dict, error: Optional[str] = None):
    conn = get_db()
    conn.execute(
        """UPDATE eval_runs
           SET status = ?, summary_json = ?, results_json = ?,
               completed_at = datetime('now'), duration_ms = ?, token_usage_json = ?, error = ?
           WHERE id = ?""",
        (
            status,
            json.dumps(summary),
            json.dumps(results),
            duration_ms,
            json.dumps(token_usage),
            error,
            run_id,
        ),
    )
    conn.commit()


def get_eval_run(run_id: str) -> Optional[dict]:
    conn = get_db()
    row = conn.execute("SELECT * FROM eval_runs WHERE id = ?", (run_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["summary"] = json.loads(d.pop("summary_json") or "{}")
    d["results"] = json.loads(d.pop("results_json") or "[]")
    d["token_usage"] = json.loads(d.pop("token_usage_json") or "{}")
    return d


def list_eval_runs(skill_id: str, limit: int = 50) -> list:
    conn = get_db()
    rows = conn.execute(
        """SELECT id, skill_version_id, suite_id, model, run_type, status,
                  summary_json, duration_ms, started_at, completed_at
           FROM eval_runs WHERE skill_id = ? ORDER BY started_at DESC LIMIT ?""",
        (skill_id, limit),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["summary"] = json.loads(d.pop("summary_json") or "{}")
        out.append(d)
    return out


# ============================================================
# REGRESSION MATRICES — cross-model diffs
# ============================================================

def create_regression_matrix(customer_id: str, skill_id: str, skill_version_id: str,
                             models: list, run_ids: list, diff: dict) -> str:
    matrix_id = _mk_id("rmx")
    conn = get_db()
    conn.execute(
        """INSERT INTO regression_matrices
           (id, customer_id, skill_id, skill_version_id, models_json, run_ids_json, diff_json)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            matrix_id,
            customer_id,
            skill_id,
            skill_version_id,
            json.dumps(models),
            json.dumps(run_ids),
            json.dumps(diff),
        ),
    )
    conn.commit()
    return matrix_id


def get_regression_matrix(matrix_id: str) -> Optional[dict]:
    conn = get_db()
    row = conn.execute("SELECT * FROM regression_matrices WHERE id = ?", (matrix_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["models"] = json.loads(d.pop("models_json") or "[]")
    d["run_ids"] = json.loads(d.pop("run_ids_json") or "[]")
    d["diff"] = json.loads(d.pop("diff_json") or "{}")
    return d


def list_regression_matrices(skill_id: str, limit: int = 20) -> list:
    conn = get_db()
    rows = conn.execute(
        """SELECT id, skill_version_id, models_json, created_at
           FROM regression_matrices WHERE skill_id = ? ORDER BY created_at DESC LIMIT ?""",
        (skill_id, limit),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["models"] = json.loads(d.pop("models_json") or "[]")
        out.append(d)
    return out
