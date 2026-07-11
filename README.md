# GloSkin Slideshow Content Maker

An automated pipeline that turns text angles into post-ready short-form content.
One brief → two outputs:

- **`slides_for_tiktok_photomode/`** — raw 1080×1920 PNGs. Upload these to
  **TikTok Photo Mode** (and IG carousel) and attach a *trending sound in-app*.
  Native photo posts get the most organic reach right now, and you pick the
  audio where the trends actually live.
- **`<slug>_reel.mp4`** — a 9:16 video with subtle zoom + crossfades. Use for
  **IG Reels, YouTube Shorts, and paid ads** (Meta / TikTok Ads Manager), where
  you need an actual video file.

## Current build direction

The current runtime/status handoff is in `BUILD_SPEC.md`. The active refactor
roadmap is in `docs/multi_brand_refactor_waves_0_3.md`.

Short version: `content_job.py` is the generation entrypoint, generated posts are
stored locally under `posts/<brand>/YYYY-MM-DD/<post_id>/`, publishing is manual
for now, and brand identity lives in `brands/<brand_id>.yaml`.

## The 3-step loop

```
1. ANGLES        2. BRIEFS                3. RENDER
one-liners  -->  generate_briefs.py  -->  slideshow_maker.py  -->  posts + ads
(your ideas)     (Claude writes copy)     (PIL + ffmpeg)
```

### Step 1 — write angles
Put one idea per line in `angles.txt`. Aim for 15–20 so you can test broadly.
```
scan your $60 serum, it's basically water
let an AI rate your skin, get a Glo Score
things my AI skincare coach roasted me for
ingredients you should never mix
```

### Step 2 — generate briefs (the automation layer)
```
pip install anthropic
export ANTHROPIC_API_KEY=sk-ant-...
python generate_briefs.py --angles angles.txt --out briefs
```
This writes one JSON brief per angle. Skim them, tweak any wording, delete duds.
(You can also skip this and hand-write briefs — see `briefs/serum_scan.json`.)

### Step 3 — render everything
```
python slideshow_maker.py --briefs-dir briefs --out output
```
One folder per angle, each with the PNG slides and the reel video.

## Local automation job  (recommended first workflow)
Use `content_job.py` when you want one Codex/automation-friendly command that
generates avatars, renders post iterations, packages each post into a local PC
folder, and marks it ready for manual posting.

Default packaged-post folder:
```
posts/<brand>/YYYY-MM-DD/<post_id>/
  slides/        # TikTok Photo Mode / IG carousel PNGs
  video.mp4      # Reel/Short/ads-ready render
  source_assets/ # before, scan, after, and composited app screenshots
  caption.txt    # includes compliance line + tracking code
  brief.json     # rendered slide brief
  post.json      # manifest snapshot for this post
```

Run a no-API placeholder test:
```
python content_job.py --roster roster.json --avatars 2 --posts-per-avatar 2 --placeholder
```

Run the VendraRx stub path without screenshot templates:
```
python content_job.py --brand vendrarx --spec "founder, 30s, White" --placeholder
```

Run a real OpenAI image batch:
```
set OPENAI_API_KEY=sk-...
python content_job.py --brand gloskin --roster roster.json --avatars 6 --posts-per-avatar 2
```

Batch sizing has two separate knobs:
- `--avatars` controls how many characters/personas to generate from `roster.json`.
- `--posts-per-avatar` controls how many post iterations to render from each avatar.

Creative visual options:
- `--opening-style selfie` keeps slide 1 as the normal before selfie.
- `--opening-style close_up_acne` creates `opening.png`, a close-up acne/texture hook image for slide 1.
- `--opening-style forehead_texture` creates a forehead/texture close-up for slide 1.
- `--product-style none` keeps the deck at the standard before/scan/after format.
- `--product-style common_products|niche_products|random_products` creates an unbranded `product_prop.png` and inserts a neutral product-attention slide. These props are visual hooks, not product recommendations.

Example:
```
python content_job.py --roster roster.json --avatars 2 --posts-per-avatar 2 --opening-style close_up_acne --product-style random_products
```

The current default image provider is OpenAI (`IMAGE_PROVIDER=openai`), routed
through `image_router.py`. Dreamina or another provider can be added there as
long as it is a real documented API, not browser automation against a consumer
website.

For now, generated posts are queued for manual publishing with
`publish_queue.status = "ready_to_post"` and the selected brand's configured
target account.
This is intentional: TikTok Photo Mode and trend audio are often best handled
in-app while the GloSkin account is still warming up. Later, `publish.py` can
add official TikTok/Instagram/Facebook API adapters.

## Local dashboard and manual publishing queue
Run the local control room:
```
pip install -r requirements.txt
python api_server.py
```

