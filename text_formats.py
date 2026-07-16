#!/usr/bin/env python3
"""
Text-native format renderer.

Generates brand-aware Reddit longform posts, X threads, and TikTok scripts from
a brief. Real generation goes through llm_router; --placeholder creates local
deterministic drafts for tests and dashboard dry runs.
"""
import argparse
import json
import re
from pathlib import Path

from brand_loader import DEFAULT_BRAND, load_brand
from llm_router import complete


FORMAT_FILES = {
    "reddit_longform": "reddit.md",
    "x_thread": "thread.json",
    "tiktok_script": "tiktok_script.md",
}
SECTION_NAMES = ["HOOK", "BEATS", "CTA", "SHOTLIST"]


class TextFormatError(RuntimeError):
    pass


def parse_formats(value, brand=None, default=None):
    if value is None or value == "":
        return list(default or ["slideshow"])
    if isinstance(value, (list, tuple)):
        raw = value
    else:
        raw = str(value).split(",")
    formats = []
    for item in raw:
        name = str(item).strip()
        if not name:
            continue
        if name == "all" and brand:
            formats.extend(brand.formats)
        else:
            formats.append(name)
    seen = []
    for name in formats:
        if name not in seen:
            seen.append(name)
    if brand:
        unsupported = [name for name in seen if name not in brand.formats]
        if unsupported:
            raise TextFormatError(
                f"{brand.brand_id} does not enable format(s): {', '.join(unsupported)}"
            )
    return seen


def text_format_names(formats):
    return [name for name in formats if name != "slideshow"]


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_") or "text_post"


def strip_fences(text):
    text = str(text or "").strip()
    text = re.sub(r"^```(?:json|markdown|md)?", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"```$", "", text).strip()
    return text


def brief_angle(brief):
    if brief.get("angle"):
        return brief["angle"]
    if brief.get("hook"):
        return brief["hook"]
    slides = brief.get("slides") or []
    for slide in slides:
        if slide.get("text") or slide.get("caption"):
            return slide.get("text") or slide.get("caption")
    return brief.get("slug", "content angle")


def brief_context(brief, brand, format_name):
    slides = brief.get("slides") or []
    slide_lines = [
        f"- {s.get('kind', 'body')}: {s.get('text') or s.get('caption') or ''}"
        for s in slides
    ]
    return "\n".join([
        f"Brand: {brand.display_name}",
        f"Format: {format_name}",
        f"Angle: {brief_angle(brief)}",
        f"CTA text: {brand.cta.get('text', '')}",
        f"CTA URL: {brand.cta.get('url', '')}",
        f"Voice: {json.dumps(brand.voice)}",
        f"Pillars: {', '.join(brand.pillars)}",
        "Existing slide/copy context:",
        "\n".join(slide_lines) if slide_lines else "(none)",
    ])


def load_system_prompt(brand, format_name):
    copy_prompt = brand.prompt_path("copy_system")
    format_prompt = brand.format_prompt_path(format_name)
    if not copy_prompt or not copy_prompt.exists():
        raise TextFormatError(f"missing copy prompt for {brand.brand_id}")
    if not format_prompt.exists():
        raise TextFormatError(f"missing format prompt: {format_prompt}")
    return "\n\n".join([
        copy_prompt.read_text(encoding="utf-8"),
        format_prompt.read_text(encoding="utf-8"),
    ])


def generate_format(brief, brand, format_name, *, placeholder=False):
    if placeholder:
        return placeholder_format(brief, brand, format_name)
    raw = complete(
        system=load_system_prompt(brand, format_name),
        user=brief_context(brief, brand, format_name),
        task=format_name,
        max_tokens=1800 if format_name == "reddit_longform" else 1000,
    )
    return normalize_format(format_name, raw)


def normalize_format(format_name, raw):
    if format_name == "reddit_longform":
        return validate_reddit(strip_fences(raw))
    if format_name == "x_thread":
        text = strip_fences(raw)
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise TextFormatError(f"x_thread did not return valid JSON: {exc}") from exc
        return validate_x_thread(data)
    if format_name == "tiktok_script":
        return validate_tiktok_script(strip_fences(raw))
    raise TextFormatError(f"unknown text format: {format_name}")


def validate_reddit(text):
    lines = text.splitlines()
    if not lines or not lines[0].strip():
        raise TextFormatError("reddit_longform must start with a title line")
    if len(lines) < 3 or lines[1].strip():
        raise TextFormatError("reddit_longform must have a blank line after the title")
    body = "\n".join(lines[2:]).strip()
    words = re.findall(r"\b[\w'-]+\b", body)
    if not 300 <= len(words) <= 800:
        raise TextFormatError(
            f"reddit_longform body must be 300-800 words; got {len(words)}"
        )
    return text.rstrip() + "\n"


