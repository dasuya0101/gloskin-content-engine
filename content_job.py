#!/usr/bin/env python3
"""
content_job.py - local content automation entrypoint
====================================================

Runs a configurable batch and packages each finished post into a PC-friendly
folder for review and manual publishing.

Examples:
  python content_job.py --roster roster.json --avatars 2 --posts-per-avatar 3 --placeholder
  python content_job.py --roster roster.json --avatars 6 --posts-per-avatar 2

Defaults:
  - IMAGE_PROVIDER=openai unless --provider is passed
  - packaged posts land in posts/<brand>/<project_id>/YYYY-MM-DD/<post_id>/
  - publish_queue.status is "ready_to_post"
"""
import argparse
import copy
import hashlib
import json
import os
import shutil
import time
from datetime import datetime
from pathlib import Path

import character_factory as cf
import compliance_lint
from brand_loader import DEFAULT_BRAND, load_brand, mechanism_claims_for
from claim_packs import mechanism_claims as pack_mechanism_claims, relevant_claim_packs
import manifest
from project_store import default_project_id
import publish
import screenshot_factory as sf
import slideshow_maker as sm
import text_formats as tf


def rel(path):
    if path is None:
        return None
    p = Path(path)
    try:
        p = p.relative_to(Path.cwd())
    except ValueError:
        pass
    return str(p).replace("\\", "/")


def clean_line(text):
    return " ".join((text or "").replace("\n", " ").split())


def compact_render_key(character, fallback, max_length=24):
    raw = str(character.get("variant_id") or fallback)
    if len(raw) <= max_length:
        return raw
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
    return f"{raw[:max_length - 9]}_{digest}"


def pick_iteration(character, index):
    iterations = character.get("iterations") or []
    if index < len(iterations):
        return iterations[index]
    return {}


def fill_template(text, character):
    if text is None:
        return ""
    values = {
        "before_score": character.get("before_score", 54),
        "after_score": character.get("after_score", 87),
        "spec": character.get("spec", ""),
    }
    try:
        return str(text).format(**values)
    except (KeyError, ValueError):
        return str(text)


def pick_hook(character, index, brand):
    iteration = pick_iteration(character, index)
    if iteration.get("hook"):
        return iteration["hook"]

    hooks = character.get("hooks") or []
    if not hooks and character.get("hook"):
        hooks = [character["hook"]]
    if index < len(hooks):
        return hooks[index]

    fallbacks = brand.testimonial.get("fallback_hooks") or [
        "I stopped guessing.\nThen I made a plan.",
    ]
    return fill_template(fallbacks[(index - len(hooks)) % len(fallbacks)], character)


def apply_hook_overrides(characters, hook_overrides):
    for character in characters:
        slug = character.get("slug")
        overrides = hook_overrides.get(slug) if slug else None
        if isinstance(overrides, str):
            overrides = [overrides]
        if not isinstance(overrides, list):
            continue
        iterations = list(character.get("iterations") or [])
        while len(iterations) < len(overrides):
            iterations.append({})
        for index, hook in enumerate(overrides):
            if str(hook or "").strip():
                iterations[index] = {**iterations[index], "hook": str(hook).strip()}
        character["iterations"] = iterations
    return characters


SLIDE_COPY_FIELDS = {
    "scan_text", "result_text", "progress_text", "progress_subtext",
}


def apply_slide_copy_overrides(characters, slide_copy_overrides):
    for character in characters:
        slug = character.get("slug")
        overrides = slide_copy_overrides.get(slug) if slug else None
        if not isinstance(overrides, list):
            continue
        iterations = list(character.get("iterations") or [])
        while len(iterations) < len(overrides):
            iterations.append({})
        for index, values in enumerate(overrides):
            if not isinstance(values, dict):
                continue
            accepted = {
                key: str(values.get(key) or "").strip()
                for key in SLIDE_COPY_FIELDS
                if str(values.get(key) or "").strip()
            }
            iterations[index] = {**iterations[index], **accepted}
        character["iterations"] = iterations
    return characters


def pick_after_text(character, index, brand):
    iteration = pick_iteration(character, index)
    if iteration.get("after_text"):
        return iteration["after_text"]

    texts = character.get("after_texts") or []
    if index < len(texts):
        return texts[index]

    fallbacks = brand.testimonial.get("after_texts") or [
        "Same person. Better plan.",
    ]
    return fill_template(fallbacks[index % len(fallbacks)], character)


