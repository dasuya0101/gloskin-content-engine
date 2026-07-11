# GloSkin Content Engine - Current Build Spec

This repo is a local-first Python content engine. The active direction is the
multi-brand refactor described in:

- `docs/multi_brand_refactor_waves_0_3.md`

Wave 0 hygiene is complete in this branch. Waves 1-3 should follow that document
unless Amol supersedes it.

## Current Runtime

- Local Windows PC only.
- No VPS, scheduler, DB server, auth, or hosted storage.
- Dashboard: `python api_server.py`, then open `http://127.0.0.1:5055`.
- Source of truth: local `posts.json` written by `manifest.py`.
- GitHub: `https://github.com/dasuya0101/gloskin-content-engine`, branch `main`.

## Entrypoints

Primary generation entrypoint:

```powershell
python content_job.py --roster roster.json --avatars 2 --posts-per-avatar 2 --placeholder
```

Copy-only brief flow:

```powershell
python generate_briefs.py --angles angles.txt --out briefs
python slideshow_maker.py --briefs-dir briefs --out output
```

`run_pipeline.py` was deprecated and removed. Do not add new work there.

## Repo Structure

- `content_job.py` - orchestrates avatar generation, screenshot compositing, slide/video rendering, packaging, and manifest writes.
- `character_factory.py` - generates `before.png`, optional `opening.png`, `scan.png`, `after.png`, and optional `product_prop.png`.
- `image_router.py` - provider registry for image APIs. Default is OpenAI `gpt-image-1`; `custom` is an HTTP template.
- `screenshot_factory.py` - personalizes real app screenshots by replacing measured slots, currently Scan Results face/score/progress.
- `slideshow_maker.py` - renders 1080x1920 slide PNGs and MP4 videos. It no longer contains fake result/product UI renderers.
- `api_server.py` + `dashboard.html` - local Flask API and dashboard.
- `manifest.py` - JSON manifest helpers.
- `publish.py` - manual publishing bridge and future API scaffolds.
- `metrics_refresh.py` / `import_metrics.py` - CSV metrics import and future API scaffolds.
- `prompts/` - current GloSkin prompt files.
- `templates/` - real app screenshot templates.
- `briefs/` - example brief JSON files.

Generated/local artifacts are ignored by Git: `assets/`, `output/`, `posts/`,
`screenshots/`, `posts.json`, logs, runs, and local secrets.

## End-To-End Flow

Dashboard or CLI inputs:

- roster character spec, scores, hooks
- batch size: avatars and posts per avatar
- prompt options: opening image style, product prop style
- image provider: OpenAI by default, placeholder for no-API tests

Pipeline:

1. `content_job.py` selects roster characters or ad-hoc spec.
2. `character_factory.py` creates persona assets through `image_router.py` or placeholders.
3. `screenshot_factory.py` composites `scan.png` / `after.png` into `templates/scan_results.webp`.
4. `content_job.py` builds an in-memory testimonial brief.
5. `slideshow_maker.py` renders slide PNGs and MP4.
6. `content_job.py` packages files under `posts/YYYY-MM-DD/<post_id>/`.
7. `manifest.py` records the post in `posts.json`.

Packaged post shape:

```text
posts/YYYY-MM-DD/<post_id>/
  slides/
  video.mp4
  source_assets/
  caption.txt
  brief.json
  post.json
```

## Current GloSkin-Specific Locations

These are intentionally still hardcoded until Wave 1 moves brand identity into
`brands/<brand_id>.yaml`.

- Prompts: `prompts/copy_system.md`, `prompts/learned_rules.md`, `prompts/image_character.json`, plus defaults in `character_factory.py`.
- Styling/wordmark/CTA chrome: `slideshow_maker.py`.
- Default account: `gloskin_main` in `content_job.py`, `api_server.py`, and `publish.py`.
- App screenshot inventory: `app_assets.py`.
- Real Scan Results screenshot: `templates/scan_results.webp`.
- Roster/template defaults: `roster.json`.

## Manifest Schema

Current `posts.json` records are a list of objects with:

- `post_id`, `created_at`, `format`
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

Wave 1 adds `brand`, defaults missing legacy values to `gloskin`, and partitions
packages under `posts/<brand>/YYYY-MM-DD/<post_id>/`.

## Working

- Local dashboard can start runs, preview prompts, preview rendered files, update queue status, mark winners, and import CSV metrics.
- Placeholder generation runs without API keys.
- OpenAI image route exists for real generation.
- Real Scan Results compositing works.
- Manual publish queue works.
- CSV metrics import works.
- GitHub remote is linked.

## Stale / Deferred

- Direct platform publishing APIs are scaffolded but not implemented.
- Direct metrics API pulls are scaffolded but not implemented.
- Dreamina provider is deferred.
- VPS/deploy/scheduler/database/auth are explicitly out of scope for Waves 0-3.
- Multi-brand config is not implemented yet; see Wave 1 in `docs/multi_brand_refactor_waves_0_3.md`.

## Next Work

1. Wave 1: add `brands/gloskin.yaml`, `brands/vendrarx.yaml`, `brand_loader.py`, brand-aware prompts/assets, and manifest `brand`.
2. Wave 2: VendraRx brand pack and text-native formats.
3. Wave 3: compliance linter and publish gate.
