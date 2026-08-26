import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import api_server
import heygen_adapter
import video_queue


class FakeHeyGenClient:
    def __init__(self):
        self.uploaded = []
        self.created = []

    def upload_asset(self, path, idempotency_key=None):
        self.uploaded.append((Path(path), idempotency_key))
        return "asset_test"

    def create_video(self, payload, idempotency_key):
        self.created.append((payload, idempotency_key))
        return {"video_id": "video_test", "status": "pending"}

    def get_video(self, video_id):
        return {
            "id": video_id,
            "status": "completed",
            "video_url": "https://files.heygen.test/video.mp4",
            "video_page_url": "https://app.heygen.test/video_test",
            "duration": 12.5,
        }

    def download(self, url, destination):
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"fake-mp4")
        return target


class HeyGenAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.queue = self.root / "video_jobs"
        portrait = self.root / "assets" / "person" / "after.png"
        portrait.parent.mkdir(parents=True)
        portrait.write_bytes(b"portrait")

    def tearDown(self):
        self.temp.cleanup()

    def enqueue(self, auth_mode="api_key"):
        job, _ = video_queue.enqueue_job({
            "job_id": f"job_{auth_mode}",
            "auth_mode": auth_mode,
            "slug": "person",
            "source_asset": "after",
            "portrait_path": "assets/person/after.png",
            "output_path": f"videos/person/{auth_mode}.mp4",
            "script": "This is an approved talking-head script.",
            "voice_id": "voice_test",
            "aspect_ratio": "9:16",
            "resolution": "1080p",
            "consent_confirmed": True,
        }, queue_root=self.queue)
        return job

    def test_direct_job_uploads_portrait_and_downloads_video(self):
        job = self.enqueue()
        client = FakeHeyGenClient()
        result = heygen_adapter.process_job(
            job["job_id"], queue_root=self.queue, workspace_root=self.root,
            client=client, sleep=lambda _: None)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["heygen_video_id"], "video_test")
        self.assertEqual(client.created[0][0]["type"], "image")
        self.assertEqual(client.created[0][0]["aspect_ratio"], "9:16")
        self.assertEqual(client.created[0][1], f"{job['job_id']}:video")
        self.assertEqual((self.root / result["output_path"]).read_bytes(), b"fake-mp4")

    def test_oauth_job_never_falls_through_to_api_transport(self):
        job = self.enqueue(auth_mode="oauth_mcp")
        with self.assertRaisesRegex(heygen_adapter.HeyGenError, "OAuth/MCP"):
            heygen_adapter.process_job(
                job["job_id"], queue_root=self.queue, workspace_root=self.root,
                client=FakeHeyGenClient())
        self.assertEqual(video_queue.find_job(job["job_id"], self.queue)[1]["status"], "queued")

    def test_workspace_path_escape_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "escapes workspace"):
            heygen_adapter.resolve_workspace_path("../outside.png", self.root)

    def test_matching_active_job_is_deduplicated(self):
        first = self.enqueue()
        duplicate, created = video_queue.enqueue_job({
            **first,
            "job_id": "another_id",
        }, queue_root=self.queue)
        self.assertFalse(created)
        self.assertEqual(duplicate["job_id"], first["job_id"])


class HeyGenApiTests(unittest.TestCase):
    def test_queue_requires_consent_and_accepts_local_character(self):
        with tempfile.TemporaryDirectory(dir=api_server.ROOT) as temp:
            root = Path(temp)
            roster_path = root / "roster.json"
            assets_dir = root / "assets"
            queue_dir = root / "video_jobs"
            roster_path.write_text(json.dumps({
                "template": "scan_results",
                "characters": [{"slug": "person", "spec": "test person"}],
            }), encoding="utf-8")
            portrait = assets_dir / "person" / "after.png"
            portrait.parent.mkdir(parents=True)
            portrait.write_bytes(b"portrait")
            payload = {
                "character_index": 0,
                "auth_mode": "oauth_mcp",
                "source_asset": "after",
                "script": "This is an approved test script.",
            }
            with mock.patch.object(api_server, "ROSTER_FILE", roster_path), \
                    mock.patch.object(api_server, "CHARACTER_ASSETS_DIR", assets_dir), \
                    mock.patch.object(api_server, "VIDEO_JOBS_DIR", queue_dir):
                client = api_server.app.test_client()
                denied = client.post("/api/heygen/jobs", json=payload)
                self.assertEqual(denied.status_code, 400)
                accepted = client.post("/api/heygen/jobs", json={
                    **payload, "consent_confirmed": True,
                })
                self.assertEqual(accepted.status_code, 202)
                job = accepted.get_json()["job"]
                self.assertEqual(job["auth_mode"], "oauth_mcp")
                self.assertEqual(job["workflow"], "talking_head")
                self.assertTrue(job["batch_id"].startswith("hgs_"))

    def test_batch_validates_every_portrait_before_queueing(self):
        with tempfile.TemporaryDirectory(dir=api_server.ROOT) as temp:
            root = Path(temp)
            roster_path = root / "roster.json"
            assets_dir = root / "assets"
            queue_dir = root / "video_jobs"
            roster_path.write_text(json.dumps({
                "template": "scan_results",
                "characters": [
                    {"slug": "person_one", "spec": "first test person"},
                    {"slug": "person_two", "spec": "second test person"},
                ],
            }), encoding="utf-8")
            for slug, names in {"person_one": ("before", "after"), "person_two": ("before",)}.items():
                folder = assets_dir / slug
                folder.mkdir(parents=True)
                for name in names:
                    (folder / f"{name}.png").write_bytes(b"portrait")
            jobs = [
                {
                    "character_index": index,
                    "source_asset": source,
                    "clip_role": source,
                    "script": f"Approved {source} script for person {index}.",
                }
                for index in range(2)
                for source in ("before", "after")
            ]
            payload = {
                "auth_mode": "oauth_mcp",
                "consent_confirmed": True,
                "jobs": jobs,
            }
            with mock.patch.object(api_server, "ROSTER_FILE", roster_path), \
                    mock.patch.object(api_server, "CHARACTER_ASSETS_DIR", assets_dir), \
                    mock.patch.object(api_server, "VIDEO_JOBS_DIR", queue_dir):
                client = api_server.app.test_client()
                rejected = client.post("/api/heygen/batches", json=payload)
                self.assertEqual(rejected.status_code, 409)
                self.assertEqual(video_queue.list_jobs(queue_dir), [])

                (assets_dir / "person_two" / "after.png").write_bytes(b"portrait")
                accepted = client.post("/api/heygen/batches", json=payload)
                self.assertEqual(accepted.status_code, 202)
                result = accepted.get_json()
                self.assertEqual(result["requested_count"], 4)
                self.assertEqual(result["created_count"], 4)
                self.assertEqual({job["batch_id"] for job in result["jobs"]}, {result["batch_id"]})


if __name__ == "__main__":
    unittest.main()
