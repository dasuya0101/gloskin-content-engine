#!/usr/bin/env python3
"""Durable local snapshots for remixing slideshow and talking-head setups."""
import json
import os
import time
from pathlib import Path


SCHEMA_VERSION = 1
WORKFLOWS = {"slideshow", "talking_head", "text"}


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _public_path(root, recipe_id):
    return Path(root) / f"{recipe_id}.json"


def list_recipes(root, *, brand=None):
    folder = Path(root)
    if not folder.exists():
        return []
    rows = []
    for path in folder.glob("recipe_*.json"):
        try:
            recipe = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if brand and recipe.get("brand") != brand:
            continue
        rows.append(recipe)
    return sorted(rows, key=lambda row: row.get("updated_at") or "", reverse=True)


def get_recipe(root, recipe_id):
    if not str(recipe_id or "").startswith("recipe_"):
        return None
    path = _public_path(root, recipe_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_recipe(root, payload):
    name = str(payload.get("name") or "").strip()
    brand = str(payload.get("brand") or "").strip()
    project_id = str(payload.get("project_id") or "").strip()
    workflow = str(payload.get("workflow") or "").strip()
    if not name:
        raise ValueError("recipe name is required")
    if not brand or not project_id:
        raise ValueError("recipe brand and project_id are required")
    if workflow not in WORKFLOWS:
        raise ValueError(f"unsupported recipe workflow: {workflow}")
    now = _now()
    recipe_id = f"recipe_{time.strftime('%Y%m%d%H%M%S')}_{os.urandom(4).hex()}"
    recipe = {
        "schema_version": SCHEMA_VERSION,
        "recipe_id": recipe_id,
        "name": name[:120],
        "brand": brand,
        "project_id": project_id,
        "workflow": workflow,
        "source_batch_id": payload.get("source_batch_id"),
        "notes": str(payload.get("notes") or "").strip()[:2000],
        "setup": payload.get("setup") if isinstance(payload.get("setup"), dict) else {},
        "prompt_snapshot": (
            payload.get("prompt_snapshot")
            if isinstance(payload.get("prompt_snapshot"), dict) else {}
        ),
        "creative_snapshot": (
            payload.get("creative_snapshot")
            if isinstance(payload.get("creative_snapshot"), list) else []
        ),
        "created_at": now,
        "updated_at": now,
    }
    folder = Path(root)
    folder.mkdir(parents=True, exist_ok=True)
    _public_path(folder, recipe_id).write_text(
        json.dumps(recipe, indent=2), encoding="utf-8")
    return recipe


def delete_recipe(root, recipe_id):
    recipe = get_recipe(root, recipe_id)
    if not recipe:
        return False
    _public_path(root, recipe_id).unlink()
    return True
