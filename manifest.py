#!/usr/bin/env python3
"""
manifest.py — the data backbone
================================
Every post the pipeline generates gets a structured record here. The dashboard
reads posts.json; the metrics importer and winner-analysis update it. Keeping
all post metadata in one place is what makes the feedback loop possible.

Storage: a single posts.json (list of records). Simple, diffable, no DB needed
until volume demands one (the BUILD_SPEC notes when to migrate to SQLite).
"""
import json
import time
import uuid
from pathlib import Path

POSTS_FILE = "posts.json"


def _load(path):
    p = Path(path)
    if p.exists():
        return json.loads(p.read_text())
    return []


def _save(records, path):
    Path(path).write_text(json.dumps(records, indent=2))


def record_post(*, character, fmt, hook, slides, assets, outputs,
                variant_of=None, tracking_code=None, caption=None,
                package=None, publish_queue=None, path=POSTS_FILE):
    """Append a new post record. Returns the post_id."""
    records = _load(path)
    post_id = uuid.uuid4().hex[:12]
    records.append({
        "post_id": post_id,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "format": fmt,                      # e.g. testimonial_beforeafter / macro_faceless
        "character": character,             # {slug, spec, before_score, after_score}
        "hook": hook,
        "slides": slides,                   # [{kind, text_or_caption}]
        "assets": assets,                   # {before, after, shot_before, shot_after, ...}
        "outputs": outputs,                 # {slides_dir, video}
        "caption": caption,
        "package": package or {"dir": None, "slides_dir": None, "video": None,
                               "caption": None, "brief": None, "metadata": None},
        "variant_of": variant_of,           # post_id this was A/B-derived from
        "tracking_code": tracking_code,     # link UTM / bio-link code to match metrics back
        "publish": {"platform": None, "account": None, "url": None, "posted_at": None},
        "publish_queue": publish_queue or {"status": "draft", "target_account": None,
                                           "notes": None, "updated_at": None},
        "metrics": {"views": None, "likes": None, "shares": None, "saves": None,
                    "ctr": None, "installs": None, "updated_at": None},
        "is_winner": None,                  # set by analyze_winners
    })
    _save(records, path)
    return post_id


def get_post(post_id, path=POSTS_FILE):
    for r in _load(path):
        if r["post_id"] == post_id:
            return r
    return None


def update_post(post_id, updates, path=POSTS_FILE):
    records = _load(path)
    found = None
    for r in records:
        if r["post_id"] == post_id:
            r.update(updates)
            found = r
            break
    _save(records, path)
    return found


def set_package(post_id, package, caption=None, path=POSTS_FILE):
    updates = {"package": package}
    if caption is not None:
        updates["caption"] = caption
    return update_post(post_id, updates, path)


def set_publish_queue(post_id, status, target_account=None, notes=None, path=POSTS_FILE):
    records = _load(path)
    found = None
    for r in records:
        if r["post_id"] == post_id:
            q = r.get("publish_queue") or {}
            q.update({
                "status": status,
                "target_account": target_account if target_account is not None else q.get("target_account"),
                "notes": notes,
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            })
            r["publish_queue"] = q
            found = r
            break
    _save(records, path)
    return found


def set_winner(post_id, is_winner, path=POSTS_FILE):
    return update_post(post_id, {"is_winner": bool(is_winner)}, path)


def update_metrics(post_id, metrics, path=POSTS_FILE):
    records = _load(path)
    for r in records:
        if r["post_id"] == post_id:
            r["metrics"].update(metrics)
            r["metrics"]["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    _save(records, path)


def set_publish(post_id, platform, account, url, path=POSTS_FILE):
    records = _load(path)
    found = None
    for r in records:
        if r["post_id"] == post_id:
            r["publish"] = {"platform": platform, "account": account, "url": url,
                            "posted_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
            found = r
    _save(records, path)
    return found


def all_posts(path=POSTS_FILE):
    return _load(path)
