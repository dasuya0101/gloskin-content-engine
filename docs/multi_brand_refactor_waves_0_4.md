# Content Engine Multi-Brand Refactor Plan

Repo: `gloskin-content-engine`
Local path: `C:/Users/Amols/Downloads/gloskin_content_engine`
GitHub: `dasuya0101/gloskin-content-engine`

## Goal

Turn the current GloSkin-only content engine into one local-first engine that can
serve multiple brands. GloSkin is the active brand now. VendraRx is next. Ventra
is deferred.

The target architecture is brand-as-config:

- brand voice, prompts, palette, CTA, accounts, and compliance rules live in
  `brands/<brand_id>.yaml`
- modules read a validated `Brand` object
- no brand literals live in core module code except the documented default
  brand/back-compat logic
- publishing remains manual
- the local JSON manifest remains the source of truth

Current runtime and status live in `BUILD_SPEC.md`. This file is the roadmap for
the next agents.

## Locked Decisions

- D1: Local-only. No VPS, scheduler, DB server, auth, hosted storage, or deploy
  scaffolding in Waves 0-3.
- D2: Manifest stays JSON. `posts.json` remains local source of truth. Wave 1
  adds `brand` to every entry and writes packages under
  `posts/<brand>/YYYY-MM-DD/<post_id>/`. Entries missing `brand` are read as
  `gloskin`.
- D3: CTAs are config values. GloSkin points to `https://gloskin.app` until the
  App Store listing is live. VendraRx quiz/waitlist lives on the homepage:
  `https://vendrarx.com/`.
- D4: Image provider default is OpenAI. Dreamina is deferred.
- D5: Manual publishing only. No TikTok, Instagram, Meta, X, or Reddit posting
  API integrations in these waves.
- D6: Fake result/product renderers stay removed. Testimonial-style content that
  uses AI avatars plus composited screenshots must carry an illustrative /
  AI-generated label once Wave 3 compliance is active.

Suggested execution: Wave 2 and Wave 3 can run in parallel after Wave 1 lands.

## Wave 0 - Completed Hygiene

Objective: single documented generation entrypoint, no fake-result rendering
path, and an up-to-date build handoff.

Completed changes:

- `content_job.py` is the generation entrypoint of record.
- Copy-only flow remains `generate_briefs.py` to `slideshow_maker.py`.
- The legacy pipeline script has been removed from the active repo.
- `slideshow_maker.py` no longer contains fake `results` or `products` card
  renderers or branches.
- `BUILD_SPEC.md` now reflects the actual dashboard, manifest, local runtime,
  repo structure, and working/deferred areas.

Wave 0 acceptance for future checks:

- Grep for removed renderer names returns nothing in `*.py`.
- A placeholder testimonial job completes end-to-end.
- Docs identify `content_job.py` as the generation entrypoint plus the copy-only
  brief flow.

## Wave 1 - Completed Brand-As-Config Refactor

Objective: all brand identity moves into YAML config, brand prompt folders, and
brand asset folders.

Status: complete. Current implementation is summarized in `BUILD_SPEC.md`.

New files:

- `brands/gloskin.yaml`: fully populated from current GloSkin hardcoded values.
- `brands/vendrarx.yaml`: structurally complete stub using
  `https://vendrarx.com/` for CTA URL, homepage-derived provisional theme, and
  `TODO` account handles.
- `brand_loader.py`: loads and validates YAML, exposes a `Brand` dataclass, and
  fails loudly with the missing/invalid key named.
- `prompts/gloskin/`: move current GloSkin prompt files here.
- `prompts/vendrarx/copy_system.md`: stub prompt for Wave 2 expansion.
- `assets/brands/<brand_id>/`: convention for wordmarks/logos.

Validation requirements for `brand_loader.py`:

- required keys present
- referenced prompt and asset paths exist when non-null
- hex colors parse
- configured screenshot templates exist when declared

Modified files:

- `content_job.py`: add `--brand` defaulting to `gloskin`, load `Brand` once,
  thread it through generation, and replace hardcoded account defaults with
  brand config.
- `generate_briefs.py`: brand-aware prompt assembly and `brand` in brief JSON.
- `llm_router.py`: prompt assembly accepts brand prompt paths and voice context.
- `slideshow_maker.py`: palette, fonts, wordmark text/asset, chrome, CTA text,
  and CTA URL come from `Brand`.
- `screenshot_factory.py`: only runs for brands with screenshot templates; skip
  clearly for brands without templates.
- `manifest.py`: add `brand`, partition packages under
  `posts/<brand>/YYYY-MM-DD/<post_id>/`, and default legacy records to
  `gloskin` on read.
- `publish.py` and `api_server.py`: accept brand params, default to `gloskin`,
  and remove hardcoded account routing.
