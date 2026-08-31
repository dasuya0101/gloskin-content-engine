#!/usr/bin/env python3
"""
api_server.py - local dashboard API for the content engine
==========================================================

Run:
  python api_server.py

Then open:
  http://127.0.0.1:5055

This server is intentionally local-first. It serves dashboard.html, reads and
writes posts.json, starts content_job.py in the background, and exposes generated
files for preview from the dashboard.
"""
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_file
from PIL import Image, ImageOps, UnidentifiedImageError

import manifest
import import_metrics
import metrics_refresh
import publish as publish_bridge
import app_assets
import character_factory
import creative_recipes
import heygen_adapter
import image_queue
import image_router
import image_variants
import project_store
import video_queue
from brand_loader import DEFAULT_BRAND, BrandConfigError, available_brands, brand_summary, load_brand


ROOT = Path(__file__).resolve().parent
POSTS_FILE = ROOT / "posts.json"
RUNS_DIR = ROOT / "runs"
OUTPUT_DIR = ROOT / "output"
PACKAGE_DIR = ROOT / "posts"
ROSTER_FILE = ROOT / "roster.json"
CHARACTER_ASSETS_DIR = ROOT / "assets"
CHARACTER_ASSET_NAMES = ("before", "opening", "scan", "after", "product_prop")
IMAGE_GENERATION_LOCK = threading.Lock()
IMAGE_JOBS_DIR = ROOT / "image_jobs"
VIDEO_JOBS_DIR = ROOT / "video_jobs"
SCREENSHOT_DIR = ROOT / "screenshots"
WORKSPACE_DATA_DIR = ROOT / "workspace_data"
PROJECTS_FILE = WORKSPACE_DATA_DIR / "projects.json"
RECIPES_DIR = WORKSPACE_DATA_DIR / "recipes"
VARIANTS_DIR = WORKSPACE_DATA_DIR / "image_variants"

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 80 * 1024 * 1024


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def safe_path(rel_path):
    if not rel_path:
        abort(404)
    candidate = (ROOT / rel_path).resolve()
    if candidate != ROOT and ROOT not in candidate.parents:
        abort(404)
    if not candidate.exists():
        abort(404)
    return candidate


def safe_optional_file(rel_path):
    if not rel_path:
        abort(400, description="missing file path")
    path = safe_path(rel_path)
    if path.is_dir():
        abort(400, description="expected a file path")
    return path


def root_rel(path):
    return str(Path(path).resolve().relative_to(ROOT)).replace("\\", "/")


def read_json(path, default):
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_roster():
    roster = read_json(ROSTER_FILE, {"template": "scan_results", "characters": []})
    roster.setdefault("template", "scan_results")
    roster.setdefault("characters", [])
    return roster


def unique_character_slug(roster, desired, current_index=None):
    base = character_factory.slugify(desired) or "character"
    used = {
        character.get("slug")
        for index, character in enumerate(roster.get("characters", []))
        if index != current_index and character.get("slug")
    }
    slug = base
    suffix = 2
    while slug in used:
        slug = f"{base}_{suffix}"
        suffix += 1
    return slug


def fixture_set_record(slug):
    metadata_path = CHARACTER_ASSETS_DIR / slug / "fixture_set.json"
    if not metadata_path.exists():
        return None
    metadata = read_json(metadata_path, {})
    levels = {}
    for severity, level in metadata.get("levels", {}).items():
        relative_path = level.get("path") or f"fixtures/{severity}.png"
        path = CHARACTER_ASSETS_DIR / slug / relative_path
        levels[severity] = {
            "id": level.get("id"),
            "severity": severity,
            "exists": path.exists(),
            "path": root_rel(path) if path.exists() else None,
            "sha256": level.get("sha256"),
            "expected_glo_score_band": level.get("expected_glo_score_band"),
        }
    return {
        key: metadata.get(key)
        for key in (
            "identity_family", "skin_tone_mst", "fitzpatrick_ref", "provenance",
            "qa_scope", "qa_note", "not_longitudinal", "usage_note", "default_mapping",
        )
    } | {"levels": levels, "metadata_path": root_rel(metadata_path)}


def character_asset_record(index, character):
    slug = character.get("slug") or ""
    assets = {}
    for name in CHARACTER_ASSET_NAMES:
        path = CHARACTER_ASSETS_DIR / slug / f"{name}.png" if slug else None
        exists = bool(path and path.exists())
        assets[name] = {
            "exists": exists,
            "path": root_rel(path) if exists else None,
        }
    fixture_set = fixture_set_record(slug) if slug else None
    return {
        **character,
        "index": index,
        "slug": slug,
        "assets": assets,
        "fixture_set": fixture_set or character.get("fixture_set"),
    }


def asset_record_for_slug(slug):
    assets = {}
    for name in CHARACTER_ASSET_NAMES:
        path = CHARACTER_ASSETS_DIR / slug / f"{name}.png"
        exists = path.exists()
        assets[name] = {
            "exists": exists,
            "path": root_rel(path) if exists else None,
        }
    return assets


def image_provider_payload():
    return [{
        "id": "codex_local",
        "label": "Codex subscription / local queue",
        "mode": "queue",
        "can_generate": True,
        "can_edit": True,
        "configured": True,
        "missing_env": [],
        "missing_edit_env": [],
        "notes": "Processed by a signed-in Codex task; no direct API billing.",
    }, *image_router.list_providers()]


def public_image_variant(variant, jobs_by_id=None):
    row = dict(variant)
    job = (jobs_by_id or {}).get(row.get("job_id"))
    status = row.get("status") or "planned"
    if job:
        status = "ready" if job.get("status") == "completed" else job.get("status", status)
    assets = asset_record_for_slug(row["asset_slug"])
    required = ["before", "scan", "after"]
    if row.get("opening_style") and row.get("opening_style") != "selfie":
        required.append("opening")
    if row.get("product_style") and row.get("product_style") != "none":
        required.append("product_prop")
    if all(assets[name]["exists"] for name in required):
        status = "ready"
    effective = image_variants.effective_character({**row, "status": status})
    return {
        **row,
        "status": status,
        "assets": assets,
        "character": {**effective, "assets": assets},
        "job": ({key: job.get(key) for key in ("job_id", "status", "error")} if job else None),
    }


def project_variants(brand_id, project_id):
    jobs = {job.get("job_id"): job for job in image_queue.list_jobs(IMAGE_JOBS_DIR)}
    return [
        public_image_variant(variant, jobs)
        for variant in image_variants.list_variants(
            VARIANTS_DIR, brand=brand_id, project_id=project_id)
    ]


def roster_payload(brand=None):
    roster = load_roster()
    return {
        "template": roster.get("template"),
        "can_generate": bool(brand and brand.prompt_path("image_character")),
        "characters": [
            character_asset_record(index, character)
            for index, character in enumerate(roster.get("characters", []))
        ],
    }


def normalize_uploaded_image(upload):
    try:
        with Image.open(upload.stream) as source:
            image = ImageOps.exif_transpose(source)
            image.thumbnail((2048, 3072), Image.Resampling.LANCZOS)
            if image.mode not in {"RGB", "RGBA"}:
                image = image.convert("RGBA" if "transparency" in image.info else "RGB")
            return image.copy()
    except (UnidentifiedImageError, OSError) as exc:
        abort(400, description=f"{upload.filename or 'upload'} is not a supported image: {exc}")


def requested_brand(default=DEFAULT_BRAND):
    data = request.get_json(force=True, silent=True) if request.method in {"POST", "PATCH"} else None
    brand_id = request.args.get("brand") or ((data or {}).get("brand")) or default
    try:
        return load_brand(brand_id)
    except BrandConfigError as exc:
        abort(400, description=str(exc))


def brand_ids():
    return [brand.brand_id for brand in available_brands()]


def projects_payload():
    rows = project_store.load_projects(PROJECTS_FILE, brand_ids())
    return [
        {
            **row,
            "paths": {
                key: root_rel(path)
                for key, path in project_store.output_paths(
                    ROOT, row["brand"], row["project_id"]).items()
                if key != "recipes"
            },
        }
        for row in rows
    ]


