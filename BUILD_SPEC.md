# Content Engine - Current Build Spec

This repo is a local-first Python content engine with multi-brand config. The
active roadmap is:

- `docs/multi_brand_refactor_waves_0_3.md`

Wave 0 and Wave 1 are complete. Wave 2 is next.

## Current Runtime

- Local Windows PC only.
- No VPS, scheduler, DB server, auth, or hosted storage.
- Dashboard: `python api_server.py`, then open `http://127.0.0.1:5055`.
- Source of truth: local `posts.json` written by `manifest.py`.
- GitHub: `https://github.com/dasuya0101/gloskin-content-engine`, branch `main`.

## Entrypoints

Primary generation entrypoint:

```powershell
python content_job.py --brand gloskin --roster roster.json --avatars 2 --posts-per-avatar 2 --placeholder
python content_job.py --brand vendrarx --spec "founder, 30s, White" --placeholder
```

Copy-only brief flow:

```powershell
python generate_briefs.py --brand gloskin --angles angles.txt --out briefs
python slideshow_maker.py --briefs-dir briefs --out output
```

`run_pipeline.py` was deprecated and removed. Do not add new work there.

## Repo Structure

- `brand_loader.py` - validates `brands/<brand_id>.yaml` and exposes `Brand`.
- `brands/gloskin.yaml` - GloSkin voice, CTA, palette, accounts, prompts, screenshot inventory, compliance seed rules.
- `brands/vendrarx.yaml` - VendraRx stub using homepage-derived theme and `https://vendrarx.com/` CTA.
- `content_job.py` - brand-aware avatar generation, optional screenshot compositing, slide/video rendering, packaging, and manifest writes.
- `character_factory.py` - generates `before.png`, optional `opening.png`, `scan.png`, `after.png`, and optional `product_prop.png`.
- `image_router.py` - provider registry for image APIs. Default is OpenAI `gpt-image-1`; `custom` is an HTTP template.
- `screenshot_factory.py` - personalizes real app screenshots by replacing measured slots. Used only when the selected brand declares templates.
- `slideshow_maker.py` - renders 1080x1920 slide PNGs and MP4 videos with brand palette/chrome/CTA.
- `api_server.py` + `dashboard.html` - local Flask API and dashboard with brand selector.
- `manifest.py` - JSON manifest helpers with legacy default-brand fallback.
- `publish.py` - manual publishing bridge and future API scaffolds.
- `metrics_refresh.py` / `import_metrics.py` - CSV metrics import and future API scaffolds.
- `prompts/<brand_id>/` - brand prompt files.
- `templates/` - real screenshot templates referenced by brand config.

Generated/local artifacts are ignored by Git: `assets/`, `output/`, `posts/`,
`screenshots/`, `posts.json`, logs, runs, and local secrets.

## End-To-End Flow

Dashboard or CLI inputs:

- brand: `gloskin` by default, `vendrarx` supported in placeholder mode
- roster character spec, scores, hooks
- batch size: avatars and posts per avatar
- prompt options: opening image style, product prop style
- image provider: OpenAI by default, placeholder for no-API tests

Pipeline:

1. `content_job.py` loads `Brand` from `brands/<brand_id>.yaml`.
2. `character_factory.py` creates persona assets through `image_router.py` or placeholders.
3. If the brand declares a screenshot template, `screenshot_factory.py` composites into the real app screen.
4. If the brand has no screenshot templates, screenshot slides are skipped and brand-config body slides are used.
5. `content_job.py` builds an in-memory branded brief.
6. `slideshow_maker.py` renders branded slide PNGs and MP4.
7. `content_job.py` packages files under `posts/<brand>/YYYY-MM-DD/<post_id>/`.
8. `manifest.py` records the post in `posts.json`.

Packaged post shape:

```text
posts/<brand>/YYYY-MM-DD/<post_id>/
  slides/
  video.mp4
  source_assets/
  caption.txt
  brief.json
  post.json
```

## Brand-Specific Locations

Brand-specific identity now lives in config:

- `brands/gloskin.yaml`
- `brands/vendrarx.yaml`
- `prompts/gloskin/`
- `prompts/vendrarx/`

The only intended brand literal in Python is the documented default brand
constant in `brand_loader.py`; legacy manifest reads default missing `brand` to
that value.

## Manifest Schema

Current `posts.json` records are a list of objects with:

- `post_id`, `brand`, `created_at`, `format`
- `character`: slug/spec/scores plus current style metadata
- `hook`
- `slides`: kind/text summary
- `assets`: source asset paths such as opening/before/scan/after/product_prop/shot_before/shot_after
- `outputs`: slides/video paths
- `caption`
- `package`: packaged folder paths
- `variant_of`
- `tracking_code`
- `publish`
- `publish_queue`
- `metrics`
- `is_winner`

Entries missing `brand` are treated as the default brand on read.

## Working

- Local dashboard can select brand, start runs, preview prompts, preview rendered files, update queue status, mark winners, and import CSV metrics.
- GloSkin placeholder generation runs with real Scan Results compositing.
- VendraRx placeholder generation runs without screenshot templates and packages under `posts/vendrarx/...`.
- OpenAI image route exists for real generation.
- Manual publish queue works.
- CSV metrics import works.
- GitHub remote is linked.

## Stale / Deferred

- Direct platform publishing APIs are scaffolded but not implemented.
- Direct metrics API pulls are scaffolded but not implemented.
- Dreamina provider is deferred.
- VPS/deploy/scheduler/database/auth are explicitly out of scope for Waves 0-3.
- Text-native output formats are not implemented yet; see Wave 2.
- Compliance lint/publish gate is not implemented yet; see Wave 3.

## Next Work

1. Wave 2: VendraRx brand pack and text-native formats.
2. Wave 3: compliance linter and publish gate.