- `dashboard.html`: add a brand selector wired to the local API. Do not restyle
  the dashboard beyond what is needed.

Wave 1 acceptance:

- GloSkin placeholder run still completes and outputs equivalent slides/video
  with the new `brand: gloskin` manifest field.
- `python content_job.py --brand vendrarx --placeholder` completes end-to-end
  with Vendra stub styling, Vendra CTA, package path under `posts/vendrarx/...`,
  and manifest `brand: vendrarx`.
- Literal sweep for `gloskin` in `*.py` returns only the documented default brand
  constant and back-compat manifest logic.
- Existing `posts.json` loads without migration errors.

## Wave 2 - Completed VendraRx Brand Pack And Text-Native Formats

Objective: make VendraRx a real runnable brand and add text-first outputs that
both brands can use.

Status: complete. Current implementation is summarized in `BUILD_SPEC.md`.

VendraRx brand pack:

- voice: evidence-forward, direct, operator/founder POV
- audience: optimization/longevity crowd, Reddit/X-native, skeptical of
  marketing
- pillars: `peptide_explainers`, `research_summaries`,
  `telehealth_logistics`, `build_in_public`
- CTA: waitlist/quiz framing pointing to `https://vendrarx.com/`
- palette/fonts/wordmark: extract provisional values from the homepage; see
  `docs/vendrarx_homepage_notes.md`
- formats enabled: `reddit_longform`, `x_thread`, `tiktok_script`, `slideshow`
- `prompts/vendrarx/copy_system.md`: real voice rules, banned hype phrases,
  cautious research posture, and founder-POV framing

Text format renderer:

- Add `text_formats.py` or a single equivalent renderer module.
- `reddit_longform` writes `reddit.md`; first line is title, blank line, then
  300-800 word body markdown.
- `x_thread` writes `thread.json` as `{"tweets": ["..."]}` and validates every
  tweet is 275 characters or shorter.
- `tiktok_script` writes `tiktok_script.md` with `HOOK`, `BEATS`, `CTA`, and
  `SHOTLIST`.
- Add per-brand format prompts at `prompts/<brand>/formats/<format>.md`.
- Brief schema gains `formats`.
- CLI accepts `--formats reddit_longform,x_thread,...`.
- Manifest `outputs` records generated format files.

Wave 2 acceptance:

- One Vendra angle run writes `reddit.md`, `thread.json`, and
  `tiktok_script.md` into the post folder and records all three in manifest.
- Any tweet over 275 characters fails the run before packaging.
- Same command with `--brand gloskin` produces GloSkin-voiced text outputs.

## Wave 3 - Compliance Linter And Publish Gate

Status: implemented; final real-copy acceptance requires the project 14-angle
source list.

Objective: no generated copy reaches the publish queue without passing
brand-specific compliance rules.

`compliance_lint.py` runs once per output file with three layers:

- Layer 1 immediately blocks only unambiguous `hard_block` patterns. Review
  terms and shared false-precision patterns are candidates, not verdicts.
- Layer 2 is the primary semantic control. It calls the brand compliance policy
  through `llm_router.py` with the full output, brief factual claims, approved
  mechanism claims, Layer-1 candidates, and post context. It catches fabricated
  research acts, evidence details, unsourced mechanisms, disease/Rx promises,
  and unverifiable operational claims. It also clears debunks and disclaimers
  in context. Invalid JSON becomes `needs_review`, never pass.
- Layer 3 asserts that every format-required disclaimer is present verbatim.

Vendra briefs carry `mechanism_claims`, selected from the per-compound allowlist
in brand config. Generation may use only approved directional language; the
semantic gate blocks named pathways, receptors, molecules, or mechanisms absent
from that allowlist.

The renderer owns deterministic copy. `text_formats.py` inserts the CTA and
required disclaimers from brand config at sentinels, with format-appropriate
fallback placement. CTA URLs receive `utm_source=reddit|twitter|tiktok` and
`utm_campaign=<tracking_code>` while preserving existing query parameters.
Landing-side UTM capture on `vendrarx.com` remains a dependency in the separate
landing repository.

On a semantic failure with a suggested full rewrite, the engine normalizes the
rewrite and reruns all layers once. A second failure becomes `needs_review`.
Each new post records `compliance.status`, `violations`, and `checked_at` in both
`posts.json` and packaged `post.json`. The dashboard shows the status. The CLI
and dashboard API reject queue/publish actions for non-pass posts unless an
override and reason are supplied; the override is recorded in the manifest.

Operational-practice language was removed from source prompts and homepage
notes. The linter retains a frozen shipping/storage fixture and warns on such
claims if generated anyway.

Wave 3 acceptance:

- `python compliance_lint.py --selftest` passes all seed cases.
- The five clean-regex frozen leaks are caught by Layer 2, while the cure/heal
  debunk cases and approved directional mechanism phrase pass.
