"""
SKILL.md parser + importer.

Accepts three input shapes:
  1. Raw text (just the SKILL.md contents)
  2. A dict of {filename: content} representing a full skill folder
  3. A zipfile bytes payload

Returns: (skill_md: str, frontmatter: dict, files: dict)
"""

import io
import os
import re
import json
import zipfile
from typing import Tuple


# Minimal YAML frontmatter parser — no external deps.
# Handles the subset we need: string/list values, --- delimiters.
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", re.DOTALL)


def _parse_simple_yaml(text: str) -> dict:
    """Handles flat key: value pairs, lists, and quoted strings."""
    out = {}
    current_key = None
    current_list = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        # List item continuation
        if current_key and (line.startswith("  - ") or line.startswith("- ")):
            val = line.split("-", 1)[1].strip().strip('"').strip("'")
            if current_list is None:
                current_list = []
                out[current_key] = current_list
            current_list.append(val)
            continue
        # New key
        m = re.match(r"^([A-Za-z0-9_\-]+)\s*:\s*(.*)$", line)
        if m:
            key, value = m.group(1), m.group(2).strip()
            current_key = key
            current_list = None
            if value == "" or value == "|":
                out[key] = ""
                continue
            # Strip surrounding quotes
            if (value.startswith('"') and value.endswith('"')) or \
               (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]
            # Inline list like [a, b, c]
            if value.startswith("[") and value.endswith("]"):
                inner = value[1:-1]
                parts = [p.strip().strip('"').strip("'") for p in inner.split(",") if p.strip()]
                out[key] = parts
            else:
                out[key] = value
    return out


def parse_skill_md(skill_md: str) -> Tuple[dict, str]:
    """
    Extract frontmatter + body.
    Returns (frontmatter_dict, body_text).
    """
    m = FRONTMATTER_RE.match(skill_md)
    if m:
        frontmatter_raw = m.group(1)
        body = m.group(2)
        frontmatter = _parse_simple_yaml(frontmatter_raw)
    else:
        frontmatter = {}
        body = skill_md

    # Derive name from first H1 if not in frontmatter
    if "name" not in frontmatter:
        for line in body.splitlines():
            s = line.strip()
            if s.startswith("# "):
                frontmatter["name"] = s[2:].strip()
                break

    # Derive description from first paragraph after H1 if missing
    if "description" not in frontmatter:
        lines = body.splitlines()
        seen_h1 = False
        para = []
        for line in lines:
            s = line.strip()
            if s.startswith("# "):
                seen_h1 = True
                continue
            if seen_h1:
                if not s:
                    if para:
                        break
                    continue
                if s.startswith("#"):
                    break
                para.append(s)
        if para:
            frontmatter["description"] = " ".join(para)[:500]

    return frontmatter, body


def slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9\-_]+", "-", (name or "").strip().lower())
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "skill"


def from_folder_dict(files: dict, skill_md_name: str = "SKILL.md") -> dict:
    """
    Takes a dict of {relative_path: text_content} and returns a normalized
    {skill_md, frontmatter, files} dict. Files other than SKILL.md are kept
    as supporting content.
    """
    # Case-insensitive SKILL.md lookup
    target = None
    for key in files.keys():
        if os.path.basename(key).lower() == skill_md_name.lower():
            target = key
            break
    if target is None:
        raise ValueError(f"No {skill_md_name} found in uploaded files. "
                         f"Received: {list(files.keys())[:10]}")

    skill_md = files[target]
    supporting = {k: v for k, v in files.items() if k != target}
    frontmatter, _ = parse_skill_md(skill_md)
    return {
        "skill_md": skill_md,
        "frontmatter": frontmatter,
        "files": supporting,
        "skill_md_path": target,
    }


def from_zip_bytes(zip_bytes: bytes, max_file_size: int = 500_000,
                   max_total_size: int = 5_000_000) -> dict:
    """
    Extract a zip into a {path: content} dict, then delegate to from_folder_dict.
    Enforces size caps to keep SQLite row sizes reasonable.
    """
    files = {}
    total = 0
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename
            # Skip OS cruft
            if any(seg.startswith(".") for seg in name.split("/")):
                # allow top-level .something only if it's not macOS metadata
                if "__MACOSX" in name or name.endswith(".DS_Store"):
                    continue
            if info.file_size > max_file_size:
                continue
            total += info.file_size
            if total > max_total_size:
                raise ValueError(f"Zip exceeds {max_total_size} bytes (stripped)")
            try:
                raw = zf.read(info)
                # Store as text when possible, else base64 string
                try:
                    text = raw.decode("utf-8")
                    files[name] = text
                except UnicodeDecodeError:
                    import base64
                    files[name] = "base64::" + base64.b64encode(raw).decode("ascii")
            except Exception:
                continue

    # Strip a common top-level folder prefix if present ("my-skill/SKILL.md" -> "SKILL.md")
    tops = {p.split("/", 1)[0] for p in files.keys() if "/" in p}
    if len(tops) == 1:
        prefix = tops.pop() + "/"
        files = {(k[len(prefix):] if k.startswith(prefix) else k): v for k, v in files.items()}

    return from_folder_dict(files)


def from_raw_skill_md(skill_md: str) -> dict:
    """Accept just a SKILL.md string, no supporting files."""
    frontmatter, _ = parse_skill_md(skill_md)
    return {
        "skill_md": skill_md,
        "frontmatter": frontmatter,
        "files": {},
        "skill_md_path": "SKILL.md",
    }


def token_estimate(text: str) -> int:
    """Rough estimate — 4 chars per token."""
    return max(1, len(text) // 4)
