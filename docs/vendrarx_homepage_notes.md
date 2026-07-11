# VendraRx Homepage Extraction Notes

Source: `https://vendrarx.com/`
Captured: 2026-07-11

Use these notes for Wave 1 provisional `brands/vendrarx.yaml` values and Wave 2
copy prompts. The homepage is the quiz/waitlist destination.

## CTA

- URL: `https://vendrarx.com/`
- Framing: founding-member / early-access quiz
- Primary action language can center on taking the short quiz or claiming a
  founding spot.

## Theme

Homepage CSS variables:

```css
--ink: #0E1410;
--forest: #1B2A24;
--forest-2: #243530;
--moss: #3F5A4E;
--cream: #F5F0E6;
--cream-2: #ECE5D5;
--paper: #FAF7EF;
--line: #1B2A2418;
--line-2: #1B2A2410;
--copper: #B8542C;
--copper-2: #D26A3F;
--mint: #C8D6CB;
--mint-3: #7E9C88;
--muted: #5C6A63;
--ok: #2E6B4F;
--ok-bg: #E4EDE6;
```

Suggested provisional brand YAML palette:

```yaml
palette:
  bg: "#F5F0E6"
  fg: "#0E1410"
  surface: "#FAF7EF"
  primary: "#1B2A24"
  secondary: "#3F5A4E"
  accent: "#B8542C"
  accent_2: "#D26A3F"
  muted: "#5C6A63"
```

Fonts loaded on homepage:

- Inter
- Inter Tight
- Instrument Serif
- JetBrains Mono

Suggested provisional font mapping:

```yaml
fonts:
  heading: "Inter Tight"
  body: "Inter"
  accent: "Instrument Serif"
  mono: "JetBrains Mono"
```

## Content And Voice Signals

Homepage positioning:

- physician-supervised peptide therapy
- telehealth assessment, prescription, and ongoing care
- 503A compounding pharmacy framework
- founding-member early access
- evidence-forward, compliance-aware, non-hype posture

Recurring proof points:

- US-licensed physician review
- clinician-owned protocols rather than generic subscriptions
- labs where appropriate
- cold-chain shipping
- Certificate of Analysis per batch
- no research-peptide sourcing
- no outcome guarantees

Suggested prompt posture:

- sound direct, careful, and regulatory-aware
- explain telehealth and compounding in plain language
- contrast licensed medical oversight with unregulated online research peptides
- avoid miracle, optimization-bro, and guaranteed-result language
- add disclaimers for compounded medications and physician suitability

## Account Handles

These remain placeholders:

```yaml
accounts:
  tiktok: "TODO"
  x: "TODO"
  reddit: "TODO"
```
