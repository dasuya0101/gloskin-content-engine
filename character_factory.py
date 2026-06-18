#!/usr/bin/env python3
"""
Character factory
=================
Generates before/scan/after selfie sets for testimonial slideshows.

For each character it produces:
  assets/<slug>/before.png   acne, plain selfie, neutral/unhappy
  assets/<slug>/opening.png  optional first-slide close-up / attention image
  assets/<slug>/scan.png     SAME person, neutral app-scan selfie
  assets/<slug>/after.png    SAME person, clear glowing skin, smiling
  assets/<slug>/product_prop.png  optional unbranded skincare product prop image

Consistency trick: "scan" and "after" are produced with the OpenAI *image edit*
endpoint using before.png as the reference, so each asset reads as the same face.

It sweeps demographics (age band, gender presentation, ethnicity, etc.) so you
can fan out dozens of variants and let the platforms tell you which converts.

Setup:
  pip install openai
  export OPENAI_API_KEY=sk-...

Usage:
  python character_factory.py --count 8 --out assets          # random sweep
  python character_factory.py --spec "f, 20s, East Asian" --out assets
  python character_factory.py --placeholder --count 4 --out assets   # no API, layout test

The slug it prints can be referenced from a testimonial brief's slide "image".
"""
import argparse
import base64
import itertools
import os
import random
import re
import json
from pathlib import Path

AGES = ["late teens", "early 20s", "late 20s", "30s"]
GENDERS = ["woman", "man", "non-binary person"]
ETHNICITIES = ["East Asian", "South Asian", "Black", "Hispanic/Latino",
               "White", "Middle Eastern", "Southeast Asian", "mixed-race"]


def _first_font(candidates):
    for p in candidates:
        if p and Path(p).exists():
            return p
    return None


FONT_BOLD = os.environ.get("GLO_FONT_BOLD") or _first_font([
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/calibrib.ttf",
])
FONT_REG = os.environ.get("GLO_FONT_REG") or _first_font([
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/calibri.ttf",
])

BEFORE_TMPL = (
    "Front-facing iPhone selfie of a {age} {ethnicity} {gender}, bare face with "
    "visible moderate acne and redness on cheeks and forehead, no makeup, neutral "
    "to slightly unhappy expression, plain soft-lit bathroom background, natural "
    "skin texture, realistic, not airbrushed, vertical 9:16 framing."
)
AFTER_PROMPT = (
    "Same person, same face and hair, now with clear healthy glowing skin and a "
    "warm genuine smile, acne resolved, even tone, same lighting and framing, "
    "realistic natural skin texture."
)
SCAN_PROMPT = (
    "Same person, same face and hair, front-facing neutral app scan selfie, bare "
    "skin, centered face, even soft bathroom lighting, no makeup, realistic "
    "natural skin texture, vertical 9:16 framing."
)
OPENING_PRESETS = {
    "selfie": "",
    "close_up_acne": (
        "Same person, macro close-up iPhone photo cropped tightly on one cheek "
        "and chin with visible acne, redness, pores, and natural skin texture, "
        "no makeup, soft bathroom lighting, realistic, not clinical, vertical "
        "9:16 framing."
    ),
    "forehead_texture": (
        "Same person, close-up iPhone photo cropped on forehead and upper cheeks "
        "showing visible bumps, redness, pores, and uneven texture, no makeup, "
        "soft natural bathroom lighting, realistic, vertical 9:16 framing."
    ),
}
PRODUCT_PROP_PRESETS = {
    "none": "",
    "common_products": (
        "Vertical iPhone photo of a bathroom counter with a few unbranded common "
        "skincare products: cleanser, moisturizer, sunscreen, serum bottle, and "
        "pimple patches. No readable brand names, no medical claims, realistic "
        "messy routine vibe, attention-grabbing composition."
    ),
    "niche_products": (
        "Vertical iPhone photo of a bathroom counter with unbranded niche skincare "
        "items: ampoule bottle, barrier cream tube, hypochlorous spray, azelaic "
        "acid-style tube, pimple patches, and a small LED mask. No readable brand "
        "names, no recommendation framing, realistic attention-grabbing layout."
    ),
    "random_products": (
        "Vertical iPhone photo of a random mix of unbranded skincare products on "
        "a bathroom counter, combining common and niche items, varied bottle "
        "shapes, tubes, patches, and one unusual skincare gadget. No readable "
        "brand names, no medical claims, not a recommendation, realistic "
        "attention-grabbing layout."
    ),
}
PRODUCT_SLIDE_CAPTION = "I had products. Not a plan."
PROMPT_CONFIG = Path(__file__).parent / "prompts" / "image_character.json"


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def random_spec():
    return f"{random.choice(GENDERS)}, {random.choice(AGES)}, {random.choice(ETHNICITIES)}"


