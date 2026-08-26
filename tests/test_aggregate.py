import csv
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aggregate_results import read_blind_key, read_labels


class AggregateTests(unittest.TestCase):
    def test_blind_labels_require_and_use_separate_key(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            labels_path = root / "blind_labels.csv"
            key_path = root / "blind_key.csv"
            with labels_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["blind_id", "hallucination", "severity", "propagation", "reviewer", "notes"])
                writer.writeheader()
                writer.writerow({"blind_id": "B0001", "hallucination": "1", "severity": "3", "propagation": "Initial", "reviewer": "R1", "notes": "근거 없음"})
            with key_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["blind_id", "article_id", "question_id", "repetition", "stage"])
                writer.writeheader()
                writer.writerow({"blind_id": "B0001", "article_id": "A001", "question_id": "Q001", "repetition": "1", "stage": "S3"})
            mode, labels = read_labels(labels_path)
            lookup = read_blind_key(key_path)
            self.assertEqual(mode, "blind")
            self.assertEqual(labels["B0001"]["hallucination"], "1")
            self.assertEqual(lookup[("A001", "Q001", 1, "S3")], "B0001")


if __name__ == "__main__":
    unittest.main()

