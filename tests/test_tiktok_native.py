"""All TikTok/OAuth/R2 write paths use fixtures; never real accounts or HTTP."""
import copy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cryptography.fernet import Fernet
from flask import Flask
from PIL import Image
import yaml

import distribution
import manifest
import publish
from publisher_tiktok import NativeTikTok, PhotoSettings, TikTokError, assemble_request, digest
from tiktok_media import FakeMediaHost, R2MediaHost, MediaError, validate_prefix
from tiktok_oauth import OAuth, TokenStore, call
import tiktok_dashboard
from test_publish_gate import synthetic_post


CREATOR = {"creator_username": "fixture_creator", "creator_nickname": "Fixture Creator",
           "privacy_level_options": ["SELF_ONLY", "PUBLIC_TO_EVERYONE"], "comment_disabled": False}


class FakeTokens:
    def __init__(self):
        self.requests = []
        self.scopes = {"video.publish", "video.upload"}

    def token(self, account, pinned, scopes):
        self.requests.append((account, pinned, scopes))
        if not set(scopes).issubset(self.scopes):
            raise TikTokError("scope denied")
        return "fixture-secret-token"


class Transport:
    def __init__(self):
        self.calls = []
        self.creator = copy.deepcopy(CREATOR)
        self.fail_init = False
        self.status = {"status": "PUBLISH_COMPLETE", "publicaly_available_post_id": [1234567]}

    def __call__(self, path, body, token=None, **kwargs):
        self.calls.append((path, copy.deepcopy(body), kwargs))
        if path.endswith("creator_info/query/"):
            data = self.creator
        elif path.endswith("content/init/"):
            if self.fail_init:
                raise TimeoutError("fixture-secret-token refresh_token=do-not-leak")
            data = {"publish_id": "p_pub_url~v2.fixture"}
        elif path.endswith("status/fetch/"):
            data = self.status
        else:
            raise AssertionError("unexpected endpoint")
        return 200, {"data": copy.deepcopy(data), "error": {"code": "ok"}}


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {"TEST_OPEN_ID": "fixture-open-id", "TIKTOK_ALLOW_SUBMISSIONS": "true"})
        self.env.start(); self.addCleanup(self.env.stop)
        self.account = {"account_id": "gloskin_fixture", "brand": "gloskin", "platform": "tiktok",
                        "handle": "@fixture_creator", "role": "flagship", "owning_entity": "Fixture Entity",
                        "verification_status": "verified", "enabled": True, "test_account": True,
                        "native_tiktok": {"mode": "private", "open_id_env": "TEST_OPEN_ID"}}
        self.registry = {"accounts": [self.account], "vendor": {}, "scheduling": {
            "daily_caps": {"tiktok": 20}, "jitter_minutes": {"min": 7, "max": 23}},
            "native_tiktok": {"submission_enabled": True, "scheduler_enabled": True,
                "developer_app_approved": True, "intended_use_approved": True,
                "intended_use_approval_reference": "fixture approval only", "manual_launch_complete": True,
                "private_validation_approved": True, "direct_checkpoint_approved": True}}
        self.regpath = self.root / "accounts.yaml"
        self.write_registry()
        slides = self.root / "slides"; slides.mkdir()
        for index in range(2):
            Image.new("RGB", (1080, 1350), (30 + index, 50, 70)).save(slides / f"slide_{index:02d}.png")
        self.post = synthetic_post(post_id="p1", tracking_code="fixture-track-1",
            package={"platform_slides": {"tiktok": str(slides)}}, distribution=[])
        self.posts = self.root / "posts.json"
        self.posts.write_text(json.dumps([self.post]), encoding="utf-8")
        self.transport = Transport(); self.tokens = FakeTokens()
        self.clock = datetime(2026, 9, 10, 12, tzinfo=timezone.utc)
        self.host = FakeMediaHost(cache=self.root / "native/media")
        self.service = NativeTikTok(self.posts, self.regpath, self.root / "native", transport=self.transport,
            oauth=self.tokens, host=self.host, now=lambda: self.clock)
        self.settings = {"title": "Fixture title", "privacy_level": "SELF_ONLY"}

    def write_registry(self):
        self.regpath.write_text(yaml.safe_dump(self.registry), encoding="utf-8")

    def preview(self):
        return self.service.preview("p1", self.account["account_id"], self.settings,
                                    self.clock.isoformat(), "fixture operator")

    def approve(self):
        preview = self.preview()
        for index in range(2):
            self.service.preview_image(preview["ticket"], index, "fixture operator")
        record = self.service.approve(preview["ticket"], "fixture operator",
                                      content_preview_confirmed=True, express_consent=True)
        self.clock = datetime.fromisoformat(record["scheduled_for"])
        return record

    def submit(self):
        record = self.approve()
        self.service.submit(record["native_attempt_id"], allow_network_writes=True)
        return record["native_attempt_id"]

    def test_request_schema_and_consent_defaults(self):
        result = self.preview()
        request = result["snapshot"]["request"]
        self.assertEqual(request["post_mode"], "DIRECT_POST")
        self.assertIs(request["is_aigc"], True)
        self.assertNotIn("is_aigc", request["post_info"])
        self.assertTrue(request["post_info"]["brand_organic_toggle"])
        self.assertFalse(request["post_info"]["brand_content_toggle"])
        self.assertTrue(request["post_info"]["disable_comment"])
        self.assertFalse(request["post_info"]["auto_add_music"])
        self.assertFalse(result["express_consent"])
        self.assertFalse(result["content_preview_confirmed"])
        self.assertNotIn(str(self.root), json.dumps(request))
        self.assertTrue(all(p["mime"] == "image/jpeg" for p in result["snapshot"]["photos"]))
        self.assertEqual(len(self.host.uploaded), 0)
        self.assertTrue(all("creator_info" in p for p, _, _ in self.transport.calls))

    def test_hard_gates_cannot_be_overridden(self):
        mutations = [lambda p: p["metadata"].update(is_aigc=False),
                     lambda p: p["compliance"].update(status="fail", override={"flag": True}),
                     lambda p: p["compliance"].update(violations=[{"rule": "regulatory_hold"}]),
                     lambda p: p["slides"][0].update(disclosure_chip=None),
                     lambda p: p.update(caption="missing disclosure"),
                     lambda p: p.update(brand="vendrarx")]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                post = copy.deepcopy(self.post); mutation(post)
                self.posts.write_text(json.dumps([post]))
                with self.assertRaises((publish.PublishError, TikTokError)):
                    self.preview()
        self.assertEqual(self.transport.calls, [])

    def test_dimensions_gate(self):
        Image.new("RGB", (100, 100)).save(self.root / "slides/slide_00.png")
        with self.assertRaises(publish.PublishError): self.preview()

    def test_media_count_matches_release_manifest(self):
        Image.new("RGB", (1080, 1350)).save(self.root / "slides/slide_02.png")
        with self.assertRaisesRegex(TikTokError, "slide count"):
            self.preview()

    def test_unpinned_unknown_disabled_and_wrong_brand_accounts(self):
        with self.assertRaises(distribution.DistributionError): self.service.account("unknown")
        with patch.dict(os.environ, {"TEST_OPEN_ID": ""}):
            with self.assertRaises(TikTokError): self.preview()
        for key, value in (("enabled", False), ("verification_status", "unverified"),
                           ("owning_entity", "TODO"), ("brand", "vendrarx")):
            original = self.account[key]; self.account[key] = value; self.write_registry()
            with self.assertRaises((TikTokError, publish.PublishError)): self.preview()
            self.account[key] = original

    def test_privacy_comments_cover_and_utf16_limits(self):
        for settings in ({"privacy_level": ""}, {"privacy_level": "FOLLOWER_OF_CREATOR"},
                         {"cover_index": 2}, {"title": "😀" * 46}, {"allow_comments": "true"}):
            self.settings = {"privacy_level": "SELF_ONLY", **settings}
            with self.assertRaises(TikTokError): self.preview()
        self.settings = {"privacy_level": "SELF_ONLY", "allow_comments": True}
        self.transport.creator["comment_disabled"] = True
        with self.assertRaises(TikTokError): self.preview()

    def test_approval_requires_click_flags_and_all_images(self):
        preview = self.preview()
        with self.assertRaises(TikTokError):
            self.service.approve(preview["ticket"], "fixture operator")
        with self.assertRaises(TikTokError):
            self.service.approve(preview["ticket"], "fixture operator", content_preview_confirmed=True, express_consent=True)
        self.assertFalse(self.service.journal.attempts())

    def test_caption_media_account_setting_edits_invalidate_digest(self):
        for edit in ("caption", "media", "account", "mode"):
            with self.subTest(edit=edit):
                preview = self.preview()
                for index in range(2): self.service.preview_image(preview["ticket"], index, "fixture operator")
                if edit == "caption":
                    self.post["caption"] += " updated"
                    self.posts.write_text(json.dumps([self.post]))
                elif edit == "media":
                    Image.new("RGB", (1080, 1350), "blue").save(self.root / "slides/slide_00.png")
                elif edit == "account":
                    self.account["owning_entity"] += " updated"; self.write_registry()
                else:
                    self.account["native_tiktok"]["mode"] = "direct"; self.write_registry()
                with self.assertRaisesRegex(TikTokError, "changed"):
                    self.service.approve(preview["ticket"], "fixture operator", content_preview_confirmed=True, express_consent=True)

    def test_post_approval_edit_blocks_worker(self):
        record = self.approve()
        self.post["caption"] += " changed"
        existing = manifest.get_post("p1", self.posts)
        existing["caption"] = self.post["caption"]
        self.posts.write_text(json.dumps([existing]))
        with self.assertRaisesRegex(TikTokError, "invalidated"):
            self.service.submit(record["native_attempt_id"], allow_network_writes=True)
        self.assertFalse(any("content/init" in p for p, _, _ in self.transport.calls))

    def test_native_rollout_and_explicit_submission_flags(self):
        for flag in ("submission_enabled", "developer_app_approved", "intended_use_approved",
                     "manual_launch_complete", "private_validation_approved"):
            self.registry["native_tiktok"][flag] = False; self.write_registry()
            with self.assertRaises(TikTokError): self.approve()
            self.registry["native_tiktok"][flag] = True
        self.write_registry()
        record = self.approve()
        with self.assertRaises(TikTokError): self.service.submit(record["native_attempt_id"])
        with patch.dict(os.environ, {"TIKTOK_ALLOW_SUBMISSIONS": "false"}):
            with self.assertRaises(TikTokError): self.service.submit(record["native_attempt_id"], allow_network_writes=True)

    def test_duplicate_creative_across_accounts_including_manual(self):
        self.post["distribution"] = [{"platform": "tiktok", "account_id": "different_account", "status": "posted"}]
        self.posts.write_text(json.dumps([self.post]))
        with self.assertRaisesRegex(distribution.DistributionError, "identical creative"):
            self.preview()

    def test_one_per_day_cap_and_jitter(self):
        record = self.approve()
        self.assertGreaterEqual(datetime.fromisoformat(record["scheduled_for"]).minute, 7)
        self.assertLessEqual(datetime.fromisoformat(record["scheduled_for"]).minute, 23)
        with self.assertRaisesRegex(distribution.DistributionError, "daily cap"):
            self.service.scheduled(self.account, self.post, self.clock.isoformat())
        planned = self.service.scheduled(self.account, self.post, (self.clock + timedelta(days=1)).isoformat())
        self.assertIn("2026-09-11", planned)

    def test_idempotent_init_and_status_projection(self):
        key = self.submit()
        self.service.submit(key, allow_network_writes=True)
        self.assertEqual(sum("content/init" in p for p, _, _ in self.transport.calls), 1)
        row = self.service.refresh_status(key)
        self.assertEqual(row["status"], "posted")
        self.assertEqual(row["platform_post_id"], "1234567")
        self.assertEqual(row["url"], "https://www.tiktok.com/@fixture_creator/photo/1234567")
        self.assertEqual(manifest.get_post("p1", self.posts)["distribution"][0]["publish_id"], "p_pub_url~v2.fixture")
        self.assertEqual(len(self.host.uploaded), 2)

    def test_uncertain_init_never_retried_after_restart(self):
        record = self.approve(); self.transport.fail_init = True
        key = record["native_attempt_id"]
        with self.assertRaisesRegex(TikTokError, "retry prohibited") as error:
            self.service.submit(key, allow_network_writes=True)
        self.assertNotIn("fixture-secret", str(error.exception))
        restarted = NativeTikTok(self.posts, self.regpath, self.root / "native", transport=self.transport,
            oauth=self.tokens, host=self.host, now=lambda: self.clock)
        restarted.submit(key, allow_network_writes=True)
        self.assertEqual(sum("content/init" in p for p, _, _ in self.transport.calls), 1)
        self.assertTrue(restarted.journal.get("attempts", key)["record"]["reconciliation_required"])

    def test_draft_scopes_and_inbox_is_not_posted(self):
        self.account["native_tiktok"]["mode"] = "draft"; self.write_registry()
        self.settings["draft_disclosure_acknowledged"] = True
        key = self.submit()
        init = next(body for path, body, _ in self.transport.calls if "content/init" in path)
        self.assertEqual(init["post_mode"], "MEDIA_UPLOAD")
        self.assertTrue(init["is_aigc"])
        self.assertNotIn("privacy_level", init["post_info"])
        self.assertTrue(any("video.upload" in scopes for _, _, scopes in self.tokens.requests))
        self.transport.status = {"status": "SEND_TO_USER_INBOX"}
        self.assertEqual(self.service.refresh_status(key)["status"], "queued")
        self.transport.status = {"status": "PUBLISH_COMPLETE"}
        self.assertIsNone(self.service.refresh_status(key)["url"])

    def test_status_failure_redacts_unknown_reason(self):
        key = self.submit()
        self.transport.status = {"status": "FAILED", "fail_reason": "fixture-secret-token"}
        row = self.service.refresh_status(key)
        self.assertEqual(row["status"], "failed")
        self.assertNotIn("fixture-secret-token", json.dumps(row))

    def test_worker_is_bounded_and_disabled_by_default(self):
        self.approve()
        self.registry["native_tiktok"]["scheduler_enabled"] = False; self.write_registry()
        self.assertEqual(self.service.worker(allow_network_writes=True), [])
        with self.assertRaises(TikTokError): self.service.worker(limit=101)

    def test_cancellation_requires_new_consent_and_cannot_cancel_claimed(self):
        row = self.approve()
        old_receipt = row["consent_id"]
        self.service.cancel_schedule(row["native_attempt_id"], "fixture operator")
        row = self.approve()
        self.assertNotEqual(row["consent_id"], old_receipt)
        self.assertTrue(self.service.journal.get("consents", old_receipt)["express_consent"])
        self.service.submit(row["native_attempt_id"], allow_network_writes=True)
        with self.assertRaises(TikTokError):
            self.service.cancel_schedule(row["native_attempt_id"], "fixture operator")

    def test_two_workers_claim_only_one_init(self):
        from concurrent.futures import ThreadPoolExecutor
        row = self.approve()
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: self.service.submit(row["native_attempt_id"],
                allow_network_writes=True), range(2)))
        self.assertEqual(len(results), 2)
        self.assertEqual(sum("content/init" in p for p, _, _ in self.transport.calls), 1)

    def test_manifest_concurrent_updates_do_not_drop_fields(self):
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(lambda i: manifest.update_post("p1", {f"field_{i}": i}, self.posts), range(12)))
        post = manifest.get_post("p1", self.posts)
        self.assertTrue(all(post[f"field_{i}"] == i for i in range(12)))

    def test_dashboard_auth_origin_and_explicit_receipt(self):
        app = Flask(__name__)
        app.config["TIKTOK_SERVICE_FACTORY"] = lambda: self.service
        tiktok_dashboard.register(app, lambda: self.posts)
        client = app.test_client()
        env = {"TIKTOK_OPERATOR_TOKEN": "x" * 40, "TIKTOK_OPERATOR_ID": "fixture operator",
               "TIKTOK_DASHBOARD_ORIGIN": "http://localhost"}
        with patch.dict(os.environ, env):
            self.assertEqual(client.get("/api/tiktok/config").status_code, 400)
            headers = {"Authorization": "Bearer " + "x" * 40, "Origin": "https://evil.test"}
            self.assertEqual(client.post("/api/tiktok/inspect", json={}, headers=headers).status_code, 400)
            headers["Origin"] = "http://localhost"
            response = client.post("/api/tiktok/preview", headers=headers, json={"post_id": "p1",
                "account_id": "gloskin_fixture", "settings": self.settings, "requested_at": self.clock.isoformat()})
            self.assertEqual(response.status_code, 200)
            ticket = response.json["ticket"]
            for i in range(2):
                image = client.get(f"/api/tiktok/preview/{ticket}/{i}", headers=headers)
                self.assertEqual(image.status_code, 200); image.close()
            response = client.post("/api/tiktok/approve", headers=headers, json={"ticket": ticket,
                "content_preview_confirmed": True, "express_consent": True})
            self.assertEqual(response.status_code, 200)
            consent = self.service.journal.get("consents", ticket)
            self.assertEqual(consent["operator"], "fixture operator")
            self.assertEqual(consent["digest"], digest(consent["snapshot"]))
            self.assertFalse(any("content/init" in p for p, _, _ in self.transport.calls))


