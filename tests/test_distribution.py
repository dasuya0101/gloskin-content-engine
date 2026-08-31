import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from PIL import Image

import distribution
import manifest
import publish


def registry():
    return {
        "vendor": {"name": "test", "api_url_env": "VENDOR_URL", "api_key_env": "VENDOR_KEY"},
        "scheduling": {
            "daily_caps": {"tiktok": 2, "instagram": 3},
            "jitter_minutes": {"min": 5, "max": 10},
        },
        "accounts": [],
    }


def account(**overrides):
    row = {
        "account_id": "gloskin_tiktok_test",
        "brand": "gloskin",
        "platform": "tiktok",
        "handle": "@gloskin_test",
        "role": "flagship",
        "owning_entity": "GloSkin LLC",
        "verification_status": "verified",
        "vendor_account_ref_env": "TEST_ACCOUNT_REF",
        "enabled": True,
        "test_account": True,
    }
    row.update(overrides)
    return row


class DistributionTests(unittest.TestCase):
    def test_unverified_tiktok_account_is_blocked(self):
        row = account(verification_status="pending")
        with mock.patch.dict(os.environ, {"TEST_ACCOUNT_REF": "ref"}, clear=False):
            self.assertIn("TikTok account is not verified", distribution.account_blockers(row))

    def test_schedule_jitter_is_deterministic_and_cap_is_enforced(self):
        cfg = registry()
        row = account()
        post = {"post_id": "abc", "tracking_code": "glo_abc"}
        first = distribution.scheduled_time(cfg, row, post, "2026-09-01T09:00:00")
        second = distribution.scheduled_time(cfg, row, post, "2026-09-01T09:00:00")
        self.assertEqual(first, second)
        records = [
            {"account_id": row["account_id"], "platform": "tiktok", "status": "queued",
             "scheduled_for": "2026-09-01T10:00:00"},
            {"account_id": row["account_id"], "platform": "tiktok", "status": "posted",
             "scheduled_for": "2026-09-01T11:00:00"},
        ]
        with self.assertRaisesRegex(distribution.DistributionError, "daily cap reached"):
            distribution.scheduled_time(
                cfg, row, post, "2026-09-01T09:00:00", existing_records=records)

    def test_duplicate_creative_on_second_account_is_blocked(self):
        records = [{
            "platform": "tiktok",
            "account_id": "gloskin_tiktok_first",
            "creative_fingerprint": "same",
            "status": "packaged",
        }]
        with self.assertRaisesRegex(distribution.DistributionError, "identical creative"):
            distribution.require_distinct_creative(
                "tiktok", "gloskin_tiktok_second", "same", records)

    def test_manifest_distribution_status_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "posts.json"
            path.write_text(json.dumps([{"post_id": "p1", "brand": "gloskin"}]), encoding="utf-8")
            manifest.set_distribution("p1", "tiktok", "acct", "packaged", path)
            manifest.set_distribution("p1", "tiktok", "acct", "queued", path)
            manifest.set_distribution(
                "p1", "tiktok", "acct", "posted", path, url="https://example.test/post")
            manifest.update_metrics(
                "p1", {"views": 10}, path, source_url="https://example.test/post")
            row = manifest.get_post("p1", path)["distribution"][0]
            self.assertEqual(row["status"], "metrics_matched")

    def test_manifest_rejects_skipped_transition(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "posts.json"
            path.write_text(json.dumps([{"post_id": "p1", "brand": "gloskin"}]), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalid distribution transition"):
                manifest.set_distribution("p1", "instagram", "acct", "queued", path)

    def test_vendor_dry_run_builds_instagram_request_without_submission(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            slides = root / "slides"
            slides.mkdir()
            Image.new("RGB", (1080, 1350), (20, 40, 60)).save(slides / "slide.png")
            registry_path = root / "accounts.yaml"
            cfg = registry()
            cfg["accounts"] = [account(
                account_id="gloskin_instagram_test",
                platform="instagram",
                vendor_account_ref_env="TEST_IG_REF",
            )]
            registry_path.write_text(json.dumps(cfg), encoding="utf-8")
            post = {
                "post_id": "p1",
                "brand": "gloskin",
                "hook": "A useful skincare hook",
                "caption": "Caption",
                "tracking_code": "glo_p1",
                "slides": [],
                "metadata": {},
                "compliance": {"status": "pass", "violations": []},
                "package": {"dir": str(root / "package"), "slides_dir": str(slides)},
                "publish_queue": {"status": "ready_to_post", "target_account": "manual"},
            }
            posts_path = root / "posts.json"
            posts_path.write_text(json.dumps([post]), encoding="utf-8")
            with mock.patch.dict(os.environ, {"TEST_IG_REF": "vendor-account"}, clear=False):
                result = publish.vendor_dry_run(
                    post,
                    "instagram",
                    "gloskin_instagram_test",
                    posts_path=posts_path,
                    registry_path=registry_path,
                )
            self.assertFalse(result["submission_attempted"])
            self.assertEqual(result["request"]["post_type"], "carousel")
            self.assertTrue(result["request"]["media"][0].endswith(".jpg"))
            destination = manifest.get_post("p1", posts_path)["distribution"][0]
            self.assertEqual(destination["status"], "packaged")
            self.assertEqual(destination["mode"], "vendor")


if __name__ == "__main__":
    unittest.main()
