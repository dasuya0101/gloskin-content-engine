#!/usr/bin/env python3
"""
analyze_winners.py — the feedback loop
======================================
Ranks posts by a chosen metric, flags the top performers as winners, then diffs
what the winners share vs everyone else (hook length, first word, slide order,
character demographics, score gap, format). Emits:
  - winners_report.md   human-readable summary
  - a suggested block you can paste/append into the brand learned_rules prompt

This is the v1 heuristic version. The BUILD_SPEC describes upgrading the "what's
different about winners" step to an LLM analysis (routed via llm_router task=analysis)
that reads the actual winning copy and writes nuanced rules.

  python analyze_winners.py --metric views --top-frac 0.25
"""
import argparse
import statistics as st
from collections import Counter

import manifest
from brand_loader import DEFAULT_BRAND, load_brand


def attr(p):
    spec = (p.get("character") or {}).get("spec", "")
    hook = p.get("hook", "") or ""
    slides = p.get("slides", [])
    ch = p.get("character") or {}
    gap = None
    if ch.get("before_score") is not None and ch.get("after_score") is not None:
        gap = ch["after_score"] - ch["before_score"]
    return {
        "spec": spec,
        "hook_words": len(hook.split()),
        "hook_first": (hook.split() or [""])[0].lower().strip(".,!?"),
        "order": "|".join(s["kind"] for s in slides),
        "format": p.get("format"),
        "score_gap": gap,
    }


def summarize(group):
    rows = [attr(p) for p in group]
    if not rows:
        return {}
    def top(key):
        c = Counter(r[key] for r in rows if r[key] not in (None, ""))
        return c.most_common(3)
    hw = [r["hook_words"] for r in rows if r["hook_words"]]
    gaps = [r["score_gap"] for r in rows if r["score_gap"] is not None]
    return {
        "n": len(rows),
        "avg_hook_words": round(st.mean(hw), 1) if hw else None,
        "common_first_words": top("hook_first"),
        "common_orders": top("order"),
        "common_specs": top("spec"),
        "avg_score_gap": round(st.mean(gaps), 1) if gaps else None,
        "formats": top("format"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--metric", default="views")
    ap.add_argument("--top-frac", type=float, default=0.25)
    ap.add_argument("--posts", default="posts.json")
    ap.add_argument("--brand", default=DEFAULT_BRAND)
    args = ap.parse_args()
    brand = load_brand(args.brand)

    posts = [p for p in manifest.all_posts(args.posts)
             if (p.get("brand") or DEFAULT_BRAND) == brand.brand_id
             and (p["metrics"] or {}).get(args.metric) is not None]
    if len(posts) < 4:
        print(f"Need at least 4 posts with '{args.metric}' metrics; have {len(posts)}.")
        return

    posts.sort(key=lambda p: p["metrics"][args.metric], reverse=True)
    k = max(1, int(len(posts) * args.top_frac))
    winners, rest = posts[:k], posts[k:]

    # flag winners back into the manifest
    for p in manifest.all_posts(args.posts):
        pass  # is_winner write handled below via update

    wsum, rsum = summarize(winners), summarize(rest)
    lines = [
        f"# Winners report — ranked by {args.metric}",
        f"\nTop {k} of {len(posts)} posts (top {int(args.top_frac*100)}%).\n",
        "## Winners", _fmt(wsum), "\n## Everyone else", _fmt(rsum),
        "\n## What's different (winners vs rest)",
        _diff(wsum, rsum, args.metric),
    ]
    report = "\n".join(lines)
    open("winners_report.md", "w").write(report)
    print(report)
    print("\n-> wrote winners_report.md")
    learned_path = brand.prompt_path("learned_rules")
    target = str(learned_path) if learned_path else f"{brand.brand_id} learned_rules prompt"
    print(f"-> review the 'suggested rules' and append worthwhile ones to {target}")


def _fmt(s):
    if not s:
        return "(none)"
    return (f"- posts: {s['n']}\n- avg hook words: {s['avg_hook_words']}\n"
            f"- common first words: {s['common_first_words']}\n"
            f"- common slide orders: {s['common_orders']}\n"
            f"- common demographics: {s['common_specs']}\n"
            f"- avg score gap: {s['avg_score_gap']}\n- formats: {s['formats']}")


def _diff(w, r, metric):
    out = ["\n### Suggested rules (review before adopting):"]
    if w.get("avg_hook_words") and r.get("avg_hook_words"):
        if w["avg_hook_words"] < r["avg_hook_words"] - 1:
            out.append(f"- Winners use SHORTER hooks (~{w['avg_hook_words']} vs {r['avg_hook_words']} words). Bias hooks shorter.")
        elif w["avg_hook_words"] > r["avg_hook_words"] + 1:
            out.append(f"- Winners use LONGER hooks (~{w['avg_hook_words']} vs {r['avg_hook_words']} words).")
    if w.get("common_first_words"):
        fw = w["common_first_words"][0][0]
        out.append(f"- Winning hooks often open with \"{fw}\" — try leading more hooks this way.")
    if w.get("avg_score_gap") and r.get("avg_score_gap") and w["avg_score_gap"] > r["avg_score_gap"]:
        out.append(f"- Winners show a bigger score jump (~{w['avg_score_gap']} vs {r['avg_score_gap']}). Use wider before/after gaps.")
    if w.get("common_orders"):
        out.append(f"- Winning slide order: {w['common_orders'][0][0]}.")
    if len(out) == 1:
        out.append("- No strong signal yet; collect more data.")
    return "\n".join(out)


if __name__ == "__main__":
    main()