def parse_spec(spec):
    parts = [p.strip() for p in spec.split(",")]
    gender = next((p for p in parts if any(g in p.lower()
                  for g in ["woman", "man", "female", "male", "f", "m", "non"])), "woman")
    gender = {"f": "woman", "female": "woman", "m": "man", "male": "man"}.get(
        gender.lower(), gender)
    age = next((p for p in parts if any(c.isdigit() for c in p) or "teen" in p.lower()),
               "early 20s")
    eth = next((p for p in parts if p not in (gender, age)), "")
    return age, gender, eth


def load_prompt_config(path=PROMPT_CONFIG):
    if Path(path).exists():
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    else:
        data = {}
    opening_presets = {**OPENING_PRESETS, **data.get("opening_presets", {})}
    product_prop_presets = {**PRODUCT_PROP_PRESETS, **data.get("product_prop_presets", {})}
    opening_style = data.get("opening_style") or "selfie"
    product_style = data.get("product_style") or "none"
    return {
        "before_template": data.get("before_template") or BEFORE_TMPL,
        "opening_style": opening_style,
        "opening_presets": opening_presets,
        "opening_prompt": data.get("opening_prompt") or opening_presets.get(opening_style, ""),
        "scan_prompt": data.get("scan_prompt") or SCAN_PROMPT,
        "after_prompt": data.get("after_prompt") or AFTER_PROMPT,
        "product_style": product_style,
        "product_prop_presets": product_prop_presets,
        "product_prop_prompt": data.get("product_prop_prompt") or product_prop_presets.get(product_style, ""),
        "product_slide_caption": data.get("product_slide_caption") or PRODUCT_SLIDE_CAPTION,
    }


def save_prompt_config(before_template, after_prompt, scan_prompt=None,
                       opening_style=None, opening_prompt=None,
                       product_style=None, product_prop_prompt=None,
                       product_slide_caption=None, path=PROMPT_CONFIG):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    cfg = load_prompt_config(path)
    data = {
        "before_template": before_template,
        "opening_style": opening_style or cfg["opening_style"],
        "opening_prompt": opening_prompt if opening_prompt is not None else cfg["opening_prompt"],
        "scan_prompt": scan_prompt or cfg["scan_prompt"],
        "after_prompt": after_prompt,
        "product_style": product_style or cfg["product_style"],
        "product_prop_prompt": (
            product_prop_prompt if product_prop_prompt is not None else cfg["product_prop_prompt"]
        ),
        "product_slide_caption": product_slide_caption or cfg["product_slide_caption"],
    }
    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def fill_prompt(template, age, gender, eth):
    return template.format(age=age, ethnicity=eth, gender=gender)