def validate_x_thread(data):
    if not isinstance(data, dict) or not isinstance(data.get("tweets"), list):
        raise TextFormatError('x_thread must be JSON shaped as {"tweets": ["..."]}')
    tweets = data["tweets"]
    if not tweets:
        raise TextFormatError("x_thread must contain at least one tweet")
    clean = []
    for index, tweet in enumerate(tweets, start=1):
        if not isinstance(tweet, str) or not tweet.strip():
            raise TextFormatError(f"tweet {index} is empty or not a string")
        if len(tweet) > 275:
            raise TextFormatError(
                f"tweet {index} is {len(tweet)} characters; max is 275"
            )
        clean.append(tweet.strip())
    return {"tweets": clean}


def validate_tiktok_script(text):
    upper = text.upper()
    for section in SECTION_NAMES:
        if not re.search(rf"(^|\n){section}\s*(\n|$)", upper):
            raise TextFormatError(f"tiktok_script missing section: {section}")
    return text.rstrip() + "\n"


def placeholder_format(brief, brand, format_name):
    if format_name == "reddit_longform":
        return validate_reddit(placeholder_reddit(brief, brand))
    if format_name == "x_thread":
        return validate_x_thread({"tweets": placeholder_thread(brief, brand)})
    if format_name == "tiktok_script":
        return validate_tiktok_script(placeholder_tiktok_script(brief, brand))
    raise TextFormatError(f"unknown text format: {format_name}")


def placeholder_reddit(brief, brand):
    angle = str(brief_angle(brief)).strip().rstrip(".")
    if brand.brand_id == "vendrarx":
        title = "The peptide therapy question I would ask before joining any program"
        paragraphs = [
            f"I keep coming back to this angle: {angle}. The interesting part is not whether peptides sound exciting. The interesting part is whether the operation around them is serious enough for a medical category that has been pushed through a lot of internet noise.",
            "The first filter is oversight. A real program should start with intake, history, and physician review before anyone talks about a protocol. That sounds obvious, but it is exactly where a lot of peptide marketing gets weird. People are sold vials, stacks, and slogans before anyone has checked whether the category is appropriate for them.",
            "The second filter is sourcing. VendraRx is being built around physician-prescribed protocols and 503A compounding pharmacy partners, not research-use-only vendors. That distinction matters because research peptides sold online are often outside normal patient-specific prescribing and pharmacy controls. Serious care should be boring in the right places: documentation, pharmacy process, lot testing, cold-chain shipping, and follow-up.",
            "The third filter is expectations. Compounded medications are not FDA-approved drugs, and nobody should promise a specific outcome or a guaranteed prescription from a quiz. The quiz should help route people toward a clinician review, and that clinician should be able to say no, pause, or adjust based on the person's history, labs, goals, and risk profile.",
            "A good intake flow should also make disqualification feel normal. Underage patients, pregnancy, active malignancy, certain endocrine situations, medication conflicts, or missing labs can all change the answer. The point of a clinical program is not to push every person through the same funnel. It is to decide who should move forward, who needs more information, and who should be declined or sent elsewhere.",
            "That is the bar I would use as a patient: not the loudest peptide brand, not the most aggressive claim, and not the fastest checkout. I would look for the group willing to explain the framework, name the caveats, and keep the prescribing decision in a clinician's hands. If that is the kind of access you want, the founding-member quiz is on vendrarx.com.",
        ]
    else:
        title = "The skincare audit I wish I had done before buying another serum"
        paragraphs = [
            f"The angle is simple: {angle}. Most routines do not fail because someone forgot to buy enough products. They fail because the products were chosen one at a time, usually after a panic scroll, and nobody ever looked at the whole routine as a system.",
            "That is where an AI skincare app can be useful. GloSkin is not there to tell you that one bottle fixes everything. It gives you a way to scan your face, get a Glo Score, look at product labels, and understand where the routine might be overloaded, missing basics, or repeating the same category three times with different packaging.",
            "The helpful part is the audit. You can look at texture, tone, pores, hydration, and progress without pretending that a single screenshot explains your entire skin. You can also scan products you already own, which matters because the cheapest routine upgrade is often using what is already on your shelf in a smarter order.",
            "It also creates a better feedback loop. Instead of changing five things at once and trying to remember what happened, you can keep the routine stable, track progress, and make smaller adjustments. That is less dramatic than buying a viral product, but it is usually more useful. The boring questions matter: are you cleansing too much, skipping moisturizer, doubling up on harsh actives, or missing sunscreen during the day?",
            "I would treat it like a second brain for skincare: useful for pattern spotting, ingredient translation, and routine organization. It should not replace medical care, and it should not promise to cure acne or any skin condition. Results vary. Skin is personal. But a clearer system beats a drawer full of random impulse buys.",
            "If your routine feels chaotic, the first move is not necessarily another active. It might be a better map of what you are already doing. That is the point of checking your Glo Score and building from there at gloskin.app.",
        ]
    return title + "\n\n" + "\n\n".join(paragraphs)


