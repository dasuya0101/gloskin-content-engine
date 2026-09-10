# GloSkin native TikTok launch

## Launch sequence and boundaries

Publish **5-10 distinct flagship carousel posts manually** while this integration
is developed. Review every slide, use its packaged caption/tracking code, enable
TikTok's AI-generated label and own-brand commercial disclosure, and record the
URL with the registry account ID. Keep the existing compliance, regulatory,
disclosure, dimensions, and duplicate gates authoritative. No compliance override
is accepted by native publishing.

Start with one GloSkin flagship account. Only after reviewing its launch may an
operator separately approve at most one clearly disclosed **GloSkin-owned** UGC
or virtual-creator test account. The existing `volume_01` placeholder is retained
for that possible test; it is not permission to operate an account farm. Never
send identical creative to multiple TikTok accounts. Native attempts additionally
block reuse of the same creative on the same account.

There is no device/IP folklore, evasion, proxies, emulators, fake engagement, or
account warming automation in this plan. Operators register accounts manually.
Automation is limited to publishing and publishing-status checks. It never
browses feeds, views, likes, follows, saves, comments, or performs other engagement.
VendraRx is paused and outside this integration. Its records and configuration
are not targets of the native adapter.

## Approval blocker to resolve first

TikTok's [Content Sharing Guidelines](https://developers.tiktok.com/docs/en/content-sharing-guidelines)
explicitly list a utility limited to accounts managed by its developer/team as
an unacceptable Direct Post use case. This owned-account tool must therefore
remain manual unless TikTok explicitly approves this intended use. Technical
readiness, a registered app, and a private account do not establish that approval.
Do not falsely attest to it or restructure accounts to evade review. Store the
actual decision reference in `native_tiktok.intended_use_approval_reference`;
`intended_use_approved` defaults to false. TikTok also restricts unaudited direct
posts to private visibility; this implementation conservatively requires explicit
developer approval even for its validation path.

## Checkpoints (all false/manual by default)

1. **Manual:** complete and review 5-10 distinct flagship posts; retain URLs and
   tracking codes. Set `manual_launch_complete` only after that review.
2. **Draft/private validation:** after TikTok authorization and hosting setup,
   approve `private_validation_approved` to authorize a validation attempt, set
   the account mode to `draft` or `private`, and enable `submission_enabled`.
   `draft` uses `MEDIA_UPLOAD` and delivers an inbox notification; it does not
   publish automatically. The operator must finish in TikTok. `private` uses
   `DIRECT_POST` with an explicitly chosen `SELF_ONLY` privacy setting. Preview,
   click approval for exactly one post, then submit it with the explicit CLI flag.
   Keep `scheduler_enabled: false` for this checkpoint. Review the actual TikTok
   rendering, slide order, disclosures, and status/URL write-back manually.
3. **Direct:** record the successful validation and a separate decision to permit
   direct posting, then set `direct_checkpoint_approved: true` and account mode
   `direct`. Every post still needs its own dashboard approval. First approve and
   submit one direct post; enable `scheduler_enabled` separately only after review.

Native scheduling caps every account at **one post per UTC calendar day**, or a
lower configured cap, with the existing deterministic 7-23 minute jitter. This
does not change the old vendor caps or VendraRx behavior. The dashboard shows the
actual jittered schedule before consent. Execution also checks the actual UTC
day. Jobs more than one hour late stop for operator review. Cancel an unsubmitted
schedule in the dashboard before editing/rescheduling it. Cancellation retains
the old consent receipt; a new preview/click is required.

## Request and consent contract

