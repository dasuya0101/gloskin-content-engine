import unittest

import publish
import slideshow_maker


DISCLOSURE = "Illustrative example. Not a real-user outcome."


def synthetic_post(**overrides):
    post = {
        "post_id": "synthetic_test",
        "brand": "gloskin",
        "caption": f"Test caption\n\n{DISCLOSURE}",
        "slides": [
            {"kind": "hook", "text": "Test", "disclosure": DISCLOSURE},
            {"kind": "cta", "text": "Test", "disclosure": DISCLOSURE},
        ],
        "metadata": {
            "is_aigc": True,
            "synthetic_person": True,
            "composited_result": True,
            "illustrative_results": True,
            "illustrative_results_text": DISCLOSURE,
        },
        "compliance": {"status": "pass", "violations": []},
    }
    post.update(overrides)
    return post


class PublishGateTests(unittest.TestCase):
    def test_carousel_canvas_is_four_by_five(self):
        self.assertEqual((slideshow_maker.W, slideshow_maker.H), (1080, 1350))

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
        with self.assertRaisesRegex(publish.PublishError, "unlabeled synthetic"):
            publish.require_compliance(post)

    def test_complete_metadata_and_framing_pass_and_enter_payload(self):
        post = synthetic_post()
        publish.require_compliance(post)
        self.assertIs(publish.payload_for(post)["metadata"]["is_aigc"], True)

    def test_non_synthetic_post_is_unchanged(self):
        post = synthetic_post(metadata={}, caption="Ordinary post", slides=[])
        publish.require_compliance(post)


if __name__ == "__main__":
    unittest.main()
