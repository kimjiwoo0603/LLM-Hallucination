from __future__ import annotations

import unittest

from halo_runner.v21_execution import single_oneshot_prompt


class V21ExecutionTests(unittest.TestCase):
    def test_calibration_prompt_has_source_and_question_without_refusal_contract(self) -> None:
        record = {"candidate": {"source_text": "Source evidence."}, "packet_draft": {"question": "What happened?"}}
        prompt = single_oneshot_prompt(record)
        self.assertIn("Source evidence.", prompt)
        self.assertIn("What happened?", prompt)
        self.assertNotIn("cannot verify", prompt.lower())


if __name__ == "__main__":
    unittest.main()
