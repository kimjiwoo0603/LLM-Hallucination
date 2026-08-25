import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from halo_runner.multi import retry_delay_seconds, run_batch


class MultiRunnerTests(unittest.TestCase):
    def test_rate_limit_retry_delay_uses_provider_hint(self):
        self.assertEqual(retry_delay_seconds("Please try again in 977ms.", 0), 1.0)
        self.assertEqual(retry_delay_seconds("Try again in 2.5s.", 0), 2.5)

    def test_external_high_pressure_question_set_is_recorded(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "config").mkdir()
            (root / "data").mkdir()
            (root / "results").mkdir()
            (root / "data" / "manifest.jsonl").write_text(
                json.dumps({"article_id": "A001", "dataset_path": "data/pack.json", "questions_path": "data/high.jsonl"}) + "\n",
                encoding="utf-8",
            )
            (root / "data" / "pack.json").write_text(
                json.dumps({"article_id": "A001", "source_type": "news_article", "article_text": "article", "questions": []}),
                encoding="utf-8",
            )
            (root / "data" / "high.jsonl").write_text(
                json.dumps({"question_id": "A001_HP_Q001", "type": "INFORMATION_ABSENCE", "condition": "HIGH_PRESSURE_INDUCTION", "induction_strategy": "FORCED_COMPLETION", "source_question_id": "A001_Q001", "target_error": "invented detail", "question": "question"}) + "\n",
                encoding="utf-8",
            )
            (root / "config" / "test.json").write_text(
                json.dumps({"dataset_manifest_path": "data/manifest.jsonl", "repetitions": 1, "agents": {"S1": {"provider": "openai", "model": "gpt-4.1", "api_key_env": "OPENAI_API_KEY", "temperature": 0, "max_tokens": 10}}, "stages": [{"id": "SINGLE_STAGE_1", "agent": "S1", "prompt_template": "{ARTICLE} {QUESTION}"}]}),
                encoding="utf-8",
            )
            run_dir = run_batch(root / "config" / "test.json", root / "results", "test", dry_run=True)
            record = json.loads((run_dir / "responses.jsonl").read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(record["question_condition"], "HIGH_PRESSURE_INDUCTION")
            self.assertEqual(record["source_question_id"], "A001_Q001")


if __name__ == "__main__":
    unittest.main()

