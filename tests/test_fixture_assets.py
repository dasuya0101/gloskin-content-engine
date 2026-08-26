import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import fixture_assets


class FixtureAssetImportTests(unittest.TestCase):
    def test_import_verifies_and_preserves_four_level_set(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rows = []
            for index, severity in enumerate(fixture_assets.SEVERITIES, 1):
                image = root / f"source-{severity}.png"
                image.write_bytes(f"fixture-{severity}".encode("ascii"))
                rows.append({
                    "id": f"A{index}",
                    "identity_family": "synthetic-A-r01",
                    "subject_id": "synthetic-A-r01",
                    "expected_severity": severity,
                    "expected_glo_score_band": ">=85" if severity == "clear" else "policy",
                    "expected_zone_grid": {"forehead": severity},
                    "image_path": str(image),
                    "image_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                    "skin_tone_mst": 2,
                    "fitzpatrick_ref": "I-II",
                    "status": "accepted",
                    "qa_scope": "user-accepted-candidate",
                    "notes": "formal QA not documented",
                    "prompt_id": f"A{index}",
                    "provenance": "synthetic",
                })
            manifest = root / "fixtures.jsonl"
            manifest.write_text(
                "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

            imported = fixture_assets.import_fixture_sets(
                manifest, root / "assets", root / "roster.json")

            self.assertEqual(imported[0]["slug"], "fixture_woman_mst2")
            character_dir = root / "assets" / "fixture_woman_mst2"
            for severity in fixture_assets.SEVERITIES:
                self.assertTrue((character_dir / "fixtures" / f"{severity}.png").exists())
            self.assertEqual(
                (character_dir / "before.png").read_bytes(),
                (character_dir / "fixtures" / "moderate.png").read_bytes(),
            )
            self.assertEqual(
                (character_dir / "after.png").read_bytes(),
                (character_dir / "fixtures" / "clear.png").read_bytes(),
            )
            metadata = json.loads((character_dir / "fixture_set.json").read_text())
            self.assertTrue(metadata["not_longitudinal"])
            self.assertEqual(set(metadata["levels"]), set(fixture_assets.SEVERITIES))
            roster = json.loads((root / "roster.json").read_text())
            self.assertEqual(roster["characters"][0]["source_type"], "synthetic_fixture_set")

    def test_checksum_mismatch_stops_import(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rows = []
            for severity in fixture_assets.SEVERITIES:
                image = root / f"{severity}.png"
                image.write_bytes(severity.encode("ascii"))
                rows.append({
                    "id": severity,
                    "identity_family": "family",
                    "expected_severity": severity,
                    "image_path": str(image),
                    "image_sha256": "bad-hash",
                    "skin_tone_mst": 2,
                    "status": "accepted",
                })
            manifest = root / "fixtures.jsonl"
            manifest.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

            with self.assertRaisesRegex(fixture_assets.FixtureImportError, "checksum mismatch"):
                fixture_assets.import_fixture_sets(
                    manifest, root / "assets", root / "roster.json")


if __name__ == "__main__":
    unittest.main()
