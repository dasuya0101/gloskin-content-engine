# Local Codex Image Queue

The dashboard's default image source is `codex_local`. It writes complete jobs
under `image_jobs/queued/`; it does not call the OpenAI Platform API.

Use this task prompt in Codex or a Codex automation:

```text
Process every queued image job in this repo according to
docs/codex_image_queue.md. Use built-in image generation only, save each final
asset to its job target_path, mark the job complete, and stop when the queue is
empty. Never use OPENAI_API_KEY and never overwrite an existing target.
```

## Worker protocol

1. List work with `python image_queue.py list --status queued`.
2. Claim the oldest job with `python image_queue.py claim`, or claim a specific
   one with `python image_queue.py claim --job <job_id>`.
3. Process `targets` in their listed order. This matters because later edits can
   reference a `before.png` generated earlier in the same job.
4. For a `generate` target, call Codex built-in image generation with the exact
   job prompt.
5. For an `edit` target, inspect `reference_path`, then use it as the edit target
   with the exact job prompt. Preserve identity and all invariants in the prompt.
6. Copy the selected built-in result from Codex's generated-images folder to the
   repo-relative `target_path`. Never replace a target that already exists.
7. Inspect the saved image for subject, identity, framing, and obvious artifacts.
8. After every target exists, run `python image_queue.py complete --job <job_id>`.
9. On an unrecoverable error, run
   `python image_queue.py fail --job <job_id> --reason "<short reason>"`.

The dashboard polls job state and refreshes character and project-variant
previews after completion.
Queued work is local runtime state and is intentionally excluded from git.

`codex_local` is a stable manual or Codex-automation worker path, but it is not
an in-process API: the Flask dashboard cannot invoke the signed-in Codex image
tool itself. Use a direct provider when a batch must run unattended without a
Codex task claiming the queue.

## Folder layout

```text
image_jobs/
  queued/
  processing/
  completed/
  failed/

assets/<character-slug>/
  before.png
  opening.png
  scan.png
  after.png
  product_prop.png

workspace_data/image_variants/<brand>/<project>/<variant-id>/
  variant.json
  prompt_config.json
```

Canonical-character jobs generate only absent assets. Project variants inherit
unselected source images and queue the checked image slots plus any missing core
assets. `opening.png` and `product_prop.png` are included only when the
corresponding Prompt Lab styles request them. Variant jobs record their project,
source asset slug, exact prompt snapshot, and target order.
