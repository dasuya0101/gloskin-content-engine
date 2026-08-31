import unittest
from pathlib import Path
import tempfile

from PIL import Image, ImageDraw

import content_job
import publish
import screenshot_factory
import slideshow_maker
from brand_loader import load_brand


DISCLOSURE = "Illustrative example. Not a real-user outcome."


def synthetic_post(**overrides):
    post = {
        "post_id": "synthetic_test",
        "brand": "gloskin",
        "caption": f"Test caption\n\n{DISCLOSURE}",
        "slides": [
            {
                "kind": "hook", "text": "Test", "disclosure": DISCLOSURE,
                "disclosure_footer": DISCLOSURE,
                "disclosure_chip": "Illustrative",
                "requires_disclosure_chip": True,
            },
            {
                "kind": "cta", "text": "Test", "disclosure": DISCLOSURE,
                "disclosure_footer": DISCLOSURE,
                "requires_disclosure_chip": False,
            },
        ],
        "metadata": {
            "is_aigc": True,
            "synthetic_person": True,
            "composited_result": True,
            "illustrative_results": True,
            "illustrative_results_text": DISCLOSURE,
            "disclosure_layers": {
                "corner_chip": True,
                "slide_footer": True,
                "caption_line": True,
                "platform_aigc_flag": True,
            },
        },
        "compliance": {"status": "pass", "violations": []},
    }
    post.update(overrides)
    return post