- The full 14-angle Vendra batch is the real-copy acceptance test. Review false
  positives on debunks and directional mechanism language before trusting the
  gate; the synthetic seeds verify wiring, not production precision.
- A failing post cannot enter publish queue without `--override`.
- Override is recorded in the manifest.
- New posts include `compliance` in both `post.json` and `posts.json`.

## Deferred Backlog

- Dreamina image provider
- direct TikTok/IG/Meta/X/Reddit posting APIs
- platform metrics API pulls
- VPS deploy and scheduler
- SQLite migration
- repo rename to a brand-neutral name
- Ventra brand pack

## Brand YAML Reference

```yaml
brand_id: vendrarx
display_name: VendraRx
operational_status: pre_launch
voice:
  tone: [evidence-forward, direct, operator]
  audience: "optimization/longevity crowd; Reddit/X-native; skeptical of marketing"
  pov: founder
pillars: [peptide_explainers, research_summaries, telehealth_logistics, build_in_public]
cta:
  text: "Take the 60-second quiz"
  url: "https://vendrarx.com/"
palette:
  bg: "#F5F0E6"
  fg: "#0E1410"
  surface: "#FAF7EF"
  primary: "#1B2A24"
  secondary: "#3F5A4E"
  accent: "#B8542C"
  accent_2: "#D26A3F"
  muted: "#5C6A63"
fonts:
  heading: "Inter Tight"
  body: "Inter"
  accent: "Instrument Serif"
  mono: "JetBrains Mono"
assets:
  wordmark: assets/brands/vendrarx/wordmark.png
accounts:
  tiktok: "TODO"
  x: "TODO"
  reddit: "TODO"
formats: [reddit_longform, x_thread, tiktok_script, slideshow]
templates: {}
prompts:
  copy_system: prompts/vendrarx/copy_system.md
  compliance_policy: prompts/vendrarx/compliance_policy.md
  image_character: null
compliance:
  hard_block:
    - "\\bguaranteed (prescription|results|outcome)\\b"
  review:
    - "\\b(cure|cures|treat|treats|prevent|prevents|heal|heals)\\b"
  required_disclaimers:
    - id: compounded
      applies_to: [reddit_longform, tiktok_script]
      text: "Compounded medications are prepared by licensed pharmacies and are not FDA-approved. Individual suitability is determined by a licensed clinician."
```

## Resolved And Remaining Inputs

Resolved inputs:

- VendraRx quiz/waitlist URL: `https://vendrarx.com/`
- VendraRx theme/content extraction: approved from the homepage; see
  `docs/vendrarx_homepage_notes.md`
- GloSkin CTA: confirmed as `https://gloskin.app` until App Store approval

Still TODO:

- VendraRx account handles for TikTok, X, and Reddit

## Wave 4: Compliance Hardening And Operational Status

Wave 4 moves patternable fabrication checks out of the stochastic judgment
layer. Layer 1 now catches named mechanisms, research/regulatory years,
percentages, trial-scale language, and legal conclusions identically across
formats. A match clears only when it falls inside an exact approved phrase from
the brief or a relevant compound claim pack. Unapproved mechanism and evidence
specifics block; legal conclusions use the stricter
`unapproved_regulatory_claim` rule. The LLM judge remains responsible for
unpatternable semantic residuals.

Human-authored ground truth lives in `claims/<compound>.yaml`. Packs provide
exact `evidence_claims`, `mechanism_claims`, `regulatory_claims`, and
`disallowed_claims`, plus aliases used to select the pack from an angle. The
generator injects relevant packs into the brief. With no pack, specific claims
are unavailable and copy must stay qualitative. Disallowed claims hard-block.

Brand config now carries `operational_status: pre_launch | live`. VendraRx is
`pre_launch`. At that status, generated clinical-model copy must use explicit
design, building, or launch framing. Bare present-tense care-delivery claims
route to review. Changing the config to `live` clears present-tense framing;
other compliance rules remain active.

Compliance rewrites now replace violating detail with useful qualitative copy
at a supplied length target. Each full rewrite is normalized and validated;
format or Reddit length failures regenerate up to the existing three-attempt
cap. A post is never accepted with an invalid short rewrite.

Wave 4 acceptance:

- `python compliance_lint.py --selftest` covers all Layer 1 pattern families,
  exact and missing pack membership, disallowed claims, and pre-launch/live
  operational framing.
- Batch angles 6, 7, 8, 10, 11, and 12 are regenerated through all three text
  formats and linted in `acceptance/vendrarx_wave4_rerun/`.
- The acceptance report compares the new distribution with the Wave 3 subset,
  records initial deterministic catches even when a rewrite succeeds, and
  confirms there are no `rewrite_render_error` violations.
- No publishing or compliance override is part of Wave 4.
