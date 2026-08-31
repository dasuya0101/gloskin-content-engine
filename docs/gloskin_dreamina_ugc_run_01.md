# GloSkin Dreamina UGC Run 01

This input is designed for the 10-second static-app-screen UGC video skill.
Run one screenshot per video. Do not combine multiple app screens in one run.

## Brand Pronunciation

Keep the visible and written brand name `GloSkin`. In every spoken line,
voice-over, and TTS instruction, spell it `Glow Skin`. Never ask the voice model
to pronounce the written spelling `GloSkin`.

## Recommended Primary Screenshot

`templates/today_routine.webp`

This is the safest first test because it demonstrates a real product workflow
without synthetic outcome framing or an unreviewed improvement timeline.

## Form Values

**App name**

GloSkin

**App core functions (1-2 sentences)**

GloSkin is an AI skincare app that gives users a Glo Score from a face scan,
builds a personalized routine from products they already own, answers skincare
questions through an AI Guru, scans product ingredients, and tracks progress.

**Target users**

Gen-Z and millennial skincare users who are tired of guessing which products to
use, what order to use them in, and whether their routine is working.

**Core selling points (1-3)**

1. Builds a clear skincare routine from products the user already owns.
2. Turns a face scan into a trackable 0-100 Glo Score.
3. Keeps routines, skin check-ins, and progress tracking in one app.

## Confirmable Storyboard

| Time | Picture and action | Spoken line |
| --- | --- | --- |
| 0:00-0:02 | Young adult skincare user in a normal bedroom or bathroom, holding a few products and looking mildly overwhelmed. Natural window light, handheld iPhone texture. | "My skincare shelf was chaos." |
| 0:02-0:07 | Camera flips to the iPhone showing `templates/today_routine.webp`. The screenshot remains completely static. A finger taps once on the Morning routine card and does not scroll. | "Glow Skin built a routine from products I already own." |
| 0:07-0:10 | Camera flips back to the same person. They set the products down and give a small relieved smile. | "Now I know what goes where. What's your Glo Score?" |

## Generation Prompt

Overall style: 10-second TikTok UGC, 9:16 vertical iPhone video, one continuous
handheld take, native amateur skincare recommendation, cozy real bedroom or
bathroom, warm natural window light, ordinary background furnishings, natural
skin texture, casual clothes, minimal makeup, genuine conversational delivery,
no beauty retouching, no commercial studio polish, no generated text overlays,
no captions, no watermark, no TikTok interface.

0:00-0:02 | A young adult skincare user stands beside a cluttered bathroom shelf
holding two skincare products. Handheld front camera, slight natural movement,
mildly overwhelmed expression. They say: "My skincare shelf was chaos."

0:02-0:07 | The camera naturally flips toward the iPhone screen showing the
GloSkin Today interface from <<<image_1>>>. The uploaded screenshot MUST REMAIN
COMPLETELY STATIC AND FIXED. NO SCROLLING, NO PANNING, NO MOVING OR SHIFTING OF
THE SCREEN CONTENT. A finger taps once on the Morning routine card; the finger
does NOT scroll and the screen does not transition. They say: "Glow Skin built a
routine from products I already own."

0:07-0:10 | The camera flips back to the same person. They set the products down
and give a small relieved smile. They say: "Now I know what goes where. What's
your Glo Score?" End on the natural handheld frame with no added graphics.

Use `templates/today_routine.webp` as `<<<image_1>>>`.

## Routine Page Variants

Use three separate shots with plain hard cuts. The phone must be out of frame in
the first and final shots. Begin the middle shot with one black iPhone already
in position and keep `templates/today_routine.webp` static and readable. Do not
tap, scroll, animate, rewrite, or transition the screen. Silence between lines
is preferable to rushed delivery.

### Variant 1 - Personal Routine

| Time | Picture and action | Spoken line |
| --- | --- | --- |
| 0:00-0:02 | Person looks confused by several products. Phone is out of frame. | "Skincare used to be so confusing." |
| 0:02-0:07 | Hard cut to the static Today routine screen already in position. Products are out of frame. | "Then Glow Skin built my personal routine." |
| 0:07-0:10 | Hard cut back to the person calmly putting products in order. | "Now I know exactly what goes where." |

### Variant 2 - Every Step in Order

