# Compound Claim Packs

Claim packs are human-authored ground truth. Put one YAML file per compound in
this directory. Generation and compliance load a pack only when the compound or
one of its aliases appears in the angle.

```yaml
compound: Example compound
aliases: [EXAMPLE]
evidence_claims:
  - "An exact, verified evidence statement."
mechanism_claims:
  - "An exact, verified mechanism statement."
regulatory_claims:
  - "An exact, verified regulatory statement."
disallowed_claims:
  - "A claim that must always be blocked."
regulatory_hold:
  - claim_ref: "The compound is eligible for 503A compounding."
    review_after: 2026-07-25
    status: held
    note: "Re-verify after the named regulatory event."
caveats:
  - "A mandatory framing constraint for approved claims."
```

Approved claims are exact phrases, not topics. Missing packs deliberately grant
no permission to make specific evidence, mechanism, or regulatory assertions.

`regulatory_hold` never expires automatically. A human must set `status` to
`cleared` and add `cleared_at: YYYY-MM-DD`. The clearance date must be later
than `review_after`, and it must have arrived, before the claim can proceed to
normal checks. Until then, the referenced claim and any assertion that the
compound is eligible for 503A compounding hard-block before LLM judgment.

`caveats` constrain how approved claims are framed. They are injected into both
generation and compliance judgment; deterministic caveat patterns also block
before the LLM where possible.