Open:
```
http://127.0.0.1:5055
```

The dashboard can:
- start `content_job.py` with dashboard-controlled `avatars` and `posts / avatar`
- select `gloskin` or `vendrarx`
- preview and save the actual character image prompt templates
- run a 1-post prompt test from an ad-hoc character spec
- show which real app screenshots are present or missing
- run placeholder batches for testing without image API calls
- show recent run logs
- preview videos, source selfies/screenshots, rendered slide PNGs, and captions
- copy captions and open packaged post folders
- move posts through `draft`, `ready_to_post`, `posted`, `needs_edit`, `skipped`, or `failed`
- mark winners for the feedback loop

Manual posting workflow:
1. Generate a batch from the dashboard.
2. Filter to `Ready`.
3. Open each package folder, upload `slides/` or `video.mp4`, and use `caption.txt`.
4. Mark the post `Posted` in the dashboard and paste the platform URL when available.

Prompt testing workflow:
1. In **Prompt Lab**, choose an opening-image style and optional product-prop slide.
2. Enter a test spec like `woman, early 20s, East Asian`.
3. Edit the before identity, opening image, scan selfie, after edit, and product prop prompts as needed.
4. Click `Preview` to see the rendered prompts with `{age}`, `{gender}`, and `{ethnicity}` filled in.
5. Click `Save prompts` to make those templates the actual prompts used by `character_factory.py`.
6. Click `Run 1-post test`. Keep `placeholder` on for layout-only tests; turn it off when your image API credentials are ready and you want to spend a real generation.

## Publishing and metrics integrations
Manual publishing is the working first adapter. CLI helpers:
```
python publish.py ready
python publish.py payload --post-id <post_id>
python publish.py mark --post-id <post_id> --platform tiktok --url https://...
python publish.py queue --post-id <post_id> --status needs_edit
```

`publish.py api-plan --platform tiktok|instagram|facebook` shows the credentials
and payload shape for official API adapters. The adapters are intentionally not
enabled until account/app permissions are approved.

Metrics import works today from CSV exports or a manual sheet:
```
python metrics_refresh.py csv --csv metrics.csv
python metrics_refresh.py csv --csv metrics.csv --map views="Video Views" ctr=CTR tracking_code=Caption
```

The dashboard has the same CSV import path. Put the CSV in this project folder,
enter the relative path, and import. Rows match by `tracking_code` first, then
`publish.url`. The tracking-code column can contain just the code or a full
caption that includes the code from `caption.txt`.

Future direct pulls are scaffolded behind:
```
python metrics_refresh.py api-plan --provider tiktok
python metrics_refresh.py api-plan --provider instagram
python metrics_refresh.py api-plan --provider meta_ads
python metrics_refresh.py api-plan --provider installs
```

Credential names live in `.env.example`. Keep organic metrics, paid metrics, and
install attribution separate when those adapters are filled in.

## Use REAL screenshots, never fake UI  (screenshot_factory.py)
The AI image generator is only for the human images:
- `before.png` - ordinary starting selfie with visible skin concern
- `opening.png` - optional first-slide close-up acne/texture hook image
- `scan.png` - neutral centered selfie used inside the app Scan Results screenshot
- `after.png` - ordinary ending selfie with clearer skin
- `product_prop.png` - optional unbranded skincare product prop visual

The Scan Results screen itself comes from `templates/scan_results.webp`. If that
screen does not match the actual app, replace the template with a real exported app
screenshot and update the measured `REGIONS` in `screenshot_factory.py` if its size
changes. Do not prompt an image model to invent this screen.

We do NOT recreate the app interface — that's inaccurate to advertise with. Instead
we keep a folder of genuine screenshots and personalize only the parts that change.

Recommended screenshot strategy:
- **Static reusable screens:** use the exact same app screenshots across many
  characters when nothing personal is visible. Good examples: Products, Insights,
  generic Guru chat, generic Today/routine.
- **Semi-personalized screens:** reuse one real screenshot, but patch measured text
  slots such as a routine title, chat question, or product name. This is useful
  when the screen is mostly generic but one line should match the creative angle.
- **Fully personalized screens:** use a real template and replace character-specific
  slots. Today this is `scan_results`: the face image, Glo Score number, and score
  progress bar are replaced per character.

**Two buckets of app assets:**

