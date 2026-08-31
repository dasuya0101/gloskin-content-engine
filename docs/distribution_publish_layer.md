# Distribution And Publish Layer

The current production path stops at manual upload. This layer prepares the
same slideshow package for TikTok photo carousel and Instagram carousel, tracks
each destination independently, and exposes a dry-run adapter boundary for the
eventual audited posting vendor. It does not submit network requests.

## Current State

- `distribution_accounts.yaml` is the committed account registry. It contains
  handles, roles, entities, verification state, caps, and environment-variable
  names. It never contains tokens.
- `publisher_vendor.py` assembles a vendor-neutral carousel request. Its
  `submit()` method is intentionally disabled.
- `publish.py vendor-dry-run` runs compliance, disclosure, account,
  regulatory-hold, carousel, cap, and duplicate-creative gates, then records
  that account destination as `packaged` without submitting it.
- Instagram receives 1080x1350 JPEG assets. TikTok receives its own 1080x1350
  carousel asset folder from the same creative package.
- A post can carry separate TikTok and Instagram distribution records through
  `packaged -> queued -> posted -> metrics_matched`.
- CSV metrics import moves the matching posted destination to
  `metrics_matched` when a platform URL is available.

## Account Registry

Fill each account row with:

- `platform`: `tiktok` or `instagram`
- `handle`: the actual public handle
- `role`: `flagship` or `volume`
- `owning_entity`: the verified legal entity
- `verification_status`: `unverified`, `pending`, `verified`, or `rejected`
- `vendor_account_ref_env`: the environment variable containing the vendor's
  account reference
- `enabled`: keep false until the account is intentionally available to the
  adapter
- `test_account`: true only for the private/test destination used at Checkpoint B

The default caps are 20 TikTok posts and 50 Instagram posts per account per day.
Scheduling adds deterministic account-specific jitter so multiple accounts do
not burst at the same minute.

## Hard Gates

Vendor automation requires all of the following:

1. Compliance status is exactly `pass`; overrides are not accepted.
2. Regulatory-hold or hard-block violations are absent.
3. Synthetic/composited media carries `is_aigc: true` plus the configured
   caption disclosure.
4. Every slide has the small disclosure footer. Every face/composite slide also
   has a small `REFERENCE`, `EXAMPLE`, or `ILLUSTRATIVE` corner chip.
5. Disclosure language is absent from headline copy. Synthetic creative copy
   cannot use real-user framing, before/after labels, named-person framing, or
   day/week timelines.
6. The account belongs to the post's brand, is enabled, has a real handle and
   owning entity, has its vendor reference configured, and is verified.
7. Every slide is 1080x1350. Instagram slides are JPEG.
8. The creative fingerprint is not already queued to another account on the
   same platform.

## Operator Sequence

```text
Checkpoint A: review packages and post manually
    -> import 48-72h metrics and mark winners
    -> choose/fund one audited posting vendor
    -> configure one private/test account
Checkpoint B: inspect one vendor dry run, then one private/test post
    -> review the platform-rendered carousel
Checkpoint C: approve exactly one live automatic post
    -> verify URL write-back and metrics matching
    -> separately enable scheduling
```

Useful commands:

```text
python publish.py accounts
python publish.py vendor-status
python publish.py vendor-dry-run --post-id <post_id> --platform instagram --account-id <account_id>
```

The vendor-specific HTTP endpoint, authentication headers, media-upload method,
and AIGC field name must be implemented only after the vendor is selected. Native
TikTok and Instagram adapters, Facebook, Spark Ads, comments, DMs, and direct
analytics pulls remain outside v1.

The separate `gloskin.app/go/<account>` attribution routes belong in the app/site
repository. They are not implemented here because this repository must not move
or modify the App Review landing page.
