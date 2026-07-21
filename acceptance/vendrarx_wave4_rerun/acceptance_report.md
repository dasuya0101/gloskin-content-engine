# Wave 4 Acceptance Report

- Input: `angles/vendrarx_wave4_rerun.yaml`
- Scope: real text generation and compliance only; no publishing or overrides
- Brand status: `pre_launch`

## Distribution

- Wave 3 subset: 5 pass / 1 needs_review / 0 fail
- Wave 4 final: 2 pass / 4 needs_review / 0 fail
- Rewrites may turn an initial deterministic block into a final pass; initial violations remain in each format result.

## Deterministic Regression

The final Layer 1 rules were run against the exact Wave 3 outputs for these six angles with no claim packs. Every format now flags at least one specific claim:

| Angle | Reddit | X | TikTok |
|---:|---:|---:|---:|
| 6 | 7 | 1 | 2 |
| 7 | 5 | 2 | 4 |
| 8 | 8 | 6 | 2 |
| 10 | 8 | 3 | 4 |
| 11 | 9 | 6 | 5 |
| 12 | 5 | 1 | 3 |

**Result: 18/18 historical format files flag deterministically.**

## Rewrite And Mechanical Checks

- `rewrite_render_error`: 0
- Angle 11 produced an under-length first rewrite (269 words) and regenerated successfully; a later final-code re-lint did the same at 277 words. Neither invalid draft was written as accepted output.
- Final Reddit body word counts: 6=369, 7=442, 8=326, 10=333, 11=370, 12=451
- All tweets are <=275 characters; all TikTok sections and canonical CTA URLs are present.
- All `publish` records remain empty. No compliance override was applied.

## Final Verdicts

### Angle 6: `needs_review`

NAD+ precursors vs injections — what human trials actually show

- `reddit_longform` / `unsourced_mechanism`: "The conversation around NAD+ supplementation often includes oral precursors like NMN and NR alongside injectable NAD+."
- `reddit_longform` / `unsourced_mechanism`: "For NMN, the evidence in humans is sparse and mostly preliminary, with much of the available information coming from early-stage research that has not yet established clear effects in people."
- `reddit_longform` / `unsourced_mechanism`: "Injectable NAD+ avoids some questions related to oral absorption, but it introduces other unknowns."
- `x_thread` / `unverifiable_operational_claim`: "Compounded NAD+ therapies are not FDA-approved medications. Suitability is determined case-by-case by licensed clinicians. We avoid promising outcomes or guaranteed prescriptions, focusing instead on responsible, evidence-informed care."

### Angle 7: `pass`

Sermorelin and secretagogues vs direct GH — why the category exists

- No final violations after rewrite.

### Angle 8: `needs_review`

GLP-1s beyond weight loss — cardiovascular + addiction-signal research, framed cautiously

- `reddit_longform` / `unsourced_mechanism`: "GLP-1 receptor agonists have established roles in weight management, but there are also early-stage signals in other areas that deserve cautious attention."
- `x_thread` / `unsourced_mechanism`: "{\"tweets\": [\"GLP-1 agonists like semaglutide are primarily known for their role in weight management."
- `x_thread` / `unsourced_mechanism`: "The research landscape includes various exploratory areas, but current evidence remains preliminary and should be interpreted with caution.\", \"Some clinical reports mention changes observed during GLP-1 agonist use, but the underlying biological processes are not well understood and need more investigation.\", \"Early human data suggest possible effects on behavior, though these findings are preliminary and not definitive.\", \"It’s important to note that much of the evidence comes from studies not designed to assess these specific outcomes, and animal research may not reliably translate to humans.\", \"We’re building a practice where US-licensed physicians asynchronously review cases, prescribing 503A-compounded peptides with labs and follow-up when clinically appropriate—no research peptides or refill mills.\", \"Take the 60-second quiz: https://vendrarx.com/?utm_source=twitter&utm_campaign=vendra_20260721132022_01_01\"]}"

### Angle 10: `needs_review`

How GLP-1 agonists actually work — satiety signaling + gastric emptying, plain English

- `reddit_longform` / `unsourced_mechanism`: "There’s been a lot of discussion lately about GLP-1 therapies like semaglutide and tirzepatide, often accompanied by hype or oversimplified takes."
- `x_thread` / `unsourced_mechanism`: "{\"tweets\": [\"GLP-1 agonists like semaglutide are widely discussed now — understanding their clinical use requires careful physician oversight and patient safety measures."

### Angle 11: `needs_review`

Why peptides are injected — oral bioavailability, SNAC tech, what that implies about peptide pills

- `reddit_longform` / `unsourced_mechanism`: "Because of these factors, many oral peptide products have limited evidence supporting their absorption and systemic availability in humans."
- `reddit_longform` / `unsourced_mechanism`: "Without proven delivery technologies or absorption enhancers, oral peptides are unlikely to reach effective levels in the bloodstream."
- `reddit_longform` / `unsourced_mechanism`: "- Does the product use validated methods to enhance absorption or protect the peptide through digestion?"
- `reddit_longform` / `unsourced_mechanism`: "Without such methods, absorption is probably minimal."
- `reddit_longform` / `unsourced_mechanism`: "Low-dose oral peptides without absorption support are unlikely to have systemic effects."
- `x_thread` / `unsourced_mechanism`: "{\"tweets\": [\"Peptides are typically injected because delivering them orally presents challenges that can affect their clinical use compared to injections.\", \"Peptides taken orally may face barriers that influence how much active compound reaches systemic circulation, which can impact their overall effectiveness.\", \"Various approaches exist to improve oral peptide formulations, but their success can vary depending on the specific peptide and how it’s prepared.\", \"Despite formulation advances, oral peptides often encounter variability in absorption and metabolism that can influence the amount of active peptide available.\", \"While some peptides might be suitable for oral delivery, many require injection to support consistent clinical use, reflecting the complexity of peptide therapies.\", \"We're building a practice where US-licensed clinicians review each case to determine appropriate peptide options and delivery methods."

### Angle 12: `pass`

GHK-Cu topical vs injected — where evidence exists and where it's thin

- No final violations after rewrite.

## Operational False-Positive Audit

- Cleared: explicit design/future framing such as ?we?re designing,? ?our model,? and ?will?; generic clinician-oversight advice; configured disclaimer text and substrings.
- Held: angle 6 X states that suitability is currently determined case-by-case by licensed clinicians, which is a present-tense pre-launch care assertion.

## Selftest

- `python compliance_lint.py --selftest`: 28/28 cases pass. Full output: `acceptance/vendrarx_wave4_rerun/selftest.txt`.
- Coverage includes all 4A pattern families, exact/nonmember/disallowed claim-pack cases, and pre-launch design/present plus live present-tense cases.
