# VendraRx Reddit Longform Prompt

Write a Reddit-native post for a skeptical optimization/longevity audience.

Requirements:
- First line is the post title.
- Then one blank line.
- Then a 300-800 word markdown body.
- Voice is founder/operator POV: direct, concrete, and non-hype.
- Explain the operational/regulatory angle plainly: physician review, 503A
  compounding, suitability, labs/follow-up when appropriate.
- Avoid miracle claims, prescription guarantees, and treat/cure/prevent language.
- Mention that compounded medications are not FDA-approved when relevant.
- Emit the literal token <<CTA>> on its own line exactly once where the CTA belongs; never write CTA text or a URL.

Return only the finished Reddit markdown. No preamble.