def pick_mid_text(character, index, brand):
    iteration = pick_iteration(character, index)
    if iteration.get("mid_text"):
        return iteration["mid_text"]
    texts = character.get("mid_texts") or []
    if index < len(texts):
        return texts[index]
    return fill_template(brand.testimonial.get("mid_text", "Progress came from the plan."), character)


def prepare_character(character, assets_dir, placeholder, prompt_config_path,
                      opening_style=None, product_style=None):
    prompt_cfg = cf.load_prompt_config(prompt_config_path)
    active_opening = opening_style or character.get("opening_style") or prompt_cfg["opening_style"]
    active_product = product_style or character.get("product_style") or prompt_cfg["product_style"]
    existing_slug = character.get("slug")
    if existing_slug:
        char_dir = Path(assets_dir) / existing_slug
        needs_opening = active_opening != "selfie" and not (char_dir / "opening.png").exists()
        needs_product = active_product != "none" and not (char_dir / "product_prop.png").exists()
        if ((char_dir / "before.png").exists() and (char_dir / "after.png").exists()
                and not needs_opening and not needs_product):
            return existing_slug
        if not placeholder:
            cf.generate_missing_assets(
                character["spec"],
                char_dir,
                opening_style=active_opening,
                product_style=active_product,
                prompt_config_path=prompt_config_path,
            )
            return existing_slug

    gen = cf.gen_pair_placeholder if placeholder else cf.gen_pair_openai
    return gen(character["spec"], assets_dir,
               opening_style=active_opening,
               product_style=active_product,
               prompt_config_path=prompt_config_path)


def face_asset(char_dir, name, fallback="before"):
    path = Path(char_dir) / f"{name}.png"
    if path.exists():
        return path
    return Path(char_dir) / f"{fallback}.png"


def optional_asset(char_dir, name):
    path = Path(char_dir) / f"{name}.png"
    return path if path.exists() else None


def is_synthetic_character(character):
    source_type = str(character.get("source_type") or "").strip().lower()
    fixture_set = character.get("fixture_set") or {}
    provenance = str(fixture_set.get("provenance") or "").strip().lower()
    return source_type in {"synthetic_fixture_set", "ai_generated", "synthetic"} \
        or provenance == "synthetic"


def creative_metadata_for(character, slides, brand):
    synthetic_person = is_synthetic_character(character)
    composited_result = any(slide.get("kind") == "screenshot" for slide in (slides or []))
    illustrative_results = synthetic_person and composited_result
    disclosure = (
        str(brand.caption.get("illustrative_results") or "").strip()
        if illustrative_results else ""
    )
    if illustrative_results and not disclosure:
        raise RuntimeError(
            f"{brand.brand_id} must configure caption.illustrative_results for "
            "synthetic composited creatives"
        )
    return {
        "is_aigc": synthetic_person,
        "synthetic_person": synthetic_person,
        "composited_result": composited_result,
        "illustrative_results": illustrative_results,
        "illustrative_results_text": disclosure or None,
    }


def synthetic_slide_copy(character, index, brand):
    iteration = pick_iteration(character, index)
    defaults = {
        "scan_text": brand.testimonial.get("synthetic_scan_text")
            or "Scan your face. Get your Glo Score.",
        "result_text": brand.testimonial.get("synthetic_result_text")
            or "See what your routine is doing.",
        "progress_text": brand.testimonial.get("synthetic_progress_text")
            or "Track your progress over time.",
        "progress_subtext": brand.testimonial.get("synthetic_progress_subtext")
            or "Results vary.",
    }
    return {
        key: str(iteration.get(key) or value).strip()
        for key, value in defaults.items()
    }


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


