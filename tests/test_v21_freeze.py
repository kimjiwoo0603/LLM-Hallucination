from __future__ import annotations

import unittest

from halo_runner.v21_freeze import approved


class V21FreezeTests(unittest.TestCase):
    def test_approved_requires_all_human_fields(self) -> None:
        decision = {"review_status": "approved", "fact_table_verified": 1, "question_approved": 1, "ready_for_freeze": "ready"}
        self.assertTrue(approved(decision))
        decision["question_approved"] = 0
        self.assertFalse(approved(decision))


if __name__ == "__main__":
    unittest.main()