def character_prompts(spec, path=PROMPT_CONFIG, opening_style=None, product_style=None):
    age, gender, eth = parse_spec(spec)
    cfg = load_prompt_config(path)
    active_opening_style = opening_style or cfg["opening_style"]
    active_product_style = product_style or cfg["product_style"]
    opening_prompt = cfg["opening_prompt"]
    if active_opening_style != cfg["opening_style"]:
        opening_prompt = cfg["opening_presets"].get(active_opening_style, opening_prompt)
    product_prop_prompt = cfg["product_prop_prompt"]
    if active_product_style != cfg["product_style"]:
        product_prop_prompt = cfg["product_prop_presets"].get(active_product_style, product_prop_prompt)
    return {
        "spec": spec,
        "age": age,
        "gender": gender,
        "ethnicity": eth,
        "before_prompt": fill_prompt(cfg["before_template"], age, gender, eth),
        "opening_style": active_opening_style,
        "opening_prompt": fill_prompt(opening_prompt, age, gender, eth) if opening_prompt else "",
        "scan_prompt": fill_prompt(cfg["scan_prompt"], age, gender, eth),
        "after_prompt": fill_prompt(cfg["after_prompt"], age, gender, eth),
        "product_style": active_product_style,
        "product_prop_prompt": (
            fill_prompt(product_prop_prompt, age, gender, eth) if product_prop_prompt else ""
        ),
        "product_slide_caption": cfg["product_slide_caption"],
        "before_template": cfg["before_template"],
        "opening_prompt_template": opening_prompt,
        "scan_prompt_template": cfg["scan_prompt"],
        "product_prop_prompt_template": product_prop_prompt,
        "opening_presets": cfg["opening_presets"],
        "product_prop_presets": cfg["product_prop_presets"],
    }


# ---- API path (provider-pluggable via image_router) ------------------------
def gen_pair_api(spec, out_dir, opening_style=None, product_style=None):
    import image_router
    age, gender, eth = parse_spec(spec)
    slug = slugify(f"{eth}_{gender}_{age}_{random.randint(100,999)}")
    d = Path(out_dir) / slug
    d.mkdir(parents=True, exist_ok=True)

    prompts = character_prompts(spec, opening_style=opening_style, product_style=product_style)
    before_prompt = prompts["before_prompt"]
    before_bytes = image_router.generate(before_prompt, size="1024x1536")
    (d / "before.png").write_bytes(before_bytes)

    if prompts["opening_style"] != "selfie" and prompts["opening_prompt"]:
        opening_bytes = image_router.edit(before_bytes, prompts["opening_prompt"], size="1024x1536")
        (d / "opening.png").write_bytes(opening_bytes)

    # scan: a neutral, centered selfie intended to be inserted into the real app
    # Scan Results template. The screen itself is never AI-generated.
    scan_bytes = image_router.edit(before_bytes, prompts["scan_prompt"], size="1024x1536")
    (d / "scan.png").write_bytes(scan_bytes)

    # after: edit the before image so the face stays consistent (provider falls
    # back to a fresh generate if it can't edit).
    after_bytes = image_router.edit(before_bytes, prompts["after_prompt"], size="1024x1536")
    (d / "after.png").write_bytes(after_bytes)

    if prompts["product_style"] != "none" and prompts["product_prop_prompt"]:
        prop_bytes = image_router.generate(prompts["product_prop_prompt"], size="1024x1536")
        (d / "product_prop.png").write_bytes(prop_bytes)
    return slug


# back-compat alias (run_pipeline / older callers)
gen_pair_openai = gen_pair_api


