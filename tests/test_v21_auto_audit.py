from __future__ import annotations

import unittest

from halo_runner.v21_auto_audit import automatic_audit_prompt, parse_audit_response


class V21AutoAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.packet = {
            "candidate": {"source_text": "The source says the value is 10."},
            "packet_draft": {
                "question": "What is the value?", "fact_table": [], "official_urls": [],
                "numeric_spec": None, "validation_rules": {"fact": "Use only the source."},
            },
        }

    def test_audit_prompt_is_source_only_and_condition_blind(self) -> None:
        prompt = automatic_audit_prompt(self.packet, "The value is 20.")
        self.assertIn("The source says the value is 10.", prompt)
        self.assertIn("The value is 20.", prompt)
        self.assertNotIn("multi-agent", prompt.lower())

    def test_audit_response_requires_all_label_fields(self) -> None:
        payload = '{"fact_hallucination_candidate":1,"numeric_error_candidate":0,"causal_overreach_candidate":0,"citation_link_hallucination_candidate":0,"findings":[],"confidence":3}'
        self.assertEqual(parse_audit_response(payload)["fact_hallucination_candidate"], 1)
        with self.assertRaises(ValueError):
            parse_audit_response('{"fact_hallucination_candidate":1}')


if __name__ == "__main__":
    unittest.main()
