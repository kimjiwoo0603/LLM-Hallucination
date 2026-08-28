import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from halo_runner.v21_dataset import (
    build_candidate_artifacts,
    eligible_types,
    parse_type_quotas,
    select_balanced_source_pool,
)


class HaloV21DatasetTests(unittest.TestCase):
    def test_eligibility_marks_numeric_and_link_candidates(self):
        types, _ = eligible_types(
            ("The report lists 20 units and 30 units. " * 8) + "Details are available at https://example.org/report.",
            "QA",
        )
        self.assertIn("numeric_calculation", types)
        self.assertIn("citation_link", types)

    def test_short_data_to_text_is_numeric_only(self):
        types, notes = eligible_types(("The table reports 15 cases and 30 cases. " * 8), "Data2txt")
        self.assertEqual(types, ["numeric_calculation"])
        self.assertIn("short_structured_source_numeric_only", notes)

    def test_candidate_artifacts_are_deterministic_and_do_not_call_models(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source_info.jsonl"
            records = [
                {"source_id": "1", "task_type": "QA", "source": "demo", "source_info": "A report says 10 people joined and 20 left because of rain. https://example.org/a", "prompt": "Q"},
                {"source_id": "2", "task_type": "Summary", "source": "demo", "source_info": "Long enough " * 100 + "because the evidence changed.", "prompt": "Q"},
            ]
            source.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
            output = root / "out"
            manifest = build_candidate_artifacts(source, output, seed=7)
            self.assertEqual(manifest["candidate_records"], 2)
            self.assertTrue((output / "ragtruth_source_candidates.jsonl").exists())
            self.assertTrue((output / "candidate_manifest.json").exists())
            self.assertTrue((output / "candidate_review.template.csv").exists())

    def test_selection_uses_unique_sources_and_prioritizes_rare_type(self):
        candidates = [
            {"candidate_id": "a", "eligible_question_types": ["fact_event", "citation_link"]},
            {"candidate_id": "b", "eligible_question_types": ["fact_event"]},
        ]
        selected, manifest = select_balanced_source_pool(
            candidates, {"fact_event": 1, "citation_link": 1}, seed=7
        )
        self.assertEqual(manifest["unique_source_packets"], 2)
        self.assertEqual({row["candidate_id"] for row in selected}, {"a", "b"})
        linked = next(row for row in selected if row["candidate_id"] == "a")
        self.assertEqual(linked["selected_question_type"], "citation_link")

    def test_quota_parser_requires_explicit_valid_quota(self):
        self.assertEqual(parse_type_quotas(["fact_event=3"]), {"fact_event": 3})
        with self.assertRaises(ValueError):
            parse_type_quotas(["fact_event=0"])

    def test_selection_can_exclude_previously_used_source(self):
        candidates = [
            {"candidate_id": "a", "source_id": "old", "eligible_question_types": ["numeric_calculation"]},
            {"candidate_id": "b", "source_id": "new", "eligible_question_types": ["numeric_calculation"]},
        ]
        selected, _ = select_balanced_source_pool(
            candidates, {"numeric_calculation": 1}, seed=7, excluded_source_ids={"old"}
        )
        self.assertEqual(selected[0]["source_id"], "new")


if __name__ == "__main__":
    unittest.main()
