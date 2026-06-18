#!/usr/bin/env python3
"""
content_job.py - local GloSkin content automation entrypoint
============================================================

Runs a configurable batch and packages each finished post into a PC-friendly
folder for review and manual publishing.

Examples:
  python content_job.py --roster roster.json --avatars 2 --posts-per-avatar 3 --placeholder
  python content_job.py --roster roster.json --avatars 6 --posts-per-avatar 2

Defaults:
  - IMAGE_PROVIDER=openai unless --provider is passed
  - packaged posts land in posts/YYYY-MM-DD/<post_id>/
  - publish_queue.status is "ready_to_post"
"""
import argparse
import json
import os
import shutil
import time
from datetime import datetime
from pathlib import Path

import character_factory as cf
import manifest
import screenshot_factory as sf
import slideshow_maker as sm


DISCLAIMER = "Results vary. Not medical advice."
DEFAULT_ACCOUNT = "gloskin_main"


def rel(path):
    p = Path(path)
    try:
        p = p.relative_to(Path.cwd())
    except ValueError:
        pass
    return str(p).replace("\\", "/")


def clean_line(text):
    return " ".join((text or "").replace("\n", " ").split())


def pick_iteration(character, index):
    iterations = character.get("iterations") or []
    if index < len(iterations):
        return iterations[index]
    return {}


def pick_hook(character, index):
    iteration = pick_iteration(character, index)
    if iteration.get("hook"):
        return iteration["hook"]

    hooks = character.get("hooks") or []
    if not hooks and character.get("hook"):
        hooks = [character["hook"]]
    if index < len(hooks):
        return hooks[index]

    before = character.get("before_score", 54)
    after = character.get("after_score", 87)
    fallbacks = [
        "I let AI score my skin.\nThe number hurt.",
        f"My Glo Score was {before}.\nI needed a real routine.",
        f"Same face, same lighting.\nScore {after} after 8 weeks.",
        "I stopped guessing at skincare.\nAI did the audit.",
        "My routine was chaos.\nThen I scanned it.",
    ]
    return fallbacks[(index - len(hooks)) % len(fallbacks)]


def pick_after_text(character, index):
    iteration = pick_iteration(character, index)
    if iteration.get("after_text"):
        return iteration["after_text"]

    texts = character.get("after_texts") or []
    if index < len(texts):
        return texts[index]

    after = character.get("after_score", 87)
    fallbacks = [
        f"Score {after}. Same face, no filter.",
        f"Glo Score {after}. My routine finally made sense.",
        f"Score {after}. I stopped guessing.",
    ]
    return fallbacks[index % len(fallbacks)]


def pick_mid_text(character, index):
    iteration = pick_iteration(character, index)
    if iteration.get("mid_text"):
        return iteration["mid_text"]
    texts = character.get("mid_texts") or []
    if index < len(texts):
        return texts[index]
    return "8 weeks on Glo's routine."


def prepare_character(character, assets_dir, placeholder, opening_style=None, product_style=None):
    active_opening = opening_style or character.get("opening_style") or cf.load_prompt_config()["opening_style"]
    active_product = product_style or character.get("product_style") or cf.load_prompt_config()["product_style"]
    existing_slug = character.get("slug")
    if existing_slug:
        char_dir = Path(assets_dir) / existing_slug
        needs_opening = active_opening != "selfie" and not (char_dir / "opening.png").exists()
        needs_product = active_product != "none" and not (char_dir / "product_prop.png").exists()
        if ((char_dir / "before.png").exists() and (char_dir / "after.png").exists()
                and not needs_opening and not needs_product):
            return existing_slug

    gen = cf.gen_pair_placeholder if placeholder else cf.gen_pair_openai
    return gen(character["spec"], assets_dir,
               opening_style=active_opening,
               product_style=active_product)


def face_asset(char_dir, name, fallback="before"):
    path = Path(char_dir) / f"{name}.png"
    if path.exists():
        return path
    return Path(char_dir) / f"{fallback}.png"


def optional_asset(char_dir, name):
    path = Path(char_dir) / f"{name}.png"
    return path if path.exists() else None


def prepare_screenshots(template, char_dir, slug, character, shots_dir):
    Path(shots_dir).mkdir(parents=True, exist_ok=True)
    shot_before = Path(shots_dir) / f"{slug}_before.png"
    shot_after = Path(shots_dir) / f"{slug}_after.png"
    sf.composite_scan_result(
        str(template),
        str(face_asset(char_dir, "scan", "before")),
        character.get("before_score", 54),
        str(shot_before),
        patches=character.get("scan_patches") or character.get("scan_before_patches"),
    )
    sf.composite_scan_result(
        str(template),
        str(char_dir / "after.png"),
        character.get("after_score", 87),
        str(shot_after),
        patches=character.get("scan_patches") or character.get("scan_after_patches"),
    )
    return shot_before, shot_after


