import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from halo_runner.v2 import (approved_benchmark, exact_mcnemar_pvalue, normalize_url, read_v2_labels,
                            validate_articles, validate_questions, wilson_interval, write_adjudication)
from halo_runner.v2_candidates import build_candidates


def article(article_id="A001", status="approved"):
    return {"article_id": article_id, "title": "제목", "article_text": (article_id + "가" * 1600), "source_name": "공식", "original_url": f"https://example.test/{article_id}?utm_source=x", "published_at": "2026-08-27", "category": "society", "review_status": status}


def question(question_id="Q001", article_id="A001", status="approved"):
    return {"question_id": question_id, "article_id": article_id, "question_type": "false_number", "difficulty": "HARD", "question": "질문", "false_premise": "허위 수치", "target_claim": "기사 밖 주장", "evidence_basis": "본문", "annotation_status": status}


class HaloV2Tests(unittest.TestCase):
    def test_url_normalization_removes_tracking(self):
        self.assertEqual(normalize_url("HTTPS://EXAMPLE.TEST/a/?utm_source=x&id=7#top"), "https://example.test/a?id=7")

    def test_candidate_validation_and_approved_selection(self):
        articles = [article("A001"), article("A002", "pending")]
        questions = [question("Q001", "A001"), question("Q002", "A002")]
        self.assertEqual(validate_articles(articles, 1500, 30000), [])
        self.assertEqual(validate_questions(questions, {"A001", "A002"}), [])
        selected_articles, selected_questions = approved_benchmark(articles, questions, 42, None)
        self.assertEqual([row["article_id"] for row in selected_articles], ["A001"])
        self.assertEqual([row["question_id"] for row in selected_questions], ["Q001"])

    def test_intervals_and_exact_mcnemar(self):
        low, high = wilson_interval(0, 12)
        self.assertEqual(low, 0.0)
        self.assertGreater(high, 0.2)
        self.assertEqual(exact_mcnemar_pvalue(0, 0), None)
        self.assertEqual(exact_mcnemar_pvalue(0, 4), 0.125)

    def test_adjudication_never_auto_resolves_disagreement(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fields = ["blind_id", "question_validity", "false_premise_validity", "hallucination", "accuracy", "usefulness", "abstention", "reviewer", "notes"]
            rows = [
                {"blind_id": "B00001", "question_validity": "1", "false_premise_validity": "1", "hallucination": "0", "accuracy": "2", "usefulness": "4", "abstention": "0", "reviewer": "A", "notes": ""},
                {"blind_id": "B00002", "question_validity": "1", "false_premise_validity": "1", "hallucination": "1", "accuracy": "0", "usefulness": "2", "abstention": "0", "reviewer": "A", "notes": ""},
            ]
            for name, change in (("a", None), ("b", ("B00002", "hallucination", "0"))):
                path = root / f"{name}.csv"
                out = [dict(row) for row in rows]
                if change:
                    next(row for row in out if row["blind_id"] == change[0])[change[1]] = change[2]
                    for row in out: row["reviewer"] = "B"
                with path.open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(out)
            agreed, disagreements = write_adjudication(root / "out", read_v2_labels(root / "a.csv"), read_v2_labels(root / "b.csv"))
            self.assertEqual((agreed, disagreements), (1, 1))
            with (root / "out" / "adjudication_required.csv").open(encoding="utf-8") as handle:
                self.assertEqual(len(list(csv.DictReader(handle))), 1)

    def test_budget_estimate_blocks_request_limit(self):
        completed = subprocess.run([sys.executable, str(ROOT / "run_halo_v2.py"), "estimate", "--questions", "10", "--repetitions", "3", "--conditions", "4", "--stages", "3", "--max-requests", "100"], capture_output=True, text=True, env={**__import__("os").environ, "PYTHONPATH": str(ROOT / "src")})
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(json.loads(completed.stdout)["estimated_requests"], 360)

    def test_legacy_conversion_creates_pending_candidates_only(self):
        articles, questions, manifest = build_candidates(ROOT)
        self.assertEqual(len(articles), 10)
        # The legacy corpus contains 33 base and 33 high-pressure questions.
        self.assertEqual(len(questions), 66)
        self.assertTrue(all(row["review_status"] == "pending" for row in articles))
        self.assertTrue(all(row["annotation_status"] == "pending" for row in questions))
        self.assertEqual(manifest["all_article_review_status"], "pending")


if __name__ == "__main__":
    unittest.main()
