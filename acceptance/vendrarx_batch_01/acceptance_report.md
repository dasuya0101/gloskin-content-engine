# VendraRx Batch 01 - Wave 3 Acceptance Report

## Result

**Acceptance verdict: NOT PASSED.**

The pipeline and publish gate wiring worked, but the linter is not yet reliable
enough for production sign-off. It produced useful true catches and one clear
false positive, while also allowing material unsourced mechanisms, fabricated
evidence shape, false precision, legal assertions, and operational promises to
pass in other outputs.

- Input: `angles/vendrarx_batch_01.yaml`
- Brand: `vendrarx`
- Formats: `reddit_longform`, `x_thread`, `tiktok_script`
- Started: `2026-07-21T12:30:25`
- Completed: `2026-07-21T12:43:00`
- Posts: 14
- Text outputs: 42
- Execution failures: 0
- API calls reporting usage: 88
- Reported tokens: 121,594
- Reported cost: $0.053303
- Publishing actions: 0
- Overrides: 0

## Status Distribution

| Angle | Post ID | Compliance | Queue |
|---:|---|---|---|
| 1 | `1e203377f89a` | pass | ready_to_post |
| 2 | `07d02d0b7f87` | pass | ready_to_post |
| 3 | `de65946192a7` | pass | ready_to_post |
| 4 | `e8728a7deb68` | needs_review | needs_edit |
| 5 | `783f97789b1f` | needs_review | needs_edit |
| 6 | `72d71c1cc79e` | pass | ready_to_post |
| 7 | `060e44d9cbfa` | pass | ready_to_post |
| 8 | `445e034b5fd0` | pass | ready_to_post |
| 9 | `c9a683a62429` | pass | ready_to_post |
| 10 | `cf3c30972074` | pass | ready_to_post |
| 11 | `9a28067417b2` | pass | ready_to_post |
| 12 | `8d4fb8225255` | needs_review | needs_edit |
| 13 | `d24423d53722` | pass | ready_to_post |
| 14 | `bd00efab6940` | pass | ready_to_post |

Distribution: **11 pass / 3 needs_review / 0 fail**.

## Final Flag Review

Every final flag from each `needs_review` post is classified below. Verdicts in
the manifests were not edited or overridden.

### Angle 4 - Telehealth Rx flow

- **TRUE CATCH** - `tiktok_script` / `unverifiable_operational_claim`:
  `temperature-controlled`
  The supplied angle says shipment, not temperature-controlled shipment. This
  requires operational confirmation.

### Angle 5 - BPC-157 literature

- **TRUE CATCH** - `reddit_longform` / `fabricated_research_act`:
  `I Read the BPC-157 Literature So You Don’t Have To`
  This conflicts with the non-negotiable no-research-act policy even though it
  came from the supplied angle.
- **TRUE CATCH** - `reddit_longform` / `unverifiable_operational_claim`:
  `Every case is reviewed by a US-licensed physician`
  This requires operational confirmation.
- **PIPELINE ERROR** - `reddit_longform` / `rewrite_render_error`:
  `reddit_longform body must be 300-800 words; got 186`
  The suggested rewrite did not satisfy the format validator, so the original
  violating output remained and the post correctly stayed in review.
- The X thread initially failed for `Here's what I found digging through the
  literature (so you don't have to).` The one-pass rewrite removed it and the
  rewritten thread passed.

### Angle 12 - GHK-Cu topical vs injected

- **TRUE CATCH** - `reddit_longform` / `fabricated_evidence`:
  `Most of this research involves small trials or case studies, but the results
  are directionally consistent: GHK-Cu applied to the skin *may* support
  collagen production and skin barrier function.`
- **TRUE CATCH, WRONG RULE TAXONOMY** - `reddit_longform` /
  `unverifiable_operational_claim`:
  `The caveat? Quality matters. A lot. GHK-Cu is unstable in solution and
  degrades quickly without proper formulation — so buying a random peptide
  vial and mixing it into your moisturizer probably won’t cut it.`
  This is an unsupported stability/formulation claim, not primarily an
  operational claim.
- **TRUE CATCH, WRONG RULE TAXONOMY** - `reddit_longform` /
  `unverifiable_operational_claim`:
  `Clinical-grade topicals are formulated to stabilize the peptide and enhance
  absorption, which matters if you’re expecting results.`
  This is an unsupported formulation/absorption claim.
- **TRUE CATCH** - `reddit_longform` / `fabricated_evidence`:
  `In preclinical models, GHK-Cu injection *may* support tissue repair and
  reduce inflammation, but we don’t know if those effects occur in humans at
  safe doses.`
- **TRUE CATCH** - `reddit_longform` / `fabricated_evidence`:
  `There’s also almost no safety data for injectable GHK-Cu, which is a red
  flag.`
- **TRUE CATCH** - `reddit_longform` / `unverifiable_operational_claim`:
  `We’re building a clinician-guided telehealth practice for peptide therapy,
  and we only work with US-licensed physicians who evaluate suitability on a
  case-by-case basis.`
