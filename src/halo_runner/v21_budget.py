"""Cost controls for HALO 2.1 before any API-backed experiment runs."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int
    output_tokens: int


def call_cost_usd(usage: TokenUsage, pricing: dict[str, Any]) -> float:
    """Return cost in USD from provider-reported token usage."""
    if usage.input_tokens < 0 or usage.output_tokens < 0:
        raise ValueError("Token counts cannot be negative")
    return (
        usage.input_tokens * float(pricing["input_usd_per_million_tokens"])
        + usage.output_tokens * float(pricing["output_usd_per_million_tokens"])
    ) / 1_000_000


def approximate_tokens(text: str) -> int:
    """Conservative English text estimate for preflight only, never final accounting."""
    return max(1, (len(text) + 2) // 3)


def projected_unit_cost_usd(
    source_text: str,
    question_text: str,
    pricing: dict[str, Any],
    *,
    final_output_tokens: int = 350,
    review_output_tokens: int = 250,
) -> float:
    """Estimate the four-condition (A/B/C/D) cost for one frozen source-question unit.

    The design performs 10 calls: A=1, B=3, C=3, D=3.  It deliberately
    overestimates prompt size by assuming that all later stages see source,
    draft, and review where applicable.
    """
    if final_output_tokens < 1 or review_output_tokens < 1:
        raise ValueError("Output token limits must be positive")
    base = approximate_tokens(source_text) + approximate_tokens(question_text) + 180
    draft = final_output_tokens
    review = review_output_tokens
    # A one-shot; B and C each draft/review/final; D draft/review/gated-final.
    input_tokens = (
        base
        + 2 * (base + (base + draft) + (base + draft + review))
        + base + (base + draft) + (base + review)
    )
    output_tokens = final_output_tokens + 3 * (final_output_tokens + review_output_tokens + final_output_tokens)
    return call_cost_usd(TokenUsage(input_tokens, output_tokens), pricing)


def projected_run_cost_usd(
    units: Iterable[tuple[str, str]], pricing: dict[str, Any], *, repetitions: int = 1
) -> float:
    if repetitions < 1:
        raise ValueError("repetitions must be positive")
    return sum(projected_unit_cost_usd(source, question, pricing) for source, question in units) * repetitions


def assert_within_budget(
    *, projected_new_cost_usd: float,
    spent_live_cost_usd: float,
    budget: dict[str, Any],
) -> None:
    """Block a run before a request is sent if it would breach the project cap."""
    if projected_new_cost_usd < 0 or spent_live_cost_usd < 0:
        raise ValueError("Costs cannot be negative")
    cap = float(budget["live_run_cap_usd"])
    total = projected_new_cost_usd + spent_live_cost_usd
    if total > cap:
        raise RuntimeError(
            f"HALO 2.1 budget guard blocked this run: projected ${total:.2f} exceeds "
            f"the ${cap:.2f} API-call ceiling."
        )
