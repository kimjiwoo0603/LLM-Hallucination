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
from halo_runner.v2_candidates import apply_review_templates, attest_user_provided_snapshot_candidates
from halo_runner.v2_execution import build_primary_execution_configs
from halo_runner.v2_batches import build_pair_batches
from halo_runner.multi import run_batch


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

    def test_review_import_requires_complete_approval_and_writes_reviewed_copy(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            articles, questions = [article()], [question()]
            from halo_runner.core import write_jsonl
            write_jsonl(root / "articles.jsonl", articles); write_jsonl(root / "questions.jsonl", questions)
            article_fields = ["article_id", "review_status", "source_name", "original_url", "published_at", "category", "reviewer", "notes"]
            question_fields = ["question_id", "annotation_status", "question_type", "difficulty", "false_premise", "target_claim", "evidence_basis", "reviewer", "notes"]
            article_review = {"article_id": "A001", "review_status": "approved", "source_name": "공식", "original_url": "https://example.test/A001", "published_at": "2026-08-27", "category": "society", "reviewer": "R1", "notes": ""}
            question_review = {"question_id": "Q001", "annotation_status": "approved", "question_type": "false_number", "difficulty": "HARD", "false_premise": "허위 수치", "target_claim": "기사 밖 주장", "evidence_basis": "본문", "reviewer": "R1", "notes": ""}
            for filename, fields, row in (("article.csv", article_fields, article_review), ("question.csv", question_fields, question_review)):
                with (root / filename).open("w", encoding="utf-8-sig", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerow(row)
            report = apply_review_templates(root / "articles.jsonl", root / "questions.jsonl", root / "article.csv", root / "question.csv", root / "out")
            self.assertEqual(report["articles"]["approved"], 1)
            self.assertEqual(report["questions"]["approved"], 1)
            self.assertTrue((root / "out" / "articles.reviewed.jsonl").exists())

    def test_primary_config_builder_freezes_the_same_model_2x2_design(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            freeze = build_primary_execution_configs(root / "benchmark", root / "configs", "halo-v2-test", repetitions=2)
            self.assertEqual([row["condition_id"] for row in freeze["conditions"]], ["single_raw", "single_gated", "multi_raw", "multi_gated"])
            config = json.loads((root / "configs" / "halo_v2_primary.multi_gated.json").read_text(encoding="utf-8"))
            self.assertEqual(config["dataset_format"], "halo_v2_benchmark")
            self.assertEqual(config["stages"][-1]["input_policy"], "checker_supported_only")

    def test_v2_benchmark_runs_in_dry_mode_after_freeze(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            benchmark = root / "benchmark"; benchmark.mkdir()
            from halo_runner.core import read_jsonl, write_jsonl
            write_jsonl(benchmark / "articles.jsonl", [article()])
            write_jsonl(benchmark / "questions.jsonl", [question()])
            build_primary_execution_configs(benchmark, root / "configs" / "frozen", "halo-v2-test", repetitions=1)
            run_dir = run_batch(root / "configs" / "frozen" / "halo_v2_primary.multi_gated.json", root / "results", "dry", dry_run=True)
            records = read_jsonl(run_dir / "responses.jsonl")
            self.assertEqual(len(records), 3)
            self.assertEqual(records[-1]["m3_input_policy"], "checker_supported_only")
            self.assertEqual(records[-1]["question_type"], "false_number")

    def test_snapshot_attestation_preserves_no_url_limitation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            from halo_runner.core import read_jsonl, write_jsonl
            article_row, question_row = article(status="pending"), question(status="pending")
            article_row["source_article_id"] = "A001"; question_row["target_claim"] = "기사 밖 세부사항"
            write_jsonl(root / "articles.jsonl", [article_row]); write_jsonl(root / "questions.jsonl", [question_row])
            report = attest_user_provided_snapshot_candidates(root / "articles.jsonl", root / "questions.jsonl", root / "out", "research-team", "v2-test")
            attested = read_jsonl(root / "out" / "articles.attested.jsonl")[0]
            self.assertEqual(attested["review_status"], "approved")
            self.assertTrue(attested["original_url"].startswith("snapshot://"))
            self.assertIn("no_public_url", report["provenance_policy"])

    def test_batch_plan_pairs_base_and_pressure_questions_before_runs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); benchmark = root / "benchmark"; benchmark.mkdir()
            from halo_runner.core import write_jsonl
            write_jsonl(benchmark / "articles.jsonl", [article("A001"), article("A002")])
            rows = []
            for article_id in ("A001", "A002"):
                for number in range(2):
                    source_id = f"{article_id}_Q{number}"
                    for origin in ("base", "high_pressure"):
                        row = question(f"{source_id}_{origin}", article_id)
                        row.update({"source_question_id": source_id, "candidate_origin": origin, "annotation_status": "approved"})
                        rows.append(row)
            write_jsonl(benchmark / "questions.jsonl", rows)
            plan = build_pair_batches(benchmark, root / "batches", 7, repetitions=3)
            self.assertEqual(plan["batches"][0]["question_count"], 4)
            self.assertEqual(plan["batches"][0]["base_questions"], 2)
            self.assertEqual(plan["batches"][0]["high_pressure_questions"], 2)
            self.assertEqual(plan["batches"][0]["estimated_requests"], 144)


if __name__ == "__main__":
    unittest.main()
