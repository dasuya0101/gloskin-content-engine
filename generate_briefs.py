#!/usr/bin/env python3
"""
generate_briefs.py — copy automation layer
Turns one-line angles into full slide briefs. Reads the EDITABLE system prompt
from prompts/copy_system.md + prompts/learned_rules.md so the feedback loop can
improve copy over time without code changes. Routes through llm_router so you can
send this cheap, repetitive task to a lower-tier model.

  python generate_briefs.py --angles angles.txt --out briefs
  python generate_briefs.py --angle "scan your moisturizer, half of it is filler"
"""
import argparse
import json
import re
from pathlib import Path

from llm_router import complete   # routed model call (see llm_router.py)

PROMPT_DIR = Path(__file__).parent / "prompts"

SCHEMA = """
Given ONE content angle, output a slideshow brief as STRICT JSON, no markdown, no preamble.
Schema:
{
  "slug": "snake_case_id",
  "slides": [
    {"kind":"hook","kicker":"2-3 word punchy chip","text":"hook, <=8 words, \\n for line breaks"},
    {"kind":"body","text":"<=12 words"},
    {"kind":"body","text":"<=12 words"},
    {"kind":"body","text":"<=12 words"},
    {"kind":"cta","text":"<=6 words","button":"<=3 words","subtext":"Free on the App Store"}
  ]
}
Exactly 5 slides: 1 hook, 3 body, 1 cta. The hook must stop the scroll in 1.5 seconds."""


def load_system_prompt():
    base = (PROMPT_DIR / "copy_system.md").read_text()
    learned_path = PROMPT_DIR / "learned_rules.md"
    parts = [base]
    if learned_path.exists():
        parts.append("\n# CODIFIED LEARNINGS FROM TOP PERFORMERS\n" + learned_path.read_text())
    parts.append(SCHEMA)
    return "\n".join(parts)


def gen_brief(angle, task="copy_brief"):
    raw = complete(system=load_system_prompt(), user=f"Angle: {angle}", task=task)
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
    return json.loads(raw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--angle")
    ap.add_argument("--angles")
    ap.add_argument("--out", default="briefs")
    args = ap.parse_args()

    if args.angle:
        angles = [args.angle]
    elif args.angles:
        angles = [l.strip() for l in open(args.angles) if l.strip()]
    else:
        ap.error("pass --angle or --angles")

    Path(args.out).mkdir(parents=True, exist_ok=True)
    for a in angles:
        b = gen_brief(a)
        p = Path(args.out) / f"{b['slug']}.json"
        json.dump(b, open(p, "w"), indent=2)
        print(f"[brief] {a[:50]!r} -> {p}")


if __name__ == "__main__":
    main()
