import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import api_server
import character_factory
import image_router
import image_variants


def prompt_snapshot():
    config = character_factory.load_prompt_config(
        api_server.ROOT / "prompts" / "gloskin" / "image_character.json")
    return {
        "before_template": config["before_template"],
        "opening_style": "selfie",
        "opening_prompt": config["opening_prompt"],
        "scan_prompt": config["scan_prompt"],
        "after_prompt": config["after_prompt"],
        "product_style": "none",
        "product_prop_prompt": config["product_prop_prompt"],
        "product_slide_caption": config["product_slide_caption"],
    }


class ImageProviderTests(unittest.TestCase):
    def test_provider_status_exposes_names_not_secret_values(self):
        rows = image_router.list_providers()
        openai = next(row for row in rows if row["id"] == "openai")
        self.assertNotIn("api_key", openai)
        self.assertNotIn("key_value", openai)
        serialized = json.dumps(rows)
        self.assertNotIn("sk-", serialized)
        custom = next(row for row in rows if row["id"] == "custom")
        self.assertIn("missing_edit_env", custom)


class ImageVariantTests(unittest.TestCase):
    def test_variant_copies_unselected_assets_and_plans_only_selected_asset(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "assets" / "person"
            source.mkdir(parents=True)
            for name in ("before", "scan", "after"):
                (source / f"{name}.png").write_bytes(name.encode("ascii"))

            variant, plan = image_variants.create_variant(
                metadata_root=root / "metadata",
                assets_root=root / "assets",
                source_dir=source,
                source_character={
                    "slug": "person",
                    "spec": "woman, early 20s, East Asian",
                    "before_score": 54,
                    "after_score": 87,
                },
                brand="gloskin",
                project_id="gloskin_main",
                name="After test",
                provider="codex_local",
                selected_assets=["after"],
                prompt_snapshot=prompt_snapshot(),
                opening_style="selfie",
                product_style="none",
            )
            asset_dir = Path(variant["asset_dir"])
            self.assertTrue((asset_dir / "before.png").exists())
            self.assertTrue((asset_dir / "scan.png").exists())
            self.assertFalse((asset_dir / "after.png").exists())
            self.assertEqual([target["name"] for target in plan["targets"]], ["after"])
            self.assertEqual(plan["targets"][0]["mode"], "edit")
            self.assertEqual(
                Path(plan["targets"][0]["reference_path"]), asset_dir / "before.png")
            self.assertEqual(
                image_variants.get_variant(root / "metadata", variant["variant_id"])["name"],
                "After test",
            )

    def test_dashboard_queues_variant_without_calling_an_image_api(self):
        with tempfile.TemporaryDirectory(dir=api_server.ROOT) as temp:
            root = Path(temp)
            assets = root / "assets"
            person = assets / "person"
            person.mkdir(parents=True)
            for name in ("before", "scan", "after"):
                (person / f"{name}.png").write_bytes(name.encode("ascii"))
            roster = root / "roster.json"
            roster.write_text(json.dumps({
                "template": "scan_results",
                "characters": [{
                    "slug": "person",
                    "spec": "woman, early 20s, East Asian",
                    "before_score": 54,
                    "after_score": 87,
                }],
            }), encoding="utf-8")

            with mock.patch.object(api_server, "ROSTER_FILE", roster), \
                    mock.patch.object(api_server, "CHARACTER_ASSETS_DIR", assets), \
                    mock.patch.object(api_server, "VARIANTS_DIR", root / "variants"), \
                    mock.patch.object(api_server, "IMAGE_JOBS_DIR", root / "image_jobs"), \
                    mock.patch.object(api_server, "PROJECTS_FILE", root / "projects.json"), \
                    mock.patch.object(api_server.image_router, "generate") as generate:
                response = api_server.app.test_client().post("/api/image-variants", json={
                    "brand": "gloskin",
                    "project_id": "gloskin_main",
                    "source_asset_slug": "person",
                    "name": "Queued after",
                    "provider": "codex_local",
                    "selected_assets": ["after"],
                    "opening_style": "selfie",
                    "product_style": "none",
                    "prompt_snapshot": prompt_snapshot(),
                })
                self.assertEqual(response.status_code, 202)
                result = response.get_json()
                self.assertEqual(result["variant"]["status"], "queued")
                self.assertEqual(result["job"]["targets"][0]["name"], "after")
                generate.assert_not_called()

    def test_run_uses_project_variant_in_a_run_scoped_roster(self):
        with tempfile.TemporaryDirectory(dir=api_server.ROOT) as temp:
            root = Path(temp)
            assets = root / "assets"
            source = assets / "person"
            source.mkdir(parents=True)
            for name in ("before", "scan", "after"):
                (source / f"{name}.png").write_bytes(name.encode("ascii"))
            roster = root / "roster.json"
            roster.write_text(json.dumps({
                "template": "scan_results",
                "characters": [{"slug": "person", "spec": "test person"}],
            }), encoding="utf-8")
            variant, _ = image_variants.create_variant(
                metadata_root=root / "variants",
                assets_root=assets,
                source_dir=source,
                source_character={"slug": "person", "spec": "test person"},
                brand="gloskin",
                project_id="gloskin_main",
                name="Ready variant",
                provider="codex_local",
                selected_assets=["after"],
                prompt_snapshot=prompt_snapshot(),
                opening_style="selfie",
                product_style="none",
            )
            Path(variant["asset_dir"], "after.png").write_bytes(b"after variant")
            variant["status"] = "ready"
            image_variants.save_variant(root / "variants", variant)

            with mock.patch.object(api_server, "ROSTER_FILE", roster), \
                    mock.patch.object(api_server, "CHARACTER_ASSETS_DIR", assets), \
                    mock.patch.object(api_server, "VARIANTS_DIR", root / "variants"), \
                    mock.patch.object(api_server, "IMAGE_JOBS_DIR", root / "image_jobs"), \
                    mock.patch.object(api_server, "PROJECTS_FILE", root / "projects.json"), \
                    mock.patch.object(api_server, "RUNS_DIR", root / "runs"), \
                    mock.patch.object(api_server, "POSTS_FILE", root / "posts.json"), \
                    mock.patch.object(api_server.threading, "Thread") as thread_cls:
                response = api_server.app.test_client().post("/api/runs", json={
                    "brand": "gloskin",
                    "project_id": "gloskin_main",
                    "formats": "slideshow",
                    "provider": "codex_local",
                    "placeholder": True,
                    "character_slugs": [variant["asset_slug"]],
                })
                self.assertEqual(response.status_code, 202)
                run = response.get_json()
                roster_path = api_server.ROOT / run["config"]["run_roster_path"]
                run_roster = json.loads(roster_path.read_text(encoding="utf-8"))
                self.assertEqual(run_roster["characters"][0]["slug"], variant["asset_slug"])
                self.assertEqual(run_roster["characters"][0]["variant_id"], variant["variant_id"])
                self.assertEqual(
                    run["command"][run["command"].index("--roster") + 1],
                    run["config"]["run_roster_path"],
                )
                thread_cls.return_value.start.assert_called_once()


if __name__ == "__main__":
    unittest.main()
