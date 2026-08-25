from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from halo_runner.core import render_prompt, sha256_text


class CoreTests(unittest.TestCase):
    def test_render_prompt_includes_prior_stage(self):
        prompt = render_prompt("{QUESTION}|{SINGLE_STAGE_1}", {"QUESTION": "Q", "SINGLE_STAGE_1": "A"}, "S2")
        self.assertEqual(prompt, "Q|A")

    def test_missing_placeholder_is_clear_error(self):
        with self.assertRaisesRegex(ValueError, "unavailable placeholder"):
            render_prompt("{MISSING}", {}, "S1")

    def test_hash_is_stable(self):
        self.assertEqual(sha256_text("halo"), sha256_text("halo"))


if __name__ == "__main__":
    unittest.main()
