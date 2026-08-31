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
import re
import shutil

from PIL import Image

from brand_loader import DEFAULT_BRAND, load_brand
import distribution
import manifest
import publisher_vendor
from text_formats import build_cta_url


POSTS_FILE = "posts.json"
VALID_QUEUE_STATUSES = {"draft", "ready_to_post", "posted", "skipped", "failed", "needs_edit"}
PACKAGE_PLATFORMS = ("tiktok", "instagram")
HEADLINE_DISCLOSURE_PATTERN = re.compile(
    r"\b(?:illustrative|example|reference|not a real[- ]user outcome|results vary)\b",
    re.IGNORECASE,
)
TIMELINE_PATTERN = re.compile(
    r"\b(?:day|week)\s*\d+\b|\b\d+\s*(?:day|days|week|weeks)\b",
    re.IGNORECASE,
)
NAMED_PERSON_PATTERN = re.compile(
    r"\b(?:meet\s+)?[A-Z][a-z]{2,}(?:'s|’s)\s+(?:skin|routine|results|journey)\b"
)
DISCLOSURE_CHIPS = {"reference", "example", "illustrative"}


class PublishError(RuntimeError):
    pass


def require_synthetic_disclosure(post):
    metadata = post.get("metadata") or {}
    if not (metadata.get("synthetic_person") or metadata.get("composited_result")):
        return
    if metadata.get("is_aigc") is not True:
        raise PublishError(
            f"post {post['post_id']} is a synthetic composited result without "
            "metadata.is_aigc=true"
        )
    if metadata.get("illustrative_results") is not True:
        raise PublishError(
            f"post {post['post_id']} is a synthetic composited result without "
            "illustrative-results metadata"
        )

    disclosure = str(metadata.get("illustrative_results_text") or "").strip()
    if not disclosure or disclosure.casefold() not in caption_for(post).casefold():
        raise PublishError(
            f"post {post['post_id']} caption is missing its illustrative-results framing"
        )
    layers = metadata.get("disclosure_layers") or {}
    required_layers = ("corner_chip", "slide_footer", "caption_line", "platform_aigc_flag")
    if any(layers.get(name) is not True for name in required_layers):
        raise PublishError(
            f"post {post['post_id']} is missing required disclosure-layer metadata"
        )

    slides = post.get("slides") or []
    for index, slide in enumerate(slides, start=1):
        footer = slide.get("disclosure_footer") or slide.get("disclosure")
        if disclosure.casefold() not in str(footer or "").casefold():
            raise PublishError(
                f"post {post['post_id']} slide {index} is missing its disclosure footer"
            )
        if slide.get("requires_disclosure_chip") or slide.get("kind") == "screenshot":
            chip = str(slide.get("disclosure_chip") or "").strip().casefold()
            if chip not in DISCLOSURE_CHIPS:
                raise PublishError(
                    f"post {post['post_id']} slide {index} is missing its disclosure chip"
                )
        headline = str(slide.get("text") or "")
        if HEADLINE_DISCLOSURE_PATTERN.search(headline):
            raise PublishError(
                f"post {post['post_id']} slide {index} puts disclosure copy in the headline"
            )
        if str(slide.get("label") or "").strip().casefold() in {"before", "after"}:
            raise PublishError(
                f"post {post['post_id']} slide {index} uses a before/after label"
            )

    creative_copy = "\n".join([
        str(post.get("hook") or ""),
        caption_for(post).replace(disclosure, ""),
        *[
            " ".join(str(slide.get(key) or "") for key in ("text", "subtext", "label"))
            for slide in slides
        ],
    ])
    if re.search(r"\breal\b", creative_copy, re.IGNORECASE):
        raise PublishError(f"post {post['post_id']} uses banned real-user framing")
    if TIMELINE_PATTERN.search(creative_copy):
        raise PublishError(f"post {post['post_id']} uses a banned day/week timeline")
    if NAMED_PERSON_PATTERN.search(creative_copy):
        raise PublishError(f"post {post['post_id']} uses banned named-person framing")


