# GloSkin carousel hook review

Reviewed September 11, 2026 against the ten final batch briefs. The user subsequently authorized production. Edits have been rendered into separate revised packages for C1, C2, C5, C6, C7, C8, C9 and C10; original packages and publishing records remain intact. The calendar now points to these revisions for those eight slots.

During visual QA, C2 slide 3 was shortened to “Start your routine with your skin profile.” and C8 slide 3 to “Review your skin profile before a routine change.” C9's existing slide 3 was also shortened to “More products, or a clearer routine?” These changes prevent captions overlapping the phone image. The table below preserves the original editorial proposals for reference; the exported briefs contain the final wording.

The batch repeats the same scan/routine promise. Keep the clearest hooks and give the others more specific entry points. A copy change will require re-exporting the affected slides and matching slideshow video before using the revised package.

| Code / package | Existing hook | Recommendation | Reason |
| --- | --- | --- | --- |
| C1 / ec5cfa7516bd | What can an AI skin scan notice in one selfie? | **What does an AI skin scan show you?** | Shorter question, with a direct setup for the result screen. |
| C2 / 587a75f6746a | One selfie can show where your routine needs focus. | **Your next routine starts with a closer look at your skin.** | Avoid implying one selfie identifies everything missing from a routine. |
| C3 / 4241bf1d0228 | Your Glo Score starts with one face scan. | Keep | Clear feature introduction. |
| C4 / 59f195a8fe59 | Still guessing at skincare? Start with a scan. | Keep | Clear problem and next step. |
| C5 / 051fb505147f | A better routine starts with seeing your skin clearly. | **Building a routine? Start with your skin profile.** | More concrete action; less generic benefit language. |
| C6 / 78297f5f88ce | What is your skin trying to tell your routine? | **Does your skincare routine have a starting point?** | Replaces an awkward metaphor with a simple question. |
| C7 / 1cb2359b772b | Before you buy another serum, scan what your skin needs. | **Before another serum, take a look at your skin profile.** | Keeps the purchase context without suggesting a scan definitively establishes skin needs. |
| C8 / 50d5f8d99bae | Your shelf is full. Your routine still feels random. | Keep | Most concrete and relatable problem in this batch. |
| C9 / 623a548db7b0 | The skincare audit that starts with one front-facing selfie. | **Your skincare check-in starts with one selfie.** | Shorter; “check-in” fits the evidence shown better than a comprehensive audit. |
| C10 / 35e27c98315a | Stop building routines blind. Check your Glo Score first. | Keep | Direct CTA; space it away from C4's similar guessing angle. |

## Body copy that deserves an edit

The earlier automated compliance pass established that the packages passed the current rules. It did not validate every product claim. Reading the full briefs reveals these editorial issues:

| Package / slide | Existing copy | Proposed copy |
| --- | --- | --- |
| C1 / 2 | Scan your face. Get your Glo Score in seconds. | Scan your face. See your Glo Score. |
| C1 / 3 | Know what's working — and what isn't. | Compare your Glo Score across check-ins. |
| C1 / 4 | Progress you can actually measure. | Keep track of your Glo Score over time. |
| C2 / 3 | See what your current routine is missing. | Use your skin profile as a starting point for your routine. |
| C5 / 3 | Stop guessing what your skin needs. | Take a closer look at your skin profile. |
| C6 / 3 | Find the gaps in your current routine. | Bring your skin profile into your routine planning. |
| C8 / 3 | Know what to keep — and what to rethink. | Review your skin profile before your next routine change. |
| C10 / 3 | Get a clearer view of what your routine is doing. | Review your Glo Score alongside your routine. |

These edits keep the existing scan/progress story. Product-selection promises belong in the new product-match carousel, backed by its actual result screen. Keep illustrative labels visible on synthetic examples; a score comparison does not establish that a product caused an improvement.

## Release-screen follow-up

The existing copy guide describes ingredient scanning but does not yet list product profile-fit scoring. The saved `product_match_result.png` visibly shows “PROFILE FIT,” a 70/100 example and “Great match.” The Dreamina brief describes profile fit based on a face scan or entry quiz. The user reports the feature shipped in the latest release; the saved screenshot has not been verified against that release.

Use “product match score” in explanatory copy and match the exact label in the new screenshots when rendering. Keep Glo Score (skin check-in) and product match/profile-fit score distinct. Do not silently update global generation prompts or current ready packages as part of this review.
