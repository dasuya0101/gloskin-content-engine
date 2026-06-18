#!/usr/bin/env python3
"""
GloSkin Slideshow Content Maker (v1)
====================================

Turns a JSON "brief" into ready-to-post short-form content:
  1. A folder of 1080x1920 PNG slides  -> upload to TikTok Photo Mode (attach
     trending audio in-app for max reach)
  2. A 9:16 .mp4 with timed slides + subtle zoom + crossfades -> IG Reels,
     YouTube Shorts, and paid ads (Meta / TikTok Ads Manager)

Design goals:
  - One brief in, two formats out.
  - Brand-consistent (GloSkin rose/pink palette, baked-in but overridable).
  - Batch a whole folder of briefs in one run so you can test 15 angles at once.
  - No paid APIs required to render. Backgrounds can be (a) your own AI-gen
    persona images / app screenshots dropped in a folder, or (b) auto-generated
    on-brand gradients when you have no image yet.

Usage:
  # render one brief
  python slideshow_maker.py --brief briefs/serum_scan.json --out output

  # render every *.json in a folder (batch)
  python slideshow_maker.py --briefs-dir briefs --out output

Brief schema (see briefs/ for examples):
{
  "slug": "serum_scan",
  "palette": {"bg1": "#FDE7EF", "bg2": "#F8C8DC", "accent": "#E8467C", "text": "#2B2B2B"},
  "slides": [
    {
      "kind": "hook",            # hook | body | cta
      "text": "I scanned my $60 serum...\nand it's basically water.",
      "image": null,            # path to a bg image, or null -> gradient
      "duration": 2.6           # seconds in the video (optional)
    },
    ...
  ]
}
"""

import argparse
import json
import math
import os
import shutil
import subprocess
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageEnhance

# ----------------------------------------------------------------------------
# Constants / defaults
# ----------------------------------------------------------------------------
W, H = 1080, 1920                      # vertical 9:16


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
FPS = 30

# GloSkin brand defaults — measured from the real app (purple / lavender).
# Override per-brief via "palette".
DEFAULT_PALETTE = {
    "bg1": "#ECE5F8",      # light lavender (gradient top)
    "bg2": "#F3E7EF",      # warm lavender-pink (gradient bottom)
    "accent": "#773CED",   # real app purple (Share button / active nav)
    "text": "#16131F",     # near-black, matches in-app text
}

# Per-slide default durations (seconds) used in the video render.
KIND_DURATION = {"hook": 2.8, "body": 2.4, "cta": 3.2,
                 "results": 3.0, "products": 3.4, "screenshot": 3.0}


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def load_font(path, size):
    if path:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()


def gradient_bg(c1, c2):
    """Vertical gradient with a soft radial glow — used when no image given."""
    base = Image.new("RGB", (W, H), c1)
    top = hex_to_rgb(c1) if isinstance(c1, str) else c1
    bot = hex_to_rgb(c2) if isinstance(c2, str) else c2
    px = base.load()
    for y in range(H):
        t = y / H
        r = int(top[0] + (bot[0] - top[0]) * t)
        g = int(top[1] + (bot[1] - top[1]) * t)
        b = int(top[2] + (bot[2] - top[2]) * t)
        for x in range(W):
            px[x, y] = (r, g, b)
    # soft white glow upper-center for a clean "skincare" feel
    glow = Image.new("L", (W, H), 0)
    gd = ImageDraw.Draw(glow)
    gd.ellipse([W * 0.1, -H * 0.1, W * 0.9, H * 0.5], fill=110)
    glow = glow.filter(ImageFilter.GaussianBlur(180))
    white = Image.new("RGB", (W, H), (255, 255, 255))
    base = Image.composite(white, base, glow)
    return base


def cover_image(path):
    """Load an image and crop-fill to 1080x1920 (object-fit: cover)."""
    img = Image.open(path).convert("RGB")
    scale = max(W / img.width, H / img.height)
    nw, nh = int(img.width * scale), int(img.height * scale)
    img = img.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - W) // 2, (nh - H) // 2
    return img.crop((left, top, left + W, top + H))


def scrim(img, strength=0.42, top=False):
    """Darken image so white text is readable. Bottom-weighted by default."""
    overlay = Image.new("L", (W, H), 0)
    od = ImageDraw.Draw(overlay)
    for y in range(H):
        t = y / H
        a = (1 - t) if top else t
        od.line([(0, y), (W, y)], fill=int(255 * strength * (0.35 + 0.65 * a)))
    black = Image.new("RGB", (W, H), (0, 0, 0))
    return Image.composite(black, img, overlay)