def build_testimonial_brief(render_slug, char_dir, shot_before, shot_after, character, index):
    hook = pick_hook(character, index)
    slides = [
        {
            "kind": "hook",
            "layout": "image_top",
            "label": "before",
            "image": str(face_asset(char_dir, "opening", "before")),
            "text": hook,
        },
    ]
    product_prop = optional_asset(char_dir, "product_prop")
    if product_prop:
        slides.append({
            "kind": "body",
            "image": str(product_prop),
            "text": character.get("product_slide_caption") or cf.load_prompt_config()["product_slide_caption"],
            "duration": 2.3,
        })
    slides += [
        {
            "kind": "screenshot",
            "image": str(shot_before),
            "caption": f"So I scanned my face.\nGlo Score: {character.get('before_score', 54)}.",
        },
        {
            "kind": "screenshot",
            "image": str(shot_after),
            "caption": pick_mid_text(character, index),
        },
        {
            "kind": "body",
            "layout": "image_top",
            "label": "after",
            "image": str(char_dir / "after.png"),
            "text": pick_after_text(character, index),
        },
        {
            "kind": "cta",
            "text": character.get("cta", "What's your Glo Score?"),
            "button": "Get GloSkin",
            "subtext": "Free on the App Store",
        },
    ]
    return {
        "slug": render_slug,
        "slides": slides,
    }


def caption_for(character, hook, tracking_code):
    base = character.get("caption")
    if base:
        lead = base.strip()
    else:
        lead = clean_line(hook)
    return "\n\n".join([
        lead,
        "What's your Glo Score?",
        DISCLAIMER,
        f"Tracking: {tracking_code}",
    ])


def copy_package(post_id, result, brief, caption, posts_dir, run_date, assets=None):
    package_dir = Path(posts_dir) / run_date / post_id
    slides_dest = package_dir / "slides"
    slides_dest.mkdir(parents=True, exist_ok=True)

    for slide_path in result["slides"]:
        shutil.copy2(slide_path, slides_dest / Path(slide_path).name)

    video_dest = package_dir / "video.mp4"
    shutil.copy2(result["video"], video_dest)

    caption_dest = package_dir / "caption.txt"
    caption_dest.write_text(caption, encoding="utf-8")

    brief_dest = package_dir / "brief.json"
    brief_dest.write_text(json.dumps(brief, indent=2), encoding="utf-8")

    asset_dest = package_dir / "source_assets"
    copied_assets = {}
    for key, path in (assets or {}).items():
        if not path:
            continue
        src = Path(path)
        if src.exists() and src.is_file():
            asset_dest.mkdir(parents=True, exist_ok=True)
            dst = asset_dest / f"{key}{src.suffix}"
            shutil.copy2(src, dst)
            copied_assets[key] = rel(dst)

    metadata_dest = package_dir / "post.json"
    package = {
        "dir": rel(package_dir),
        "slides_dir": rel(slides_dest),
        "video": rel(video_dest),
        "caption": rel(caption_dest),
        "brief": rel(brief_dest),
        "assets_dir": rel(asset_dest) if copied_assets else None,
        "assets": copied_assets,
        "metadata": rel(metadata_dest),
    }
    return package, metadata_dest


