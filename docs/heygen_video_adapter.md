# HeyGen Talking-Head Adapter

## Current state

The dashboard can create local talking-head jobs from a roster character, approved
script, portrait source, voice ID, and optional existing HeyGen avatar ID. Jobs are
stored under `video_jobs/` and completed MP4s are downloaded under
`videos/<character_slug>/`. Both directories are local runtime data and gitignored.

Generation is a separate action from queueing. It never publishes a video.

The dashboard has two video modes:

- **Single clip** queues one selected character portrait and one editable script.
- **Batch before + after** defaults to three roster characters and previews two
  editable clips per character. Both `before.png` and `after.png` must exist for
  every selected character. The API validates the full set before writing any jobs.

Batch scripts support `{character}`, `{spec}`, `{hook}`, `{before_score}`, and
`{after_score}` placeholders. Preview expands these values and each resulting clip
can be edited independently before queueing.

## Authentication routes

### Subscription credits: Remote MCP/OAuth

Choose **Subscription / OAuth** in the dashboard. The job is queued with
`auth_mode: oauth_mcp` and `worker: heygen_mcp_oauth`. Process it from a Codex task
that has HeyGen Remote MCP connected. The local Flask server cannot access or store
the Codex OAuth session, and it will never fall back to API billing.

This workspace does not currently expose `mcp__heygen__*` tools, so OAuth jobs can
be queued but not submitted until the connection is added to Codex. Verify a future
connection with HeyGen's `get_current_user` MCP tool before running a job.

### API wallet: direct API key

Add these values to the local `.env` and restart `api_server.py`:

```dotenv
HEYGEN_API_KEY=<key from HeyGen API settings>
HEYGEN_VOICE_ID=<default voice ID>
```

Choose **API wallet**, queue the script, use **Test API connection**, then click
**Start render** on the queued job. API-key authentication is billed from HeyGen's
separate API wallet, not the consumer subscription.

## Direct API flow

1. The queue records the selected `before.png`, `after.png`, or `opening.png`.
2. If an existing `avatar_id` is supplied, the worker uses that avatar directly.
3. Otherwise, the worker uploads the local portrait and uses HeyGen's image-to-video
   request, avoiding an unnecessary avatar-creation call.
4. The worker creates a 1080p, 9:16 render with an idempotency key.
5. Polling is bounded to five minutes with exponential backoff and at most three
   retries per HTTP request. A still-running remote render remains `submitted`.
6. The worker downloads the completed MP4 immediately because HeyGen download URLs
   expire, then marks the local job `completed`.

## Job commands

```powershell
python video_queue.py list
python heygen_adapter.py status
python heygen_adapter.py process --job <job_id>
python heygen_adapter.py refresh --job <job_id>
```

## Character mapping

The adapter recognizes an optional mapping on each roster character:

```json
{
  "heygen": {
    "avatar_id": null,
    "voice_id": null,
    "source_asset": "after",
    "consent_status": null
  }
}
```

An existing avatar ID avoids re-uploading the portrait for every video. Keep a
separate mapping for each stable character look.

## Safety gates

- Queueing requires explicit character and voice consent confirmation.
- API rendering requires a second deliberate click and never starts on page load.
- OAuth jobs cannot be processed by the API-key worker.
- Scripts and generated videos require human review before any publishing step.
- Credentials are loaded from `.env` only and are never returned by the API.
- Workspace path checks prevent queued jobs from reading or writing outside the repo.
- Product-only `product_prop.png` is not available as a talking-head source.
- Screen-overlay or picture-in-picture segments are intentionally deferred until
  the paired before/after clip workflow has been reviewed with real HeyGen output.
