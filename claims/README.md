# Compound Claim Packs

Claim packs are human-authored ground truth. Put one YAML file per compound in
this directory. Generation and compliance load a pack only when the compound or
one of its aliases appears in the angle.

```yaml
compound: Example compound
aliases: [EXAMPLE]
lanes: [cosmetic_topical, compounded_injectable]
evidence_claims:
  - claim: "An exact, verified evidence statement."
    lanes: [cosmetic_topical]
mechanism_claims:
  - claim: "An exact, verified mechanism statement."
    lanes: [compounded_injectable]
regulatory_facts:
  - claim: "An exact, verified regulatory statement."
    lanes: [compounded_injectable]
disallowed_claims:
  - "A claim that must always be blocked."
regulatory_hold:
  - claim_ref: "The compound is eligible for 503A compounding."
    lanes: [compounded_injectable]
    review_after: null
    status: held
    note: "No automatic review event; human re-verification is required."
caveats:
  - "A mandatory framing constraint for approved claims."
```

Approved claims are exact phrases, not topics. Missing packs deliberately grant
no permission to make specific evidence, mechanism, or regulatory assertions.

`regulatory_hold` never expires automatically. A human must set `status` to
`cleared` and add `cleared_at: YYYY-MM-DD`. When `review_after` is a date, the
clearance must be later than that date and must have arrived. `review_after:
null` is valid and means the hold is permanent until that human clearance is
recorded; no date logic can age it out. Until then, the referenced claim and any
held availability or 503A-eligibility assertion hard-block before LLM judgment.

Each brand declares `claim_lanes` in `brands/<brand>.yaml`. In lane-aware packs,
every evidence, mechanism, and regulatory entry declares one or more lanes. An
exact claim used by a brand outside those lanes hard-blocks as `claim_lane`; it
cannot be cleared by the semantic judge. Legacy string entries remain readable
for existing fixtures, but new route-dependent packs should use structured
`claim` plus `lanes` entries. `regulatory_claims` remains accepted as a legacy
alias for `regulatory_facts`.

`caveats` constrain how approved claims are framed. They are injected into both
generation and compliance judgment; deterministic caveat patterns also block
before the LLM where possible.
