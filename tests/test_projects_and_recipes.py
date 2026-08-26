import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import api_server
import content_job
import creative_recipes
import manifest
import project_store


class ProjectStoreTests(unittest.TestCase):
    def test_defaults_and_named_projects_have_separate_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / "projects.json"
            defaults = project_store.load_projects(config, ["gloskin", "vendrarx"])
            self.assertEqual(
                {row["project_id"] for row in defaults},
                {"gloskin_main", "vendrarx_main"},
            )
            project = project_store.create_project(
                config, ["gloskin", "vendrarx"], name="UGC Tests", brand="gloskin")
            self.assertEqual(project["project_id"], "gloskin_ugc_tests")
            paths = project_store.output_paths(root, "gloskin", project["project_id"])
            self.assertEqual(
                paths["posts"], root / "posts" / "gloskin" / "gloskin_ugc_tests")
            with self.assertRaisesRegex(ValueError, "belongs to gloskin"):
                project_store.require_project(
                    config, ["gloskin", "vendrarx"], project["project_id"], "vendrarx")

    def test_legacy_manifest_rows_map_to_main_project(self):
        row = manifest.normalize_post({"brand": "gloskin", "format": "text_native"})
        self.assertEqual(row["project_id"], "gloskin_main")


class RecipeTests(unittest.TestCase):
    def test_recipe_round_trip_preserves_editable_setup(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "recipes"
            saved = creative_recipes.save_recipe(folder, {
                "name": "Winning acne hook",
                "brand": "gloskin",
                "project_id": "gloskin_main",
                "workflow": "slideshow",
                "setup": {
                    "character_slugs": ["person"],
                    "hook_overrides": {"person": ["Original hook", "Variant hook"]},
                },
                "prompt_snapshot": {"before_template": "Exact prompt"},
            })
            loaded = creative_recipes.get_recipe(folder, saved["recipe_id"])
            self.assertEqual(
                loaded["setup"]["hook_overrides"]["person"][1], "Variant hook")
            self.assertEqual(loaded["prompt_snapshot"]["before_template"], "Exact prompt")
            self.assertTrue(creative_recipes.delete_recipe(folder, saved["recipe_id"]))
            self.assertEqual(creative_recipes.list_recipes(folder), [])

    def test_batch_recipe_captures_generated_hooks_and_copy(self):
        with tempfile.TemporaryDirectory(dir=api_server.ROOT) as temp:
            root = Path(temp)
            posts_path = root / "posts.json"
            recipes_dir = root / "recipes"
            runs_dir = root / "runs"
            queue_dir = root / "video_jobs"
            manifest.record_post(
                brand="gloskin",
                project_id="gloskin_main",
                batch_id="batch_source",
                workflow="slideshow",
                character={"slug": "person", "spec": "test person"},
                fmt="testimonial_beforeafter",
                hook="Exact generated hook",
                slides=[{"kind": "hook", "text": "Exact generated hook"}],
                assets={},
                outputs={},
                caption="Exact generated caption",
                path=posts_path,
            )
            with mock.patch.object(api_server, "POSTS_FILE", posts_path), \
                    mock.patch.object(api_server, "RECIPES_DIR", recipes_dir), \
                    mock.patch.object(api_server, "RUNS_DIR", runs_dir), \
                    mock.patch.object(api_server, "VIDEO_JOBS_DIR", queue_dir):
                client = api_server.app.test_client()
                response = client.post("/api/recipes", json={
                    "source_batch_id": "batch_source",
                    "name": "Saved generated batch",
                })
                self.assertEqual(response.status_code, 201)
                recipe = response.get_json()
                self.assertEqual(
                    recipe["setup"]["hook_overrides"]["person"],
                    ["Exact generated hook"],
                )
                self.assertEqual(
                    recipe["creative_snapshot"][0]["caption"],
                    "Exact generated caption",
                )


class RunSetupTests(unittest.TestCase):
    def test_project_run_snapshots_prompts_and_hook_edits_without_starting_worker(self):
        with tempfile.TemporaryDirectory(dir=api_server.ROOT) as temp:
            root = Path(temp)
            projects_path = root / "projects.json"
            runs_dir = root / "runs"
            roster_path = root / "roster.json"
            posts_path = root / "posts.json"
            project_store.create_project(
                projects_path, ["gloskin", "vendrarx"],
                name="Campaign A", brand="gloskin")
            roster_path.write_text(json.dumps({
                "template": "scan_results",
                "characters": [{"slug": "person", "spec": "test person"}],
            }), encoding="utf-8")
            prompt_snapshot = {
                "before_template": "Before {age} {ethnicity} {gender}",
                "opening_style": "selfie",
                "opening_prompt": "",
                "scan_prompt": "Scan {age} {ethnicity} {gender}",
                "after_prompt": "After {age} {ethnicity} {gender}",
                "product_style": "none",
                "product_prop_prompt": "",
                "product_slide_caption": "Product caption",
            }
            with mock.patch.object(api_server, "PROJECTS_FILE", projects_path), \
                    mock.patch.object(api_server, "RUNS_DIR", runs_dir), \
                    mock.patch.object(api_server, "ROSTER_FILE", roster_path), \
                    mock.patch.object(api_server, "POSTS_FILE", posts_path), \
                    mock.patch.object(api_server.threading, "Thread") as thread_cls:
                client = api_server.app.test_client()
                response = client.post("/api/runs", json={
                    "brand": "gloskin",
                    "project_id": "gloskin_campaign_a",
                    "formats": "slideshow",
                    "provider": "codex_local",
                    "placeholder": True,
                    "character_slugs": ["person"],
                    "posts_per_avatar": 2,
                    "hook_overrides": {"person": ["Edited one", "Edited two"]},
                    "prompt_snapshot": prompt_snapshot,
                })
                self.assertEqual(response.status_code, 202)
                run = response.get_json()
                command = run["command"]
                self.assertEqual(run["config"]["project_id"], "gloskin_campaign_a")
                self.assertIn("output/gloskin/gloskin_campaign_a", command)
                self.assertIn("screenshots/gloskin/gloskin_campaign_a", command)
                prompt_path = api_server.ROOT / run["config"]["prompt_snapshot_path"]
                input_path = api_server.ROOT / run["config"]["run_input_path"]
                self.assertEqual(json.loads(prompt_path.read_text(encoding="utf-8")), prompt_snapshot)
                self.assertEqual(
                    json.loads(input_path.read_text(encoding="utf-8"))["hook_overrides"]["person"],
                    ["Edited one", "Edited two"],
                )
                thread_cls.return_value.start.assert_called_once()

    def test_hook_overrides_replace_only_named_iterations(self):
        characters = [{
            "slug": "person",
            "iterations": [{"hook": "Old one", "after_text": "Keep this"}],
        }]
        content_job.apply_hook_overrides(
            characters, {"person": ["New one", "New two"]})
        self.assertEqual(characters[0]["iterations"][0]["hook"], "New one")
        self.assertEqual(characters[0]["iterations"][0]["after_text"], "Keep this")
        self.assertEqual(characters[0]["iterations"][1]["hook"], "New two")


if __name__ == "__main__":
    unittest.main()