def require_compliance(post, *, override=False, reason=None, posts_path=POSTS_FILE):
    # Release metadata is a hard gate and cannot be bypassed by a compliance override.
    require_synthetic_disclosure(post)
    status = (post.get("compliance") or {}).get("status")
    if status == "pass":
        return
    if not override:
        raise PublishError(
            f"post {post['post_id']} compliance is {status or 'not_checked'}; "
            "use --override with --reason to proceed"
        )
    if not str(reason or "").strip():
        raise PublishError("--override requires a non-empty --reason")
    manifest.record_compliance_override(post["post_id"], reason, posts_path)


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


def _relative(path):
    try:
        return str(Path(path).resolve().relative_to(Path.cwd().resolve())).replace("\\", "/")
    except ValueError:
        return str(Path(path)).replace("\\", "/")


def prepare_platform_slide_assets(slides_dir, package_dir):
    source_dir = Path(slides_dir)
    if not source_dir.exists():
        return {}
    sources = [
        path for path in sorted(source_dir.iterdir())
        if path.is_file() and path.suffix.casefold() in {".png", ".jpg", ".jpeg", ".webp"}
    ]
    if not sources:
        return {}

    dimensions = []
    for path in sources:
        with Image.open(path) as image:
            dimensions.append(image.size)
    if len(set(dimensions)) != 1 or dimensions[0] != (1080, 1350):
        raise PublishError(
            f"carousel slides must all be 1080x1350; found {sorted(set(dimensions))}")

    root = Path(package_dir) / "platforms"
    tiktok_dir = root / "tiktok" / "slides"
    instagram_dir = root / "instagram" / "slides"
    tiktok_dir.mkdir(parents=True, exist_ok=True)
    instagram_dir.mkdir(parents=True, exist_ok=True)
    for index, source in enumerate(sources, start=1):
        tiktok_target = tiktok_dir / f"slide_{index:02d}{source.suffix.casefold()}"
        shutil.copy2(source, tiktok_target)
        instagram_target = instagram_dir / f"slide_{index:02d}.jpg"
        with Image.open(source) as image:
            image.convert("RGB").save(
                instagram_target, format="JPEG", quality=95, optimize=True)
    return {
        "tiktok": _relative(tiktok_dir),
        "instagram": _relative(instagram_dir),
    }


def file_list(path):
    if not path:
        return []
    p = Path(path)
    if not p.exists() or not p.is_dir():
        return []
    return [str(x).replace("\\", "/") for x in sorted(p.glob("*.png"))]


def media_file_list(path):
    if not path:
        return []
    folder = Path(path)
    if not folder.exists() or not folder.is_dir():
        return []
    return [
        str(item).replace("\\", "/")
        for item in sorted(folder.iterdir())
        if item.is_file() and item.suffix.casefold() in {".png", ".jpg", ".jpeg"}
    ]


def validate_carousel(slides, platform):
    if not slides:
        raise PublishError(f"{platform} carousel has no slide assets")
    sizes = []
    for value in slides:
        path = Path(value)
        if not path.exists():
            raise PublishError(f"carousel slide is missing: {value}")
        if platform == "instagram" and path.suffix.casefold() not in {".jpg", ".jpeg"}:
            raise PublishError(f"Instagram carousel slide must be JPEG: {value}")
        with Image.open(path) as image:
            sizes.append(image.size)
    if len(set(sizes)) != 1 or sizes[0] != (1080, 1350):
        raise PublishError(
            f"{platform} carousel slides must all be 1080x1350; found {sorted(set(sizes))}")
    return True


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


def platform_caption_for(post, platform):
    brand = load_brand(post.get("brand") or DEFAULT_BRAND)
    cta_text = str(brand.cta.get("text") or "").strip()
    cta_url = build_cta_url(
        brand.cta.get("url"), platform, post.get("tracking_code"))
    blocks = [block.strip() for block in caption_for(post).split("\n\n") if block.strip()]
    blocks = [block for block in blocks if block.casefold() != cta_text.casefold()]
    if cta_text and cta_url:
        blocks.append(f"{cta_text}: {cta_url}")
    return "\n\n".join(blocks)


