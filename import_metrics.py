#!/usr/bin/env python3
"""
import_metrics.py — pull performance back into the manifest
===========================================================
Takes a CSV exported from TikTok / IG / Meta (or a manual sheet) and merges the
numbers into posts.json so the dashboard and winner-analysis can use them.

Match strategy (in priority order):
  1. tracking_code column matches a post's tracking_code
  2. url column matches a post's publish.url

CSV is expected to have a header row. Map your columns with --map if they differ
from the defaults. Example:
  python import_metrics.py --csv tiktok_export.csv \
      --map views=Video Views,likes=Likes,ctr=CTR,installs=Installs,tracking_code=Caption

This is the manual-import path to start. The BUILD_SPEC describes swapping this for
direct API pulls (TikTok Business API / IG Graph API) once accounts are set up.
"""
import argparse
import csv

import manifest

DEFAULT_MAP = {
    "tracking_code": "tracking_code", "url": "url",
    "views": "views", "likes": "likes", "shares": "shares",
    "saves": "saves", "ctr": "ctr", "installs": "installs",
}


METRIC_FIELDS = ["views", "likes", "shares", "saves", "ctr", "installs"]


def num(v):
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(",", "").replace("%", ""))
    except ValueError:
        return None


def build_colmap(overrides=None):
    colmap = dict(DEFAULT_MAP)
    for kv in overrides or []:
        k, _, v = kv.partition("=")
        colmap[k.strip()] = v.strip()
    return colmap


def find_by_code(value, by_code):
    if not value:
        return None
    text = str(value).strip()
    if text in by_code:
        return by_code[text]
    for code, post in by_code.items():
        if code and code in text:
            return post
    return None


def find_by_url(value, by_url):
    if not value:
        return None
    text = str(value).strip()
    if text in by_url:
        return by_url[text]
    for url, post in by_url.items():
        if url and (url in text or text in url):
            return post
    return None


def import_csv(csv_path, posts_path="posts.json", map_overrides=None):
    colmap = build_colmap(map_overrides)
    posts = manifest.all_posts(posts_path)
    by_code = {p.get("tracking_code"): p for p in posts if p.get("tracking_code")}
    by_url = {p["publish"].get("url"): p for p in posts if p.get("publish", {}).get("url")}

    matched = 0
    unmatched = 0
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            code = row.get(colmap["tracking_code"])
            url = row.get(colmap["url"])
            post = find_by_code(code, by_code) or find_by_url(url, by_url)
            if not post:
                unmatched += 1
                continue
            metrics = {k: num(row.get(colmap[k]))
                       for k in METRIC_FIELDS
                       if colmap[k] in row}
            manifest.update_metrics(post["post_id"], metrics, posts_path)
            matched += 1
    return {"matched": matched, "unmatched": unmatched, "posts": posts_path}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--posts", default="posts.json")
    ap.add_argument("--map", nargs="*", default=[],
                    help="field=ColumnName overrides, e.g. views='Video Views'")
    args = ap.parse_args()

    result = import_csv(args.csv, args.posts, args.map)
    print(f"[metrics] updated {result['matched']} posts in {args.posts}")
    if result["unmatched"]:
        print(f"[metrics] skipped {result['unmatched']} unmatched rows")


if __name__ == "__main__":
    main()
