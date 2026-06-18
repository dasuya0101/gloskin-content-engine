#!/usr/bin/env python3
"""
Screenshot factory
===================
Personalizes REAL app screenshots instead of faking the UI. You keep a folder
of genuine screenshot templates; this script swaps the parts that change per
character (the selfie + the Glo Score) and leaves the real chrome untouched.

Right now it templatizes the **Scan Results** screen, which is the only one that
is truly per-character (face + score). Screens like Today/routine and the Guru
chat are reusable as-is, or with light text edits — keep those as static assets.

  python screenshot_factory.py \
      --template templates/scan_results.webp \
      --face assets/<char>/before.png --score 54 \
      --out screenshots/<char>_scan_before.png

Batch by looping in your own script, or wire it into the character roster.

Coordinates below are measured for the 722x1568 Scan Results template. If you
re-export screenshots at a different size, set --template-size or adjust REGIONS.

For a pixel-perfect score number, drop Apple's SF-Pro-Display-Bold.otf (free for
your own dev use) next to this file and point SCORE_FONT at it. DejaVu is the
fallback and is close enough for fast-scroll social.
"""
import argparse
import json
import os
from PIL import Image, ImageDraw, ImageFont

# ---- Scan Results template geometry (722 x 1568) ----------------------------
REGIONS = {
    "photo": (30, 96, 692, 1012),     # selfie slot (rounded)
    "photo_radius": 34,
    "score_box": (52, 1112, 192, 1208),   # area to clear + redraw the number
    "score_left": 64,                      # left x of the number
    "score_top": 1116,                     # top y of the number
    "score_h": 80,                         # target glyph height (px)
    "bar": (60, 1244, 685, 1263),          # progress track (x0,y0,x1,y1)
    "clean_patch": (330, 1112, 470, 1208),  # empty card bg to copy over old number
}
BAR_GREEN = (52, 199, 89)
BAR_TRACK = (228, 228, 232)


def _first_font(candidates):
    for p in candidates:
        if p and os.path.exists(p):
            return p
    return None


SCORE_FONT = os.environ.get("GLO_SCORE_FONT") or _first_font([
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/calibrib.ttf",
])
# If you add SF Pro:  SCORE_FONT = os.path.join(os.path.dirname(__file__), "SF-Pro-Display-Bold.otf")


def _font(size, bold=True):
    path = SCORE_FONT if bold else _first_font([
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/calibri.ttf",
    ])
    if path:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()


def rounded(img, radius):
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, img.size[0], img.size[1]],
                                           radius=radius, fill=255)
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste(img, (0, 0))
    out.putalpha(mask)
    return out


def fit(img, w, h):
    s = max(w / img.width, h / img.height)
    nw, nh = int(img.width * s), int(img.height * s)
    img = img.resize((nw, nh), Image.LANCZOS)
    l, t = (nw - w) // 2, (nh - h) // 2
    return img.crop((l, t, l + w, t + h))


def fit_score_font(draw, text, target_h):
    """Find a font size whose digit height matches the original number."""
    if not SCORE_FONT:
        return ImageFont.load_default(), draw.textbbox((0, 0), text, font=ImageFont.load_default())
    size = 100
    for _ in range(12):
        f = ImageFont.truetype(SCORE_FONT, size)
        bb = draw.textbbox((0, 0), text, font=f)
        h = bb[3] - bb[1]
        if abs(h - target_h) <= 2:
            return f, bb
        size += int((target_h - h) * 0.8) or (1 if h < target_h else -1)
    return ImageFont.truetype(SCORE_FONT, size), draw.textbbox((0, 0), text, font=f)


def _rgb(value, default=(17, 17, 22)):
    if value is None:
        return default
    if isinstance(value, str):
        value = value.lstrip("#")
        return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))
    return tuple(value)


def wrap_text(draw, text, font, max_w, max_lines=None):
    lines, cur = [], ""
    chunks = str(text or "").split("\n")
    for chunk_index, chunk in enumerate(chunks):
        words = chunk.split()
        if chunk_index > 0:
            if cur:
                lines.append(cur)
                cur = ""
        for word in words:
            test = (cur + " " + word).strip()
            if draw.textlength(test, font=font) <= max_w:
                cur = test
            else:
                if cur:
                    lines.append(cur)
                cur = word
            if max_lines and len(lines) >= max_lines:
                break
        if max_lines and len(lines) >= max_lines:
            break
    if cur and (not max_lines or len(lines) < max_lines):
        lines.append(cur)
    return lines


