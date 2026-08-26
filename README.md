# GloSkin Slideshow Content Maker

An automated pipeline that turns text angles into post-ready short-form content.
One brief → two outputs:

- **`slides_for_tiktok_photomode/`** — raw 1080×1350 (4:5) PNGs. Upload these to
  **TikTok Photo Mode** (and IG carousel) and attach a *trending sound in-app*.
  Native photo posts get the most organic reach right now, and you pick the
  audio where the trends actually live.
- **`<slug>_reel.mp4`** — a 9:16 video with subtle zoom + crossfades. Use for
  **IG Reels, YouTube Shorts, and paid ads** (Meta / TikTok Ads Manager), where
  you need an actual video file.

## Current build direction

The current runtime/status handoff is in `BUILD_SPEC.md`. The active refactor
roadmap is in `docs/multi_brand_refactor_waves_0_4.md`.

Short version: `content_job.py` is the generation entrypoint, generated posts are
stored locally under `posts/<brand>/<project_id>/YYYY-MM-DD/<post_id>/`, publishing is manual
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

Default packaged-post folder (the dashboard supplies the project ID):
```
posts/<brand>/<project_id>/YYYY-MM-DD/<post_id>/
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

Run text-native formats only:
```
python content_job.py --brand vendrarx --angle "how 503A peptide compounding works" --formats reddit_longform,x_thread,tiktok_script --placeholder
```

Run a real OpenAI image batch:
```
set OPENAI_API_KEY=sk-...
python content_job.py --brand gloskin --roster roster.json --avatars 6 --posts-per-avatar 2
```

Batch sizing has two separate knobs:
- `--avatars` controls how many characters/personas to generate from `roster.json`.
- `--posts-per-avatar` controls how many post iterations to render from each avatar.
- `--formats` controls outputs: `slideshow`, `reddit_longform`, `x_thread`,
  `tiktok_script`, or a comma-separated mix.

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

The CLI image default is OpenAI (`IMAGE_PROVIDER=openai`), routed through
`image_router.py`. The dashboard defaults to the signed-in Codex queue. Dreamina,
Kling, or another service needs a documented developer API and a provider-specific
adapter; consumer subscription browser automation is not used as a backend.

For now, generated posts are queued for manual publishing only when
`compliance.status = "pass"`; otherwise they land in `needs_edit`. The selected
brand's configured account remains the target account.
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
- keep slideshow generation, talking-head video generation, character assets,
  batch review, and settings in separate workspaces
- select an explicit set of slideshow characters and preview every required asset
  before starting `content_job.py`
- control the number of post iterations independently for each selected character set
- create and edit saved roster characters, with previews for all five image slots
- upload any mix of before, opening, scan, after, and product-prop images
- generate only the missing character images from an uploaded identity reference
- create project-scoped image variants that inherit a character, regenerate only
  selected slots, preserve the prompt/provider snapshot, and appear in slideshow batches
- select `gloskin` or `vendrarx`
- create local projects and isolate each project's results without duplicating the shared character library
- save slideshow and video setups as reusable recipes, then reload and edit hooks or scripts before generating
- preview and save the actual character image prompt templates
- run a 1-post prompt test from an ad-hoc character spec
- show which real app screenshots are present or missing
- run placeholder batches for testing without image API calls
- show recent run logs
- review outputs by batch, grouped into character rows with slideshow filmstrips,
  iteration controls, paired video clips, scripts, and statuses
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

Character roster workflow:
1. Open **Characters** and choose an existing character or click **New character**.
2. Enter the character spec, scores, and default hook. Every image slot is optional.
3. Pick any existing images you have. The dashboard previews local selections immediately; click **Save character** to store them under `assets/<slug>/`.
4. Keep **Image source** set to **codex subscription / local queue** and click **Queue missing images**. A single before, scan, after, or opening face can serve as the identity reference. Opening and product-prop images are queued only when their Prompt Lab styles request them.
5. Run a Codex task using `docs/codex_image_queue.md`. Built-in GPT Image fills only absent files and marks the folder job complete; no `OPENAI_API_KEY` is used.
6. Open **Slideshows**, check the characters to include, choose posts per avatar,
   and review the asset matrix. Local Codex batches wait until every required image
   in the selected rows is complete.

Manifest-backed synthetic severity sets can be imported without calling an image API:

```text
python fixture_assets.py --manifest "C:\path\to\fixtures.jsonl"
```

The importer verifies each source checksum, requires clear/mild/moderate/severe for
every identity, and stores the full source metadata under
`assets/<slug>/fixture_set.json`. Moderate is mapped to the default before and scan
slots, while clear is mapped to after. The dashboard also shows all four levels.
These sets are internal visual references and are explicitly recorded as not being
measured treatment timelines. Like uploaded character images, they stay in the local,
gitignored `assets/` folder.

Slideshow variant workflow:
1. Select the project that should own the experiment.
2. In **Image variants**, choose a canonical character or a ready variant.
3. Choose the image slots to change. The current Prompt Lab values are stored as
   the variant's prompt snapshot; the source files remain untouched.
4. Use `codex_local` to queue subscription-backed edits, or choose a configured
   direct API. Providers without reference-edit support cannot be used for face slots.
5. When the variant is ready, click **Use** or select it in Character preflight.
   Saved slideshow recipes retain the variant asset slug for exact remakes.

Every new slideshow run and talking-head request receives a stable `batch_id`,
`workflow`, and selected `project_id`. Open **Review** to inspect the complete batch instead of searching a
flat post or clip list. Records created before this metadata existed are grouped
by brand, workflow, and creation date and marked **Legacy**.

### Projects and creative recipes

The header project selector is the local result boundary. Canonical character
images remain shared under `assets/<character_slug>/`. Derived variant metadata
belongs to its project under
`workspace_data/image_variants/<brand>/<project_id>/`; generated variant images
use a unique `assets/variant_.../` slug. New results are separated under:

```text
output/<brand>/<project_id>/
posts/<brand>/<project_id>/<date>/<post_id>/
screenshots/<brand>/<project_id>/
videos/<brand>/<project_id>/<character_slug>/
```

Project definitions and recipes persist under the gitignored `workspace_data/`
folder. Recipes are reusable across projects for the same brand. **Save setup**
captures current characters, batch settings, editable hooks or scripts, and the
image prompt snapshot. **Save recipe** in Batch Review additionally captures the
generated hooks, slide copy, captions, and source package references. Loading a
recipe never generates or queues media; it restores an editable preview first.

Uploaded images, variants, and queued jobs remain local. The default Codex queue
uses the signed-in Codex subscription, but a Codex task must claim it; the Flask
app cannot call subscription tools by itself. This path is dependable for
human-reviewed local production. Selecting `openai` or `custom` uses the API
router and is the better fit for unattended volume, retries, and scheduling.

Asset requirements: `before.png`, `scan.png`, and `after.png` are core character outputs, although uploading each one is optional because Codex can generate the missing files. `opening.png` is an optional identity-preserving hook. `product_prop.png` is an optional product-only visual and does not contain the character.

Queue inspection commands:
```text
python image_queue.py list --status queued
python image_queue.py claim
python image_queue.py complete --job <job_id>
```

The HeyGen talking-head queue is available in the dashboard and documented in
`docs/heygen_video_adapter.md`. Select a roster character, portrait, approved
script, and credit route, then queue the video. Subscription-backed jobs require a
HeyGen Remote MCP/OAuth connection in the processing Codex task; direct API-key
jobs use HeyGen's separate API wallet and can be tested and started in the local
dashboard. Neither route publishes automatically.

The gated follow-on plan for the first paid HeyGen smoke, local video assembly,
and manual winner remixes is in
`docs/next_video_assembly_and_winner_loop.md`. Those phases are not implemented
or triggered by the current dashboard.

In **Videos**, batch mode defaults to three checked roster characters and prepares
a before clip plus an after clip for each one. Characters can be added or removed
individually. Each character appears as one grouped row with both portraits and
editable scripts; the batch is rejected if any selected portrait is missing.

## Publishing and metrics integrations
Manual publishing is the working first adapter. CLI helpers:
```
python publish.py ready
python publish.py payload --post-id <post_id>
python publish.py mark --post-id <post_id> --platform tiktok --url https://...
python publish.py queue --post-id <post_id> --status needs_edit
```

Queue and publish actions require `compliance.status = "pass"`. A deliberate
exception uses `--override --reason "..."`; the override is recorded in the
manifest.

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

## Text-native formats
Wave 2 adds brand-aware text outputs:

```
python content_job.py --brand vendrarx --angle "how to evaluate a peptide telehealth offer" --formats reddit_longform,x_thread,tiktok_script --placeholder
python content_job.py --brand gloskin --angle "why your serum routine feels random" --formats reddit_longform,x_thread,tiktok_script --placeholder
```

Generated files land in the post package:
- `reddit.md` - Reddit title plus 300-800 word markdown body
- `thread.json` - `{"tweets": ["..."]}` with every tweet validated at 275 chars or less
- `tiktok_script.md` - `HOOK`, `BEATS`, `CTA`, and `SHOTLIST`

Real text generation uses `llm_router.py` and the per-brand prompts in
`prompts/<brand>/formats/`. `--placeholder` creates deterministic local drafts
for dry runs without API keys.

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

Capture notes:
- A native screenshot from the current app build is preferred because it keeps text
  and controls sharp. A paused QuickTime device recording is also usable if the frame
  is exported to PNG without scaling or compression.
- The Dynamic Island and status bar may remain when they are part of the real capture.
  The renderer does not add a separate iPhone hardware shell.
- Background color and glow come from the captured app screen. Replace the template
  with a current screen if those visuals change; do not recolor an old screen into a
  UI state the app does not actually use.

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
The built-in custom adapter accepts a synchronous prompt/width/height JSON
contract. Set `IMAGE_API_URL`; set `IMAGE_API_EDIT_URL` when the service supports
reference edits. Provider responses may be image bytes, `b64`, `b64_json`, or an
image URL. For a different contract, register a provider-specific generate/edit
adapter. The dashboard never falls back to a fresh face when a selected slot
requires an identity-preserving edit. To use your own roster instead, drop `before.png`,
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
Run the Wave 3 semantic fixtures with a configured `OPENROUTER_API_KEY`:
```
python compliance_lint.py --selftest
```

Before/after acne creative is heavily scrutinized. Keep copy cosmetic/educational
(no "cures" / medical promises — the brief generator enforces this), and put a
visible "results vary · not medical advice" line in captions/bio.

## Where this is going (next builds)
- **Compliance gate**: lint copy before it can enter the manual publish queue.