def platform_payload_for(post, platform, account_id=None):
    if platform not in PACKAGE_PLATFORMS:
        raise PublishError(f"unsupported package platform: {platform}")
    brand = load_brand(post.get("brand") or DEFAULT_BRAND)
    pkg = package(post)
    outputs = post.get("outputs") or {}
    platform_slides = dict(pkg.get("platform_slides") or {})
    slides_dir = platform_slides.get(platform) or pkg.get("slides_dir")
    if not slides_dir and outputs.get("slides_dir"):
        slides_dir = str(
            Path(outputs["slides_dir"]) / "slides_for_tiktok_photomode"
        ).replace("\\", "/")
    if slides_dir and not platform_slides.get(platform) and pkg.get("dir"):
        prepared = prepare_platform_slide_assets(slides_dir, pkg["dir"])
        slides_dir = prepared.get(platform) or slides_dir
    slides = media_file_list(slides_dir)
    payload = {
        "post_id": post["post_id"],
        "platform": platform,
        "target_account": account_id or brand.accounts.get(platform) or queue(post)["target_account"],
        "tracking_code": post.get("tracking_code"),
        "metadata": post.get("metadata") or {},
        "is_aigc": bool((post.get("metadata") or {}).get("is_aigc")),
        "caption": platform_caption_for(post, platform),
        "cta": {
            "text": brand.cta.get("text"),
            "url": build_cta_url(
                brand.cta.get("url"), platform, post.get("tracking_code")),
        },
        "slides": slides,
        "video": pkg.get("video") or outputs.get("video"),
    }
    if slides:
        validate_carousel(slides, platform)
        payload["creative_fingerprint"] = distribution.creative_fingerprint(payload)
    return payload


def platform_payloads_for(post):
    return {
        platform: platform_payload_for(post, platform)
        for platform in PACKAGE_PLATFORMS
    }


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
        "batch_id": post.get("batch_id"),
        "workflow": post.get("workflow"),
        "format": post.get("format"),
        "target_account": queue(post).get("target_account"),
        "tracking_code": post.get("tracking_code"),
        "metadata": post.get("metadata") or {},
        "caption": caption_for(post),
        "package_dir": pkg.get("dir"),
        "package_assets_dir": pkg.get("assets_dir"),
        "assets": post.get("assets") or {},
        "packaged_assets": pkg.get("assets") or {},
        "formats": pkg.get("formats") or (outputs.get("formats") if isinstance(outputs.get("formats"), dict) else {}),
        "platform_payloads_file": pkg.get("platform_payloads"),
        "platform_payloads": platform_payloads_for(post),
        "video": pkg.get("video") or outputs.get("video"),
        "slides": file_list(slides_dir),
        "publish": post.get("publish"),
        "queue": queue(post),
        "compliance": post.get("compliance"),
    }


def require_env(names):
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        raise PublishError("missing environment variables: " + ", ".join(missing))


def api_plan(platform):
    plans = {
        "tiktok": {
            "status": "vendor_adapter_pending_selection",
            "requires": ["POSTING_VENDOR_API_URL", "POSTING_VENDOR_API_KEY"],
            "notes": "TikTok photo carousels will use the selected audited vendor. Native API work is deferred.",
        },
        "instagram": {
            "status": "vendor_adapter_pending_selection",
            "requires": ["POSTING_VENDOR_API_URL", "POSTING_VENDOR_API_KEY"],
            "notes": "Instagram carousels will use the selected audited vendor. Native Graph publishing is deferred.",
        },
        "facebook": {
            "status": "deferred",
            "requires": [],
            "notes": "Facebook publishing is outside publish-layer v1.",
        },
    }
    if platform not in plans:
        raise PublishError(f"unknown platform: {platform}")
    return plans[platform]


