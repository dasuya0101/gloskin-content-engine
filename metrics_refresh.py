#!/usr/bin/env python3
"""
metrics_refresh.py - metrics integration bridge
===============================================

Imports available metrics into posts.json and provides named slots for future
official platform API pulls.

Today:
  python metrics_refresh.py csv --csv metrics.csv

Future adapters:
  python metrics_refresh.py api-plan --provider tiktok
  python metrics_refresh.py api --provider instagram
"""
import argparse
import json
import os

import import_metrics


POSTS_FILE = "posts.json"


class MetricsError(RuntimeError):
    pass


API_PLANS = {
    "tiktok": {
        "status": "adapter_pending_credentials",
        "requires": ["TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_ACCESS_TOKEN"],
        "matches_by": ["tracking_code in caption", "published video id/url"],
        "metrics": ["views", "likes", "shares", "saves"],
    },
    "instagram": {
        "status": "adapter_pending_credentials",
        "requires": ["META_ACCESS_TOKEN", "IG_USER_ID"],
        "matches_by": ["publish.url", "platform media id"],
        "metrics": ["views", "likes", "shares", "saves"],
    },
    "meta_ads": {
        "status": "adapter_pending_credentials",
        "requires": ["META_ACCESS_TOKEN", "META_AD_ACCOUNT_ID"],
        "matches_by": ["tracking_code", "creative id", "utm"],
        "metrics": ["views", "ctr", "installs", "spend", "cpi"],
    },
    "installs": {
        "status": "adapter_pending_credentials",
        "requires": ["ATTRIBUTION_API_KEY"],
        "matches_by": ["tracking_code", "utm"],
        "metrics": ["installs"],
    },
}


def api_plan(provider):
    if provider not in API_PLANS:
        raise MetricsError(f"unknown provider: {provider}")
    return API_PLANS[provider]


def require_env(names):
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        raise MetricsError("missing environment variables: " + ", ".join(missing))


def pull_api(provider, posts_path):
    plan = api_plan(provider)
    require_env(plan["requires"])
    raise MetricsError(
        f"{provider} metrics adapter is scaffolded but not enabled yet. "
        "Use csv import now, then fill this adapter once official API credentials are approved."
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--posts", default=POSTS_FILE)
    sub = ap.add_subparsers(dest="cmd", required=True)

    csv_p = sub.add_parser("csv")
    csv_p.add_argument("--csv", required=True)
    csv_p.add_argument("--map", nargs="*", default=[],
                       help="field=ColumnName overrides, e.g. views='Video Views'")

    plan_p = sub.add_parser("api-plan")
    plan_p.add_argument("--provider", required=True, choices=sorted(API_PLANS))

    api_p = sub.add_parser("api")
    api_p.add_argument("--provider", required=True, choices=sorted(API_PLANS))

    args = ap.parse_args()
    try:
        if args.cmd == "csv":
            result = import_metrics.import_csv(args.csv, args.posts, args.map)
            print(json.dumps(result, indent=2))
        elif args.cmd == "api-plan":
            print(json.dumps(api_plan(args.provider), indent=2))
        elif args.cmd == "api":
            pull_api(args.provider, args.posts)
    except MetricsError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