def requested_project(brand, data=None):
    data = data or (
        request.get_json(force=True, silent=True)
        if request.method in {"POST", "PATCH", "DELETE"} else {}
    ) or {}
    project_id = request.args.get("project_id") or data.get("project_id")
    try:
        return project_store.require_project(
            PROJECTS_FILE, brand_ids(), project_id, brand.brand_id)
    except ValueError as exc:
        abort(400, description=str(exc))


def default_account_for(brand_id):
    try:
        return load_brand(brand_id or DEFAULT_BRAND).default_account
    except BrandConfigError:
        return "TODO"


def normalize_post(post):
    p = manifest.normalize_post(dict(post))
    p.setdefault("brand", DEFAULT_BRAND)
    p.setdefault("caption", None)
    p.setdefault("package", {
        "dir": None,
        "slides_dir": None,
        "video": None,
        "caption": None,
        "brief": None,
        "metadata": None,
    })
    p.setdefault("publish_queue", {
        "status": "draft",
        "target_account": default_account_for(p.get("brand")),
        "notes": None,
        "updated_at": None,
    })
    if not p["publish_queue"].get("target_account"):
        p["publish_queue"]["target_account"] = default_account_for(p.get("brand"))
    p.setdefault("publish", {"platform": None, "account": None, "url": None, "posted_at": None})
    p.setdefault("distribution", [])
    p.setdefault("metrics", {})
    p.setdefault("compliance", {
        "status": "needs_review", "violations": [], "checked_at": None,
    })
    return p


def run_support_path(run_id, name):
    return RUNS_DIR / "support" / f"{run_id}.{name}.json"


def run_meta_path(run_id):
    return RUNS_DIR / f"{run_id}.json"


def run_log_path(run_id):
    return RUNS_DIR / f"{run_id}.log"


def update_run(run_id, **updates):
    meta_path = run_meta_path(run_id)
    meta = read_json(meta_path, {})
    meta.update(updates)
    write_json(meta_path, meta)
    return meta


def tail_text(path, chars=8000):
    p = Path(path)
    if not p.exists():
        return ""
    text = p.read_text(encoding="utf-8", errors="replace")
    return text[-chars:]


def run_rows():
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for meta_file in sorted(RUNS_DIR.glob("*.json"), reverse=True):
        meta = read_json(meta_file, {})
        run_id = meta.get("run_id") or meta_file.stem
        meta["run_id"] = run_id
        meta["tail"] = tail_text(run_log_path(run_id), 2000)
        rows.append(meta)
    return rows


def batch_status(batch):
    run = batch.get("run") or {}
    if run.get("status") in {"queued", "running", "failed"}:
        return run["status"]
    jobs = batch.get("jobs") or []
    if jobs:
        states = {job.get("status") for job in jobs}
        if "failed" in states:
            return "needs_review"
        if states & {"queued", "processing", "submitted"}:
            return "rendering"
        if states == {"completed"}:
            return "completed"
        return "draft"
    posts = batch.get("posts") or []
    if posts:
        queue_states = {(post.get("publish_queue") or {}).get("status") for post in posts}
        compliance_states = {(post.get("compliance") or {}).get("status") for post in posts}
        if queue_states & {"failed", "needs_edit"} or compliance_states & {"fail", "needs_review", "hard_block"}:
            return "needs_review"
        if queue_states == {"posted"}:
            return "posted"
        if "ready_to_post" in queue_states:
            return "ready"
        return "completed"
    return run.get("status") or "draft"


def collect_batches():
    batches = {}

    def ensure(batch_id, workflow, brand, project_id=None, created_at=None, legacy=False):
        key = str(batch_id)
        active_brand = brand or DEFAULT_BRAND
        batch = batches.setdefault(key, {
            "batch_id": key,
            "workflow": workflow,
            "brand": active_brand,
            "project_id": project_id or project_store.default_project_id(active_brand),
            "created_at": created_at,
            "legacy": bool(legacy),
            "posts": [],
            "jobs": [],
            "run": None,
        })
        if created_at and (not batch.get("created_at") or created_at < batch["created_at"]):
            batch["created_at"] = created_at
        return batch

    for raw_post in manifest.all_posts(str(POSTS_FILE)):
        post = normalize_post(raw_post)
        legacy_date = (post.get("created_at") or "unknown")[:10].replace("-", "")
        batch_id = post.get("batch_id") or (
            f"legacy_{post.get('brand')}_{post.get('workflow')}_{legacy_date}"
        )
        batch = ensure(
            batch_id, post.get("workflow"), post.get("brand"), post.get("project_id"),
            post.get("created_at"), legacy=not bool(post.get("batch_id")))
        batch["posts"].append(post)

    for job in video_queue.list_jobs(VIDEO_JOBS_DIR):
        public = public_video_job(job)
        legacy_date = (public.get("created_at") or "unknown")[:10].replace("-", "")
        batch_id = public.get("batch_id") or (
            f"legacy_{public.get('brand')}_{public.get('workflow') or 'talking_head'}_{legacy_date}"
        )
        batch = ensure(
            batch_id, public.get("workflow") or "talking_head", public.get("brand"),
            public.get("project_id"),
            public.get("created_at"), legacy=not bool(public.get("batch_id")))
        batch["jobs"].append(public)

    for run in run_rows():
        config = run.get("config") or {}
        workflow = config.get("workflow")
        if workflow not in {"slideshow", "text"}:
            continue
        batch = ensure(
            run["run_id"], workflow, config.get("brand"), config.get("project_id"),
            run.get("started_at"))
        batch["run"] = run

    for batch in batches.values():
        slugs = {
            (post.get("character") or {}).get("slug")
            for post in batch["posts"]
            if (post.get("character") or {}).get("slug")
        }
        slugs.update(job.get("slug") for job in batch["jobs"] if job.get("slug"))
        batch["character_count"] = len(slugs)
        batch["item_count"] = len(batch["posts"]) + len(batch["jobs"])
        batch["status"] = batch_status(batch)
    return sorted(
        batches.values(), key=lambda batch: batch.get("created_at") or "", reverse=True)