def draw_wrapped(draw, text, font, max_w, x, y, fill, stroke=None,
                 line_spacing=1.18, align="center", anchor_mid=True):
    """Word-wrap text to max_w and draw it. Returns total text height."""
    words = text.split(" ")
    lines, cur = [], ""
    for w in words:
        # keep explicit newlines
        if "\n" in w:
            parts = w.split("\n")
            for i, p in enumerate(parts):
                test = (cur + " " + p).strip() if i == 0 else p
                if draw.textlength(test, font=font) <= max_w:
                    cur = test
                else:
                    if cur:
                        lines.append(cur)
                    cur = p
                if i < len(parts) - 1:
                    lines.append(cur)
                    cur = ""
            continue
        test = (cur + " " + w).strip()
        if draw.textlength(test, font=font) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)

    asc, desc = font.getmetrics()
    lh = int((asc + desc) * line_spacing)
    total_h = lh * len(lines)
    cy = y - total_h // 2 if anchor_mid else y
    for ln in lines:
        lw = draw.textlength(ln, font=font)
        if align == "center":
            lx = x - lw / 2
        elif align == "left":
            lx = x
        else:
            lx = x - lw
        if stroke:
            draw.text((lx, cy), ln, font=font, fill=fill,
                      stroke_width=stroke[0], stroke_fill=stroke[1])
        else:
            draw.text((lx, cy), ln, font=font, fill=fill)
        cy += lh
    return total_h


def rounded_chip(draw, cx, cy, label, font, fill_rgb, text_rgb=(255, 255, 255),
                 pad_x=46, pad_y=24, radius=44):
    tw = draw.textlength(label, font=font)
    asc, desc = font.getmetrics()
    th = asc + desc
    x0, y0 = cx - tw / 2 - pad_x, cy - th / 2 - pad_y
    x1, y1 = cx + tw / 2 + pad_x, cy + th / 2 + pad_y
    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=fill_rgb)
    draw.text((cx - tw / 2, cy - th / 2), label, font=font, fill=text_rgb)


def fit_region(path, rw, rh):
    """Crop-fill an image to an arbitrary region (object-fit: cover)."""
    img = Image.open(path).convert("RGB")
    scale = max(rw / img.width, rh / img.height)
    nw, nh = int(img.width * scale), int(img.height * scale)
    img = img.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - rw) // 2, (nh - rh) // 2
    return img.crop((left, top, left + rw, top + rh))


def render_image_top(slide, palette):
    """Top ~58% = character photo, bottom = gradient panel with the text.
    Used for before/after testimonial slides."""
    accent = hex_to_rgb(palette["accent"])
    text_rgb = hex_to_rgb(palette["text"])
    img_h = int(H * 0.58)

    base = gradient_bg(palette["bg1"], palette["bg2"])
    if slide.get("image") and os.path.exists(slide["image"]):
        photo = fit_region(slide["image"], W, img_h)
    else:  # placeholder frame so layout is visible without a real gen yet
        photo = Image.new("RGB", (W, img_h), (228, 210, 220))
        pd = ImageDraw.Draw(photo)
        tag = slide.get("placeholder", "your generated image")
        f = load_font(FONT_BOLD, 46)
        pd.text((W / 2 - pd.textlength(tag, font=f) / 2, img_h / 2 - 30),
                tag, font=f, fill=(150, 120, 138))
    base.paste(photo, (0, 0))

    # feather the seam between photo and panel
    fade = Image.new("L", (W, 160), 0)
    fd = ImageDraw.Draw(fade)
    for y in range(160):
        fd.line([(0, y), (W, y)], fill=int(255 * (y / 160)))
    panel_top = gradient_bg(palette["bg1"], palette["bg2"]).crop(
        (0, img_h - 160, W, img_h))
    base.paste(Image.composite(panel_top, photo.crop((0, img_h - 160, W, img_h)),
                               fade), (0, img_h - 160))

    draw = ImageDraw.Draw(base)
    # corner ribbon: BEFORE / AFTER (sits on the photo, below the chrome row)
    label = slide.get("label")
    if label:
        rounded_chip(draw, 200, 220, label.upper(), load_font(FONT_BOLD, 46),
                     accent if label.lower() == "after" else (60, 60, 70))

    panel_cy = img_h + (H - img_h) // 2
    font = load_font(FONT_BOLD, 78)
    draw_wrapped(draw, slide.get("text", ""), font, W - 180, W // 2, panel_cy,
                 text_rgb, line_spacing=1.16)
    return base.convert("RGB")