# ---- Offline placeholder path ---------------------------------------------
def gen_pair_placeholder(spec, out_dir, opening_style=None, product_style=None):
    from PIL import Image, ImageDraw, ImageFont
    age, gender, eth = parse_spec(spec)
    prompts = character_prompts(spec, opening_style=opening_style, product_style=product_style)
    slug = slugify(f"{eth}_{gender}_{age}_{random.randint(100,999)}")
    d = Path(out_dir) / slug
    d.mkdir(parents=True, exist_ok=True)

    def draw_face(path, state, tone):
        im = Image.new("RGB", (1024, 1536), tone)
        dr = ImageDraw.Draw(im)
        # Simple synthetic portrait placeholders make layout tests readable
        # without pretending the screenshot UI was generated.
        dr.rounded_rectangle([120, 120, 904, 1416], radius=64, fill=(232, 222, 224))
        dr.ellipse([290, 160, 735, 760], fill=(82, 61, 66))
        dr.rectangle([425, 670, 600, 910], fill=(188, 140, 125))
        dr.ellipse([310, 245, 715, 820], fill=(206, 154, 138))
        dr.arc([382, 445, 455, 490], 0, 180, fill=(55, 43, 48), width=8)
        dr.arc([570, 445, 642, 490], 0, 180, fill=(55, 43, 48), width=8)
        dr.ellipse([413, 468, 438, 493], fill=(50, 40, 46))
        dr.ellipse([594, 468, 619, 493], fill=(50, 40, 46))
        dr.line([512, 500, 492, 610, 532, 610], fill=(150, 100, 96), width=8)
        mouth_box = [452, 660, 572, 720]
        if state == "after":
            dr.arc(mouth_box, 5, 175, fill=(122, 52, 70), width=8)
        else:
            dr.line([462, 690, 562, 690], fill=(122, 52, 70), width=8)
        dr.pieslice([210, 820, 814, 1430], 180, 360, fill=(128, 88, 104))
        if state in {"before", "scan"}:
            for x, y, r in [(420, 545, 13), (602, 565, 10), (470, 640, 11),
                            (565, 625, 9), (390, 605, 8)]:
                dr.ellipse([x - r, y - r, x + r, y + r], fill=(184, 82, 89))
        im.save(path)

    for state, tone in (
        ("before", (214, 196, 204)),
        ("scan", (218, 204, 210)),
        ("after", (225, 205, 214)),
    ):
        draw_face(d / f"{state}.png", state, tone)

    if prompts["opening_style"] != "selfie":
        im = Image.new("RGB", (1024, 1536), (222, 203, 208))
        dr = ImageDraw.Draw(im)
        dr.rounded_rectangle([90, 120, 934, 1416], radius=58, fill=(212, 158, 142))
        for x, y, r in [(310, 430, 24), (440, 520, 32), (560, 475, 22),
                        (665, 600, 28), (520, 700, 20), (390, 760, 18)]:
            dr.ellipse([x - r, y - r, x + r, y + r], fill=(177, 74, 82))
        for x, y in [(250, 340), (725, 405), (610, 820), (365, 930)]:
            dr.arc([x, y, x + 120, y + 70], 0, 180, fill=(150, 100, 96), width=8)
        im.save(d / "opening.png")

    if prompts["product_style"] != "none":
        im = Image.new("RGB", (1024, 1536), (210, 205, 199))
        dr = ImageDraw.Draw(im)
        dr.rounded_rectangle([80, 170, 944, 1340], radius=64, fill=(238, 232, 224))
        palette = [(120, 94, 142), (82, 146, 137), (232, 186, 97), (210, 112, 125), (76, 82, 98)]
        boxes = [
            (150, 500, 290, 1060), (340, 420, 475, 1160), (540, 600, 710, 1200),
            (750, 470, 870, 1050), (210, 1070, 520, 1210), (570, 285, 805, 395),
        ]
        for i, box in enumerate(boxes):
            col = palette[i % len(palette)]
            dr.rounded_rectangle(box, radius=34, fill=col)
            x0, y0, x1, y1 = box
            dr.rectangle([x0 + 20, y0 + 40, x1 - 20, y0 + 72], fill=(255, 255, 255))
        im.save(d / "product_prop.png")
    return slug


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--spec")
    ap.add_argument("--out", default="assets")
    ap.add_argument("--opening-style", choices=sorted(OPENING_PRESETS), default=None)
    ap.add_argument("--product-style", choices=sorted(PRODUCT_PROP_PRESETS), default=None)
    ap.add_argument("--placeholder", action="store_true",
                    help="generate labeled placeholders instead of calling OpenAI")
    args = ap.parse_args()

    gen = gen_pair_placeholder if args.placeholder else gen_pair_openai
    specs = [args.spec] * args.count if args.spec else [random_spec() for _ in range(args.count)]
    for s in specs:
        slug = gen(s, args.out, opening_style=args.opening_style, product_style=args.product_style)
        print(f"[char] {s!r} -> assets/{slug}/  (before.png, scan.png, after.png)")


if __name__ == "__main__":
    main()