def background_run(run_id, cmd, env):
    log_path = run_log_path(run_id)
    update_run(run_id, status="running", log=str(log_path.relative_to(ROOT)))
    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        log.write(f"$ {' '.join(cmd)}\n\n")
        log.flush()
        proc = subprocess.Popen(
            cmd,
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        rc = proc.wait()
    update_run(
        run_id,
        status="success" if rc == 0 else "failed",
        returncode=rc,
        finished_at=now_iso(),
    )


@app.get("/")
@app.get("/dashboard.html")
def dashboard():
    return send_file(ROOT / "dashboard.html")


@app.get("/files/<path:rel_path>")
def files(rel_path):
    return send_file(safe_path(rel_path))


@app.get("/api/config")
def config():
    brand = requested_brand()
    project = requested_project(brand)
    roster = load_roster()
    return jsonify({
        "default_brand": DEFAULT_BRAND,
        "active_brand": brand_summary(brand),
        "brands": [brand_summary(b) for b in available_brands()],
        "projects": projects_payload(),
        "active_project": project,
        "default_account": brand.default_account,
        "image_provider": os.environ.get("DASHBOARD_IMAGE_PROVIDER", "codex_local"),
        "heygen": heygen_adapter.connection_status(),
        "roster_count": len(roster.get("characters", [])),
        "publish_integrations": {
            "vendor": publish_bridge.vendor_plan(),
            **{
                name: publish_bridge.api_plan(name)
                for name in ["tiktok", "instagram", "facebook"]
            },
        },
        "publish_accounts": publish_bridge.account_registry_payload(),
        "metrics_integrations": {
            name: metrics_refresh.api_plan(name)
            for name in sorted(metrics_refresh.API_PLANS)
        },
    })


@app.get("/api/projects")
def projects():
    brand = (request.args.get("brand") or "").strip()
    rows = projects_payload()
    if brand:
        rows = [row for row in rows if row["brand"] == brand]
    return jsonify(rows)


@app.get("/api/image-providers")
def image_providers():
    return jsonify(image_provider_payload())


@app.get("/api/image-variants")
def list_image_variants():
    brand = requested_brand()
    project = requested_project(brand)
    return jsonify(project_variants(brand.brand_id, project["project_id"]))


def resolve_variant_source(brand_id, project_id, source_slug):
    roster_data = load_roster()
    for index, character in enumerate(roster_data.get("characters", [])):
        if character.get("slug") == source_slug:
            return character_asset_record(index, character), CHARACTER_ASSETS_DIR / source_slug
    for variant in project_variants(brand_id, project_id):
        if variant.get("asset_slug") == source_slug:
            return variant["character"], CHARACTER_ASSETS_DIR / source_slug
    raise FileNotFoundError(f"character or variant not found: {source_slug}")


@app.post("/api/image-variants")
def create_image_variant():
    data = request.get_json(force=True, silent=True) or {}
    brand = requested_brand()
    project = requested_project(brand, data)
    source_slug = (data.get("source_asset_slug") or "").strip()
    if not source_slug:
        abort(400, description="source_asset_slug is required")
    try:
        source_character, source_dir = resolve_variant_source(
            brand.brand_id, project["project_id"], source_slug)
    except FileNotFoundError as exc:
        abort(404, description=str(exc))

    selected_assets = data.get("selected_assets") or []
    if not isinstance(selected_assets, list):
        abort(400, description="selected_assets must be a list")
    opening_style = (data.get("opening_style") or "").strip() or None
    product_style = (data.get("product_style") or "").strip() or None
    if opening_style and opening_style not in character_factory.OPENING_PRESETS:
        abort(400, description="invalid opening_style")
    if product_style and product_style not in character_factory.PRODUCT_PROP_PRESETS:
        abort(400, description="invalid product_style")
    if "opening" in selected_assets and (opening_style or "selfie") == "selfie":
        abort(400, description="choose a generated opening style before regenerating opening")
    if "product_prop" in selected_assets and (product_style or "none") == "none":
        abort(400, description="choose a product style before regenerating product_prop")

    provider_id = (data.get("provider") or "codex_local").strip()
    providers = {row["id"]: row for row in image_provider_payload()}
    provider = providers.get(provider_id)
    if not provider:
        abort(400, description=f"unknown image provider: {provider_id}")
    if provider["mode"] == "api" and not provider["configured"]:
        abort(400, description=(
            f"{provider['label']} is missing environment variables: "
            + ", ".join(provider["missing_env"])
        ))
    edit_assets = {"before", "opening", "scan", "after"}
    required_face_assets = {"before", "scan", "after"}
    if (opening_style or "selfie") != "selfie":
        required_face_assets.add("opening")
    source_assets = source_character.get("assets") or {}
    needs_face_work = bool(edit_assets.intersection(selected_assets)) or any(
        not (source_assets.get(name) or {}).get("exists") for name in required_face_assets)
    if provider["mode"] == "api" and needs_face_work and not provider["can_edit"]:
        missing = provider.get("missing_edit_env") or []
        detail = f" ({', '.join(missing)})" if missing else ""
        abort(400, description=(
            f"{provider['label']} cannot make identity-preserving reference edits{detail}"
        ))

    base_prompts = character_factory.load_prompt_config(brand.prompt_path("image_character"))
    supplied_prompts = data.get("prompt_snapshot") or {}
    if supplied_prompts and not isinstance(supplied_prompts, dict):
        abort(400, description="prompt_snapshot must be an object")
    prompt_snapshot = {
        "before_template": supplied_prompts.get("before_template") or base_prompts["before_template"],
        "opening_style": opening_style or supplied_prompts.get("opening_style") or base_prompts["opening_style"],
        "opening_prompt": supplied_prompts.get("opening_prompt", base_prompts["opening_prompt"]),
        "scan_prompt": supplied_prompts.get("scan_prompt") or base_prompts["scan_prompt"],
        "after_prompt": supplied_prompts.get("after_prompt") or base_prompts["after_prompt"],
        "product_style": product_style or supplied_prompts.get("product_style") or base_prompts["product_style"],
        "product_prop_prompt": supplied_prompts.get(
            "product_prop_prompt", base_prompts["product_prop_prompt"]),
        "product_slide_caption": supplied_prompts.get(
            "product_slide_caption") or base_prompts["product_slide_caption"],
    }
    try:
        variant, plan = image_variants.create_variant(
            metadata_root=VARIANTS_DIR,
            assets_root=CHARACTER_ASSETS_DIR,
            source_dir=source_dir,
            source_character=source_character,
            brand=brand.brand_id,
            project_id=project["project_id"],
            name=(data.get("name") or "").strip(),
            provider=provider_id,
            selected_assets=selected_assets,
            prompt_snapshot=prompt_snapshot,
            opening_style=prompt_snapshot["opening_style"],
            product_style=prompt_snapshot["product_style"],
        )
    except (ValueError, FileNotFoundError, FileExistsError) as exc:
        abort(400, description=str(exc))

    if provider_id == "codex_local":
        targets = [{
            **target,
            "reference_path": root_rel(target["reference_path"])
            if target.get("reference_path") else None,
            "target_path": root_rel(target["target_path"]),
        } for target in plan["targets"]]
        job, created = image_queue.enqueue_job({
            "worker": "codex_builtin_imagegen",
            "brand": brand.brand_id,
            "project_id": project["project_id"],
            "variant_id": variant["variant_id"],
            "slug": variant["asset_slug"],
            "spec": source_character.get("spec"),
            "opening_style": variant["opening_style"],
            "product_style": variant["product_style"],
            "character_dir": root_rel(variant["asset_dir"]),
            "targets": targets,
            "note": "Process targets in order with Codex image generation; preserve identity references.",
        }, queue_root=IMAGE_JOBS_DIR)
        variant.update({"job_id": job["job_id"], "status": job["status"]})
        variant = image_variants.save_variant(VARIANTS_DIR, variant)
        return jsonify({
            "created": created,
            "variant": public_image_variant(variant, {job["job_id"]: job}),
            "job": {key: job.get(key) for key in ("job_id", "status", "targets")},
        }), 202

    try:
        with IMAGE_GENERATION_LOCK:
            result = character_factory.generate_missing_assets(
                source_character.get("spec") or "character",
                variant["asset_dir"],
                opening_style=variant["opening_style"],
                product_style=variant["product_style"],
                prompt_config_path=variant["prompt_config_path"],
                provider=provider_id,
                allow_generate_fallback=False,
            )
        variant.update({"status": "ready", "generated": result["generated"]})
        variant = image_variants.save_variant(VARIANTS_DIR, variant)
        return jsonify({"variant": public_image_variant(variant), "generation": result}), 201
    except Exception as exc:
        variant.update({"status": "failed", "error": str(exc)})
        variant = image_variants.save_variant(VARIANTS_DIR, variant)
        return jsonify({
            "error": f"image variant generation failed: {exc}",
            "variant": public_image_variant(variant),
        }), 502


@app.post("/api/projects")
def create_project():
    data = request.get_json(force=True, silent=True) or {}
    brand = requested_brand()
    try:
        project = project_store.create_project(
            PROJECTS_FILE,
            brand_ids(),
            name=data.get("name"),
            brand=brand.brand_id,
        )
    except ValueError as exc:
        abort(400, description=str(exc))
    return jsonify({
        **project,
        "paths": {
            key: root_rel(path)
            for key, path in project_store.output_paths(
                ROOT, project["brand"], project["project_id"]).items()
            if key != "recipes"
        },
    }), 201


@app.get("/api/roster")
def roster():
    return jsonify(roster_payload(requested_brand()))


@app.post("/api/roster/characters")
def save_roster_character():
    roster_data = load_roster()
    characters = roster_data["characters"]
    raw_index = (request.form.get("index") or "").strip()
    if raw_index:
        try:
            index = int(raw_index)
        except ValueError:
            abort(400, description="invalid roster index")
        if index < 0 or index >= len(characters):
            abort(404, description="roster character not found")
        existing = dict(characters[index])
    else:
        index = len(characters)
        existing = {}

    spec = (request.form.get("spec") or existing.get("spec") or "").strip()
    if not spec:
        abort(400, description="character spec is required")
    existing_slug = existing.get("slug")
    requested_slug = (request.form.get("slug") or existing_slug or spec).strip()
    slug = existing_slug or unique_character_slug(roster_data, requested_slug, index)

    def score(name, default):
        raw = (request.form.get(name) or "").strip()
        if not raw:
            return int(existing.get(name, default))
        try:
            value = int(raw)
        except ValueError:
            abort(400, description=f"{name} must be a number")
        if value < 0 or value > 100:
            abort(400, description=f"{name} must be between 0 and 100")
        return value

    uploads = {}
    for name in CHARACTER_ASSET_NAMES:
        upload = request.files.get(name)
        if upload and upload.filename:
            uploads[name] = normalize_uploaded_image(upload)

    character = {
        **existing,
        "slug": slug,
        "spec": spec,
        "before_score": score("before_score", 54),
        "after_score": score("after_score", 87),
        "hook": (
            request.form.get("hook")
            if "hook" in request.form
            else existing.get("hook", "")
        ).strip(),
    }
    if index == len(characters):
        characters.append(character)
    else:
        characters[index] = character

    character_dir = CHARACTER_ASSETS_DIR / slug
    character_dir.mkdir(parents=True, exist_ok=True)
    for name, image in uploads.items():
        image.save(character_dir / f"{name}.png", format="PNG", optimize=True)
    write_json(ROSTER_FILE, roster_data)
    return jsonify({
        "character": character_asset_record(index, character),
        "roster": roster_payload(),
        "uploaded": sorted(uploads),
    })


@app.post("/api/roster/characters/<int:index>/generate-missing")
def generate_missing_character_assets(index):
    data = request.get_json(force=True, silent=True) or {}
    roster_data = load_roster()
    characters = roster_data["characters"]
    if index < 0 or index >= len(characters):
        abort(404, description="roster character not found")
    character = characters[index]
    brand_id = data.get("brand") or DEFAULT_BRAND
    try:
        brand = load_brand(brand_id)
    except BrandConfigError as exc:
        abort(400, description=str(exc))
    prompt_config_path = brand.prompt_path("image_character")
    if not prompt_config_path:
        abort(400, description=f"{brand.display_name} does not define character image prompts")

    if not character.get("slug"):
        character["slug"] = unique_character_slug(roster_data, character.get("spec") or "character", index)
        write_json(ROSTER_FILE, roster_data)
    provider = (data.get("provider") or os.environ.get("IMAGE_PROVIDER") or "openai").strip()
    provider_info = {row["id"]: row for row in image_provider_payload()}.get(provider)
    if not provider_info or provider_info["mode"] != "api":
        abort(400, description=f"unknown direct image provider: {provider}")
    if not provider_info["configured"]:
        abort(400, description=(
            f"{provider_info['label']} is missing environment variables: "
            + ", ".join(provider_info["missing_env"])
        ))
    if not provider_info["can_edit"]:
        abort(400, description=f"{provider_info['label']} cannot edit reference images")
    try:
        with IMAGE_GENERATION_LOCK:
            result = character_factory.generate_missing_assets(
                character["spec"],
                CHARACTER_ASSETS_DIR / character["slug"],
                opening_style=(data.get("opening_style") or None),
                product_style=(data.get("product_style") or None),
                prompt_config_path=prompt_config_path,
                provider=provider,
                allow_generate_fallback=False,
            )
    except Exception as exc:
        message = str(exc)
        if getattr(exc, "status_code", None) == 401 or "invalid_api_key" in message:
            return jsonify({
                "error": (
                    "OpenAI rejected OPENAI_API_KEY. Replace it in .env with an active "
                    "OpenAI Platform API key; ChatGPT/Codex subscriptions do not include API billing."
                )
            }), 502
        return jsonify({"error": f"image generation failed: {message}"}), 502
    return jsonify({
        "character": character_asset_record(index, character),
        "generation": result,
    })


@app.post("/api/roster/characters/<int:index>/queue-missing")
def queue_missing_character_assets(index):
    data = request.get_json(force=True, silent=True) or {}
    roster_data = load_roster()
    characters = roster_data["characters"]
    if index < 0 or index >= len(characters):
        abort(404, description="roster character not found")
    character = characters[index]
    brand_id = data.get("brand") or DEFAULT_BRAND
    try:
        brand = load_brand(brand_id)
    except BrandConfigError as exc:
        abort(400, description=str(exc))
    prompt_config_path = brand.prompt_path("image_character")
    if not prompt_config_path:
        abort(400, description=f"{brand.display_name} does not define character image prompts")
    if not character.get("slug"):
        character["slug"] = unique_character_slug(
            roster_data, character.get("spec") or "character", index)
        write_json(ROSTER_FILE, roster_data)

    plan = character_factory.missing_asset_plan(
        character["spec"],
        CHARACTER_ASSETS_DIR / character["slug"],
        opening_style=(data.get("opening_style") or None),
        product_style=(data.get("product_style") or None),
        prompt_config_path=prompt_config_path,
    )
    targets = []
    for target in plan["targets"]:
        targets.append({
            **target,
            "reference_path": root_rel(target["reference_path"])
            if target.get("reference_path") else None,
            "target_path": root_rel(target["target_path"]),
        })
    if not targets:
        return jsonify({
            "queued": False,
            "already_ready": True,
            "character": character_asset_record(index, character),
        })

    job, created = image_queue.enqueue_job({
        "worker": "codex_builtin_imagegen",
        "brand": brand.brand_id,
        "character_index": index,
        "slug": character["slug"],
        "spec": character["spec"],
        "opening_style": plan["opening_style"],
        "product_style": plan["product_style"],
        "character_dir": root_rel(plan["directory"]),
        "targets": targets,
        "note": "Process with Codex built-in image generation; never overwrite existing targets.",
    }, queue_root=IMAGE_JOBS_DIR)
    job.pop("queue_file", None)
    return jsonify({
        "queued": True,
        "created": created,
        "job": job,
        "character": character_asset_record(index, character),
    }), 202 if created else 200


@app.get("/api/image-jobs")
def image_jobs():
    jobs = image_queue.list_jobs(IMAGE_JOBS_DIR)
    slug = (request.args.get("slug") or "").strip()
    if slug:
        jobs = [job for job in jobs if job.get("slug") == slug]
    for job in jobs:
        job.pop("queue_file", None)
    return jsonify(jobs[:50])


def public_video_job(job):
    result = dict(job)
    result.pop("queue_file", None)
    result["script"] = result.get("script") or ""
    result.setdefault(
        "project_id", project_store.default_project_id(result.get("brand") or DEFAULT_BRAND))
    return result


@app.get("/api/heygen/status")
def heygen_status():
    status = heygen_adapter.connection_status()
    jobs = video_queue.list_jobs(VIDEO_JOBS_DIR)
    status["jobs"] = {
        state: sum(1 for job in jobs if job.get("status") == state)
        for state in video_queue.STATES
    }
    return jsonify(status)


@app.post("/api/heygen/test")
def test_heygen_connection():
    if not heygen_adapter.connection_status()["api_key_configured"]:
        abort(409, description="HEYGEN_API_KEY is not configured in .env")
    try:
        user = heygen_adapter.HeyGenClient().current_user()
    except heygen_adapter.HeyGenError as exc:
        abort(502, description=f"HeyGen connection failed: {exc}")
    wallet = user.get("wallet") if isinstance(user, dict) else None
    return jsonify({
        "connected": True,
        "mode": "api_key",
        "wallet": wallet,
    })


@app.get("/api/heygen/jobs")
def heygen_jobs():
    jobs = video_queue.list_jobs(VIDEO_JOBS_DIR)
    slug = (request.args.get("slug") or "").strip()
    if slug:
        jobs = [job for job in jobs if job.get("slug") == slug]
    return jsonify([public_video_job(job) for job in jobs[:50]])


def prepare_heygen_job(data, roster_data=None, batch_id=None):
    try:
        index = int(data.get("character_index"))
    except (TypeError, ValueError):
        abort(400, description="character_index is required")
    roster_data = roster_data or load_roster()
    characters = roster_data["characters"]
    if index < 0 or index >= len(characters):
        abort(404, description="roster character not found")
    character = characters[index]
    slug = character.get("slug")
    if not slug:
        abort(400, description="save the character before queueing a video")

    source_asset = (data.get("source_asset") or "after").strip()
    if source_asset not in {"before", "after", "opening"}:
        abort(400, description="source_asset must be before, after, or opening")
    portrait = CHARACTER_ASSETS_DIR / slug / f"{source_asset}.png"
    if not portrait.exists():
        abort(409, description=f"{source_asset}.png is missing for {slug}")

    script = (data.get("script") or "").strip()
    if len(script) < 10:
        abort(400, description="video script must be at least 10 characters")
    if len(script) > 5000:
        abort(400, description="video script must be 5000 characters or fewer")
    if not data.get("consent_confirmed"):
        abort(400, description="confirm character and voice consent before queueing")

    auth_mode = (data.get("auth_mode") or "oauth_mcp").strip()
    if auth_mode not in {"oauth_mcp", "api_key"}:
        abort(400, description="auth_mode must be oauth_mcp or api_key")
    mapping = character.get("heygen") or {}
    voice_id = (data.get("voice_id") or mapping.get("voice_id") or heygen_adapter.env_value("HEYGEN_VOICE_ID") or "").strip()
    mapped_avatar_id = mapping.get("avatar_id") if data.get("use_character_avatar", True) else None
    avatar_id = (data.get("avatar_id") or mapped_avatar_id or "").strip()
    if auth_mode == "api_key" and not voice_id:
        abort(400, description="voice_id or HEYGEN_VOICE_ID is required for API generation")

    brand_id = data.get("brand") or DEFAULT_BRAND
    try:
        project = project_store.require_project(
            PROJECTS_FILE, brand_ids(), data.get("project_id"), brand_id)
    except ValueError as exc:
        abort(400, description=str(exc))
    job_id = f"vid_{time.strftime('%Y%m%d%H%M%S')}_{os.urandom(4).hex()}"
    output_path = (
        Path("videos") / brand_id / project["project_id"] / slug / f"{job_id}.mp4"
    )
    return {
        "job_id": job_id,
        "batch_id": batch_id,
        "workflow": "talking_head",
        "clip_role": data.get("clip_role") or source_asset,
        "worker": "heygen_mcp_oauth" if auth_mode == "oauth_mcp" else "heygen_api_v3",
        "auth_mode": auth_mode,
        "brand": brand_id,
        "project_id": project["project_id"],
        "character_index": index,
        "slug": slug,
        "character_spec": character.get("spec"),
        "source_asset": source_asset,
        "portrait_path": root_rel(portrait),
        "script": script,
        "title": (data.get("title") or f"{slug} talking head").strip()[:200],
        "voice_id": voice_id or None,
        "avatar_id": avatar_id or None,
        "aspect_ratio": "9:16",
        "resolution": data.get("resolution") or "1080p",
        "motion_prompt": (data.get("motion_prompt") or "Natural conversational delivery with subtle head movement.").strip(),
        "output_path": str(output_path).replace("\\", "/"),
        "consent_confirmed": True,
        "approval": "human_requested_generation",
        "note": (
            "Process with a Codex task that has HeyGen Remote MCP connected."
            if auth_mode == "oauth_mcp"
            else "Run with the local HeyGen API worker; this spends API wallet credit."
        ),
    }


@app.post("/api/heygen/jobs")
def queue_heygen_job():
    data = request.get_json(force=True, silent=True) or {}
    batch_id = f"hgs_{time.strftime('%Y%m%d%H%M%S')}_{os.urandom(4).hex()}"
    prepared = prepare_heygen_job(data, batch_id=batch_id)
    job, created = video_queue.enqueue_job(prepared, queue_root=VIDEO_JOBS_DIR)
    return jsonify({"created": created, "job": public_video_job(job)}), 202 if created else 200


@app.post("/api/heygen/batches")
def queue_heygen_batch():
    data = request.get_json(force=True, silent=True) or {}
    requested_jobs = data.get("jobs") or []
    if not isinstance(requested_jobs, list) or not requested_jobs:
        abort(400, description="batch jobs are required")
    if len(requested_jobs) > 20:
        abort(400, description="a video batch may contain at most 20 clips")
    indexes = {job.get("character_index") for job in requested_jobs if isinstance(job, dict)}
    if len(indexes) > 10:
        abort(400, description="a video batch may contain at most 10 characters")
    if not data.get("consent_confirmed"):
        abort(400, description="confirm character and voice consent before queueing")

    roster_data = load_roster()
    batch_id = f"hgb_{time.strftime('%Y%m%d%H%M%S')}_{os.urandom(4).hex()}"
    shared = {
        "brand": data.get("brand") or DEFAULT_BRAND,
        "project_id": data.get("project_id"),
        "auth_mode": data.get("auth_mode") or "oauth_mcp",
        "voice_id": data.get("voice_id") or "",
        "resolution": data.get("resolution") or "1080p",
        "motion_prompt": data.get("motion_prompt") or "",
        "use_character_avatar": False,
        "consent_confirmed": True,
    }
    # Prepare every clip before enqueueing any of them so missing assets fail as a set.
    prepared = [
        prepare_heygen_job({**shared, **job}, roster_data=roster_data, batch_id=batch_id)
        for job in requested_jobs
        if isinstance(job, dict)
    ]
    if len(prepared) != len(requested_jobs):
        abort(400, description="every batch job must be an object")

    queued = []
    created_count = 0
    for item in prepared:
        job, created = video_queue.enqueue_job(item, queue_root=VIDEO_JOBS_DIR)
        queued.append(public_video_job(job))
        created_count += int(created)
    return jsonify({
        "batch_id": batch_id,
        "requested_count": len(requested_jobs),
        "created_count": created_count,
        "jobs": queued,
    }), 202 if created_count else 200


def background_heygen_job(job_id):
    try:
        heygen_adapter.process_job(
            job_id, queue_root=VIDEO_JOBS_DIR, workspace_root=ROOT, wait=True)
    except Exception:
        # The adapter records a sanitized failure on the job itself.
        pass


@app.post("/api/heygen/jobs/<job_id>/run")
def run_heygen_job(job_id):
    try:
        _, job = video_queue.find_job(job_id, VIDEO_JOBS_DIR)
    except FileNotFoundError as exc:
        abort(404, description=str(exc))
    if job.get("auth_mode") != "api_key":
        abort(409, description="OAuth jobs require a Codex task with HeyGen Remote MCP connected")
    if not heygen_adapter.connection_status()["api_key_configured"]:
        abort(409, description="HEYGEN_API_KEY is not configured in .env")
    if job.get("status") != "queued":
        abort(409, description=f"only queued jobs can start; current status is {job.get('status')}")
    thread = threading.Thread(target=background_heygen_job, args=(job_id,), daemon=True)
    thread.start()
    return jsonify({"started": True, "job": public_video_job(job)}), 202


@app.post("/api/heygen/jobs/<job_id>/refresh")
def refresh_heygen_job(job_id):
    try:
        job = heygen_adapter.refresh_job(
            job_id, queue_root=VIDEO_JOBS_DIR, workspace_root=ROOT)
    except FileNotFoundError as exc:
        abort(404, description=str(exc))
    except heygen_adapter.HeyGenError as exc:
        abort(502, description=str(exc))
    return jsonify(public_video_job(job))


@app.get("/api/assets/status")
def asset_status():
    return jsonify(app_assets.status(ROOT, requested_brand()))


@app.get("/api/prompts/character")
def character_prompt():
    brand = requested_brand()
    spec = request.args.get("spec") or "woman, early 20s, East Asian"
    return jsonify(character_factory.character_prompts(spec, path=brand.prompt_path("image_character")))


@app.post("/api/prompts/character/preview")
def preview_character_prompt():
    data = request.get_json(force=True, silent=True) or {}
    brand = requested_brand()
    prompt_config_path = brand.prompt_path("image_character")
    spec = data.get("spec") or "woman, early 20s, East Asian"
    cfg = character_factory.load_prompt_config(prompt_config_path)
    before_template = data.get("before_template") or cfg["before_template"]
    opening_style = data.get("opening_style") or cfg["opening_style"]
    opening_prompt = data.get("opening_prompt")
    if opening_prompt is None or opening_prompt == "":
        opening_prompt = cfg["opening_prompt"] or cfg["opening_presets"].get(opening_style, "")
    scan_prompt = data.get("scan_prompt") or cfg["scan_prompt"]
    after_prompt = data.get("after_prompt") or cfg["after_prompt"]
    product_style = data.get("product_style") or cfg["product_style"]
    product_prop_prompt = data.get("product_prop_prompt")
    if product_prop_prompt is None or product_prop_prompt == "":
        product_prop_prompt = (
            cfg["product_prop_prompt"] or cfg["product_prop_presets"].get(product_style, "")
        )
    product_slide_caption = data.get("product_slide_caption") or cfg["product_slide_caption"]
    age, gender, eth = character_factory.parse_spec(spec)
    return jsonify({
        "spec": spec,
        "age": age,
        "gender": gender,
        "ethnicity": eth,
        "before_template": before_template,
        "opening_style": opening_style,
        "opening_presets": cfg["opening_presets"],
        "opening_prompt": opening_prompt,
        "scan_prompt": scan_prompt,
        "after_prompt": after_prompt,
        "product_style": product_style,
        "product_prop_presets": cfg["product_prop_presets"],
        "product_prop_prompt": product_prop_prompt,
        "product_slide_caption": product_slide_caption,
        "before_prompt": character_factory.fill_prompt(before_template, age, gender, eth),
        "rendered_opening_prompt": (
            character_factory.fill_prompt(opening_prompt, age, gender, eth) if opening_prompt else ""
        ),
        "rendered_scan_prompt": character_factory.fill_prompt(scan_prompt, age, gender, eth),
        "rendered_after_prompt": character_factory.fill_prompt(after_prompt, age, gender, eth),
        "rendered_product_prop_prompt": (
            character_factory.fill_prompt(product_prop_prompt, age, gender, eth)
            if product_prop_prompt else ""
        ),
    })


@app.patch("/api/prompts/character")
def save_character_prompt():
    data = request.get_json(force=True, silent=True) or {}
    brand = requested_brand()
    prompt_config_path = brand.prompt_path("image_character")
    if not prompt_config_path:
        abort(400, description=f"{brand.display_name} does not define editable image prompts")
    before_template = (data.get("before_template") or "").strip()
    opening_style = (data.get("opening_style") or "selfie").strip()
    opening_prompt = (data.get("opening_prompt") or "").strip()
    scan_prompt = (data.get("scan_prompt") or "").strip()
    after_prompt = (data.get("after_prompt") or "").strip()
    product_style = (data.get("product_style") or "none").strip()
    product_prop_prompt = (data.get("product_prop_prompt") or "").strip()
    product_slide_caption = (data.get("product_slide_caption") or "").strip()
    if not before_template or not scan_prompt or not after_prompt:
        abort(400, description="before_template, scan_prompt, and after_prompt are required")
    if opening_style not in character_factory.OPENING_PRESETS:
        abort(400, description="invalid opening_style")
    if product_style not in character_factory.PRODUCT_PROP_PRESETS:
        abort(400, description="invalid product_style")
    saved = character_factory.save_prompt_config(
        before_template,
        after_prompt,
        scan_prompt,
        opening_style=opening_style,
        opening_prompt=opening_prompt,
        product_style=product_style,
        product_prop_prompt=product_prop_prompt,
        product_slide_caption=product_slide_caption,
        path=prompt_config_path,
    )
    spec = data.get("spec") or "woman, early 20s, East Asian"
    return jsonify({**saved, **character_factory.character_prompts(
        spec, path=prompt_config_path, opening_style=opening_style, product_style=product_style)})


def recipe_payload_from_batch(batch, name):
    run = batch.get("run") or {}
    config = dict(run.get("config") or {})
    prompt_snapshot = {}
    prompt_path = config.get("prompt_snapshot_path")
    if prompt_path:
        candidate = (ROOT / prompt_path).resolve()
        if candidate.exists() and ROOT in candidate.parents:
            prompt_snapshot = read_json(candidate, {})

    if batch.get("workflow") == "slideshow":
        posts_in_batch = batch.get("posts") or []
        slugs = list(config.get("character_slugs") or [])
        if not slugs:
            slugs = list(dict.fromkeys(
                (post.get("character") or {}).get("slug")
                for post in posts_in_batch
                if (post.get("character") or {}).get("slug")
            ))
        hook_overrides = {slug: [] for slug in slugs}
        for post in posts_in_batch:
            slug = (post.get("character") or {}).get("slug")
            if slug:
                hook_overrides.setdefault(slug, []).append(post.get("hook") or "")
        setup = {
            key: config.get(key)
            for key in (
                "posts_per_avatar", "provider", "account", "placeholder",
                "opening_style", "product_style", "product_slide_caption",
            )
        }
        setup.update({
            "character_slugs": slugs,
            "hook_overrides": hook_overrides,
            "slide_copy_overrides": config.get("slide_copy_overrides") or {},
        })
        creative_snapshot = [
            {
                "post_id": post.get("post_id"),
                "character_slug": (post.get("character") or {}).get("slug"),
                "variant_id": (post.get("character") or {}).get("variant_id"),
                "base_character_slug": (
                    post.get("character") or {}).get("base_character_slug"),
                "hook": post.get("hook"),
                "slides": post.get("slides") or [],
                "caption": post.get("caption"),
                "package": post.get("package") or {},
            }
            for post in posts_in_batch
        ]
    elif batch.get("workflow") == "talking_head":
        jobs = batch.get("jobs") or []
        first = jobs[0] if jobs else {}
        setup = {
            "auth_mode": first.get("auth_mode") or "oauth_mcp",
            "voice_id": first.get("voice_id") or "",
            "motion_prompt": first.get("motion_prompt") or "",
            "character_slugs": list(dict.fromkeys(
                job.get("slug") for job in jobs if job.get("slug")
            )),
            "jobs": [
                {
                    key: job.get(key)
                    for key in (
                        "slug", "source_asset", "clip_role", "script", "title",
                    )
                }
                for job in jobs
            ],
        }
        creative_snapshot = []
    else:
        setup = config
        creative_snapshot = [
            {
                "post_id": post.get("post_id"),
                "hook": post.get("hook"),
                "package": post.get("package") or {},
            }
            for post in (batch.get("posts") or [])
        ]
    return {
        "name": name,
        "brand": batch.get("brand") or DEFAULT_BRAND,
        "project_id": batch.get("project_id") or project_store.default_project_id(
            batch.get("brand") or DEFAULT_BRAND),
        "workflow": batch.get("workflow") or "slideshow",
        "source_batch_id": batch.get("batch_id"),
        "setup": setup,
        "prompt_snapshot": prompt_snapshot,
        "creative_snapshot": creative_snapshot,
    }


@app.get("/api/recipes")
def recipes():
    brand = (request.args.get("brand") or "").strip() or None
    return jsonify(creative_recipes.list_recipes(RECIPES_DIR, brand=brand))


@app.post("/api/recipes")
def save_recipe():
    data = request.get_json(force=True, silent=True) or {}
    source_batch_id = (data.get("source_batch_id") or "").strip()
    if source_batch_id:
        batch = next(
            (row for row in collect_batches() if row["batch_id"] == source_batch_id), None)
        if not batch:
            abort(404, description="source batch not found")
        payload = recipe_payload_from_batch(
            batch, data.get("name") or f"{batch.get('workflow')} {source_batch_id}")
        payload["notes"] = data.get("notes") or ""
    else:
        brand = requested_brand()
        project = requested_project(brand, data)
        payload = {
            **data,
            "brand": brand.brand_id,
            "project_id": project["project_id"],
        }
    try:
        recipe = creative_recipes.save_recipe(RECIPES_DIR, payload)
    except ValueError as exc:
        abort(400, description=str(exc))
    return jsonify(recipe), 201


@app.delete("/api/recipes/<recipe_id>")
def delete_recipe(recipe_id):
    if not creative_recipes.delete_recipe(RECIPES_DIR, recipe_id):
        abort(404, description="recipe not found")
    return jsonify({"deleted": True, "recipe_id": recipe_id})


@app.get("/api/batches")
def batches():
    brand = (request.args.get("brand") or "").strip()
    project_id = (request.args.get("project_id") or "").strip()
    workflow = (request.args.get("workflow") or "").strip()
    rows = collect_batches()
    if brand:
        rows = [row for row in rows if row.get("brand") == brand]
    if project_id:
        rows = [row for row in rows if row.get("project_id") == project_id]
    if workflow:
        rows = [row for row in rows if row.get("workflow") == workflow]
    summaries = []
    for row in rows:
        summary = {key: value for key, value in row.items() if key not in {"posts", "jobs"}}
        if summary.get("run"):
            run = summary["run"]
            summary["run"] = {
                key: run.get(key)
                for key in ("run_id", "status", "started_at", "finished_at", "config")
            }
        summary["post_count"] = len(row.get("posts") or [])
        summary["clip_count"] = len(row.get("jobs") or [])
        summaries.append(summary)
    return jsonify(summaries)


@app.get("/api/batches/<batch_id>")
def batch_detail(batch_id):
    batch = next((row for row in collect_batches() if row["batch_id"] == batch_id), None)
    if not batch:
        abort(404, description="batch not found")
    detail = dict(batch)
    detail["posts"] = [
        {**post, "preview": publish_bridge.payload_for(post)}
        for post in batch.get("posts") or []
    ]
    return jsonify(detail)


@app.get("/api/posts")
def posts():
    rows = [normalize_post(p) for p in manifest.all_posts(str(POSTS_FILE))]
    brand = (request.args.get("brand") or "").strip()
    project_id = (request.args.get("project_id") or "").strip()
    if brand:
        rows = [row for row in rows if row.get("brand") == brand]
    if project_id:
        rows = [row for row in rows if row.get("project_id") == project_id]
    return jsonify(rows)


@app.get("/api/publish/accounts")
def publish_accounts():
    return jsonify(publish_bridge.account_registry_payload())


@app.patch("/api/posts/<post_id>/winner")
def winner(post_id):
    data = request.get_json(force=True, silent=True) or {}
    post = manifest.set_winner(post_id, bool(data.get("is_winner")), str(POSTS_FILE))
    if not post:
        abort(404)
    return jsonify(normalize_post(post))


@app.patch("/api/posts/<post_id>/queue")
def queue(post_id):
    data = request.get_json(force=True, silent=True) or {}
    status = data.get("status")
    if status not in {"draft", "ready_to_post", "posted", "skipped", "failed", "needs_edit"}:
        abort(400, description="invalid queue status")
    existing = manifest.get_post(post_id, str(POSTS_FILE))
    if not existing:
        abort(404)
    if status in {"ready_to_post", "posted"}:
        try:
            publish_bridge.require_compliance(
                existing,
                override=bool(data.get("override")),
                reason=data.get("override_reason"),
                posts_path=str(POSTS_FILE),
            )
        except publish_bridge.PublishError as exc:
            abort(409, description=str(exc))
    post = manifest.set_publish_queue(
        post_id,
        status,
        target_account=data.get("target_account"),
        notes=data.get("notes"),
        path=str(POSTS_FILE),
    )
    if not post:
        abort(404)
    return jsonify(normalize_post(post))


@app.patch("/api/posts/<post_id>/publish")
def publish(post_id):
    data = request.get_json(force=True, silent=True) or {}
    existing = manifest.get_post(post_id, str(POSTS_FILE))
    if not existing:
        abort(404)
    platform = data.get("platform") or "manual"
    account = data.get("account") or default_account_for(existing.get("brand"))
    url = data.get("url") or ""
    try:
        publish_bridge.require_compliance(
            existing,
            override=bool(data.get("override")),
            reason=data.get("override_reason"),
            posts_path=str(POSTS_FILE),
        )
    except publish_bridge.PublishError as exc:
        abort(409, description=str(exc))
    post = manifest.set_publish(post_id, platform, account, url, str(POSTS_FILE))
    if not post:
        abort(404)
    post = manifest.set_publish_queue(post_id, "posted", account, data.get("notes"), str(POSTS_FILE))
    manifest.set_distribution(
        post_id, platform, account, "posted", str(POSTS_FILE), url=url, mode="manual")
    post = manifest.get_post(post_id, str(POSTS_FILE))
    return jsonify(normalize_post(post))


@app.get("/api/posts/<post_id>/payload")
def post_payload(post_id):
    post = manifest.get_post(post_id, str(POSTS_FILE))
    if not post:
        abort(404)
    return jsonify(publish_bridge.payload_for(post))


@app.post("/api/posts/<post_id>/publish-dry-run")
def publish_dry_run(post_id):
    data = request.get_json(force=True, silent=True) or {}
    post = manifest.get_post(post_id, str(POSTS_FILE))
    if not post:
        abort(404)
    platform = str(data.get("platform") or "").strip()
    account_id = str(data.get("account_id") or "").strip()
    if not platform or not account_id:
        abort(400, description="platform and account_id are required")
    try:
        result = publish_bridge.vendor_dry_run(
            post,
            platform,
            account_id,
            scheduled_for=data.get("scheduled_for"),
            posts_path=str(POSTS_FILE),
        )
    except publish_bridge.PublishError as exc:
        abort(409, description=str(exc))
    return jsonify(result)


@app.post("/api/metrics/import-csv")
def metrics_import_csv():
    data = request.get_json(force=True, silent=True) or {}
    csv_path = safe_optional_file(data.get("path"))
    map_overrides = data.get("map") or []
    result = import_metrics.import_csv(str(csv_path), str(POSTS_FILE), map_overrides)
    return jsonify(result)


@app.get("/api/integrations")
def integrations():
    return jsonify({
        "publish": {
            "vendor": publish_bridge.vendor_plan(),
            **{
                name: publish_bridge.api_plan(name)
                for name in ["tiktok", "instagram", "facebook"]
            },
        },
        "accounts": publish_bridge.account_registry_payload(),
        "metrics": {
            name: metrics_refresh.api_plan(name)
            for name in sorted(metrics_refresh.API_PLANS)
        },
    })


@app.post("/api/posts/<post_id>/open-folder")
def open_folder(post_id):
    post = manifest.get_post(post_id, str(POSTS_FILE))
    if not post:
        abort(404)
    package_dir = (post.get("package") or {}).get("dir") or (post.get("outputs") or {}).get("slides_dir")
    folder = safe_path(package_dir)
    if folder.is_file():
        folder = folder.parent
    if os.name == "nt":
        os.startfile(str(folder))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(folder)])
    else:
        subprocess.Popen(["xdg-open", str(folder)])
    return jsonify({"ok": True, "folder": str(folder)})