def build_testimonial_brief(render_slug, char_dir, shot_before, shot_after, character, index, brand):
    hook = pick_hook(character, index, brand)
    synthetic = is_synthetic_character(character)
    slide_copy = synthetic_slide_copy(character, index, brand) if synthetic else {}
    disclosure = (
        str(brand.caption.get("illustrative_results") or "").strip()
        if synthetic and shot_before and shot_after else ""
    )
    slides = [
        {
            "kind": "hook",
            "layout": "image_top",
            "label": None if synthetic else "before",
            "image": str(face_asset(char_dir, "opening", "before")),
            "text": hook,
        },
    ]
    product_prop = optional_asset(char_dir, "product_prop")
    if product_prop:
        slides.append({
            "kind": "body",
            "image": str(product_prop),
            "text": character.get("product_slide_caption") or cf.load_prompt_config(
                brand.prompt_path("image_character"))["product_slide_caption"],
            "duration": 2.3,
        })
    if shot_before and shot_after:
        scan_caption = (
            slide_copy["scan_text"]
            if synthetic else brand.testimonial.get("scan_caption") or "{score}"
        )
        slides += [
            {
                "kind": "screenshot",
                "image": str(shot_before),
                "caption": fill_template(
                    scan_caption.replace("{score}", str(character.get("before_score", 54))),
                    character,
                ),
            },
            {
                "kind": "screenshot",
                "image": str(shot_after),
                "caption": (
                    slide_copy["result_text"]
                    if synthetic else pick_mid_text(character, index, brand)
                ),
            },
        ]
    else:
        slides.extend(brand.testimonial.get("no_screenshot_slides") or [])

    slides += [
        {
            "kind": "body",
            "layout": "image_top",
            "label": None if synthetic else "after",
            "image": str(char_dir / "after.png"),
            "text": (
                slide_copy["progress_text"]
                if synthetic else pick_after_text(character, index, brand)
            ),
            "subtext": slide_copy.get("progress_subtext") if synthetic else None,
        },
        {
            "kind": "cta",
            "text": character.get("cta") or brand.testimonial.get("cta_text") or brand.cta.get("text"),
            "button": brand.testimonial.get("cta_button") or brand.cta.get("button"),
            "subtext": brand.testimonial.get("cta_subtext") or brand.cta.get("subtext"),
        },
    ]
    if disclosure:
        for slide in slides:
            slide["disclosure"] = disclosure
    return {
        "slug": render_slug,
        "brand": brand.brand_id,
        "slides": slides,
    }


def caption_for(character, hook, tracking_code, brand, metadata=None):
    base = character.get("caption")
    if base:
        lead = base.strip()
    else:
        lead = clean_line(hook)
    parts = [
        lead,
        brand.caption.get("secondary_cta") or brand.cta.get("text", ""),
        brand.caption.get("disclaimer", ""),
        f"Tracking: {tracking_code}",
    ]
    if (metadata or {}).get("illustrative_results"):
        parts.insert(2, metadata.get("illustrative_results_text") or "")
    return "\n\n".join(item for item in parts if item).strip()


def publish_queue_status(post_id, compliance, account, manifest_path):
    if compliance.get("status") != "pass":
        return "needs_edit", None
    post = manifest.get_post(post_id, manifest_path)
    try:
        publish.require_compliance(post, posts_path=manifest_path)
    except publish.PublishError as exc:
        return "needs_edit", str(exc)
    return "ready_to_post", None


def copy_package(post_id, result, brief, caption, posts_dir, run_date, brand_id,
                 project_id, assets=None):
    package_dir = Path(posts_dir) / brand_id / project_id / run_date / post_id
    package_dir.mkdir(parents=True, exist_ok=True)

    slides_dest = package_dir / "slides"
    if result and result.get("slides"):
        slides_dest.mkdir(parents=True, exist_ok=True)
        for slide_path in result["slides"]:
            shutil.copy2(slide_path, slides_dest / Path(slide_path).name)

    video_dest = package_dir / "video.mp4"
    if result and result.get("video"):
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
        "slides_dir": rel(slides_dest) if slides_dest.exists() else None,
        "video": rel(video_dest) if video_dest.exists() else None,
        "caption": rel(caption_dest),
        "brief": rel(brief_dest),
        "assets_dir": rel(asset_dest) if copied_assets else None,
        "assets": copied_assets,
        "metadata": rel(metadata_dest),
        "formats": {},
    }
    return package, metadata_dest


def write_metadata(post_id, metadata_dest, manifest_path):
    post = manifest.get_post(post_id, manifest_path)
    metadata_dest.write_text(json.dumps(post, indent=2), encoding="utf-8")


