import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import api_server
import manifest
import video_queue


class BatchWorkflowTests(unittest.TestCase):
    def test_manifest_records_batch_and_workflow(self):
        with tempfile.TemporaryDirectory(dir=api_server.ROOT) as temp:
            posts_path = Path(temp) / "posts.json"
            post_id = manifest.record_post(
                brand="gloskin",
                batch_id="batch_test",
                workflow="slideshow",
                character={"slug": "person"},
                fmt="testimonial_beforeafter",
                hook="Test hook",
                slides=[],
                assets={},
                outputs={},
                path=posts_path,
            )
            post = manifest.get_post(post_id, posts_path)
            self.assertEqual(post["batch_id"], "batch_test")
            self.assertEqual(post["workflow"], "slideshow")
            self.assertFalse(post["legacy"])

    def test_batch_api_groups_slideshows_and_talking_heads(self):
        with tempfile.TemporaryDirectory(dir=api_server.ROOT) as temp:
            root = Path(temp)
            posts_path = root / "posts.json"
            runs_dir = root / "runs"
            queue_dir = root / "video_jobs"
            manifest.record_post(
                brand="gloskin",
                batch_id="slide_batch",
                workflow="slideshow",
                character={"slug": "person", "spec": "test person"},
                fmt="testimonial_beforeafter",
                hook="Test hook",
                slides=[],
                assets={},
                outputs={},
                path=posts_path,
            )
            video_queue.enqueue_job({
                "job_id": "video_job",
                "batch_id": "video_batch",
                "workflow": "talking_head",
                "brand": "gloskin",
                "slug": "person",
                "source_asset": "before",
                "script": "An approved test script for batch grouping.",
            }, queue_root=queue_dir)

            with mock.patch.object(api_server, "POSTS_FILE", posts_path), \
                    mock.patch.object(api_server, "RUNS_DIR", runs_dir), \
                    mock.patch.object(api_server, "VIDEO_JOBS_DIR", queue_dir):
                client = api_server.app.test_client()
                response = client.get("/api/batches?brand=gloskin")
                self.assertEqual(response.status_code, 200)
                batches = {batch["batch_id"]: batch for batch in response.get_json()}
                self.assertEqual(batches["slide_batch"]["workflow"], "slideshow")
                self.assertEqual(batches["slide_batch"]["post_count"], 1)
                self.assertEqual(batches["video_batch"]["workflow"], "talking_head")
                self.assertEqual(batches["video_batch"]["clip_count"], 1)

                detail = client.get("/api/batches/slide_batch")
                self.assertEqual(detail.status_code, 200)
                self.assertEqual(detail.get_json()["posts"][0]["batch_id"], "slide_batch")

    def test_run_preserves_selected_character_order_and_batch_id(self):
        with tempfile.TemporaryDirectory(dir=api_server.ROOT) as temp:
            root = Path(temp)
            roster_path = root / "roster.json"
            runs_dir = root / "runs"
            posts_path = root / "posts.json"
            roster_path.write_text(json.dumps({
                "template": "scan_results",
                "characters": [
                    {"slug": "person_one", "spec": "first person"},
                    {"slug": "person_two", "spec": "second person"},
                ],
            }), encoding="utf-8")

            with mock.patch.object(api_server, "ROSTER_FILE", roster_path), \
                    mock.patch.object(api_server, "RUNS_DIR", runs_dir), \
                    mock.patch.object(api_server, "POSTS_FILE", posts_path), \
                    mock.patch.object(api_server.threading, "Thread") as thread_cls:
                client = api_server.app.test_client()
                response = client.post("/api/runs", json={
                    "brand": "gloskin",
                    "formats": "slideshow",
                    "provider": "codex_local",
                    "placeholder": True,
                    "character_slugs": ["person_two", "person_one"],
                    "posts_per_avatar": 2,
                })
                self.assertEqual(response.status_code, 202)
                result = response.get_json()
                command = result["command"]
                self.assertEqual(result["config"]["workflow"], "slideshow")
                self.assertEqual(result["config"]["character_slugs"], ["person_two", "person_one"])
                self.assertEqual(command[command.index("--batch-id") + 1], result["run_id"])
                self.assertEqual(command[command.index("--character-slugs") + 1], "person_two,person_one")
                thread_cls.return_value.start.assert_called_once()
                batches = client.get("/api/batches?workflow=slideshow").get_json()
                queued = next(batch for batch in batches if batch["batch_id"] == result["run_id"])
                self.assertEqual(queued["status"], "queued")
                self.assertEqual(queued["post_count"], 0)


if __name__ == "__main__":
    unittest.main()