@app.post("/api/runs")
def create_run():
    data = request.get_json(force=True, silent=True) or {}
    brand = requested_brand()
    project = requested_project(brand, data)
    avatars = max(1, min(100, int(data.get("avatars") or 1)))
    posts_per_avatar = max(1, min(50, int(data.get("posts_per_avatar") or 1)))
    provider = data.get("provider") or os.environ.get("IMAGE_PROVIDER", "openai")
    account = data.get("account") or brand.default_account
    formats = (data.get("formats") or "slideshow").strip()
    format_names = {name.strip() for name in formats.split(",") if name.strip()}
    requested_formats = set(brand.formats) if "all" in format_names else format_names
    text_only = "slideshow" not in requested_formats
    placeholder = bool(data.get("placeholder"))
    spec = (data.get("spec") or "").strip()
    hook = (data.get("hook") or "").strip()
    before_score = int(data.get("before_score") or 54)
    after_score = int(data.get("after_score") or 87)
    opening_style = (data.get("opening_style") or "").strip()
    product_style = (data.get("product_style") or "").strip()
    product_slide_caption = (data.get("product_slide_caption") or "").strip()
    character_slug = (data.get("character_slug") or "").strip()
    raw_character_slugs = data.get("character_slugs") or []
    if isinstance(raw_character_slugs, str):
        raw_character_slugs = raw_character_slugs.split(",")
    character_slugs = list(dict.fromkeys(
        str(slug).strip() for slug in raw_character_slugs if str(slug).strip()
    ))
    raw_hook_overrides = data.get("hook_overrides") or {}
    if not isinstance(raw_hook_overrides, dict):
        abort(400, description="hook_overrides must be an object keyed by character slug")
    hook_overrides = {}
    for slug, hooks in raw_hook_overrides.items():
        if isinstance(hooks, str):
            hooks = [hooks]
        if not isinstance(hooks, list):
            abort(400, description=f"hook_overrides.{slug} must be a list")
        hook_overrides[str(slug)] = [str(hook or "").strip()[:2000] for hook in hooks]
    raw_slide_copy_overrides = data.get("slide_copy_overrides") or {}
    if not isinstance(raw_slide_copy_overrides, dict):
        abort(400, description="slide_copy_overrides must be an object keyed by character slug")
    slide_copy_fields = {
        "scan_text", "result_text", "progress_text", "progress_subtext",
    }
    slide_copy_overrides = {}
    for slug, iterations in raw_slide_copy_overrides.items():
        if not isinstance(iterations, list):
            abort(400, description=f"slide_copy_overrides.{slug} must be a list")
        cleaned = []
        for index, values in enumerate(iterations):
            if not isinstance(values, dict):
                abort(400, description=(
                    f"slide_copy_overrides.{slug}[{index}] must be an object"))
            cleaned.append({
                key: str(values.get(key) or "").strip()[:2000]
                for key in slide_copy_fields
                if str(values.get(key) or "").strip()
            })
        slide_copy_overrides[str(slug)] = cleaned
    prompt_snapshot = data.get("prompt_snapshot") or {}
    if prompt_snapshot and not isinstance(prompt_snapshot, dict):
        abort(400, description="prompt_snapshot must be an object")
    if len(character_slugs) > 100:
        abort(400, description="a slideshow batch may contain at most 100 characters")
    if character_slug and character_slugs:
        abort(400, description="use character_slug or character_slugs, not both")
    if character_slugs:
        avatars = len(character_slugs)
    if opening_style and opening_style not in character_factory.OPENING_PRESETS:
        abort(400, description="invalid opening_style")
    if product_style and product_style not in character_factory.PRODUCT_PROP_PRESETS:
        abort(400, description="invalid product_style")
    if text_only and not hook:
        abort(400, description="text-only runs require a hook/angle")
    run_characters = None
    variants_by_slug = {}
    if "slideshow" in requested_formats and not spec:
        roster_data = load_roster()
        roster_characters = roster_data.get("characters", [])
        variants = project_variants(brand.brand_id, project["project_id"])
        variants_by_slug = {variant["asset_slug"]: variant for variant in variants}
        by_slug = {character.get("slug"): character for character in roster_characters}
        by_slug.update({
            variant["asset_slug"]: variant["character"]
            for variant in variants
        })
        requested_slugs = character_slugs or ([character_slug] if character_slug else [])
        if requested_slugs:
            missing_slugs = [slug for slug in requested_slugs if slug not in by_slug]
            if missing_slugs:
                abort(409, description=(
                    "Saved characters or project variants not found: " + ", ".join(missing_slugs)
                ))
            run_characters = [by_slug[slug] for slug in requested_slugs]
        else:
            run_characters = roster_characters[:avatars]
        if not run_characters:
            abort(409, description="No saved roster characters match this batch.")

        incomplete_variants = []
        for character in run_characters:
            variant = variants_by_slug.get(character.get("slug"))
            if variant and variant.get("status") != "ready":
                incomplete_variants.append(
                    f"{variant['asset_slug']} ({variant.get('status') or 'planned'})")
        if incomplete_variants:
            abort(409, description=(
                "Complete project image variants before starting this batch: "
                + "; ".join(incomplete_variants)
            ))

    if provider == "codex_local" and "slideshow" in requested_formats and not placeholder:
        if spec:
            abort(409, description=(
                "Local Codex image runs must use a saved roster character. "
                "Save it, queue missing images, and process the queue first."
            ))
        incomplete = []
        for character in run_characters:
            slug = character.get("slug")
            if not slug:
                incomplete.append(character.get("spec") or "unsaved character")
                continue
            plan = character_factory.missing_asset_plan(
                character["spec"],
                CHARACTER_ASSETS_DIR / slug,
                opening_style=opening_style or character.get("opening_style") or None,
                product_style=product_style or character.get("product_style") or None,
                prompt_config_path=(
                    variants_by_slug[slug]["prompt_config_path"]
                    if slug in variants_by_slug else brand.prompt_path("image_character")
                ),
            )
            if plan["targets"]:
                names = ", ".join(target["name"] for target in plan["targets"])
                incomplete.append(f"{slug} ({names})")
        if incomplete:
            abort(409, description=(
                "Process Local Codex image jobs before starting this batch: "
                + "; ".join(incomplete)
            ))

    run_id = datetime.now().strftime("%Y%m%d%H%M%S") + f"_{os.urandom(3).hex()}"
    workflow = "slideshow" if "slideshow" in requested_formats else "text"
    paths = project_store.output_paths(ROOT, brand.brand_id, project["project_id"])
    if run_characters is not None:
        run_roster_path = run_support_path(run_id, "roster")
        write_json(run_roster_path, {
            "template": load_roster().get("template", "scan_results"),
            "characters": run_characters,
        })
    else:
        run_roster_path = ROSTER_FILE
    cmd = [
        sys.executable,
        str(ROOT / "content_job.py"),
        "--brand", brand.brand_id,
        "--project-id", project["project_id"],
        "--roster", root_rel(run_roster_path),
        "--avatars", str(avatars),
        "--posts-per-avatar", str(posts_per_avatar),
        "--provider", provider,
        "--account", account,
        "--formats", formats,
        "--out", root_rel(paths["output"]),
        "--posts-dir", root_rel(PACKAGE_DIR),
        "--shots", root_rel(paths["screenshots"]),
        "--manifest", root_rel(POSTS_FILE),
        "--batch-id", run_id,
    ]
    support_dir = RUNS_DIR / "support"
    support_dir.mkdir(parents=True, exist_ok=True)
    if hook_overrides or slide_copy_overrides:
        input_path = run_support_path(run_id, "input")
        write_json(input_path, {
            "hook_overrides": hook_overrides,
            "slide_copy_overrides": slide_copy_overrides,
        })
        cmd += ["--run-input", root_rel(input_path)]
    else:
        input_path = None
    if prompt_snapshot:
        prompt_path = run_support_path(run_id, "prompts")
        write_json(prompt_path, prompt_snapshot)
        cmd += ["--prompt-config", root_rel(prompt_path)]
    else:
        prompt_path = None
    if opening_style:
        cmd += ["--opening-style", opening_style]
    if product_style:
        cmd += ["--product-style", product_style]
    if product_slide_caption:
        cmd += ["--product-slide-caption", product_slide_caption]
    if character_slug and not spec:
        cmd += ["--character-slug", character_slug]
    if character_slugs and not spec:
        cmd += ["--character-slugs", ",".join(character_slugs)]
    if text_only:
        cmd += ["--angle", hook]
    elif spec:
        cmd += [
            "--spec", spec,
            "--before-score", str(before_score),
            "--after-score", str(after_score),
        ]
        if hook:
            cmd += ["--hook", hook]
    if placeholder:
        cmd.append("--placeholder")

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    meta = {
        "run_id": run_id,
        "status": "queued",
        "started_at": now_iso(),
        "finished_at": None,
        "returncode": None,
        "config": {
            "avatars": avatars,
            "posts_per_avatar": posts_per_avatar,
            "provider": provider,
            "brand": brand.brand_id,
            "project_id": project["project_id"],
            "formats": formats,
            "account": account,
            "placeholder": placeholder,
            "spec": spec or None,
            "hook": hook or None,
            "before_score": before_score,
            "after_score": after_score,
            "opening_style": opening_style or None,
            "product_style": product_style or None,
            "product_slide_caption": product_slide_caption or None,
            "character_slug": character_slug or None,
            "character_slugs": character_slugs,
            "hook_overrides": hook_overrides,
            "slide_copy_overrides": slide_copy_overrides,
            "run_input_path": root_rel(input_path) if input_path else None,
            "prompt_snapshot_path": root_rel(prompt_path) if prompt_path else None,
            "run_roster_path": root_rel(run_roster_path) if run_characters is not None else None,
            "output_paths": {
                key: root_rel(path)
                for key, path in paths.items()
                if key in {"output", "posts", "screenshots", "videos"}
            },
            "workflow": workflow,
        },
        "command": cmd,
        "log": str(run_log_path(run_id).relative_to(ROOT)),
    }
    write_json(run_meta_path(run_id), meta)

    env = os.environ.copy()
    env["IMAGE_PROVIDER"] = provider
    thread = threading.Thread(target=background_run, args=(run_id, cmd, env), daemon=True)
    thread.start()
    return jsonify(meta), 202


@app.get("/api/runs")
def runs():
    return jsonify(run_rows()[:20])


@app.get("/api/runs/<run_id>")
def run_detail(run_id):
    meta_path = run_meta_path(run_id)
    if not meta_path.exists():
        abort(404)
    meta = read_json(meta_path, {})
    meta["tail"] = tail_text(run_log_path(run_id))
    return jsonify(meta)


def main():
    app.run(host="127.0.0.1", port=5055, debug=False)


if __name__ == "__main__":
    main()
