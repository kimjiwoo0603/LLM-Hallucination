from __future__ import annotations

import unittest

from halo_runner.v21_primary import CONDITIONS, run_condition


class V21PrimaryTests(unittest.TestCase):
    def test_all_conditions_produce_a_final_in_dry_run(self) -> None:
        record = {"candidate": {"source_text": "The source says 10."}, "packet_draft": {"question": "What does it say?"}}
        config = {"max_output_tokens": 20, "review_max_output_tokens": 10}
        for condition in CONDITIONS:
            final, trace, usages = run_condition(record, condition, config, dry_run=True)
            self.assertIn("final", trace)
            self.assertTrue(final)
            self.assertGreaterEqual(len(usages), 1)


if __name__ == "__main__":
    unittest.main()
