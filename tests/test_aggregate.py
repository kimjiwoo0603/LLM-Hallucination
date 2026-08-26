import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aggregate_results import infer_blind_propagation, read_blind_key, read_labels
from prepare_blind_review import complete_pipeline_records, load_articles


class AggregateTests(unittest.TestCase):
    def test_incomplete_pipeline_is_excluded_from_blind_review(self):
        complete = [
            {"run_id": "run", "article_id": "A001", "question_id": "Q001", "repetition": 1, "stage": stage}
            for stage in ("M1", "M2", "M3")
        ]
        incomplete = [
            {"run_id": "run", "article_id": "A001", "question_id": "Q002", "repetition": 1, "stage": stage}
            for stage in ("M1", "M2")
        ]
        self.assertEqual(len(complete_pipeline_records(complete + incomplete)), 3)

    def test_blind_propagation_is_derived_after_labels(self):
        records = [
            {"run_id": "run", "article_id": "A001", "question_id": "Q001", "repetition": 1, "status": "LABELED", "hallucination": 1},
            {"run_id": "run", "article_id": "A001", "question_id": "Q001", "repetition": 1, "status": "LABELED", "hallucination": 1},
            {"run_id": "run", "article_id": "A001", "question_id": "Q001", "repetition": 1, "status": "LABELED", "hallucination": 0},
        ]
        infer_blind_propagation(records)
        self.assertEqual([record["propagation"] for record in records], ["Initial", "Maintained", "Removed"])

    def test_prepare_blind_review_mixes_multiple_runs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pack_path = root / "pack.json"
            manifest_path = root / "manifest.jsonl"
            pack_path.write_text(json.dumps({"article_id": "A001", "article_text": "기사 원문"}), encoding="utf-8")
            manifest_path.write_text(json.dumps({"article_id": "A001", "dataset_path": str(pack_path)}) + "\n", encoding="utf-8")
            run_dirs = []
            for index in (1, 2):
                run_dir = root / f"run-{index}"
                run_dir.mkdir()
                record = {"run_id": f"run-{index}", "article_id": "A001", "question_id": "Q001", "repetition": 1, "stage": "S3", "response_sha256": str(index), "question": "질문", "response": f"답변 {index}"}
                (run_dir / "responses.jsonl").write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
                run_dirs.append(run_dir)
            output_dir = root / "combined"
            subprocess.run(
                [sys.executable, str(ROOT / "prepare_blind_review.py"), "--run-dir", str(run_dirs[0]), "--run-dir", str(run_dirs[1]), "--output-dir", str(output_dir), "--dataset-manifest", str(manifest_path)],
                check=True,
                capture_output=True,
                text=True,
            )
            with (output_dir / "blind_review_packets.csv").open(encoding="utf-8") as handle:
                self.assertEqual(len(list(csv.DictReader(handle))), 2)

    def test_existing_run_article_loader_uses_pack_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pack_path = root / "pack.json"
            manifest_path = root / "manifest.jsonl"
            pack_path.write_text(json.dumps({"article_id": "A001", "article_text": "기사 원문"}), encoding="utf-8")
            manifest_path.write_text(json.dumps({"article_id": "A001", "dataset_path": str(pack_path)}) + "\n", encoding="utf-8")
            self.assertEqual(load_articles(manifest_path), {"A001": "기사 원문"})

    def test_blind_labels_require_and_use_separate_key(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            labels_path = root / "blind_labels.csv"
            key_path = root / "blind_key.csv"
            with labels_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["blind_id", "hallucination", "severity", "reviewer", "notes"])
                writer.writeheader()
                writer.writerow({"blind_id": "B0001", "hallucination": "1", "severity": "3", "reviewer": "R1", "notes": "근거 없음"})
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

