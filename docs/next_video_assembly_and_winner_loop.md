# Next Phase: Video Assembly and Winner Loops

This is a planning boundary, not an implemented workflow. Image variants,
slideshow batches, recipes, manual winner marking, and the HeyGen queue are the
inputs. Publishing remains manual.

## Gate 1: First real HeyGen clip batch

Run only after the user deliberately approves credit spend.

1. Select one ready character with before and after portraits.
2. Preview and approve two short scripts in the dashboard.
3. Submit through the connected HeyGen OAuth plugin or the direct API wallet.
4. Download both MP4s into the project-scoped `videos/` folder.
5. Verify identity, lip sync, framing, duration, voice, motion, and credit usage.
6. Repeat with three characters only after the first pair passes.

Acceptance: queue state, remote status, downloaded files, and batch review all
agree; retries never create duplicate paid renders.

## Gate 2: Video assembly

Add an explicit assembly manifest before choosing the renderer. Each assembled
creative should reference immutable source files and contain:

- before talking-head clip
- app-screen overlay segment using the real GloSkin screen asset
- after talking-head clip
- optional captions, music reference, and end card
- timing, crop, transition, and audio settings
- source recipe, character/variant IDs, brand, and project ID

The dashboard should preview the timeline and output path before rendering.
Assembly creates a new local artifact; it never modifies source HeyGen clips.
Choose the renderer after one real clip pair establishes the actual codecs,
dimensions, and audio behavior. Keep publishing outside this phase.

Acceptance: deterministic rerenders from one manifest, vertical-safe framing,
no app-screen fabrication, readable captions, and exact project isolation.

## Gate 3: Manual winner remix loop

Keep `is_winner` as the human decision. Add a **Create remix** action that starts
from the winner's saved recipe and creative snapshot, then requires the user to
choose what changes:

- hook or script only
- character or image variant only
- opening/product treatment only
- assembly timing only
- CTA/caption only where brand compliance permits

The remix must show a before/after setup diff and create a new batch ID. It must
never overwrite the winning package or auto-submit media.

Acceptance: every remix links to its source winner, preserves unchanged settings,
and can be separated by project in metrics and review.

## Gate 4: Provider expansion

Keep `codex_local`, OpenAI, and the generic API contract as the stable base.
Add Dreamina or Kling only after confirming the account has developer API access,
official authentication, reference-image editing, async job semantics, and a
download contract. Consumer-site browser automation is not a production worker.
Each new adapter needs capability metadata, bounded retries, cost/status reporting,
and identity-edit fixtures before it appears as enabled in the dashboard.