class PublishGateTests(unittest.TestCase):
    def test_synthetic_slide_copy_uses_editable_iteration_fields(self):
        character = {
            "slug": "fixture_test",
            "spec": "synthetic test person",
            "source_type": "synthetic_fixture_set",
            "iterations": [{
                "scan_text": "Scan copy",
                "result_text": "Result copy",
                "progress_text": "Progress copy",
                "progress_subtext": "Results vary.",
            }],
        }
        brief = content_job.build_testimonial_brief(
            "test", Path("assets/fixture_test"), Path("before.png"),
            Path("after.png"), character, 0, load_brand("gloskin"))
        self.assertEqual(brief["slides"][1]["caption"], "Scan copy")
        self.assertEqual(brief["slides"][2]["caption"], "Result copy")
        self.assertEqual(brief["slides"][3]["text"], "Progress copy")
        self.assertEqual(brief["slides"][3]["subtext"], "Results vary.")
        self.assertIsNone(brief["slides"][0]["label"])
        self.assertIsNone(brief["slides"][3]["label"])

    def test_render_key_is_short_deterministic_and_unique(self):
        first = content_job.compact_render_key(
            {"variant_id": "var_20260826022945_b3745a83"}, "unused")
        repeated = content_job.compact_render_key(
            {"variant_id": "var_20260826022945_b3745a83"}, "unused")
        other = content_job.compact_render_key(
            {"variant_id": "var_20260826022945_8f10d5af"}, "unused")
        self.assertEqual(first, repeated)
        self.assertLessEqual(len(first), 24)
        self.assertNotEqual(first, other)

    def test_carousel_canvas_is_four_by_five(self):
        self.assertEqual((slideshow_maker.W, slideshow_maker.H), (1080, 1350))

    def test_phone_mockup_adds_frame_without_recoloring_screen(self):
        screen_color = (119, 87, 151)
        screen = Image.new("RGB", (200, 430), screen_color)
        device = slideshow_maker.phone_mockup(screen)
        self.assertGreater(device.width, screen.width)
        self.assertGreater(device.height, screen.height)
        self.assertEqual(device.getpixel((device.width // 2, device.height // 2))[:3],
                         screen_color)
        self.assertLess(max(device.getpixel((device.width // 2, 2))[:3]), 40)

    def test_scan_score_bar_matches_supplied_app_states(self):
        self.assertEqual(screenshot_factory.score_bar_color(54),
                         screenshot_factory.BAR_AMBER)
        self.assertEqual(screenshot_factory.score_bar_color(87),
                         screenshot_factory.BAR_GREEN)

    def test_scan_footer_cleanup_removes_clipped_copy(self):
        image = Image.new("RGB", (722, 1568), (205, 194, 230))
        draw = ImageDraw.Draw(image)
        draw.text((180, 1540), "Your skin is looking healthy", fill=(10, 10, 10))
        screenshot_factory.clean_scan_footer(image)
        footer = image.crop(screenshot_factory.REGIONS["footer_artifact"])
        self.assertGreater(min(channel for pixel in footer.getdata() for channel in pixel), 80)

    def test_missing_aigc_flag_is_a_non_overridable_block(self):
        post = synthetic_post()
        post["metadata"]["is_aigc"] = False
        with self.assertRaisesRegex(publish.PublishError, "is_aigc=true"):
            publish.require_compliance(post, override=True, reason="test override")

    def test_missing_caption_framing_blocks(self):
        with self.assertRaisesRegex(publish.PublishError, "caption is missing"):
            publish.require_compliance(synthetic_post(caption="Test caption"))

    def test_unlabeled_slide_blocks(self):
        post = synthetic_post()
        post["slides"][0]["disclosure"] = None
        post["slides"][0]["disclosure_footer"] = None
        with self.assertRaisesRegex(publish.PublishError, "disclosure footer"):
            publish.require_compliance(post)

    def test_missing_corner_chip_blocks(self):
        post = synthetic_post()
        post["slides"][0]["disclosure_chip"] = None
        with self.assertRaisesRegex(publish.PublishError, "disclosure chip"):
            publish.require_compliance(post)

    def test_disclosure_in_headline_blocks(self):
        post = synthetic_post()
        post["slides"][0]["text"] = "Illustrative results from a scan"
        with self.assertRaisesRegex(publish.PublishError, "headline"):
            publish.require_compliance(post)

    def test_synthetic_timeline_blocks(self):
        post = synthetic_post()
        post["slides"][0]["text"] = "Clearer-looking skin after 8 weeks"
        with self.assertRaisesRegex(publish.PublishError, "timeline"):
            publish.require_compliance(post)

    def test_before_after_label_blocks(self):
        post = synthetic_post()
        post["slides"][0]["label"] = "Before"
        with self.assertRaisesRegex(publish.PublishError, "before/after label"):
            publish.require_compliance(post)

    def test_complete_metadata_and_framing_pass_and_enter_payload(self):
        post = synthetic_post()
        publish.require_compliance(post)
        self.assertIs(publish.payload_for(post)["metadata"]["is_aigc"], True)

    def test_platform_payloads_carry_one_utm_tracked_cta(self):
        post = synthetic_post(
            tracking_code="glo_batch_01",
            caption=f"Test caption\n\nWhat's your Glo Score?\n\n{DISCLOSURE}",
        )
        payloads = publish.platform_payloads_for(post)
        for platform in ("tiktok", "instagram"):
            payload = payloads[platform]
            self.assertIn(f"utm_source={platform}", payload["cta"]["url"])
            self.assertIn("utm_campaign=glo_batch_01", payload["cta"]["url"])
            self.assertEqual(payload["caption"].count("What's your Glo Score?"), 1)
            self.assertIs(payload["metadata"]["is_aigc"], True)

    def test_non_synthetic_post_is_unchanged(self):
        post = synthetic_post(metadata={}, caption="Ordinary post", slides=[])
        publish.require_compliance(post)

    def test_platform_assets_make_instagram_jpegs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            slides = root / "slides"
            slides.mkdir()
            for index in range(2):
                Image.new("RGB", (1080, 1350), (40 + index, 80, 120)).save(
                    slides / f"slide_{index}.png")
            prepared = publish.prepare_platform_slide_assets(slides, root / "package")
            instagram = publish.media_file_list(prepared["instagram"])
            tiktok = publish.media_file_list(prepared["tiktok"])
            self.assertEqual(len(instagram), 2)
            self.assertTrue(all(Path(path).suffix == ".jpg" for path in instagram))
            self.assertEqual(len(tiktok), 2)
            publish.validate_carousel(instagram, "instagram")
            publish.validate_carousel(tiktok, "tiktok")


if __name__ == "__main__":
    unittest.main()
