# GloSkin Dreamina UGC Run 01

This input is designed for the 10-second static-app-screen UGC video skill.
Run one screenshot per video. Do not combine multiple app screens in one run.

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
| 0:02-0:07 | Camera flips to the iPhone showing `templates/today_routine.webp`. The screenshot remains completely static. A finger taps once on the Morning routine card and does not scroll. | "GloSkin built a routine from products I already own." |
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
does NOT scroll and the screen does not transition. They say: "GloSkin built a
routine from products I already own."

0:07-0:10 | The camera flips back to the same person. They set the products down
and give a small relieved smile. They say: "Now I know what goes where. What's
your Glo Score?" End on the natural handheld frame with no added graphics.

Use `templates/today_routine.webp` as `<<<image_1>>>`.

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
- 0:02-0:07: "GloSkin scanned my face and gave me one score to track."
- 0:07-0:10: "Now I can stop guessing. What's your Glo Score?"

The same static-screen rules apply. Do not claim a specific scan duration until
real end-to-end latency has been measured.

## Do Not Use Yet

- `templates/guru_chat.webp`: contains an unreviewed "2-3 weeks" improvement
  statement and specific product advice.
- Synthetic Scan Results composites: require `is_aigc: true` metadata and clear
  illustrative-result framing in the final distribution package.