def write_platform_payloads(post_id, package, manifest_path):
    post = manifest.get_post(post_id, manifest_path)
    destination = Path(package["dir"]) / "platform_payloads.json"
    destination.write_text(
        json.dumps(publish.platform_payloads_for(post), indent=2), encoding="utf-8")
    package = {**package, "platform_payloads": rel(destination)}
    manifest.set_package(post_id, package, path=manifest_path)
    return package


def attach_text_formats(post_id, brief, brand, package, outputs, formats, placeholder,
                        tracking_code, manifest_path):
    text_names = tf.text_format_names(formats)
    if not text_names:
        return package, outputs
    package_dir = Path(package["dir"])
    rendered = tf.render_formats(
        brief,
        brand,
        package_dir,
        text_names,
        placeholder=placeholder,
        tracking_code=tracking_code,
    )
    rel_rendered = {name: rel(path) for name, path in rendered.items()}
    package = {**package, "formats": rel_rendered}
    outputs = {**outputs, "formats": rel_rendered, **rel_rendered}
    manifest.set_package(post_id, package, path=manifest_path)
    manifest.update_post(post_id, {"outputs": outputs}, manifest_path)
    return package, outputs


def build_text_brief(slug, angle, brand, formats):
    claim_packs = relevant_claim_packs(angle)
    seeded = {
        "claim_packs": claim_packs,
        "mechanism_claims": mechanism_claims_for(brand, angle),
        "claim_lanes": brand.claim_lanes,
    }
    return {
        "slug": slug,
        "brand": brand.brand_id,
        "angle": angle,
        "formats": tf.text_format_names(formats),
        "slides": [],
        "factual_claims": [angle],
        "claim_packs": claim_packs,
        "mechanism_claims": pack_mechanism_claims(seeded),
        "claim_lanes": brand.claim_lanes,
        "operational_status": brand.operational_status,
    }