1. **Per-character (templatize):** the **Scan Results** screen shows a face and a Glo
   Score, both of which change per person. `screenshot_factory.py` takes the real
   screenshot, swaps the selfie into the photo slot (rounded to match) and rewrites
   the score + progress bar:
   ```
   python screenshot_factory.py --template templates/scan_results.webp \
       --face assets/<char>/scan.png --score 54 \
       --out screenshots/<char>_scan_before.png
   ```
   Run twice per character (low score on the scan selfie, high score on the after
   face) for a matched pair consistent with the before/after slides. If `scan.png`
   is missing for an older character, the pipeline falls back to `before.png`.

   If a real screen has another measured variable slot, add explicit text patches
   in `roster.json` under `scan_patches`, `scan_before_patches`, or
   `scan_after_patches`. Keep this for UI fields the real app can plausibly show;
   do not add fake UI claims.

2. **Reusable as-is (static library):** Today/routine, Guru chat, Insights, Products.
   These don't change per person — drop the real screenshots in `templates/` and
   reference them from a `screenshot` slide. Vary them with light edits (product
   names, chat text) or different captions, not a re-shoot. Build once, reuse forever.

The dashboard's **App Screenshot Assets** panel tracks the current library:
- `templates/scan_results.webp` — required, already used for Glo Score proof slides
- `templates/today_routine.webp` — recommended, routine/protocol proof
- `templates/guru_chat.webp` — recommended, AI skincare coach proof
- `templates/product_scan.webp` — recommended, ingredient/product scanner proof
- `templates/skin_diary.webp` — optional, progress/diary proof

**Library source:** export screenshots straight from the app (simulator/device) at a
fixed size. Re-export Scan Results at 722×1568 so the measured coordinates line up,
or adjust `REGIONS` in `screenshot_factory.py` for a different size. For pixel-perfect
score numbers, drop Apple's `SF-Pro-Display-Bold.otf` next to the script and point
`SCORE_FONT` at it (DejaVu is the close-enough fallback).

Text patch schema for semi-personalized screens:
```json
[
  {
    "region": [80, 220, 620, 300],
    "text": "Maya's AM routine",
    "font_size": 34,
    "fill": "#111116",
    "bg": "#ffffff",
    "radius": 0,
    "padding": 8,
    "align": "left",
    "valign": "center",
    "max_lines": 1
  }
]
```

Apply a patch manually:
```
python screenshot_factory.py --template templates/today_routine.webp --patch-json patches.json --out screenshots/today_routine_maya.png
```

For Scan Results, face/score replacement can be combined with patches:
```
python screenshot_factory.py --template templates/scan_results.webp --face assets/<char>/before.png --score 54 --patch-json patches.json --out screenshots/<char>_before.png
```

## The testimonial format (the money format)
`briefs/testimonial_acne.json` is the template:
1. **before/opening** — `image_top`, normal before selfie or optional `opening.png` close-up, gut-punch hook
2. **optional product prop** — unbranded product visual with neutral "not a plan" copy
3. **screenshot** — real Scan Results screen with `scan.png`, low score
4. **screenshot** — real Scan Results screen with `after.png`, high score
5. **after** — `image_top`, character clear + smiling
6. **cta** — download

Clone per character: point the `image` paths at that character's `before.png` /
`after.png` and their two composited app screenshots, then batch render. Optional
`opening.png` and `product_prop.png` are created automatically from the dashboard
style choices.

## Pluggable image provider  (image_router.py)
Face/image generation is abstracted behind a provider registry so you can swap in
any image API without touching the pipeline. Select with `IMAGE_PROVIDER`:
```
export IMAGE_PROVIDER=openai     # gpt-image-1 (default, generate + edit)
export IMAGE_PROVIDER=custom     # your own HTTP image API (template in image_router.py)
```
To add a provider, copy the `custom` template, adapt the request/response shape, and
`register("name", generate=..., edit=...)`. Returns PNG bytes; `edit` is optional
(falls back to `generate`). To use your own roster instead, drop `before.png`,
`scan.png`, and `after.png` into `assets/<char>/` — no API needed. Optional
`opening.png` and `product_prop.png` can be added manually too. `scan.png` is
optional for older folders; `before.png` is used as the fallback scan selfie.

## Tuning
- **Brand config** - edit `brands/<brand_id>.yaml` for palette, CTA, accounts,
  prompts, screenshot inventory, and compliance seed rules.
- **Palette** - brand config is the default. Override with a `"palette"` block
  per brief.
- **Pacing** — add `"duration"` (seconds) to any slide.
- **Fonts** — swap `FONT_BOLD` / `FONT_REG` at the top of `slideshow_maker.py`.

## Compliance (from day one)
Before/after acne creative is heavily scrutinized. Keep copy cosmetic/educational
(no "cures" / medical promises — the brief generator enforces this), and put a
visible "results vary · not medical advice" line in captions/bio.

## Where this is going (next builds)
- **Text-native formats**: generate Reddit posts, X threads, and TikTok scripts
  alongside slideshows.
- **Compliance gate**: lint copy before it can enter the manual publish queue.