def vendor_plan(registry_path=distribution.DEFAULT_REGISTRY_PATH):
    registry = distribution.load_registry(registry_path)
    status = distribution.vendor_status(registry)
    if not status["selected"]:
        state = "vendor_not_selected"
    elif not status["configured"]:
        state = "vendor_credentials_missing"
    elif not status["checkpoint_b_approved"]:
        state = "checkpoint_b_pending"
    elif not status["checkpoint_c_approved"]:
        state = "checkpoint_c_pending"
    elif not status["submission_enabled"]:
        state = "submission_disabled"
    else:
        state = "ready"
    return {**status, "status": state}


def account_registry_payload(registry_path=distribution.DEFAULT_REGISTRY_PATH):
    return distribution.public_registry(distribution.load_registry(registry_path))


def distribution_records(posts):
    return [row for post in posts for row in (post.get("distribution") or [])]


def require_automation_gates(post, account):
    require_synthetic_disclosure(post)
    compliance = post.get("compliance") or {}
    if compliance.get("status") != "pass":
        raise PublishError(
            f"post {post['post_id']} compliance is {compliance.get('status') or 'not_checked'}"
        )
    for violation in compliance.get("violations") or []:
        rule = str(violation.get("rule") or violation.get("id") or "").casefold()
        severity = str(violation.get("severity") or violation.get("action") or "").casefold()
        if "regulatory_hold" in rule or severity in {"hard_block", "fail"}:
            raise PublishError(f"post {post['post_id']} has a non-overridable regulatory block")
    if account.get("brand") != post.get("brand"):
        raise PublishError(
            f"account {account.get('account_id')} belongs to {account.get('brand')}, "
            f"not {post.get('brand')}"
        )
    blockers = distribution.account_blockers(account)
    if blockers:
        raise PublishError(
            f"account {account.get('account_id')} is not automation-ready: " + "; ".join(blockers)
        )


def vendor_dry_run(post, platform, account_id, *, scheduled_for=None,
                   posts_path=POSTS_FILE,
                   registry_path=distribution.DEFAULT_REGISTRY_PATH):
    if platform not in PACKAGE_PLATFORMS:
        raise PublishError(f"unsupported vendor platform: {platform}")
    registry = distribution.load_registry(registry_path)
    try:
        account = distribution.get_account(registry, account_id)
    except distribution.DistributionError as exc:
        raise PublishError(str(exc)) from exc
    if account.get("platform") != platform:
        raise PublishError(f"account {account_id} is not a {platform} account")
    require_automation_gates(post, account)
    payload = platform_payload_for(post, platform, account_id=account_id)
    validate_carousel(payload.get("slides") or [], platform)
    records = distribution_records(manifest.all_posts(posts_path))
    fingerprint = payload.get("creative_fingerprint")
    try:
        distribution.require_distinct_creative(platform, account_id, fingerprint, records)
        planned_for = (
            distribution.scheduled_time(
                registry, account, post, scheduled_for, existing_records=records)
            if scheduled_for else None
        )
    except distribution.DistributionError as exc:
        raise PublishError(str(exc)) from exc
    result = publisher_vendor.VendorAdapter(registry).dry_run(
        payload, account, scheduled_for=planned_for)
    result["creative_fingerprint"] = fingerprint
    result["gates"] = {
        "compliance": "pass",
        "aigc": "pass" if payload.get("is_aigc") else "not_applicable",
        "account": "pass",
        "regulatory_hold": "pass",
        "duplicate_creative": "pass",
    }
    manifest.set_distribution(
        post["post_id"],
        platform,
        account_id,
        "packaged",
        posts_path,
        mode="vendor",
        scheduled_for=planned_for,
        creative_fingerprint=fingerprint,
    )
    return result


def publish_via_api(platform, post, *, override=False, reason=None, posts_path=POSTS_FILE):
    raise PublishError(
        "native platform adapters are deferred. Use vendor-dry-run after an audited "
        "vendor and distribution account are configured; real submission remains disabled."
    )


