#!/usr/bin/env python3
"""
Brand screenshot inventory.

Screenshot templates are declared in each brand YAML. This module turns those
declarations into dashboard-friendly status rows.
"""
from pathlib import Path

from brand_loader import DEFAULT_BRAND, load_brand


def status(root=".", brand=None):
    root = Path(root)
    active_brand = brand if brand is not None else load_brand(DEFAULT_BRAND)
    rows = []
    for item in active_brand.template_items():
        rel_path = item.get("path")
        p = root / rel_path if rel_path else None
        exists = bool(p and p.exists())
        rows.append({
            "key": item.get("key"),
            "path": rel_path,
            "priority": item.get("priority", "optional"),
            "mode": item.get("mode"),
            "editable_fields": item.get("editable_fields", []),
            "use": item.get("use", ""),
            "notes": item.get("notes", ""),
            "exists": exists,
            "size_bytes": p.stat().st_size if exists else None,
        })
    return rows


def main():
    import argparse
    import json

    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", default=DEFAULT_BRAND)
    args = ap.parse_args()
    print(json.dumps(status(brand=load_brand(args.brand)), indent=2))


if __name__ == "__main__":
    main()
