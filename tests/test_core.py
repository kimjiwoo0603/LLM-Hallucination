from pathlib import Path
import sys
import csv
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from halo_runner.core import render_prompt, sha256_text, write_blind_review_files


class CoreTests(unittest.TestCase):
    def test_render_prompt_includes_prior_stage(self):
        prompt = render_prompt("{QUESTION}|{SINGLE_STAGE_1}", {"QUESTION": "Q", "SINGLE_STAGE_1": "A"}, "S2")
        self.assertEqual(prompt, "Q|A")

    def test_missing_placeholder_is_clear_error(self):
        with self.assertRaisesRegex(ValueError, "unavailable placeholder"):
            render_prompt("{MISSING}", {}, "S1")

    def test_hash_is_stable(self):
        self.assertEqual(sha256_text("halo"), sha256_text("halo"))

    def test_blind_review_packet_hides_condition_and_model(self):
        records = [
            {
                "run_id": "run", "article_id": "A001", "question_id": "Q1", "repetition": 1,
                "stage": "MULTI_STAGE_3", "question_condition": "HIGH_PRESSURE", "agent": "M3",
                "provider": "openai", "model": "gpt-4.1", "question": "질문", "response": "답변",
                "response_sha256": sha256_text("답변"),
            }
        ]
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            write_blind_review_files(run_dir, records, {"A001": "기사 원문"})
            with (run_dir / "blind_review_packets.csv").open(encoding="utf-8") as handle:
                packet = list(csv.DictReader(handle))
            with (run_dir / "blind_key.coordinator_only.csv").open(encoding="utf-8") as handle:
                key = list(csv.DictReader(handle))
            self.assertEqual(packet[0], {"blind_id": "B0001", "article": "기사 원문", "question": "질문", "response": "답변"})
            self.assertEqual(key[0]["model"], "gpt-4.1")
            self.assertNotIn("model", packet[0])
            self.assertNotIn("question_condition", packet[0])


if __name__ == "__main__":
    unittest.main()