def list_ready(posts_path):
    posts = manifest.all_posts(posts_path)
    ready = [p for p in posts if queue(p).get("status") == "ready_to_post"]
    for p in ready:
        data = payload_for(p)
        print(f"{data['post_id']}  {data['target_account']}  {data['package_dir'] or '-'}")
    print(f"\n{len(ready)} ready_to_post")


def mark(post_id, platform, account, url, posts_path, *, override=False, reason=None):
    existing = load_post(post_id, posts_path)
    require_compliance(existing, override=override, reason=reason, posts_path=posts_path)
    account = account or queue(existing)["target_account"]
    post = manifest.set_publish(post_id, platform, account, url, posts_path)
    if not post:
        raise PublishError(f"post not found: {post_id}")
    manifest.set_publish_queue(post_id, "posted", account, None, posts_path)
    manifest.set_distribution(
        post_id, platform, account, "posted", posts_path, url=url, mode="manual")
    print(f"[publish] {post_id} marked posted on {platform}: {url or '(no url)'}")


def set_queue(post_id, status, account, notes, posts_path, *, override=False, reason=None):
    if status not in VALID_QUEUE_STATUSES:
        raise PublishError(f"invalid status: {status}")
    existing = load_post(post_id, posts_path)
    if status in {"ready_to_post", "posted"}:
        require_compliance(existing, override=override, reason=reason, posts_path=posts_path)
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
    mark_p.add_argument("--override", action="store_true")
    mark_p.add_argument("--reason")

    queue_p = sub.add_parser("queue")
    queue_p.add_argument("--post-id", required=True)
    queue_p.add_argument("--status", required=True, choices=sorted(VALID_QUEUE_STATUSES))
    queue_p.add_argument("--account", default=None)
    queue_p.add_argument("--notes", default=None)
    queue_p.add_argument("--override", action="store_true")
    queue_p.add_argument("--reason")

    api_p = sub.add_parser("api-plan")
    api_p.add_argument("--platform", required=True, choices=["tiktok", "instagram", "facebook"])

    api_pub = sub.add_parser("api-publish")
    api_pub.add_argument("--post-id", required=True)
    api_pub.add_argument("--platform", required=True, choices=["tiktok", "instagram", "facebook"])
    api_pub.add_argument("--override", action="store_true")
    api_pub.add_argument("--reason")

    sub.add_parser("vendor-status")
    sub.add_parser("accounts")

    vendor_dry = sub.add_parser("vendor-dry-run")
    vendor_dry.add_argument("--post-id", required=True)
    vendor_dry.add_argument("--platform", required=True, choices=PACKAGE_PLATFORMS)
    vendor_dry.add_argument("--account-id", required=True)
    vendor_dry.add_argument("--scheduled-for")

    args = ap.parse_args()

    try:
        if args.cmd == "ready":
            list_ready(args.posts)
        elif args.cmd == "payload":
            print(json.dumps(payload_for(load_post(args.post_id, args.posts)), indent=2))
        elif args.cmd == "mark":
            mark(args.post_id, args.platform, args.account, args.url, args.posts,
                 override=args.override, reason=args.reason)
        elif args.cmd == "queue":
            set_queue(args.post_id, args.status, args.account, args.notes, args.posts,
                      override=args.override, reason=args.reason)
        elif args.cmd == "api-plan":
            print(json.dumps(api_plan(args.platform), indent=2))
        elif args.cmd == "api-publish":
            post = load_post(args.post_id, args.posts)
            publish_via_api(args.platform, post, override=args.override,
                            reason=args.reason, posts_path=args.posts)
        elif args.cmd == "vendor-status":
            print(json.dumps(vendor_plan(), indent=2))
        elif args.cmd == "accounts":
            print(json.dumps(distribution.public_registry(
                distribution.load_registry()), indent=2))
        elif args.cmd == "vendor-dry-run":
            print(json.dumps(vendor_dry_run(
                load_post(args.post_id, args.posts), args.platform, args.account_id,
                scheduled_for=args.scheduled_for, posts_path=args.posts), indent=2))
    except PublishError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
