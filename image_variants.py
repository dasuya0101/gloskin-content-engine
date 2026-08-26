#!/usr/bin/env python3
"""Project-scoped, non-destructive character image variants."""
import json
import shutil
import time
import uuid
from pathlib import Path

import character_factory


ASSET_NAMES = ("before", "opening", "scan", "after", "product_prop")


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _write_json(path, data):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
    temporary.replace(target)


def _variant_folder(metadata_root, brand, project_id, variant_id):
    return Path(metadata_root) / brand / project_id / variant_id


def list_variants(metadata_root, brand=None, project_id=None):
    root = Path(metadata_root)
    if not root.exists():
        return []
    rows = []
    for path in root.glob("*/*/*/variant.json"):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if brand and row.get("brand") != brand:
            continue
        if project_id and row.get("project_id") != project_id:
            continue
        rows.append(row)
    return sorted(rows, key=lambda row: row.get("created_at", ""), reverse=True)


def get_variant(metadata_root, variant_id):
    for row in list_variants(metadata_root):
        if row.get("variant_id") == variant_id:
            return row
    raise FileNotFoundError(f"image variant not found: {variant_id}")


def save_variant(metadata_root, variant):
    variant = dict(variant)
    variant["updated_at"] = now_iso()
    folder = _variant_folder(
        metadata_root, variant["brand"], variant["project_id"], variant["variant_id"])
    _write_json(folder / "variant.json", variant)
    return variant


def create_variant(*, metadata_root, assets_root, source_dir, source_character,
                   brand, project_id, name, provider, selected_assets,
                   prompt_snapshot, opening_style=None, product_style=None):
    selected = list(dict.fromkeys(selected_assets or []))
    invalid = [name for name in selected if name not in ASSET_NAMES]
    if invalid:
        raise ValueError("invalid variant assets: " + ", ".join(invalid))
    if not selected:
        raise ValueError("select at least one image to regenerate")
    source_dir = Path(source_dir)
    if not source_dir.exists():
        raise FileNotFoundError(f"variant source folder not found: {source_dir}")

    base_slug = (
        source_character.get("base_character_slug")
        or source_character.get("slug")
        or "character"
    )
    stamp = time.strftime("%Y%m%d%H%M%S")
    variant_id = f"var_{stamp}_{uuid.uuid4().hex[:8]}"
    asset_slug = character_factory.slugify(
        f"variant {base_slug} {name or stamp} {uuid.uuid4().hex[:5]}")
    asset_dir = Path(assets_root) / asset_slug
    asset_dir.mkdir(parents=True, exist_ok=False)

    for asset_name in ASSET_NAMES:
        source = source_dir / f"{asset_name}.png"
        if source.exists() and asset_name not in selected:
            shutil.copy2(source, asset_dir / source.name)

    variant_folder = _variant_folder(metadata_root, brand, project_id, variant_id)
    variant_folder.mkdir(parents=True, exist_ok=False)
    prompt_path = variant_folder / "prompt_config.json"
    _write_json(prompt_path, prompt_snapshot)
    character_snapshot = {
        key: value
        for key, value in source_character.items()
        if key not in {"assets", "index", "variant_id", "status"}
    }
    character_snapshot.update({
        "slug": asset_slug,
        "base_character_slug": base_slug,
        "source_asset_slug": source_character.get("slug"),
        "opening_style": opening_style,
        "product_style": product_style,
    })
    plan = character_factory.missing_asset_plan(
        character_snapshot.get("spec") or source_character.get("spec") or "character",
        asset_dir,
        opening_style=opening_style,
        product_style=product_style,
        prompt_config_path=prompt_path,
    )
    planned_names = {target["name"] for target in plan["targets"]}
    unplanned = [asset_name for asset_name in selected if asset_name not in planned_names]
    variant = {
        "schema_version": 1,
        "variant_id": variant_id,
        "asset_slug": asset_slug,
        "name": (name or f"{base_slug} variant").strip(),
        "brand": brand,
        "project_id": project_id,
        "base_character_slug": base_slug,
        "source_asset_slug": source_character.get("slug"),
        "source_variant_id": source_character.get("variant_id"),
        "provider": provider,
        "status": "planned" if plan["targets"] else "ready",
        "selected_assets": selected,
        "unplanned_assets": unplanned,
        "asset_dir": str(asset_dir),
        "prompt_config_path": str(prompt_path),
        "opening_style": plan["opening_style"],
        "product_style": plan["product_style"],
        "character": character_snapshot,
        "job_id": None,
        "error": None,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    _write_json(variant_folder / "variant.json", variant)
    return variant, plan


def effective_character(variant):
    character = dict(variant.get("character") or {})
    character.update({
        "slug": variant["asset_slug"],
        "variant_id": variant["variant_id"],
        "variant_name": variant.get("name"),
        "variant_status": variant.get("status"),
        "base_character_slug": variant.get("base_character_slug"),
        "source_asset_slug": variant.get("source_asset_slug"),
        "opening_style": variant.get("opening_style"),
        "product_style": variant.get("product_style"),
    })
    return character