| Time | Picture and action | Spoken line |
| --- | --- | --- |
| 0:00-0:02 | Person holds several products and looks unsure what to use first. Phone is out of frame. | "I had products, but no real routine." |
| 0:02-0:07 | Hard cut to the static Today routine screen already in position. Products are out of frame. | "Glow Skin put every step in order." |
| 0:07-0:10 | Hard cut back to the person separating morning and evening products. | "Morning and night finally make sense." |

### Variant 3 - The Order Was

| Time | Picture and action | Spoken line |
| --- | --- | --- |
| 0:00-0:03 | Person looks between several products, unsure which comes first. Phone is out of frame. | "My products weren't the problem. The order was." |
| 0:03-0:07 | Hard cut to the static Today routine screen already in position. Products are out of frame. | "Glow Skin built me a routine from what I already own." |
| 0:07-0:10 | Hard cut back to the person confidently arranging the products. | "Now I don't have to guess." |

## Scan Results Variant

Use `templates/scan_results.webp` as `<<<image_1>>>` only if this original app
promotional screenshot is cleared for reuse. Do not substitute a synthetic
before/after composite unless the final payload carries the required AIGC and
illustrative-result framing.

**Core selling point**

GloSkin turns a face scan into a 0-100 Glo Score that helps users track their
skin without guessing.

**Storyboard lines**

- 0:00-0:02: "I thought my routine was working."
- 0:02-0:07: "Glow Skin scanned my face and gave me one score to track."
- 0:07-0:10: "Now I can stop guessing. What's your Glo Score?"

The same static-screen rules apply. Do not claim a specific scan duration until
real end-to-end latency has been measured.

## Product Scan Match Variants

Use `templates/product_match_result.png` as `<<<image_1>>>`. This reference
already includes a complete black device frame. Show the complete uploaded
device as the physical phone; never place it inside a second generated phone.
The full reference must remain pixel-static: no scrolling, altered text,
animated score, selection highlight, or UI transition. The camera and hand may
move around the device, but the pixels inside the uploaded reference may not.
Use clean hard cuts between physical-product and phone-reference shots. Keep
the cleanser completely out of the phone shot and the phone completely out of
the cleanser shots; never use a continuous transition that can morph one into
the other.

The score is profile-fit guidance based on the user's skin profile from a face
scan or entry quiz. Never describe it as a safety rating, medical assessment,
proof of effectiveness, or guarantee that a product will work. Do not read the
detailed ingredient analysis aloud.

### Variant A - Scan Before You Buy

| Time | Picture and action | Spoken line |
| --- | --- | --- |
| 0:00-0:02 | Young adult holds a cleanser toward the camera. Phone is out of frame. End with the cleanser still visible. | "Scan it before you buy it." |
| 0:02-0:07 | Hard cut to the complete static Scan Match phone reference already in position. Cleanser is out of frame. No finger interaction. | "Glow Skin gives it a match score for you." |
| 0:07-0:10 | Hard cut back to the person holding the cleanser. Phone is out of frame. | "Check the match before checkout." |

### Variant B - Check the Viral Product

| Time | Picture and action | Spoken line |
| --- | --- | --- |
| 0:00-0:02 | Person holds up a popular cleanser with a skeptical expression. | "Does this viral cleanser fit my skin?" |
| 0:02-0:07 | Camera moves to the complete static Scan Match phone reference. No finger interaction. | "I scan it in Glow Skin for a fit score based on my profile." |
| 0:07-0:10 | Camera returns to the person, who nods and sets the product beside the phone. | "Now I check the match, not just the hype." |

### Variant C - Match Score

| Time | Picture and action | Spoken line |
| --- | --- | --- |
| 0:00-0:02 | Person looks between two cleansers on a bathroom counter, then holds up the phone. | "Check your products for your skin." |
| 0:02-0:07 | Camera moves to the complete static Scan Match phone reference. No finger interaction. | "Glow Skin turns my skin profile into a simple match score for each product." |
| 0:07-0:10 | Camera returns to the person choosing one product and relaxing. | "That makes the shelf way less confusing." |

## Do Not Use Yet

- `templates/guru_chat.webp`: contains an unreviewed "2-3 weeks" improvement
  statement and specific product advice.
- Synthetic Scan Results composites: require `is_aigc: true` metadata and clear
  illustrative-result framing in the final distribution package.