def run_compliance(post_id, brief, brand, package, caption, slides,
                   tracking_code, manifest_path):
    results = {}
    format_paths = package.get("formats") or {}
    for format_name, path in format_paths.items():
        results[format_name] = compliance_lint.lint_file(
            path, format_name, brand, brief, tracking_code=tracking_code,
            context={"operational_status": brand.operational_status})
    if not results:
        context = {
            "operational_status": brand.operational_status,
        }
        combined = "\n\n".join([
            caption or "",
            *[str(item.get("text") or "") for item in (slides or [])],
        ]).strip()
        results["caption_and_slides"] = compliance_lint.lint_output(
            combined, brand, brief, context=context)
    compliance = compliance_lint.aggregate_results(results)
    manifest.set_compliance(post_id, compliance, manifest_path)
    return compliance


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", default=DEFAULT_BRAND)
    ap.add_argument("--roster", default="roster.json")
    ap.add_argument("--spec", default=None,
                    help="ad-hoc character spec for a one-off dashboard prompt test")
    ap.add_argument("--angle", default=None,
                    help="angle for text-native format runs")
    ap.add_argument("--hook", default=None,
                    help="hook for --spec prompt tests")
    ap.add_argument("--before-score", type=int, default=54)
    ap.add_argument("--after-score", type=int, default=87)
    ap.add_argument("--avatars", type=int, default=None,
                    help="number of roster characters to generate this run")
    ap.add_argument("--character-slug", default=None,
                    help="run one saved roster character by slug")
    ap.add_argument("--character-slugs", default=None,
                    help="comma-separated saved roster characters in batch order")
    ap.add_argument("--batch-id", default=None,
                    help="stable dashboard batch identifier")
    ap.add_argument("--project-id", default=None,
                    help="local project used to isolate generated result folders")
    ap.add_argument("--run-input", default=None,
                    help="JSON file containing per-run creative overrides")
    ap.add_argument("--prompt-config", default=None,
                    help="per-run image prompt config snapshot")
    ap.add_argument("--posts-per-avatar", type=int, default=1,
                    help="number of post iterations to render for each avatar")
    ap.add_argument("--out", default="output")
    ap.add_argument("--posts-dir", default="posts")
    ap.add_argument("--manifest", default="posts.json")
    ap.add_argument("--templates", default="templates")
    ap.add_argument("--assets", default="assets")
    ap.add_argument("--shots", default="screenshots")
    ap.add_argument("--provider", default=os.environ.get("IMAGE_PROVIDER", "openai"))
    ap.add_argument("--account", default=None)
    ap.add_argument("--formats", default=None,
                    help="comma-separated outputs, e.g. slideshow,reddit_longform,x_thread,tiktok_script")
    ap.add_argument("--opening-style", choices=sorted(cf.OPENING_PRESETS), default=None)
    ap.add_argument("--product-style", choices=sorted(cf.PRODUCT_PROP_PRESETS), default=None)
    ap.add_argument("--product-slide-caption", default=None)
    ap.add_argument("--placeholder", action="store_true",
                    help="skip image APIs and use labeled placeholder faces")
    args = ap.parse_args()

    brand = load_brand(args.brand)
    project_id = args.project_id or default_project_id(brand.brand_id)
    formats = tf.parse_formats(args.formats, brand=brand, default=["slideshow"])
    wants_slideshow = "slideshow" in formats
    wants_text = bool(tf.text_format_names(formats))
    account = args.account or brand.default_account
    prompt_config_path = Path(args.prompt_config) if args.prompt_config else brand.prompt_path("image_character")
    os.environ["IMAGE_PROVIDER"] = args.provider
    roster = json.loads(Path(args.roster).read_text(encoding="utf-8")) if Path(args.roster).exists() else {}
    run_input = (
        json.loads(Path(args.run_input).read_text(encoding="utf-8"))
        if args.run_input and Path(args.run_input).exists() else {}
    )
    template_key = roster.get("template", "scan_results")
    template = brand.template_path(template_key)
    if template and not template.exists():
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
        characters = copy.deepcopy(roster.get("characters", []))
        if args.character_slugs:
            requested_slugs = [
                slug.strip() for slug in args.character_slugs.split(",") if slug.strip()
            ]
            by_slug = {character.get("slug"): character for character in characters}
            missing = [slug for slug in requested_slugs if slug not in by_slug]
            if missing:
                raise SystemExit("roster characters not found: " + ", ".join(missing))
            characters = [by_slug[slug] for slug in requested_slugs]
        elif args.character_slug:
            characters = [
                character for character in characters
                if character.get("slug") == args.character_slug
            ]
            if not characters:
                raise SystemExit(f"roster character not found: {args.character_slug}")
    if args.avatars is not None:
        characters = characters[:max(0, args.avatars)]

    apply_hook_overrides(characters, run_input.get("hook_overrides") or {})
    apply_slide_copy_overrides(
        characters, run_input.get("slide_copy_overrides") or {})

    run_id = args.batch_id or datetime.now().strftime("%Y%m%d%H%M%S")
    run_date = datetime.now().strftime("%Y-%m-%d")
    built = []

    if not wants_slideshow:
        if not wants_text:
            raise SystemExit("no output formats requested")
        angle = (args.angle or args.hook or "").strip()
        if not angle:
            raise SystemExit("text-only runs require --angle or --hook")
        render_slug = f"text_{tf.slugify(angle)}_{run_id}"
        tracking_code = f"{brand.tracking.get('prefix', brand.brand_id)}_{run_id}_01_01"
        brief = build_text_brief(render_slug, angle, brand, formats)
        caption = caption_for({}, angle, tracking_code, brand)
        outputs = {}
        post_id = manifest.record_post(
            brand=brand.brand_id,
            project_id=project_id,
            batch_id=run_id,
            workflow="text",
            character={},
            fmt="text_native",
            hook=angle,
            slides=[],
            assets={},
            outputs=outputs,
            tracking_code=tracking_code,
            caption=caption,
            publish_queue={
                "status": "rendered",
                "target_account": account,
                "notes": None,
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            },
            path=args.manifest,
        )
        package, metadata_dest = copy_package(
            post_id, None, brief, caption, args.posts_dir, run_date, brand.brand_id,
            project_id)
        manifest.set_package(post_id, package, caption, args.manifest)
        package, outputs = attach_text_formats(
            post_id, brief, brand, package, outputs, formats, args.placeholder,
            tracking_code, args.manifest)
        compliance = run_compliance(
            post_id, brief, brand, package, caption, [], tracking_code, args.manifest)
        queue_status, queue_note = publish_queue_status(
            post_id, compliance, account, args.manifest)
        manifest.set_publish_queue(
            post_id, queue_status, account, queue_note, path=args.manifest)
        package = write_platform_payloads(post_id, package, args.manifest)
        write_metadata(post_id, metadata_dest, args.manifest)
        built.append((post_id, package["dir"]))
        print(f"[post] {post_id} -> {package['dir']}")
        print(f"\n{len(built)} posts packaged under {args.posts_dir}/{brand.brand_id}/{project_id}/{run_date}/")
        print(f"Manual queue status: {queue_status}")
        return

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
            prompt_config_path,
            opening_style=args.opening_style,
            product_style=args.product_style,
        )
        char_dir = Path(args.assets) / slug
        if template:
            shot_before, shot_after = prepare_screenshots(
                template, char_dir, slug, character, args.shots)
        else:
            shot_before, shot_after = None, None

        for post_index in range(max(1, args.posts_per_avatar)):
            render_key = compact_render_key(character, slug)
            render_slug = f"testimonial_{render_key}_p{post_index + 1:02d}_{run_id}"
            tracking_code = (
                f"{brand.tracking.get('prefix', brand.brand_id)}_"
                f"{run_id}_{avatar_index:02d}_{post_index + 1:02d}"
            )
            brief = build_testimonial_brief(
                render_slug, char_dir, shot_before, shot_after, character, post_index, brand)
            hook = pick_hook(character, post_index, brand)
            creative_metadata = creative_metadata_for(character, brief["slides"], brand)
            brief["formats"] = formats
            brief.setdefault("factual_claims", [hook])
            brief.setdefault("claim_packs", relevant_claim_packs(hook))
            brief.setdefault("claim_lanes", brand.claim_lanes)
            brief.setdefault("mechanism_claims", pack_mechanism_claims(brief))
            brief.setdefault("operational_status", brand.operational_status)
            result = sm.make_content(brief, args.out, brand=brand)
            caption = caption_for(
                character, hook, tracking_code, brand, metadata=creative_metadata)
            outputs = {
                "slides_dir": rel(result["dir"]),
                "video": rel(result["video"]),
            }

            post_id = manifest.record_post(
                brand=brand.brand_id,
                project_id=project_id,
                batch_id=run_id,
                workflow="slideshow",
                character={
                    "slug": slug,
                    "spec": character["spec"],
                    "variant_id": character.get("variant_id"),
                    "variant_name": character.get("variant_name"),
                    "base_character_slug": character.get("base_character_slug"),
                    "source_asset_slug": character.get("source_asset_slug"),
                    "source_type": character.get("source_type"),
                    "before_score": character.get("before_score"),
                    "after_score": character.get("after_score"),
                    "opening_style": character.get("opening_style") or cf.load_prompt_config(
                        prompt_config_path)["opening_style"],
                    "product_style": character.get("product_style") or cf.load_prompt_config(
                        prompt_config_path)["product_style"],
                },
                fmt="testimonial_beforeafter",
                hook=hook,
                slides=[{"kind": s["kind"],
                         "text": s.get("text") or s.get("caption", ""),
                         "subtext": s.get("subtext"),
                         "disclosure": s.get("disclosure")}
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
                outputs=outputs,
                tracking_code=tracking_code,
                caption=caption,
                metadata=creative_metadata,
                publish_queue={
                    "status": "rendered",
                    "target_account": account,
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
                post_id, result, brief, caption, args.posts_dir, run_date,
                brand.brand_id, project_id, package_assets)
            manifest.set_package(post_id, package, caption, args.manifest)
            package, outputs = attach_text_formats(
                post_id, brief, brand, package, outputs, formats, args.placeholder,
                tracking_code, args.manifest)
            compliance = run_compliance(
                post_id, brief, brand, package, caption, brief.get("slides") or [],
                tracking_code, args.manifest)
            queue_status, queue_note = publish_queue_status(
                post_id, compliance, account, args.manifest)
            manifest.set_publish_queue(
                post_id, queue_status, account, queue_note, path=args.manifest)
            package = write_platform_payloads(post_id, package, args.manifest)
            write_metadata(post_id, metadata_dest, args.manifest)

            built.append((post_id, package["dir"]))
            print(f"[post] {post_id} -> {package['dir']}")

    print(f"\n{len(built)} posts packaged under {args.posts_dir}/{brand.brand_id}/{project_id}/{run_date}/")
    print("Manual queue status is ready_to_post only for compliance=pass; review the manifest.")


if __name__ == "__main__":
    main()