def write_metadata(post_id, metadata_dest, manifest_path):
    post = manifest.get_post(post_id, manifest_path)
    metadata_dest.write_text(json.dumps(post, indent=2), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--roster", default="roster.json")
    ap.add_argument("--spec", default=None,
                    help="ad-hoc character spec for a one-off dashboard prompt test")
    ap.add_argument("--hook", default=None,
                    help="hook for --spec prompt tests")
    ap.add_argument("--before-score", type=int, default=54)
    ap.add_argument("--after-score", type=int, default=87)
    ap.add_argument("--avatars", type=int, default=None,
                    help="number of roster characters to generate this run")
    ap.add_argument("--posts-per-avatar", type=int, default=1,
                    help="number of post iterations to render for each avatar")
    ap.add_argument("--out", default="output")
    ap.add_argument("--posts-dir", default="posts")
    ap.add_argument("--manifest", default="posts.json")
    ap.add_argument("--templates", default="templates")
    ap.add_argument("--assets", default="assets")
    ap.add_argument("--shots", default="screenshots")
    ap.add_argument("--provider", default=os.environ.get("IMAGE_PROVIDER", "openai"))
    ap.add_argument("--account", default=DEFAULT_ACCOUNT)
    ap.add_argument("--opening-style", choices=sorted(cf.OPENING_PRESETS), default=None)
    ap.add_argument("--product-style", choices=sorted(cf.PRODUCT_PROP_PRESETS), default=None)
    ap.add_argument("--product-slide-caption", default=None)
    ap.add_argument("--placeholder", action="store_true",
                    help="skip image APIs and use labeled placeholder faces")
    args = ap.parse_args()

    os.environ["IMAGE_PROVIDER"] = args.provider
    roster = json.loads(Path(args.roster).read_text(encoding="utf-8")) if Path(args.roster).exists() else {}
    template = Path(args.templates) / f"{roster.get('template', 'scan_results')}.webp"
    if not template.exists():
        raise FileNotFoundError(f"missing screenshot template: {template}")

    if args.spec:
        characters = [{
            "spec": args.spec,
            "before_score": args.before_score,
            "after_score": args.after_score,
            "hook": args.hook or "I let AI score my skin.\nThe number hurt.",
            "opening_style": args.opening_style,
            "product_style": args.product_style,
            "product_slide_caption": args.product_slide_caption,
        }]
    else:
        characters = roster.get("characters", [])
    if args.avatars is not None:
        characters = characters[:max(0, args.avatars)]

    run_id = datetime.now().strftime("%Y%m%d%H%M%S")
    run_date = datetime.now().strftime("%Y-%m-%d")
    built = []

    for avatar_index, character in enumerate(characters, start=1):
        if args.opening_style:
            character["opening_style"] = args.opening_style
        if args.product_style:
            character["product_style"] = args.product_style
        if args.product_slide_caption:
            character["product_slide_caption"] = args.product_slide_caption
        slug = prepare_character(
            character,
            args.assets,
            args.placeholder,
            opening_style=args.opening_style,
            product_style=args.product_style,
        )
        char_dir = Path(args.assets) / slug
        shot_before, shot_after = prepare_screenshots(
            template, char_dir, slug, character, args.shots)

        for post_index in range(max(1, args.posts_per_avatar)):
            render_slug = f"testimonial_{slug}_p{post_index + 1:02d}_{run_id}"
            tracking_code = f"glo_{run_id}_{avatar_index:02d}_{post_index + 1:02d}"
            brief = build_testimonial_brief(
                render_slug, char_dir, shot_before, shot_after, character, post_index)
            result = sm.make_content(brief, args.out)
            hook = pick_hook(character, post_index)
            caption = caption_for(character, hook, tracking_code)

            post_id = manifest.record_post(
                character={
                    "slug": slug,
                    "spec": character["spec"],
                    "before_score": character.get("before_score"),
                    "after_score": character.get("after_score"),
                    "opening_style": character.get("opening_style") or cf.load_prompt_config()["opening_style"],
                    "product_style": character.get("product_style") or cf.load_prompt_config()["product_style"],
                },
                fmt="testimonial_beforeafter",
                hook=hook,
                slides=[{"kind": s["kind"], "text": s.get("text") or s.get("caption", "")}
                        for s in brief["slides"]],
                assets={
                    "opening": rel(face_asset(char_dir, "opening", "before")),
                    "before": rel(char_dir / "before.png"),
                    "scan": rel(face_asset(char_dir, "scan", "before")),
                    "after": rel(char_dir / "after.png"),
                    "product_prop": rel(optional_asset(char_dir, "product_prop")) if optional_asset(char_dir, "product_prop") else None,
                    "shot_before": rel(shot_before),
                    "shot_after": rel(shot_after),
                },
                outputs={
                    "slides_dir": rel(result["dir"]),
                    "video": rel(result["video"]),
                },
                tracking_code=tracking_code,
                caption=caption,
                publish_queue={
                    "status": "rendered",
                    "target_account": args.account,
                    "notes": None,
                    "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                },
                path=args.manifest,
            )

            package_assets = {
                "opening": face_asset(char_dir, "opening", "before"),
                "before": char_dir / "before.png",
                "scan": face_asset(char_dir, "scan", "before"),
                "after": char_dir / "after.png",
                "product_prop": optional_asset(char_dir, "product_prop"),
                "shot_before": shot_before,
                "shot_after": shot_after,
            }
            package, metadata_dest = copy_package(
                post_id, result, brief, caption, args.posts_dir, run_date, package_assets)
            manifest.set_package(post_id, package, caption, args.manifest)
            manifest.set_publish_queue(post_id, "ready_to_post", args.account, path=args.manifest)
            write_metadata(post_id, metadata_dest, args.manifest)

            built.append((post_id, package["dir"]))
            print(f"[post] {post_id} -> {package['dir']}")

    print(f"\n{len(built)} posts packaged under {args.posts_dir}/{run_date}/")
    print("Manual queue status: ready_to_post")


if __name__ == "__main__":
    main()