class BoundaryTests(unittest.TestCase):
    def test_read_retries_are_bounded_write_retries_prohibited(self):
        calls = []
        def transport(*args, **kwargs):
            calls.append(args); return 503, {"error": {"message": "secret"}}
        with self.assertRaises(TikTokError) as error:
            call(transport, "/v2/post/publish/status/fetch/", {}, read_only=True, sleep=lambda _: None)
        self.assertEqual(len(calls), 3); self.assertNotIn("secret", str(error.exception))
        calls.clear()
        with self.assertRaises(TikTokError): call(transport, "/v2/post/publish/content/init/", {})
        self.assertEqual(len(calls), 1)

    def test_r2_prefix_and_mime_checks(self):
        base = "https://media.example.test/tiktok/"
        for value in ("http://media.example.test/tiktok/", "https://localhost/tiktok/",
                      "https://media.example.test.evil/tiktok/", "https://media.example.test/tiktok-other/",
                      base + "../", base + "?token=secret", "https://user:secret@media.example.test/tiktok/"):
            with self.subTest(value=value), self.assertRaises(MediaError): validate_prefix(value, base)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root / "slide.jpg"
            Image.new("RGB", (1080, 1350)).save(source)
            client = unittest.mock.Mock()
            host = R2MediaHost(base, base, client=client, bucket="fixture-bucket", cache=root,
                               probe=lambda url, mime: None)
            photos = host.plan([str(source)])
            host.upload(photos)
            self.assertEqual(client.put_object.call_args.kwargs["ContentType"], "image/jpeg")
            self.assertTrue(client.put_object.call_args.kwargs["Key"].startswith("tiktok/"))
            source.write_bytes(b"invalid")
            with self.assertRaises(MediaError): host.upload(photos)

    def test_encrypted_store_state_identity_and_refresh(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
            "TIKTOK_TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode(),
            "TIKTOK_CLIENT_KEY": "fixture-client", "TIKTOK_CLIENT_SECRET": "fixture-secret",
            "TIKTOK_REDIRECT_URI": "https://dashboard.example.test/api/tiktok/oauth/callback"}):
            store = TokenStore(tmp)
            data = {"open_id": "fixture-open", "access_token": "fixture-access", "refresh_token": "fixture-refresh",
                    "expires_in": 3600, "refresh_expires_in": 86400, "scope": "video.publish,video.upload"}
            exchanges = []
            def transport(path, body, token=None, **kwargs):
                exchanges.append(body)
                return 200, copy.deepcopy(data)
            oauth = OAuth(store, transport)
            from urllib.parse import parse_qs, urlsplit
            url = oauth.start("fixture", "fixture-open", "browser-nonce")
            state = parse_qs(urlsplit(url).query)["state"][0]
            oauth.finish(state, "fixture-code", "browser-nonce")
            with self.assertRaises(TikTokError): oauth.finish(state, "fixture-code", "browser-nonce")
            self.assertNotIn(b"fixture-access", store.path.read_bytes())
            saved = store.get("account:fixture"); saved["expires_at"] = 0; store.put("account:fixture", saved)
            data["refresh_token"] = "rotated-fixture"
            self.assertEqual(oauth.token("fixture", "fixture-open", {"video.publish"}), "fixture-access")
            self.assertEqual(store.get("account:fixture")["refresh_token"], "rotated-fixture")
            self.assertEqual(exchanges[-1]["grant_type"], "refresh_token")
            with self.assertRaises(TikTokError): oauth.token("fixture", "wrong-account", set())
            with self.assertRaises(TikTokError): oauth.token("fixture", "fixture-open", {"ungranted"})
            url = oauth.start("fixture", "fixture-open", "browser-nonce")
            state = parse_qs(urlsplit(url).query)["state"][0]
            with self.assertRaises(TikTokError): oauth.finish(state, "fixture-code", "other-browser")
            with patch.dict(os.environ, {"TIKTOK_REDIRECT_URI": "http://localhost/api/tiktok/oauth/callback"}):
                with self.assertRaises(MediaError): oauth.callback_url()


if __name__ == "__main__":
    unittest.main()