The [Photo API reference](https://developers.tiktok.com/docs/en/content-posting-api-reference-photo-post)
(updated August 24, 2026) specifies `/v2/post/publish/content/init/`, up to 35
ordered URLs, a zero-based cover index, 90 UTF-16 units for title, and 4,000 for
description. `is_aigc` is **top-level** for photos. Direct requests send
`post_info.brand_organic_toggle=true` and `brand_content_toggle=false` for the
account owner's GloSkin promotion. Draft mode does not support those commercial
or interaction switches; the dashboard requires acknowledgment to enable the
own-brand disclosure in TikTok's editing flow before posting. It carries the
caption/disclosures and top-level AIGC flag into the draft request. A draft's
selected privacy is recorded as operator intent, not misrepresented as enforced
by the upload API. `DIRECT_POST` follows the official request example; the prose
table inconsistently renders it with a space.

The [creator-info endpoint](https://developers.tiktok.com/docs/en/content-posting-api-reference-query-creator-info)
is queried when opening the composer, rendering the final preview, approving,
and executing. Nickname and username are displayed, privacy has no default, and
comments are unchecked and disabled when disallowed by the creator. The endpoint
documents `video.publish`; consequently this implementation requires that scope
for **both** preview modes, and additionally `video.upload` to submit a draft.
An upload-only token fails closed. Do not bypass creator-info to work around an
ungranted scope; clarify this requirement with TikTok during approval.

Consent is a server-side immutable receipt in
`workspace_data/tiktok/publishing.sqlite3`. A digest binds post ID, tracking code,
pinned account identity, handle/entity, creator choices, original creative hash,
converted image hashes/order/URLs, title, full caption, all settings, rollout mode,
and scheduled time. A 15-minute preview ticket belongs to the authenticated
operator. Every image must load, and the real operator must check preview
confirmation and express consent and click **Approve & Schedule**. Edits invalidate
consent. These booleans are internal evidence, not invented TikTok request fields.
CLI dry runs and creator sync never grant consent. The CLI consent operation
reads a receipt created by the dashboard; it cannot fabricate one.

## Exact setup still required from the operator

Nothing below was provisioned or authorized by this implementation.

1. Obtain TikTok's decision approving the actual intended use, register the app,
   configure Login Kit and Content Posting API, and obtain authorization for
   `video.publish` and (if using drafts) `video.upload`. Complete the applicable
   developer/audit requirements. Retain evidence before setting approval flags.
2. Fill only the real GloSkin flagship registry handle, verified owning entity,
   and account verification status. Preserve TODOs until facts are known. Pin
   the app-scoped **OAuth `open_id`**, not a username or numeric profile ID, in
   `GLOSKIN_TIKTOK_FLAGSHIP_OPEN_ID`. Obtain/verify that identifier through your
   approved TikTok developer authorization setup before connecting here; this
   callback refuses trust-on-first-use identity assignment. The optional test
   account has its own `GLOSKIN_TIKTOK_VOLUME_01_OPEN_ID` and token record.
3. Create an R2 bucket and scoped object-write credentials. Attach a public custom
   DNS domain with valid TLS and unrestricted public reads. Verify domain or URL
   prefix ownership in the TikTok developer portal. Configure the identical
   verified prefix (trailing slash) in YAML and a public base within it in env.
   For `https://media.your-domain/.../`, the base path maps directly to the R2
   object-key prefix; do not add a CDN path rewrite. R2's S3 API endpoint is used
   only for writes; it is never supplied to TikTok.
4. Export the following environment values into the dashboard and worker process
   environments. `.env.example` lists names; the application does not auto-load
   `.env`. Do not paste values into tasks, terminal history, logs, or version control.

| Environment | Required value |
| --- | --- |
| `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET` | Actual app credentials |
| `TIKTOK_TOKEN_ENCRYPTION_KEY` | Privately generated Fernet key; keep separately from database backups |
| `TIKTOK_REDIRECT_URI` | Exact registered `https://<dashboard-host>/api/tiktok/oauth/callback` |
| `GLOSKIN_TIKTOK_FLAGSHIP_OPEN_ID` | Independently verified app-scoped account identity |
| `GLOSKIN_TIKTOK_VOLUME_01_OPEN_ID` | Optional approved test account identity |
| `TIKTOK_OPERATOR_TOKEN` | Independently generated random secret, at least 32 characters |
| `TIKTOK_OPERATOR_ID` | Actual operator name/identifier used in audit receipts |
| `TIKTOK_DASHBOARD_ORIGIN` | Exact browser origin, including local port if applicable |
| `TIKTOK_ALLOW_SUBMISSIONS` | Leave `false`; set exactly `true` only for an approved run |
| `TIKTOK_MEDIA_PUBLIC_BASE` | Public custom-domain base URL ending `/` |
| `TIKTOK_R2_ENDPOINT` | `https://<actual-r2-account-id>.r2.cloudflarestorage.com` |
| `TIKTOK_R2_BUCKET` | Actual bucket name |
| `TIKTOK_R2_ACCESS_KEY_ID`, `TIKTOK_R2_SECRET_ACCESS_KEY` | Scoped R2 credentials |

5. Deploy the dashboard to a VPS with HTTPS. The
   [Login Kit Web redirect rules](https://developers.tiktok.com/docs/en/login-kit-web)
   require an absolute, registered, static HTTPS callback without query/fragment.
   This implementation rejects HTTP localhost OAuth; it supports local preview
   with `http://127.0.0.1:5055` as the configured dashboard origin. Start OAuth
   from the deployed HTTPS host, using the Connect control. The callback checks
   a random one-time state, browser-bound Secure/HttpOnly/SameSite cookie, TTL,
   exact callback, and pinned identity. No account has been connected here.
6. The token store uses Fernet encryption and stores rotated refresh tokens as
   documented in [Token Management](https://developers.tiktok.com/docs/en/oauth-user-access-token-management).
   Restrict the runtime directory to the service user (0700/0600 on Linux;
   equivalent NTFS ACL on Windows). Back up the encrypted database and keep the
   encryption key in a separate secret manager. If refresh outcome is uncertain,
   reconnect explicitly; authorization-code/refresh exchanges are not replayed.
7. Use a production WSGI server bound to loopback behind your HTTPS reverse proxy.
   Forward the original host and scheme through a trusted proxy setup (e.g. a
   deployment wrapper using Werkzeug `ProxyFix` for exactly one trusted proxy),
   and prevent direct access to its socket. Protect the **whole existing dashboard**
   with operator authentication at the proxy; its legacy generation/files routes
   were designed for local use. Native routes additionally require their operator
   bearer token and same-origin JSON mutations. Disable proxy/WSGI query logging
   on the OAuth callback, redact Authorization headers, and disable debug logging
   in HTTP/SDK libraries. Werkzeug callback query logging is redacted by the code.
8. Use one durable workspace on one host and one scheduler process. Run from the
   repository root so packaged paths resolve. The existing `posts.json` manifest
   is not a multi-host datastore. Manifest mutations now use a process lock and
   atomic replacement so the dashboard and worker cannot overwrite each other's
   updates. The SQLite journal remains the native source of truth. Do not
   expose workspace_data or secrets as static files. Set disk backups/monitoring.
9. Run config validation, sync creator info, inspect the fixture-only dry-run
   request, then use the dashboard's TikTok button on a GloSkin post. Fill settings,
   render every JPEG preview, inspect captions/disclosures, and click approval.
   Only then use an explicitly allowed submission command or enable the worker.

## Commands

All commands run from the repository root; `--posts <path>` precedes the subcommand.
`--registry <path>` optionally selects a registry without altering committed TODOs.

```text
python publish.py tiktok-status
python publish.py tiktok-config
python publish.py tiktok-creator-sync --account-id gloskin_tiktok_flagship
python publish.py tiktok-dry-run --post-id <id> --account-id gloskin_tiktok_flagship --settings <settings.json> --creator-fixture <creator-info.json> --scheduled-for <ISO-time-with-offset>
python publish.py tiktok-consent --consent-id <dashboard-receipt-id>
python publish.py tiktok-draft --attempt-id <approved-id> --allow-network-writes
python publish.py tiktok-direct --attempt-id <approved-id> --allow-network-writes
python publish.py tiktok-refresh --attempt-id <approved-id>
python publish.py tiktok-worker --limit 10 --allow-network-writes
```

The last four commands are operating instructions for a future approved rollout;
they were not run against TikTok. `tiktok-direct` also handles private validation.
Scheduling itself happens at the dashboard approval click. Invoke the bounded
worker periodically (for example once per minute via a VPS systemd timer); it
exits after at most the selected number of eligible jobs, never loops indefinitely.
Polling is spaced at least 60 seconds by the worker. The CLI can also refresh an
individual publish ID without enabling submissions. There are no webhook routes.

Example settings structure (fill title/privacy deliberately):

```json
{"title":"", "privacy_level":"SELF_ONLY", "allow_comments":false,
 "auto_add_music":false, "cover_index":0, "draft_disclosure_acknowledged":false}
```

## Hosting, retries, status, and retention

The [Media Transfer Guide](https://developers.tiktok.com/docs/en/content-posting-api-media-transfer-guide)
lists JPEG/WebP and a 20 MB image limit. Native preparation converts packaged PNGs
to immutable 1080x1350 JPEG derivatives **before** preview, preserving all pixels'
layout and disclosure labels. Source packages remain untouched. The R2 host checks
content type, dimensions, extension, size, ordered hashes, HTTPS/prefix, and a
public HEAD response without redirects. Upload uses hash-based keys, so bounded
R2 retries overwrite the same immutable content. Local paths never enter a
TikTok request. “Maximum 1080p” in the guide is imprecise for portrait images;
the existing 1080x1350 gate remains unchanged and requires real approved validation.

The journal reserves `sha256(platform + tracking_code)` before content init.
SQLite transactions serialize native consent/claims across processes. Read-only
creator/status operations use a 30-second timeout and at most three attempts;
OAuth/content-init calls use one attempt. Init has no documented idempotency key
or tracking-code lookup, so **exactly-once delivery cannot be guaranteed**. A timeout,
crash after claiming, malformed response, or rejected init never causes an automatic
second init. Keep the attempt reserved and reconcile with TikTok/operator evidence.
Do not delete its journal entry, change the tracking code, or rerun it as new content.
Pre-init hosting failures also stop for review. Unclaimed schedules alone may be
cancelled and approved again.

The [Status API](https://developers.tiktok.com/docs/en/content-posting-api-reference-get-video-status)
drives `packaged -> queued -> posted/failed`. `SEND_TO_USER_INBOX` remains queued;
only `PUBLISH_COMPLETE` marks posted. The API's misspelled
`publicaly_available_post_id` list is preserved as platform IDs. It can be empty
for private or moderated posts, so the publish ID is retained and the public URL
stays null. When an ID is available the code constructs a standard photo permalink
and labels its source; the status endpoint does not return a canonical share URL.
Verify it during validation. Repeated status refreshes can obtain IDs after
moderation. Errors stored in the manifest are redacted or allowlisted reason codes.

No automatic media deletion or bucket lifecycle is configured. Retain every
referenced object while scheduled, uploading, uncertain, pending in the inbox,
or awaiting moderation, and for **at least 30 days after terminal completion**.
Pending drafts may outlive that interval. Operators may remove only unreferenced,
terminal, expired objects after checking the journal and backups. Retain consent
receipts, tracking reservations, and publishing outcomes for the account's audit
history; deleting them would weaken duplicate/retry protection. Local converted
previews follow the same rule. Cache headers use 30 days; they are not a deletion
schedule. Restrict R2 credentials to the publishing bucket and configure billing
alerts separately.

## Verification performed in this task

All write-path tests use injected fake TikTok/OAuth transports and fake R2 clients.
The existing full unittest suite plus native gate, schema, consent, account,
privacy, cadence, duplicate, status, encryption, retry, URL/MIME and dashboard
authentication tests run without connecting a real account or submitting content.
Real platform rendering, app eligibility, DNS verification, and canonical public
URL behavior remain operator/developer approval checks.