def render_results_card(slide, palette):
    """Branded mock of the GloSkin first-scan result. No screenshot needed."""
    accent = hex_to_rgb(palette["accent"])
    text_rgb = hex_to_rgb(palette["text"])
    base = gradient_bg(palette["bg1"], palette["bg2"])
    draw = ImageDraw.Draw(base)

    cx0, cy0, cx1, cy1 = 80, int(H * 0.16), W - 80, int(H * 0.68)
    draw.rounded_rectangle([cx0, cy0, cx1, cy1], radius=56, fill=(255, 255, 255))

    hf = load_font(FONT_BOLD, 56)
    draw.text((cx0 + 60, cy0 + 50), "Your Glo Analysis", font=hf, fill=text_rgb)

    # score ring
    score = slide.get("score", 58)
    rx, ry, rr = W // 2, cy0 + 350, 165
    draw.arc([rx - rr, ry - rr, rx + rr, ry + rr], 0, 360, fill=(238, 226, 232),
             width=34)
    draw.arc([rx - rr, ry - rr, rx + rr, ry + rr], -90, -90 + int(360 * score / 100),
             fill=accent, width=34)
    sf = load_font(FONT_BOLD, 124)
    draw.text((rx - draw.textlength(str(score), font=sf) / 2, ry - 92),
              str(score), font=sf, fill=text_rgb)
    lf = load_font(FONT_REG, 30)
    draw.text((rx - draw.textlength("GLO SCORE", font=lf) / 2, ry + 58),
              "GLO SCORE", font=lf, fill=(150, 130, 142))

    # skin type
    tf = load_font(FONT_REG, 40)
    bf = load_font(FONT_BOLD, 48)
    st_label = slide.get("skin_type", "Combination · Acne-prone")
    draw.text((cx0 + 60, ry + rr + 36), "Skin type", font=tf, fill=(150, 130, 142))
    draw.text((cx0 + 60, ry + rr + 86), st_label, font=bf, fill=text_rgb)

    # concern chips (wrap before drawing so nothing overruns the card)
    concerns = slide.get("concerns", ["Active acne", "Excess oil", "Dark marks"])
    chip_y = ry + rr + 180
    chip_x = cx0 + 60
    cfont = load_font(FONT_BOLD, 36)
    for c in concerns:
        w = draw.textlength(c, font=cfont) + 64
        if chip_x + w > cx1 - 60:
            chip_x = cx0 + 60
            chip_y += 96
        draw.rounded_rectangle([chip_x, chip_y, chip_x + w, chip_y + 76],
                               radius=38, fill=(252, 230, 239))
        draw.text((chip_x + 32, chip_y + 18), c, font=cfont, fill=accent)
        chip_x += w + 24
    return base.convert("RGB")


def render_products_card(slide, palette):
    """Branded 'recommended routine' product list. No screenshot needed."""
    accent = hex_to_rgb(palette["accent"])
    text_rgb = hex_to_rgb(palette["text"])
    base = gradient_bg(palette["bg1"], palette["bg2"])
    draw = ImageDraw.Draw(base)

    cx0, cy0, cx1, cy1 = 80, int(H * 0.13), W - 80, int(H * 0.87)
    draw.rounded_rectangle([cx0, cy0, cx1, cy1], radius=56, fill=(255, 255, 255))
    hf = load_font(FONT_BOLD, 54)
    draw.text((cx0 + 60, cy0 + 46), slide.get("heading", "Your routine,\nmatched to your skin"),
              font=hf, fill=text_rgb, spacing=12)

    products = slide.get("products", [
        {"step": "CLEANSE", "name": "Gentle gel cleanser", "tag": "AM · PM"},
        {"step": "TREAT", "name": "2% BHA exfoliant", "tag": "PM"},
        {"step": "TREAT", "name": "Niacinamide 10%", "tag": "AM"},
        {"step": "HYDRATE", "name": "Oil-free moisturizer", "tag": "AM · PM"},
        {"step": "PROTECT", "name": "SPF 50 fluid", "tag": "AM"},
    ])
    sf = load_font(FONT_BOLD, 30)
    nf = load_font(FONT_BOLD, 44)
    gf = load_font(FONT_REG, 32)
    row_y = cy0 + 230
    for p in products:
        draw.rounded_rectangle([cx0 + 50, row_y, cx1 - 50, row_y + 150],
                               radius=32, fill=(250, 244, 247))
        # step chip
        sw = draw.textlength(p["step"], font=sf) + 44
        draw.rounded_rectangle([cx0 + 80, row_y + 30, cx0 + 80 + sw, row_y + 84],
                               radius=27, fill=accent)
        draw.text((cx0 + 102, row_y + 42), p["step"], font=sf, fill=(255, 255, 255))
        draw.text((cx0 + 80, row_y + 92), p["name"], font=nf, fill=text_rgb)
        draw.text((cx1 - 50 - draw.textlength(p["tag"], font=gf) - 40, row_y + 56),
                  p["tag"], font=gf, fill=(150, 130, 142))
        row_y += 174
    return base.convert("RGB")


