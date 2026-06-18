# BUILD SPEC — GloSkin content engine (handoff for Claude Code / Codex)

You are picking up a **working** content-generation pipeline. Your job is to add
the operational layer: a dashboard, real performance ingestion, an upgraded
feedback loop, and (optional) auto-publishing. Read this whole file first, then
`README.md` for how the existing pieces run.

## What already works (don't rebuild)
```
roster.json ─▶ run_pipeline.py
                 ├─ character_factory.py   before/scan/after selfies (OpenAI gpt-image-1, or --placeholder)
                 ├─ screenshot_factory.py  swaps face+score into REAL app screenshots
                 ├─ slideshow_maker.py     renders slides (TikTok photo mode) + 9:16 mp4
                 └─ manifest.py            logs each post to posts.json
generate_briefs.py   angles ─▶ briefs (copy), via llm_router (editable prompts/)
import_metrics.py    CSV ─▶ posts.json metrics
analyze_winners.py   posts.json ─▶ winners_report.md + suggested prompt rules
dashboard.html       reads posts.json (SEED — your main target)
```
Pipeline outputs are real; verify with `python run_pipeline.py --roster roster.json --out output --placeholder`.

## Data model — posts.json (source of truth)
A list of records. Schema (see manifest.py `record_post`):
```jsonc
{
  "post_id": "12hexchars",
  "created_at": "ISO8601",
  "format": "testimonial_beforeafter" | "macro_faceless" | ...,
  "character": {"slug","spec","before_score","after_score"},
  "hook": "string",
  "slides": [{"kind","text"}],
  "assets": {"before","scan","after","shot_before","shot_after"},
  "outputs": {"slides_dir","video"},
  "variant_of": null | post_id,
  "tracking_code": "string",         // how metrics get matched back
  "publish": {"platform","account","url","posted_at"},
  "metrics": {"views","likes","shares","saves","ctr","installs","updated_at"},
  "is_winner": null | true | false
}
```
If volume exceeds ~a few thousand posts, migrate posts.json → SQLite (one `posts`
table, same fields) and keep manifest.py's function signatures so callers don't change.

## TASK 1 — Dashboard (primary)
Extend `dashboard.html` (or rebuild as a small React/Vite app — your call) into a
real console. Requirements:
- **Pipeline/progress view:** show in-flight runs (tail a run log or watch output/),
  per-character status (faces ✓ / screenshots ✓ / render ✓), and failures.
- **Grid + table of posts** with hover-play video previews (table seed exists).
- **Sort/filter** by any metric, format, demographic, account, date; filter to winners.
- **Per-post detail:** all slides, the hook, the variant lineage (variant_of), and a
  side-by-side of variants spawned from the same parent.
- **Aggregate charts:** views/CTR/installs over time; performance by format; by
  demographic; by hook-first-word; by slide order. This is where the "what's
  different about winners" story should be *visible*, not just in a report.
- **Winner selection UI:** let the user star/unstar posts (write is_winner back to
  posts.json via a tiny local API — add a minimal Flask/FastAPI backend; the seed is
  static-only and can't write).
- Keep it local-first (runs on his Mac). Design: this is an internal tool — favor a
  dense, fast, legible data aesthetic. Do NOT use a purple-gradient-on-white look.

## TASK 2 — Real metrics ingestion (replace the CSV path)
`import_metrics.py` is the manual bootstrap. Build direct pulls:
- **TikTok**: Business/Display API for video metrics; match by tracking_code embedded
  in caption or by the posted video id stored in publish.url.
- **Instagram**: Graph API (Insights) for Reels.
- **Meta Ads**: Marketing API for paid-creative metrics (spend, CTR, CPI) — keep
  organic and paid metrics distinguishable on the record.
- **Installs/conversions**: wire the app-store / attribution side (tracking_code →
  bio-link or UTM → install). Schedule a periodic refresh (cron) that updates
  metrics + updated_at.

## TASK 3 — Feedback loop upgrade (the compounding part)
`analyze_winners.py` is a heuristic v1. Upgrade the "what's different" step to an LLM
pass routed through `llm_router.complete(task="analysis")`:
- Feed it the actual winning vs losing **copy + attributes** and have it write
  specific, falsifiable rules ("hooks that name a dollar amount outperform"; "POV
  framing beats confessional for the under-25 segment").
- Append accepted rules to `prompts/learned_rules.md` (already concatenated into the
  copy system prompt at generation time — close the loop so new copy inherits wins).
- Keep a human approval step before rules are adopted (show diff in dashboard).
- Track rule provenance + whether posts generated after a rule actually improved
  (so the loop can retire rules that don't hold up).

## TASK 4 — Auto-publishing (optional, after metrics work)
Add `publish.py`: take finished posts and push to TikTok/IG/FB on a schedule via
their **content APIs** (TikTok Content Posting API, IG Graph API). Write
publish.platform/account/url/posted_at back via manifest.set_publish. Support the
persona-account model: a post's character.slug maps to a target account.

## TASK 5 — Variant generator (conversion-testing engine)
Add `make_variants.py`: given one post (or asset set), produce N testable variants —
different hooks (llm_router task="hook_variants"), captions, slide orders — same
assets, near-zero marginal cost (just re-render). Each variant records variant_of =
parent post_id so the dashboard can compare lineages. This is the real A/B engine.

## Model routing (llm_router.py)
Copy tasks are routed per `ROUTES` (OpenRouter cheap tiers — Kimi/DeepSeek/GLM — for
bulk; premium only for analysis). This is where his OpenClaw multi-model setup plugs
in: point OPENROUTER_API_KEY at it, or add OpenClaw as another provider in
llm_router. Retune ROUTES to trade cost vs quality in one place.

## HARD CONSTRAINT — do not build subscription scraping
Image generation and LLM calls must go through real **APIs** (gpt-image-1, Dreamina
credits, OpenRouter, Anthropic, OpenAI). Do NOT build browser-automation / click
macros that drive a consumer ChatGPT or Dreamina *subscription* — it violates those
providers' ToS and risks account bans. If cost is the concern, route copy to cheaper
API models and keep the face roster small (it's reused across hundreds of posts).

AI image generation should produce only visual assets: `before.png`, optional
`opening.png` close-up hooks, `scan.png`, `after.png`, and optional unbranded
`product_prop.png` attention props. Product props are not recommendations. Scan
Results and other app screens must come from real exported app screenshots in
`templates/`, then be personalized by measured slot replacement.

## Compliance to preserve
Before/after skincare creative is scrutinized for health claims. Keep copy
cosmetic/educational (the prompt enforces this) and ensure a visible "results vary ·
not medical advice" line ships in captions/bio. Don't remove these guardrails.

## Env / setup
```
pip install openai anthropic pillow flask   # +vite/react if you go that route
export OPENAI_API_KEY=...        # faces
export OPENROUTER_API_KEY=...    # cheap copy routing
export ANTHROPIC_API_KEY=...     # premium analysis
```
For pixel-perfect score numbers in screenshots, add SF-Pro-Display-Bold.otf and point
`screenshot_factory.SCORE_FONT` at it.

## Acceptance criteria
- Dashboard runs locally, reads posts.json, shows progress + metrics + winner starring
  that persists.
- A scheduled job pulls real metrics into posts.json.
- analyze_winners produces LLM-written rules; approved ones land in learned_rules.md
  and measurably shift new copy.
- Optional: posts auto-publish to at least one platform with url written back.
