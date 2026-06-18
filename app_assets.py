#!/usr/bin/env python3
"""
app_assets.py - required real-app screenshot inventory
======================================================

These are the real app screenshots the content engine should use as proof
slides. Scan Results is required for the current testimonial flow; the rest are
recommended reusable screenshots for future app-use slideshows.
"""
from pathlib import Path


APP_SCREENSHOTS = [
    {
        "key": "scan_results",
        "path": "templates/scan_results.webp",
        "priority": "required",
        "mode": "personalized",
        "editable_fields": ["face", "glo_score", "score_progress_bar", "optional_text_patches"],
        "use": "Personalized Glo Score before/after slides",
        "notes": "Existing templatized screenshot. Re-export at 722x1568 if geometry changes.",
    },
    {
        "key": "today_routine",
        "path": "templates/today_routine.webp",
        "priority": "recommended",
        "mode": "static_or_text_patch",
        "editable_fields": ["routine_title", "routine_steps", "optional_name"],
        "use": "Routine/protocol proof slide",
        "notes": "Reusable static screenshot from the app.",
    },
    {
        "key": "guru_chat",
        "path": "templates/guru_chat.webp",
        "priority": "recommended",
        "mode": "static_or_text_patch",
        "editable_fields": ["chat_question", "chat_answer", "optional_name"],
        "use": "AI skincare coach/chat proof slide",
        "notes": "Capture a believable, compliant skincare Q&A.",
    },
    {
        "key": "product_scan",
        "path": "templates/product_scan.webp",
        "priority": "recommended",
        "mode": "static_or_text_patch",
        "editable_fields": ["product_name", "ingredient_callouts", "rating"],
        "use": "Ingredient/product scanner proof slide",
        "notes": "Useful for serum/moisturizer audit posts.",
    },
    {
        "key": "skin_diary",
        "path": "templates/skin_diary.webp",
        "priority": "optional",
        "mode": "mostly_static",
        "editable_fields": ["date_range", "progress_note"],
        "use": "Progress tracking / diary proof slide",
        "notes": "Useful for habit, progress, and retention creatives.",
    },
]


def status(root="."):
    root = Path(root)
    rows = []
    for item in APP_SCREENSHOTS:
        p = root / item["path"]
        rows.append({
            **item,
            "exists": p.exists(),
            "size_bytes": p.stat().st_size if p.exists() else None,
        })
    return rows


def main():
    import json
    print(json.dumps(status(), indent=2))


if __name__ == "__main__":
    main()
