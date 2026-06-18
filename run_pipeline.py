#!/usr/bin/env python3
"""
run_pipeline.py — the glue
==========================
Roster in, finished testimonials out. Chains the three stages:

  character_factory  ->  screenshot_factory  ->  slideshow_maker
  (OpenAI faces)         (personalize real UI)   (render slides + reel)

Setup:
  pip install openai anthropic pillow
  export OPENAI_API_KEY=sk-...        # only needed for real faces

Dry run with no API (placeholder faces, proves the whole chain):
  python run_pipeline.py --roster roster.json --out output --placeholder

Real run:
  python run_pipeline.py --roster roster.json --out output

roster.json:
{
  "template": "scan_results",                  # template name in templates/
  "characters": [
    {"spec": "woman, early 20s, Hispanic/Latino",
     "before_score": 54, "after_score": 87,
     "hook": "I had cystic acne for 3 years.\\nNothing worked.",
     "after_text": "Score 87. Same face, same lighting. No filter."}
  ]
}
"""
import argparse
import json
from pathlib import Path

import character_factory as cf
import screenshot_factory as sf
import slideshow_maker as sm
import manifest


def build_testimonial_brief(slug, char_dir, shot_before, shot_after, c):
    """The fixed 5-slide before/after structure, filled per character."""
    return {
        "slug": f"testimonial_{slug}",
        "slides": [
            {"kind": "hook", "layout": "image_top", "label": "before",
             "image": str(char_dir / "before.png"),
             "text": c.get("hook", "My skin was at its worst.\nNothing worked.")},
            {"kind": "screenshot", "image": str(shot_before),
             "caption": f"So I scanned my face.\nGlo Score: {c.get('before_score', 54)}."},
            {"kind": "screenshot", "image": str(shot_after),
             "caption": c.get("mid_text", "8 weeks on Glo's routine.")},
            {"kind": "body", "layout": "image_top", "label": "after",
             "image": str(char_dir / "after.png"),
             "text": c.get("after_text",
                           f"Score {c.get('after_score', 87)}. Same face, no filter.")},
            {"kind": "cta", "text": c.get("cta", "What's your Glo Score?"),
             "button": "Get GloSkin", "subtext": "Free on the App Store"},
        ],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--roster", required=True)
    ap.add_argument("--out", default="output")
    ap.add_argument("--templates", default="templates")
    ap.add_argument("--assets", default="assets")
    ap.add_argument("--shots", default="screenshots")
    ap.add_argument("--placeholder", action="store_true",
                    help="skip OpenAI, use labeled placeholder faces")
    args = ap.parse_args()

    roster = json.load(open(args.roster))
    template = Path(args.templates) / f"{roster.get('template', 'scan_results')}.webp"
    Path(args.shots).mkdir(parents=True, exist_ok=True)
    gen = cf.gen_pair_placeholder if args.placeholder else cf.gen_pair_openai

    done = []
    for c in roster["characters"]:
        # 1) faces
        slug = gen(c["spec"], args.assets)
        char_dir = Path(args.assets) / slug

        # 2) personalized real screenshots
        shot_before = Path(args.shots) / f"{slug}_before.png"
        shot_after = Path(args.shots) / f"{slug}_after.png"
        sf.composite_scan_result(str(template), str(char_dir / "before.png"),
                                 c.get("before_score", 54), str(shot_before))
        sf.composite_scan_result(str(template), str(char_dir / "after.png"),
                                 c.get("after_score", 87), str(shot_after))

        # 3) render the testimonial
        brief = build_testimonial_brief(slug, char_dir, shot_before, shot_after, c)
        res = sm.make_content(brief, args.out)

        # 4) log to manifest (backbone for dashboard + winner analysis)
        post_id = manifest.record_post(
            character={"slug": slug, "spec": c["spec"],
                       "before_score": c.get("before_score"),
                       "after_score": c.get("after_score")},
            fmt="testimonial_beforeafter",
            hook=c.get("hook", ""),
            slides=[{"kind": s["kind"], "text": s.get("text") or s.get("caption", "")}
                    for s in brief["slides"]],
            assets={"before": str(char_dir / "before.png"),
                    "after": str(char_dir / "after.png"),
                    "shot_before": str(shot_before), "shot_after": str(shot_after)},
            outputs={"slides_dir": res["dir"], "video": res["video"]},
            tracking_code=f"{slug}",
        )
        done.append((slug, res["dir"], post_id))
        print(f"[done] {slug}: {res['dir']}  (post {post_id})")

    print(f"\n{len(done)} testimonials built in {args.out}/ — logged to posts.json")


if __name__ == "__main__":
    main()