def render_screenshot_slide(slide, palette):
    """Frames a REAL app screenshot on the brand background with a soft shadow
    and optional caption. Use this for authentic app-proof slides instead of
    re-creating UI."""
    text_rgb = hex_to_rgb(palette["text"])
    base = gradient_bg(palette["bg1"], palette["bg2"])
    shot = Image.open(slide["image"]).convert("RGB")

    caption = slide.get("caption")
    target_h = 1400 if caption else 1560
    scale = target_h / shot.height
    sw, sh = int(shot.width * scale), int(shot.height * scale)
    shot = shot.resize((sw, sh), Image.LANCZOS)

    # rounded corners + drop shadow
    rad = 48
    mask = Image.new("L", (sw, sh), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, sw, sh], radius=rad, fill=255)
    x = (W - sw) // 2
    y = (H - sh) // 2 + (60 if caption else 0)
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle([x, y + 18, x + sw, y + sh + 18], radius=rad,
                         fill=(40, 20, 70, 110))
    shadow = shadow.filter(ImageFilter.GaussianBlur(40))
    base = Image.alpha_composite(base.convert("RGBA"), shadow).convert("RGB")
    base.paste(shot, (x, y), mask)

    if caption:
        draw = ImageDraw.Draw(base)
        draw_wrapped(draw, caption, load_font(FONT_BOLD, 70), W - 200, W // 2,
                     int(H * 0.075), text_rgb, line_spacing=1.12, anchor_mid=False)
    return base.convert("RGB")


def _draw_chrome(bg, palette, idx, total, on_image=False):
    """Brand wordmark (top-left) + slide progress dots (top-right)."""
    accent = hex_to_rgb(palette["accent"])
    draw = ImageDraw.Draw(bg)
    brand_font = load_font(FONT_BOLD, 40)
    draw.text((70, 72), "GloSkin", font=brand_font,
              fill=(255, 255, 255) if on_image else accent)
    dot_r, gap = 9, 30
    start_x = W - 70 - (total - 1) * gap
    for i in range(total):
        if i == idx:
            col = accent
        else:
            col = (255, 255, 255) if on_image else (210, 185, 198)
        draw.ellipse([start_x + i * gap - dot_r, 86 - dot_r,
                      start_x + i * gap + dot_r, 86 + dot_r], fill=col)


# ----------------------------------------------------------------------------
# Slide rendering
# ----------------------------------------------------------------------------
def render_slide(slide, palette, idx, total):
    kind = slide.get("kind", "body")

    # dedicated renderers
    if slide.get("layout") == "image_top":
        bg = render_image_top(slide, palette)
        _draw_chrome(bg, palette, idx, total, on_image=True)
        return bg
    if kind == "results":
        bg = render_results_card(slide, palette)
        _draw_chrome(bg, palette, idx, total, on_image=False)
        return bg
    if kind == "products":
        bg = render_products_card(slide, palette)
        _draw_chrome(bg, palette, idx, total, on_image=False)
        return bg
    if kind == "screenshot":
        bg = render_screenshot_slide(slide, palette)
        _draw_chrome(bg, palette, idx, total, on_image=False)
        return bg

    accent = hex_to_rgb(palette["accent"])
    text_rgb = hex_to_rgb(palette["text"])

    has_img = slide.get("image") and os.path.exists(slide["image"])
    if has_img:
        bg = cover_image(slide["image"])
        bg = scrim(bg, strength=0.5)
        body_fill = (255, 255, 255)
        body_stroke = (3, (0, 0, 0))
    else:
        bg = gradient_bg(palette["bg1"], palette["bg2"])
        body_fill = text_rgb
        body_stroke = None

    draw = ImageDraw.Draw(bg)
    _draw_chrome(bg, palette, idx, total, on_image=has_img)

    text = slide.get("text", "")
    max_w = W - 200

    if kind == "hook":
        font = load_font(FONT_BOLD, 104)
        # accent kicker chip
        kicker = slide.get("kicker", "POV")
        rounded_chip(draw, W // 2, H * 0.30, kicker.upper(),
                     load_font(FONT_BOLD, 44), accent)
        draw_wrapped(draw, text, font, max_w, W // 2, int(H * 0.52),
                     body_fill, stroke=body_stroke or (4, (255, 255, 255)),
                     line_spacing=1.12)
    elif kind == "cta":
        font = load_font(FONT_BOLD, 92)
        draw_wrapped(draw, text, font, max_w, W // 2, int(H * 0.42),
                     body_fill, stroke=body_stroke, line_spacing=1.15)
        # CTA button
        rounded_chip(draw, W // 2, int(H * 0.66),
                     slide.get("button", "Download GloSkin"),
                     load_font(FONT_BOLD, 52), accent, pad_x=70, pad_y=34)
        sub = slide.get("subtext", "Free on the App Store")
        draw.text((W // 2 - draw.textlength(sub, font=load_font(FONT_REG, 40)) / 2,
                   int(H * 0.72)), sub, font=load_font(FONT_REG, 40),
                  fill=body_fill)
    else:  # body
        font = load_font(FONT_BOLD, 86)
        draw_wrapped(draw, text, font, max_w, W // 2, int(H * 0.48),
                     body_fill, stroke=body_stroke, line_spacing=1.18)

    return bg.convert("RGB")


