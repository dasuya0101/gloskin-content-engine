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
```

Approved claims are exact phrases, not topics. Missing packs deliberately grant
no permission to make specific evidence, mechanism, or regulatory assertions.
