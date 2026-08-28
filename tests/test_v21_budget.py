from __future__ import annotations

import unittest

from halo_runner.v21_budget import TokenUsage, assert_within_budget, call_cost_usd, projected_unit_cost_usd


PRICING = {"input_usd_per_million_tokens": 2.0, "output_usd_per_million_tokens": 8.0}


class V21BudgetTests(unittest.TestCase):
    def test_actual_cost_uses_token_usage(self) -> None:
        self.assertAlmostEqual(call_cost_usd(TokenUsage(1_000_000, 1_000_000), PRICING), 10.0)

    def test_projected_unit_cost_is_positive(self) -> None:
        cost = projected_unit_cost_usd("Source text. " * 100, "What happened?", PRICING)
        self.assertGreater(cost, 0)

    def test_budget_guard_blocks_excess(self) -> None:
        budget = {"live_run_cap_usd": 18.0}
        with self.assertRaisesRegex(RuntimeError, "budget guard"):
            assert_within_budget(projected_new_cost_usd=2.1, spent_live_cost_usd=16.0, budget=budget)


if __name__ == "__main__":
    unittest.main()