- **TRUE CATCH** - `reddit_longform` / `unverifiable_operational_claim`:
  `If GHK-Cu is appropriate for your goals, we’ll connect you with a clinician
  who can guide you safely — and we’ll source it from a 503A compounding
  pharmacy that meets strict quality standards.`
- **TRUE CATCH** - `reddit_longform` / `unverifiable_operational_claim`:
  `If labs or follow-up are needed, we’ll make that part of the plan too.`
- **FALSE POSITIVE** - `reddit_longform` / `fabricated_evidence`:
  `Here’s the bottom line: GHK-Cu’s skin-level benefits are plausible, but
  systemic injection is still speculative.`
  This is cautious, qualitative synthesis consistent with the supplied
  topical-versus-injected evidence angle. It should not be blocked by itself.
- **PIPELINE ERROR** - `reddit_longform` / `rewrite_render_error`:
  `reddit_longform body must be 300-800 words; got 147`

Final content-flag classification: **11 true catches / 1 false positive**.
There were also **2 rewrite-format failures**.

## Mechanism Allowlist Behavior

- **Formal allowlist trip: angle 10, X thread.** Four
  `unsourced_mechanism` violations covered receptor activation, satiety
  signaling, gastric emptying, insulin/glucose pathways, and metabolic effects.
  The rewrite removed the details and the X output passed.
- **Existing BPC-157 allowlist:** no mechanism violation fired for angle 5.
- **Inconsistent enforcement:** angle 10 Reddit and TikTok passed closely related
  satiety and gastric-emptying mechanism claims that caused X to fail.
- **Mechanism false negatives:** angles 6, 7, 8, 11, and 12 contained named or
  specific NAD+, GH/IGF-1/pituitary, GLP-1/reward, SNAC/absorption, and GHK-Cu
  mechanisms without corresponding allowlists, but many outputs passed.

The allowlist therefore needs verified claim packs for GLP-1, NAD+, GH
secretagogues, SNAC/oral peptide delivery, and GHK-Cu. More importantly, the
linter must enforce absence from the allowlist consistently across every
format; adding approved phrases alone will not fix these false negatives.

## Material False Negatives

These representative examples received a final `pass` or occurred in a passing
output inside a review post. They are not exhaustive.

- **Angle 1:** `The FDA's 2023 guidance made clear...` and claims that 503A is
  the only legal pathway. The date and detailed legal conclusions were absent
  from the brief.
- **Angle 2:** `ingredients must be USP-grade or equivalent`, detailed 503A/503B
  inspection and sterility claims, and `We only work with 503A pharmacies.`
- **Angle 3:** purported FDA definitions, illegality conclusions, purity and
  sterility assertions, and Vendra operational promises passed without sources.
- **Angle 6:** claims about NAD+ pathways, animal-versus-human evidence shape,
  study design, blood pressure and insulin markers, bioavailability,
  pharmacokinetics, dosing, and addiction-recovery studies all passed.
- **Angle 7:** direct GH suppression, IGF-1 feedback loops, pituitary action,
  pulse patterns, side-effect comparisons, and animal/small-human-trial claims
  passed with an empty mechanism allowlist.
- **Angle 8:** large cardiovascular outcome trials, MACE, vascular inflammation,
  cardiac remodeling, reward-region receptor expression, case reports, sample
  shape, and addiction-study claims passed.
- **Angle 9:** the model added oxytocin, molecular definitions, and decades-of-use
  framing absent from the brief.
- **Angle 10:** Reddit and TikTok passed detailed satiety, vagus/appetite-center,
  stomach-emptying, and metabolic-lab claims while X was rewritten for similar
  mechanisms.
- **Angle 11:** SNAC's named molecular action, semaglutide examples, higher-dose
  claims, `oral bioavailability is often <1%`, and `single-digit %` passed.
- **Angle 12:** X and TikTok passed `studied for decades`, small-trial counts,
  collagen effects, mostly-rodent evidence, systemic effects, and safety/efficacy
  conclusions that were similar to the Reddit violations.
- **Angle 13:** `only legal source`, FDA-registration, licensure, state-law, and
  Vendra operational assertions passed without verified source facts.
- **Angle 14:** provider-cost, pharmacy, medical-necessity, lab-integration,
  follow-up, state-demand, and critical-mass operational claims all passed.

## Mechanical Verification

All mechanical checks passed for all 14 posts:

- exact supplied angle persisted as `hook`
- `reddit.md`, `thread.json`, and `tiktok_script.md` present
- Reddit body between 300 and 800 words
- every tweet at most 275 characters
- TikTok `HOOK`, `BEATS`, `CTA`, and `SHOTLIST` sections present
- exact CTA once per output with platform UTM and tracking code
- required disclaimer present in Reddit and TikTok
- packaged `post.json` exactly matches the batch manifest entry
- no TODO, PLACEHOLDER, or lorem residue
- no publish metadata
- no compliance override

Machine-readable results are in `mechanical_verification.json`; raw router
checkpoints are in `batch_run.json`.
