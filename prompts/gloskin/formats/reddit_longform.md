# GloSkin Reddit Longform Prompt

Write a Reddit-native skincare post for GloSkin.

Requirements:
- First line is the post title.
- Then one blank line.
- Then a 300-800 word markdown body.
- Voice is helpful, self-aware, skincare-native, and not clinical.
- Frame GloSkin as an AI skincare app that helps users audit routines, scan
  products, track progress, and stop guessing.
- Keep claims cosmetic/educational. Do not promise to cure acne or medical
  conditions.
- Emit the literal token <<CTA>> on its own line exactly once where the CTA belongs; never write CTA text or a URL.

Return only the finished Reddit markdown. No preamble.
