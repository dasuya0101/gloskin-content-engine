#!/usr/bin/env python3
"""
generate_briefs.py - copy automation layer

Turns one-line angles into full slide briefs. Reads brand prompt paths from
brands/<brand_id>.yaml, then routes through llm_router so repetitive copy tasks
can use lower-tier models.

  python generate_briefs.py --angles angles.txt --out briefs
  python generate_briefs.py --brand vendrarx --angle "how 503A compounding works"
"""
import argparse
import json
import re
from pathlib import Path

from brand_loader import DEFAULT_BRAND, load_brand
from llm_router import complete


SCHEMA_TMPL = """
Given ONE content angle, output a slideshow brief as STRICT JSON, no markdown, no preamble.
Schema:
{{
  "slug": "snake_case_id",
  "brand": "%(brand_id)s",
  "slides": [
    {{"kind":"hook","kicker":"2-3 word punchy chip","text":"hook, <=8 words, \\n for line breaks"}},
    {{"kind":"body","text":"<=12 words"}},
    {{"kind":"body","text":"<=12 words"}},
    {{"kind":"body","text":"<=12 words"}},
    {{"kind":"cta","text":"<=6 words","button":"%(button)s","subtext":"%(subtext)s"}}
  ]
}}
Exactly 5 slides: 1 hook, 3 body, 1 cta. The hook must stop the scroll in 1.5 seconds.
"""


def brand_context(brand):
    return "\n".join([
        "# BRAND CONTEXT",
        f"Brand: {brand.display_name}",
        f"CTA: {brand.cta.get('text', '')} ({brand.cta.get('url', '')})",
        "Voice: " + json.dumps(brand.voice),
        "Pillars: " + ", ".join(brand.pillars),
    ])


def load_system_prompt(brand):
    copy_path = brand.prompt_path("copy_system")
    if not copy_path:
        raise FileNotFoundError(f"{brand.brand_id} has no copy_system prompt configured")
    base = copy_path.read_text(encoding="utf-8")
    learned_path = brand.prompt_path("learned_rules")
    parts = [base]
    if learned_path and learned_path.exists():
        parts.append("\n# CODIFIED LEARNINGS FROM TOP PERFORMERS\n" + learned_path.read_text(encoding="utf-8"))
    parts.append(brand_context(brand))
    parts.append(SCHEMA_TMPL % {
        "brand_id": brand.brand_id,
        "button": brand.cta.get("button") or brand.cta.get("text", "Learn more"),
        "subtext": brand.cta.get("subtext", ""),
    })
    return "\n".join(parts)


def gen_brief(angle, brand, task="copy_brief"):
    raw = complete(system=load_system_prompt(brand), user=f"Angle: {angle}", task=task)
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
    brief = json.loads(raw)
    brief["brand"] = brand.brand_id
    return brief


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--angle")
    ap.add_argument("--angles")
    ap.add_argument("--brand", default=DEFAULT_BRAND)
    ap.add_argument("--out", default="briefs")
    args = ap.parse_args()
    brand = load_brand(args.brand)

    if args.angle:
        angles = [args.angle]
    elif args.angles:
        angles = [l.strip() for l in open(args.angles, encoding="utf-8") if l.strip()]
    else:
        ap.error("pass --angle or --angles")

    Path(args.out).mkdir(parents=True, exist_ok=True)
    for angle in angles:
        brief = gen_brief(angle, brand)
        path = Path(args.out) / f"{brief['slug']}.json"
        json.dump(brief, open(path, "w", encoding="utf-8"), indent=2)
        print(f"[brief] {angle[:50]!r} -> {path}")


if __name__ == "__main__":
    main()
