#!/usr/bin/env python3
"""
api_server.py - local dashboard API for the GloSkin content engine
==================================================================

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

import manifest
import import_metrics
import metrics_refresh
import publish as publish_bridge
import app_assets
import character_factory


ROOT = Path(__file__).resolve().parent
POSTS_FILE = ROOT / "posts.json"
RUNS_DIR = ROOT / "runs"
OUTPUT_DIR = ROOT / "output"
PACKAGE_DIR = ROOT / "posts"
DEFAULT_ACCOUNT = "gloskin_main"

app = Flask(__name__)


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


def normalize_post(post):
    p = dict(post)
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
        "target_account": DEFAULT_ACCOUNT,
        "notes": None,
        "updated_at": None,
    })
    p.setdefault("publish", {"platform": None, "account": None, "url": None, "posted_at": None})
    p.setdefault("metrics", {})
    return p


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
    roster = read_json(ROOT / "roster.json", {"characters": []})
    return jsonify({
        "default_account": DEFAULT_ACCOUNT,
        "image_provider": os.environ.get("IMAGE_PROVIDER", "openai"),
        "roster_count": len(roster.get("characters", [])),
        "publish_integrations": {
            name: publish_bridge.api_plan(name)
            for name in ["tiktok", "instagram", "facebook"]
        },
        "metrics_integrations": {
            name: metrics_refresh.api_plan(name)
            for name in sorted(metrics_refresh.API_PLANS)
        },
    })


@app.get("/api/assets/status")
def asset_status():
    return jsonify(app_assets.status(ROOT))


@app.get("/api/prompts/character")
def character_prompt():
    spec = request.args.get("spec") or "woman, early 20s, East Asian"
    return jsonify(character_factory.character_prompts(spec))


@app.post("/api/prompts/character/preview")
def preview_character_prompt():
    data = request.get_json(force=True, silent=True) or {}
    spec = data.get("spec") or "woman, early 20s, East Asian"
    cfg = character_factory.load_prompt_config()
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
    )
    spec = data.get("spec") or "woman, early 20s, East Asian"
    return jsonify({**saved, **character_factory.character_prompts(
        spec, opening_style=opening_style, product_style=product_style)})


@app.get("/api/posts")
def posts():
    rows = [normalize_post(p) for p in manifest.all_posts(str(POSTS_FILE))]
    return jsonify(rows)


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
    platform = data.get("platform") or "manual"
    account = data.get("account") or DEFAULT_ACCOUNT
    url = data.get("url") or ""
    post = manifest.set_publish(post_id, platform, account, url, str(POSTS_FILE))
    if not post:
        abort(404)
    post = manifest.set_publish_queue(post_id, "posted", account, data.get("notes"), str(POSTS_FILE))
    return jsonify(normalize_post(post))


@app.get("/api/posts/<post_id>/payload")
def post_payload(post_id):
    post = manifest.get_post(post_id, str(POSTS_FILE))
    if not post:
        abort(404)
    return jsonify(publish_bridge.payload_for(post))


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
            name: publish_bridge.api_plan(name)
            for name in ["tiktok", "instagram", "facebook"]
        },
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
    avatars = max(1, min(100, int(data.get("avatars") or 1)))
    posts_per_avatar = max(1, min(50, int(data.get("posts_per_avatar") or 1)))
    provider = data.get("provider") or os.environ.get("IMAGE_PROVIDER", "openai")
    account = data.get("account") or DEFAULT_ACCOUNT
    placeholder = bool(data.get("placeholder"))
    spec = (data.get("spec") or "").strip()
    hook = (data.get("hook") or "").strip()
    before_score = int(data.get("before_score") or 54)
    after_score = int(data.get("after_score") or 87)
    opening_style = (data.get("opening_style") or "").strip()
    product_style = (data.get("product_style") or "").strip()
    product_slide_caption = (data.get("product_slide_caption") or "").strip()
    if opening_style and opening_style not in character_factory.OPENING_PRESETS:
        abort(400, description="invalid opening_style")
    if product_style and product_style not in character_factory.PRODUCT_PROP_PRESETS:
        abort(400, description="invalid product_style")

    run_id = datetime.now().strftime("%Y%m%d%H%M%S")
    cmd = [
        sys.executable,
        str(ROOT / "content_job.py"),
        "--roster", "roster.json",
        "--avatars", str(avatars),
        "--posts-per-avatar", str(posts_per_avatar),
        "--provider", provider,
        "--account", account,
        "--out", root_rel(OUTPUT_DIR),
        "--posts-dir", root_rel(PACKAGE_DIR),
        "--manifest", root_rel(POSTS_FILE),
    ]
    if opening_style:
        cmd += ["--opening-style", opening_style]
    if product_style:
        cmd += ["--product-style", product_style]
    if product_slide_caption:
        cmd += ["--product-slide-caption", product_slide_caption]
    if spec:
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
            "account": account,
            "placeholder": placeholder,
            "spec": spec or None,
            "hook": hook or None,
            "before_score": before_score,
            "after_score": after_score,
            "opening_style": opening_style or None,
            "product_style": product_style or None,
            "product_slide_caption": product_slide_caption or None,
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
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for meta_file in sorted(RUNS_DIR.glob("*.json"), reverse=True):
        meta = read_json(meta_file, {})
        run_id = meta.get("run_id") or meta_file.stem
        meta["tail"] = tail_text(run_log_path(run_id), 2000)
        rows.append(meta)
    return jsonify(rows[:20])


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