def draw_text_patch(base, patch):
    """Draw one explicit text patch onto a real app screenshot.

    Patch schema:
      {
        "region": [x0,y0,x1,y1],
        "text": "New text",
        "font_size": 32,
        "fill": "#111116",
        "bg": "#ffffff",        # optional; omit to draw over existing pixels
        "radius": 0,             # optional bg corner radius
        "padding": 0,
        "align": "left|center|right",
        "valign": "top|center",
        "max_lines": 2,
        "bold": true
      }
    """
    draw = ImageDraw.Draw(base)
    x0, y0, x1, y1 = patch["region"]
    pad = int(patch.get("padding", 0))
    if patch.get("bg") is not None:
        bg = _rgb(patch.get("bg"), (255, 255, 255))
        radius = int(patch.get("radius", 0))
        if radius:
            draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=bg)
        else:
            draw.rectangle([x0, y0, x1, y1], fill=bg)

    font = _font(int(patch.get("font_size", 32)), bool(patch.get("bold", True)))
    fill = _rgb(patch.get("fill"), (17, 17, 22))
    max_w = max(1, x1 - x0 - pad * 2)
    lines = wrap_text(draw, patch.get("text", ""), font, max_w, patch.get("max_lines"))
    asc, desc = font.getmetrics() if hasattr(font, "getmetrics") else (patch.get("font_size", 32), 8)
    line_h = int((asc + desc) * float(patch.get("line_spacing", 1.12)))
    total_h = max(line_h, line_h * len(lines))
    cy = y0 + pad
    if patch.get("valign", "top") == "center":
        cy = y0 + (y1 - y0 - total_h) // 2

    align = patch.get("align", "left")
    for line in lines:
        lw = draw.textlength(line, font=font)
        if align == "center":
            lx = x0 + (x1 - x0 - lw) / 2
        elif align == "right":
            lx = x1 - pad - lw
        else:
            lx = x0 + pad
        draw.text((lx, cy), line, font=font, fill=fill)
        cy += line_h
    return base


def apply_text_patches(template_path, out_path, patches=None):
    base = Image.open(template_path).convert("RGB")
    for patch in patches or []:
        draw_text_patch(base, patch)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    base.save(out_path)
    return out_path


def composite_scan_result(template_path, face_path, score, out_path, patches=None):
    base = Image.open(template_path).convert("RGB")
    draw = ImageDraw.Draw(base)

    # 1) swap the selfie
    px0, py0, px1, py1 = REGIONS["photo"]
    face = fit(Image.open(face_path).convert("RGB"), px1 - px0, py1 - py0)
    face = rounded(face, REGIONS["photo_radius"])
    base.paste(face, (px0, py0), face)

    # 2) clear the old number by copying a clean patch of card background, then
    #    redraw the new score (left-aligned where the original sat)
    cp = base.crop(REGIONS["clean_patch"])
    sb = REGIONS["score_box"]
    cp = cp.resize((sb[2] - sb[0], sb[3] - sb[1]))
    base.paste(cp, (sb[0], sb[1]))
    txt = str(int(score))
    font, bb = fit_score_font(draw, txt, REGIONS["score_h"])
    draw.text((REGIONS["score_left"] - bb[0], REGIONS["score_top"] - bb[1]),
              txt, font=font, fill=(17, 17, 22))

    # 3) redraw the progress bar to match the score
    bx0, by0, bx1, by1 = REGIONS["bar"]
    r = (by1 - by0) // 2
    draw.rounded_rectangle([bx0, by0, bx1, by1], radius=r, fill=BAR_TRACK)
    fill_w = int((bx1 - bx0) * max(0, min(100, score)) / 100)
    if fill_w > 2 * r:
        draw.rounded_rectangle([bx0, by0, bx0 + fill_w, by1], radius=r, fill=BAR_GREEN)

    for patch in patches or []:
        draw_text_patch(base, patch)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    base.save(out_path)
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", required=True)
    ap.add_argument("--face")
    ap.add_argument("--score", type=int)
    ap.add_argument("--out", required=True)
    ap.add_argument("--patch-json",
                    help="JSON file containing a list of explicit text patches")
    args = ap.parse_args()
    patches = json.load(open(args.patch_json, encoding="utf-8")) if args.patch_json else []
    if args.face and args.score is not None:
        p = composite_scan_result(args.template, args.face, args.score, args.out, patches)
        print(f"[screenshot] {os.path.basename(args.face)} @ score {args.score} -> {p}")
    else:
        p = apply_text_patches(args.template, args.out, patches)
        print(f"[screenshot] {args.template} + {len(patches)} patches -> {p}")


if __name__ == "__main__":
    main()
