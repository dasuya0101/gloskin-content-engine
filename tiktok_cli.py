"""CLI boundary: consent is inspected here, created only by a dashboard click."""
import json
from pathlib import Path

import distribution
from publisher_tiktok import NativeTikTok, PhotoSettings, TikTokError


def add_commands(sub):
    for name in ("tiktok-status", "tiktok-config", "tiktok-dry-run", "tiktok-creator-sync",
                 "tiktok-consent", "tiktok-draft", "tiktok-direct", "tiktok-refresh", "tiktok-worker"):
        parser = sub.add_parser(name)
        parser.add_argument("--registry", default=str(distribution.DEFAULT_REGISTRY_PATH))
        if name == "tiktok-dry-run":
            parser.add_argument("--post-id", required=True)
            parser.add_argument("--account-id", required=True)
            parser.add_argument("--settings", required=True, help="local JSON photo settings file")
            parser.add_argument("--creator-fixture", required=True, help="saved creator_info JSON; no API calls")
            parser.add_argument("--scheduled-for", required=True)
        if name == "tiktok-creator-sync":
            parser.add_argument("--account-id", required=True)
        if name == "tiktok-consent":
            parser.add_argument("--consent-id", required=True, help="inspect the dashboard's persisted consent receipt")
        if name in {"tiktok-draft", "tiktok-direct", "tiktok-refresh"}:
            parser.add_argument("--attempt-id", required=True)
        if name in {"tiktok-draft", "tiktok-direct", "tiktok-worker"}:
            parser.add_argument("--allow-network-writes", action="store_true")
        if name == "tiktok-worker":
            parser.add_argument("--limit", type=int, default=10)


def run(args):
    service = NativeTikTok(posts_path=args.posts, registry_path=args.registry)
    if args.cmd in {"tiktok-status", "tiktok-config"}:
        return service.config_status()
    if args.cmd == "tiktok-creator-sync":
        return service.creator_info(args.account_id)
    if args.cmd == "tiktok-dry-run":
        account, _ = service.account(args.account_id)
        import publish
        post = publish.load_post(args.post_id, args.posts)
        planned = service.scheduled(account, post, args.scheduled_for)
        snapshot, _ = service.prepare(args.post_id, args.account_id,
            PhotoSettings.parse(json.loads(Path(args.settings).read_text(encoding="utf-8"))), planned,
            creator_fixture=json.loads(Path(args.creator_fixture).read_text(encoding="utf-8")))
        return {"snapshot": snapshot, "submission_attempted": False,
                "content_preview_confirmed": False, "express_consent": False,
                "note": "request only; fixture creator data cannot grant consent"}
    if args.cmd == "tiktok-consent":
        receipt = service.journal.get("consents", args.consent_id)
        if not receipt:
            raise TikTokError("consent not found; use the dashboard Approve & Schedule control")
        return receipt
    if args.cmd == "tiktok-worker":
        return service.worker(limit=args.limit, allow_network_writes=args.allow_network_writes)
    if args.cmd == "tiktok-refresh":
        return service.refresh_status(args.attempt_id)
    attempt = service.journal.get("attempts", args.attempt_id)
    allowed = {"draft"} if args.cmd == "tiktok-draft" else {"private", "direct"}
    if not attempt or attempt["snapshot"]["mode"] not in allowed:
        raise TikTokError("attempt does not match the requested submission mode")
    return service.submit(args.attempt_id, allow_network_writes=args.allow_network_writes)