# ----------------------------------------------------------------------------
# Video assembly (ffmpeg): per-slide zoom + crossfades
# ----------------------------------------------------------------------------
def build_video(slide_paths, durations, out_path):
    tmp = Path(out_path).parent / "_clips"
    tmp.mkdir(exist_ok=True)
    clips = []
    for i, (img, dur) in enumerate(zip(slide_paths, durations)):
        clip = tmp / f"clip_{i:02d}.mp4"
        frames = max(1, int(dur * FPS))
        # gentle ken-burns zoom (1.0 -> 1.06)
        zoom = (f"scale=1350:-1,zoompan=z='min(zoom+0.0009,1.06)':"
                f"d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"s={W}x{H}:fps={FPS}")
        subprocess.run(
            ["ffmpeg", "-y", "-loop", "1", "-i", img, "-t", f"{dur}",
             "-vf", zoom, "-c:v", "libx264", "-pix_fmt", "yuv420p",
             "-r", str(FPS), str(clip)],
            check=True, capture_output=True)
        clips.append((clip, dur))

    # chain crossfades
    if len(clips) == 1:
        shutil.copy(clips[0][0], out_path)
    else:
        inputs = []
        for c, _ in clips:
            inputs += ["-i", str(c)]
        xf = 0.4  # crossfade seconds
        fc, prev, offset = "", "[0:v]", 0.0
        for i in range(1, len(clips)):
            offset += clips[i - 1][1] - xf
            label = f"[v{i}]"
            fc += (f"{prev}[{i}:v]xfade=transition=fade:duration={xf}:"
                   f"offset={offset:.3f}{label};")
            prev = label
        fc = fc.rstrip(";")
        subprocess.run(
            ["ffmpeg", "-y", *inputs, "-filter_complex", fc,
             "-map", prev, "-c:v", "libx264", "-pix_fmt", "yuv420p",
             "-r", str(FPS), out_path],
            check=True, capture_output=True)
    shutil.rmtree(tmp, ignore_errors=True)


# ----------------------------------------------------------------------------
# Orchestration
# ----------------------------------------------------------------------------
def make_content(brief, out_root):
    slug = brief["slug"]
    palette = {**DEFAULT_PALETTE, **brief.get("palette", {})}
    slides = brief["slides"]
    total = len(slides)

    out_dir = Path(out_root) / slug
    slides_dir = out_dir / "slides_for_tiktok_photomode"
    slides_dir.mkdir(parents=True, exist_ok=True)

    slide_paths, durations = [], []
    for i, slide in enumerate(slides):
        img = render_slide(slide, palette, i, total)
        p = slides_dir / f"{slug}_{i+1:02d}.png"
        img.save(p, "PNG")
        slide_paths.append(str(p))
        durations.append(slide.get("duration", KIND_DURATION.get(
            slide.get("kind", "body"), 2.5)))

    video_path = out_dir / f"{slug}_reel.mp4"
    build_video(slide_paths, durations, str(video_path))

    return {"slides": slide_paths, "video": str(video_path), "dir": str(out_dir)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--brief")
    ap.add_argument("--briefs-dir")
    ap.add_argument("--out", default="output")
    args = ap.parse_args()

    briefs = []
    if args.brief:
        briefs = [json.load(open(args.brief))]
    elif args.briefs_dir:
        for f in sorted(Path(args.briefs_dir).glob("*.json")):
            briefs.append(json.load(open(f)))
    else:
        ap.error("pass --brief or --briefs-dir")

    for b in briefs:
        res = make_content(b, args.out)
        print(f"[ok] {b['slug']}: {len(res['slides'])} slides + video -> {res['dir']}")


if __name__ == "__main__":
    main()
