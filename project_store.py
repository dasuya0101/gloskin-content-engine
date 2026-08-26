#!/usr/bin/env python3
"""Local project definitions and project-scoped output paths."""
import json
import re
import time
from pathlib import Path


SCHEMA_VERSION = 1
PROJECT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")


def slugify(value):
    slug = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
    return slug[:48]


def default_project_id(brand_id):
    return f"{slugify(brand_id) or 'brand'}_main"


def default_projects(brand_ids):
    return [
        {
            "project_id": default_project_id(brand_id),
            "name": "Main",
            "brand": brand_id,
            "created_at": None,
        }
        for brand_id in brand_ids
    ]


def load_projects(path, brand_ids):
    target = Path(path)
    stored = []
    if target.exists():
        raw = json.loads(target.read_text(encoding="utf-8"))
        stored = raw.get("projects", []) if isinstance(raw, dict) else raw
    projects = []
    seen = set()
    for project in [*default_projects(brand_ids), *stored]:
        if not isinstance(project, dict):
            continue
        project_id = str(project.get("project_id") or "").strip()
        brand = str(project.get("brand") or "").strip()
        if not PROJECT_ID_PATTERN.fullmatch(project_id) or brand not in brand_ids:
            continue
        if project_id in seen:
            if project.get("created_at"):
                projects = [row for row in projects if row["project_id"] != project_id]
            else:
                continue
        seen.add(project_id)
        projects.append({
            "project_id": project_id,
            "name": str(project.get("name") or project_id).strip()[:80],
            "brand": brand,
            "created_at": project.get("created_at"),
        })
    return projects


def save_projects(path, projects):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": SCHEMA_VERSION, "projects": projects}
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def create_project(path, brand_ids, *, name, brand):
    clean_name = str(name or "").strip()
    if not clean_name:
        raise ValueError("project name is required")
    if brand not in brand_ids:
        raise ValueError(f"unknown project brand: {brand}")
    projects = load_projects(path, brand_ids)
    base = slugify(clean_name) or "project"
    if not base.startswith(f"{slugify(brand)}_"):
        base = f"{slugify(brand)}_{base}"
    project_id = base[:64]
    suffix = 2
    used = {row["project_id"] for row in projects}
    while project_id in used:
        tail = f"_{suffix}"
        project_id = f"{base[:64-len(tail)]}{tail}"
        suffix += 1
    project = {
        "project_id": project_id,
        "name": clean_name[:80],
        "brand": brand,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    projects.append(project)
    save_projects(path, projects)
    return project


def require_project(path, brand_ids, project_id, brand):
    requested = str(project_id or default_project_id(brand)).strip()
    project = next(
        (row for row in load_projects(path, brand_ids) if row["project_id"] == requested),
        None,
    )
    if not project:
        raise ValueError(f"unknown project: {requested}")
    if project["brand"] != brand:
        raise ValueError(f"project {requested} belongs to {project['brand']}, not {brand}")
    return project


def output_paths(root, brand, project_id):
    root = Path(root)
    return {
        "output": root / "output" / brand / project_id,
        "posts": root / "posts" / brand / project_id,
        "screenshots": root / "screenshots" / brand / project_id,
        "videos": root / "videos" / brand / project_id,
        "recipes": root / "workspace_data" / "recipes",
    }