def placeholder_thread(brief, brand):
    angle = str(brief_angle(brief)).strip().rstrip(".")
    if brand.brand_id == "vendrarx":
        return [
            f"{angle}: the real question is not hype. It is whether the care model is serious enough.",
            "For peptide therapy, I would look for physician review before protocol, not checkout-first selling.",
            "I would also ask where the medication comes from. VendraRx is being built around 503A compounding pharmacy partners, not research-use-only sourcing.",
            "Compounded medications are not FDA-approved. Suitability should be determined by a licensed clinician, and outcomes should not be promised.",
            "The boring parts matter: intake, history, labs when appropriate, cold-chain shipping, COAs, follow-up, and the ability to pause or adjust.",
            "Founding-member access and the 60-second quiz are at vendrarx.com.",
        ]
    return [
        f"{angle}: before buying another serum, audit the routine you already have.",
        "GloSkin is useful because it turns the routine into something you can actually inspect: face scan, Glo Score, product scanner, and progress tracking.",
        "The goal is not to promise perfect skin. It is to stop guessing and understand what your products are doing together.",
        "Scan what you own, look for overlap, check the basics, and track what changes over time.",
        "Results vary and this is not medical advice, but a clearer system beats a shelf full of random bottles.",
        "Check your Glo Score at gloskin.app.",
    ]


def placeholder_tiktok_script(brief, brand):
    angle = str(brief_angle(brief)).strip().rstrip(".")
    if brand.brand_id == "vendrarx":
        return "\n".join([
            "HOOK",
            f"{angle} is the wrong question unless the care model is serious.",
            "",
            "BEATS",
            "1. Start with the problem: peptide marketing often skips the medical process.",
            "2. Show the standard: intake, history, and physician review before any protocol.",
            "3. Explain sourcing: 503A-compounded when clinically appropriate, not research-use-only vials.",
            "4. Name the caveat: compounded medications are not FDA-approved and outcomes are not guaranteed.",
            "",
            "CTA",
            "Take the 60-second quiz for founding-member access at vendrarx.com.",
            "",
            "SHOTLIST",
            "Founder talking to camera; simple text overlays; screenshot of the homepage quiz; desk shot with notes labeled intake, labs, follow-up; end card with vendrarx.com.",
        ])
    return "\n".join([
        "HOOK",
        f"{angle} is exactly why your skincare routine needs an audit.",
        "",
        "BEATS",
        "1. Show the messy product lineup.",
        "2. Scan the face and show the Glo Score concept.",
        "3. Scan product labels and call out overlap or missing basics.",
        "4. Build a cleaner routine from what is already there.",
        "",
        "CTA",
        "Check your Glo Score at gloskin.app.",
        "",
        "SHOTLIST",
        "Before selfie; app scan screen; quick product-label closeups; routine checklist overlay; final app CTA screen.",
    ])


def write_format(out_dir, format_name, content):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / FORMAT_FILES[format_name]
    if format_name == "x_thread":
        path.write_text(json.dumps(content, indent=2), encoding="utf-8")
    else:
        path.write_text(content, encoding="utf-8")
    return path


def render_formats(brief, brand, out_dir, formats, *, placeholder=False):
    outputs = {}
    for format_name in text_format_names(formats):
        if format_name not in FORMAT_FILES:
            raise TextFormatError(f"unknown text format: {format_name}")
        content = generate_format(brief, brand, format_name, placeholder=placeholder)
        outputs[format_name] = write_format(out_dir, format_name, content)
    return outputs


def selftest():
    try:
        validate_x_thread({"tweets": ["x" * 276]})
    except TextFormatError:
        pass
    else:
        raise TextFormatError("x_thread validator failed to reject a 276-char tweet")
    validate_tiktok_script("HOOK\nA\n\nBEATS\n1. B\n\nCTA\nC\n\nSHOTLIST\nD\n")
    validate_reddit(placeholder_reddit({"angle": "routine audit"}, load_brand(DEFAULT_BRAND)))
    print("[ok] text format validators")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--brief")
    ap.add_argument("--angle")
    ap.add_argument("--brand", default=DEFAULT_BRAND)
    ap.add_argument("--formats", default="reddit_longform,x_thread,tiktok_script")
    ap.add_argument("--out", default="output/text_formats")
    ap.add_argument("--placeholder", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        selftest()
        return

    brand = load_brand(args.brand)
    formats = parse_formats(args.formats, brand=brand, default=[])
    if args.brief:
        brief = json.loads(Path(args.brief).read_text(encoding="utf-8"))
    elif args.angle:
        brief = {
            "slug": slugify(args.angle),
            "brand": brand.brand_id,
            "angle": args.angle,
            "formats": formats,
            "slides": [],
        }
    else:
        ap.error("pass --brief, --angle, or --selftest")
    outputs = render_formats(brief, brand, args.out, formats, placeholder=args.placeholder)
    print(json.dumps({k: str(v).replace("\\", "/") for k, v in outputs.items()}, indent=2))


if __name__ == "__main__":
    main()
