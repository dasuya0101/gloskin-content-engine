#!/usr/bin/env python3
"""Import manifest-backed severity fixtures into the local character library."""

import argparse
import hashlib
import json
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


SEVERITIES = ("clear", "mild", "moderate", "severe")


class FixtureImportError(ValueError):
    pass


def read_jsonl(path):
    rows = []
    for line_number, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            rows.append(json.loads(raw))
        except json.JSONDecodeError as exc:
            raise FixtureImportError(f"invalid JSON on line {line_number}: {exc}") from exc
    return rows


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validated_groups(rows):
    groups = defaultdict(dict)
    for row in rows:
        family = row.get("identity_family") or row.get("subject_id")
        severity = row.get("expected_severity")
        if not family or severity not in SEVERITIES:
            raise FixtureImportError(
                f"fixture {row.get('id', '<unknown>')} needs an identity and valid severity")
        if severity in groups[family]:
            raise FixtureImportError(f"duplicate {severity} fixture for {family}")
        if row.get("status") != "accepted":
            raise FixtureImportError(f"fixture {row.get('id')} is not accepted")
        source = Path(row.get("image_path") or "")
        if not source.is_file():
            raise FixtureImportError(f"fixture image not found: {source}")
        expected_hash = row.get("image_sha256")
        actual_hash = sha256(source)
        if expected_hash and actual_hash.lower() != expected_hash.lower():
            raise FixtureImportError(f"checksum mismatch for {source.name}")
        groups[family][severity] = {**row, "image_sha256": actual_hash}

    for family, levels in groups.items():
        missing = [severity for severity in SEVERITIES if severity not in levels]
        if missing:
            raise FixtureImportError(f"{family} is missing: {', '.join(missing)}")
    return groups


def fixture_slug(levels):
    mst_values = {row.get("skin_tone_mst") for row in levels.values()}
    if len(mst_values) != 1 or None in mst_values:
        raise FixtureImportError("each identity needs one skin_tone_mst value")
    return f"fixture_woman_mst{mst_values.pop()}"


def roster_character(slug, family, levels, metadata_path):
    sample = levels["clear"]
    mst = sample["skin_tone_mst"]
    return {
        "slug": slug,
        "spec": f"woman, 28, MST {mst} skin tone",
        "before_score": 54,
        "after_score": 87,
        "hook": "What would an AI skin scan\nnotice first?",
        "source_type": "synthetic_fixture_set",
        "fixture_set": {
            "identity_family": family,
            "metadata": metadata_path,
            "default_before_severity": "moderate",
            "default_scan_severity": "moderate",
            "default_after_severity": "clear",
            "not_longitudinal": True,
        },
    }


def import_fixture_sets(manifest_path, assets_dir, roster_path):
    manifest_path = Path(manifest_path).resolve()
    assets_dir = Path(assets_dir).resolve()
    roster_path = Path(roster_path).resolve()
    groups = validated_groups(read_jsonl(manifest_path))
    roster = (
        json.loads(roster_path.read_text(encoding="utf-8"))
        if roster_path.exists()
        else {"template": "scan_results", "characters": []}
    )
    roster.setdefault("template", "scan_results")
    roster.setdefault("characters", [])
    existing_by_slug = {
        character.get("slug"): index
        for index, character in enumerate(roster["characters"])
        if character.get("slug")
    }
    imported = []

    for family, levels in sorted(
            groups.items(), key=lambda item: item[1]["clear"]["skin_tone_mst"]):
        slug = fixture_slug(levels)
        character_dir = assets_dir / slug
        fixture_dir = character_dir / "fixtures"
        fixture_dir.mkdir(parents=True, exist_ok=True)
        level_records = {}
        for severity in SEVERITIES:
            row = levels[severity]
            destination = fixture_dir / f"{severity}.png"
            shutil.copy2(row["image_path"], destination)
            level_records[severity] = {
                "id": row.get("id"),
                "severity": severity,
                "path": f"fixtures/{severity}.png",
                "sha256": row["image_sha256"],
                "prompt_id": row.get("prompt_id"),
                "expected_glo_score_band": row.get("expected_glo_score_band"),
                "expected_zone_grid": row.get("expected_zone_grid"),
                "source_record": row,
            }

        shutil.copy2(fixture_dir / "moderate.png", character_dir / "before.png")
        shutil.copy2(fixture_dir / "moderate.png", character_dir / "scan.png")
        shutil.copy2(fixture_dir / "clear.png", character_dir / "after.png")
        metadata = {
            "schema_version": 1,
            "identity_family": family,
            "skin_tone_mst": levels["clear"].get("skin_tone_mst"),
            "fitzpatrick_ref": levels["clear"].get("fitzpatrick_ref"),
            "provenance": "synthetic",
            "qa_scope": levels["clear"].get("qa_scope"),
            "qa_note": levels["clear"].get("notes"),
            "not_longitudinal": True,
            "usage_note": (
                "Severity reference set; images do not document a measured treatment timeline."
            ),
            "default_mapping": {
                "before": "moderate",
                "scan": "moderate",
                "after": "clear",
            },
            "imported_at": datetime.now(timezone.utc).isoformat(),
            "source_manifest": str(manifest_path),
            "levels": level_records,
        }
        metadata_file = character_dir / "fixture_set.json"
        metadata_file.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        try:
            metadata_path = str(metadata_file.relative_to(roster_path.parent)).replace("\\", "/")
        except ValueError:
            metadata_path = str(metadata_file)
        character = roster_character(slug, family, levels, metadata_path)
        if slug in existing_by_slug:
            index = existing_by_slug[slug]
            roster["characters"][index] = {**roster["characters"][index], **character}
        else:
            roster["characters"].append(character)
            existing_by_slug[slug] = len(roster["characters"]) - 1
        imported.append({"slug": slug, "identity_family": family, "levels": list(SEVERITIES)})

    roster_path.parent.mkdir(parents=True, exist_ok=True)
    roster_path.write_text(json.dumps(roster, indent=2), encoding="utf-8")
    return imported


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, help="source fixtures.jsonl")
    parser.add_argument("--assets-dir", default="assets")
    parser.add_argument("--roster", default="roster.json")
    args = parser.parse_args()
    imported = import_fixture_sets(args.manifest, args.assets_dir, args.roster)
    print(json.dumps({"imported": imported, "count": len(imported)}, indent=2))


if __name__ == "__main__":
    main()
