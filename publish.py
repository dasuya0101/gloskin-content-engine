#!/usr/bin/env python3
"""
publish.py - local publishing bridge
====================================

The current production-safe default is manual publishing: prepare posts in the
dashboard, upload them in-app, then mark the platform URL here or in the UI.

Commands:
  python publish.py ready
  python publish.py payload --post-id abc123
  python publish.py mark --post-id abc123 --platform tiktok --url https://...
  python publish.py queue --post-id abc123 --status needs_edit

Official API adapters can be added behind the same payload shape once account
permissions and app reviews are in place.
"""
import argparse
import json
import os
from pathlib import Path

from brand_loader import DEFAULT_BRAND, load_brand
import manifest


POSTS_FILE = "posts.json"
VALID_QUEUE_STATUSES = {"draft", "ready_to_post", "posted", "skipped", "failed", "needs_edit"}


class PublishError(RuntimeError):
    pass


def load_post(post_id, posts_path):
    post = manifest.get_post(post_id, posts_path)
    if not post:
        raise PublishError(f"post not found: {post_id}")
    return post


def queue(post):
    q = post.get("publish_queue") or {}
    brand = load_brand(post.get("brand") or DEFAULT_BRAND)
    return {
        "status": q.get("status", "draft"),
        "target_account": q.get("target_account") or brand.default_account,
        "notes": q.get("notes"),
        "updated_at": q.get("updated_at"),
    }


def package(post):
    return post.get("package") or {}


def file_list(path):
    if not path:
        return []
    p = Path(path)
    if not p.exists() or not p.is_dir():
        return []
    return [str(x).replace("\\", "/") for x in sorted(p.glob("*.png"))]


def caption_for(post):
    if post.get("caption"):
        return post["caption"]
    brand = load_brand(post.get("brand") or DEFAULT_BRAND)
    hook = " ".join((post.get("hook") or "").replace("\n", " ").split())
    return "\n\n".join([
        hook,
        brand.caption.get("secondary_cta") or brand.cta.get("text", ""),
        brand.caption.get("disclaimer", ""),
        f"Tracking: {post.get('tracking_code') or post.get('post_id')}",
    ]).strip()


def payload_for(post):
    pkg = package(post)
    outputs = post.get("outputs") or {}
    slides_dir = pkg.get("slides_dir")
    if not slides_dir and outputs.get("slides_dir"):
        candidate = Path(outputs["slides_dir"]) / "slides_for_tiktok_photomode"
        slides_dir = str(candidate).replace("\\", "/")
    return {
        "post_id": post["post_id"],
        "brand": post.get("brand") or DEFAULT_BRAND,
        "format": post.get("format"),
        "target_account": queue(post).get("target_account"),
        "tracking_code": post.get("tracking_code"),
        "caption": caption_for(post),
        "package_dir": pkg.get("dir"),
        "package_assets_dir": pkg.get("assets_dir"),
        "assets": post.get("assets") or {},
        "packaged_assets": pkg.get("assets") or {},
        "formats": pkg.get("formats") or (outputs.get("formats") if isinstance(outputs.get("formats"), dict) else {}),
        "video": pkg.get("video") or outputs.get("video"),
        "slides": file_list(slides_dir),
        "publish": post.get("publish"),
        "queue": queue(post),
    }


def require_env(names):
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        raise PublishError("missing environment variables: " + ", ".join(missing))


def api_plan(platform):
    plans = {
        "tiktok": {
            "status": "adapter_pending_credentials",
            "requires": ["TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_ACCESS_TOKEN"],
            "notes": "Use the official TikTok Content Posting API after app approval. Photo-mode uploads may need hosted image URLs; local files alone are not enough for every TikTok endpoint.",
        },
        "instagram": {
            "status": "adapter_pending_credentials",
            "requires": ["META_ACCESS_TOKEN", "IG_USER_ID"],
            "notes": "Use Instagram Graph API content publishing after the account is a professional account connected to a Facebook Page.",
        },
        "facebook": {
            "status": "adapter_pending_credentials",
            "requires": ["META_ACCESS_TOKEN", "FB_PAGE_ID"],
            "notes": "Use the Facebook Pages API for Page publishing once permissions are approved.",
        },
    }
    if platform not in plans:
        raise PublishError(f"unknown platform: {platform}")
    return plans[platform]


def publish_via_api(platform, post):
    plan = api_plan(platform)
    require_env(plan["requires"])
    raise PublishError(
        f"{platform} API adapter is scaffolded but not enabled yet. "
        "Use manual publishing for now, then fill in this adapter once API permissions are approved."
    )


def list_ready(posts_path):
    posts = manifest.all_posts(posts_path)
    ready = [p for p in posts if queue(p).get("status") == "ready_to_post"]
    for p in ready:
        data = payload_for(p)
        print(f"{data['post_id']}  {data['target_account']}  {data['package_dir'] or '-'}")
    print(f"\n{len(ready)} ready_to_post")


def mark(post_id, platform, account, url, posts_path):
    existing = load_post(post_id, posts_path)
    account = account or queue(existing)["target_account"]
    post = manifest.set_publish(post_id, platform, account, url, posts_path)
    if not post:
        raise PublishError(f"post not found: {post_id}")
    manifest.set_publish_queue(post_id, "posted", account, None, posts_path)
    print(f"[publish] {post_id} marked posted on {platform}: {url or '(no url)'}")


def set_queue(post_id, status, account, notes, posts_path):
    if status not in VALID_QUEUE_STATUSES:
        raise PublishError(f"invalid status: {status}")
    existing = load_post(post_id, posts_path)
    account = account or queue(existing)["target_account"]
    post = manifest.set_publish_queue(post_id, status, account, notes, posts_path)
    if not post:
        raise PublishError(f"post not found: {post_id}")
    print(f"[queue] {post_id} -> {status}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--posts", default=POSTS_FILE)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("ready")

    payload = sub.add_parser("payload")
    payload.add_argument("--post-id", required=True)

    mark_p = sub.add_parser("mark")
    mark_p.add_argument("--post-id", required=True)
    mark_p.add_argument("--platform", default="manual")
    mark_p.add_argument("--account", default=None)
    mark_p.add_argument("--url", default="")

    queue_p = sub.add_parser("queue")
    queue_p.add_argument("--post-id", required=True)
    queue_p.add_argument("--status", required=True, choices=sorted(VALID_QUEUE_STATUSES))
    queue_p.add_argument("--account", default=None)
    queue_p.add_argument("--notes", default=None)

    api_p = sub.add_parser("api-plan")
    api_p.add_argument("--platform", required=True, choices=["tiktok", "instagram", "facebook"])

    api_pub = sub.add_parser("api-publish")
    api_pub.add_argument("--post-id", required=True)
    api_pub.add_argument("--platform", required=True, choices=["tiktok", "instagram", "facebook"])

    args = ap.parse_args()

    try:
        if args.cmd == "ready":
            list_ready(args.posts)
        elif args.cmd == "payload":
            print(json.dumps(payload_for(load_post(args.post_id, args.posts)), indent=2))
        elif args.cmd == "mark":
            mark(args.post_id, args.platform, args.account, args.url, args.posts)
        elif args.cmd == "queue":
            set_queue(args.post_id, args.status, args.account, args.notes, args.posts)
        elif args.cmd == "api-plan":
            print(json.dumps(api_plan(args.platform), indent=2))
        elif args.cmd == "api-publish":
            post = load_post(args.post_id, args.posts)
            publish_via_api(args.platform, post)
    except PublishError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
