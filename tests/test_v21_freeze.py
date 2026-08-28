from __future__ import annotations

import unittest

from halo_runner.v21_freeze import apply_numeric_calibration_revisions, approved, freeze_final_packets


class V21FreezeTests(unittest.TestCase):
    def test_approved_requires_all_human_fields(self) -> None:
        decision = {"review_status": "approved", "fact_table_verified": 1, "question_approved": 1, "ready_for_freeze": "ready"}
        self.assertTrue(approved(decision))
        decision["question_approved"] = 0
        self.assertFalse(approved(decision))

    def test_numeric_revision_changes_only_the_numeric_prompt(self) -> None:
        record = {
            "candidate": {"source_id": "13814"},
            "packet_draft": {"question": "old", "numeric_spec": {"expected_result": 8400}, "unchanged": "keep"},
        }
        revised = apply_numeric_calibration_revisions(record)
        self.assertEqual(record["packet_draft"]["question"], "old")
        self.assertEqual(revised["packet_draft"]["numeric_spec"]["expected_result"], "5.2% (rounded to one decimal place)")
        self.assertEqual(revised["packet_draft"]["unchanged"], "keep")
        self.assertEqual(revised["human_approval"]["round"], "numeric_recalibration_rereview")

    def test_final_freeze_rejects_development_overlap(self) -> None:
        packets = [{"candidate": {"source_id": "11945", "selected_question_type": "fact_event"}}] * 48
        with self.assertRaises(ValueError):
            freeze_final_packets(packets, approval_basis="user_confirmed_all", excluded_source_ids={"11945"})


if __name__ == "__main__":
    unittest.main()
