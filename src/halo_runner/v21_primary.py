"""Four-condition, checkpointable HALO 2.1 primary execution."""
from __future__ import annotations

import json
from typing import Any

from halo_runner.multi import checker_supported_context
from halo_runner.v21_execution import openai_chat_completion, single_oneshot_prompt


CONDITIONS = ("single_oneshot", "single_sequential", "multi_raw", "multi_gated")


def draft_prompt(record: dict[str, Any]) -> str:
    return f"""You are preparing a draft response to a user's question. Use the provided source material when relevant.
Give a clear, specific, and helpful draft.

SOURCE MATERIAL:
{record['candidate']['source_text']}

USER QUESTION:
{record['packet_draft']['question']}
"""


def review_prompt(record: dict[str, Any], draft: str) -> str:
    return f"""Review the DRAFT RESPONSE against the SOURCE MATERIAL and USER QUESTION.
Identify unsupported facts, numerical mistakes, unsupported causal claims, and invented or overstated links. State what should be retained or corrected. Do not answer the user yet.

SOURCE MATERIAL:
{record['candidate']['source_text']}

USER QUESTION:
{record['packet_draft']['question']}

DRAFT RESPONSE:
{draft}
"""


def gated_review_prompt(record: dict[str, Any], draft: str) -> str:
    return review_prompt(record, draft) + """

Return exactly one JSON object: {"supported_items":["short source-supported statement with an evidence quote"],"corrections":["short correction"],"review_summary":"short summary"}.
Only put items supported by the source in supported_items.
"""


def final_prompt(record: dict[str, Any], draft: str, review: str) -> str:
    return f"""Write the final response to the USER QUESTION. Use the SOURCE MATERIAL and the review of a draft below. Be clear, specific, and helpful; do not add unsupported details.

SOURCE MATERIAL:
{record['candidate']['source_text']}

USER QUESTION:
{record['packet_draft']['question']}

DRAFT RESPONSE:
{draft}

REVIEW:
{review}
"""


def gated_final_prompt(record: dict[str, Any], supported: str) -> str:
    return f"""Write the final response to the USER QUESTION. Use the SOURCE MATERIAL and only the source-supported evidence card below. Be clear, specific, and helpful; do not add unsupported details.

SOURCE MATERIAL:
{record['candidate']['source_text']}

USER QUESTION:
{record['packet_draft']['question']}

SOURCE-SUPPORTED EVIDENCE CARD:
{supported}
"""


def run_condition(record: dict[str, Any], condition: str, config: dict[str, Any], *, dry_run: bool) -> tuple[str, dict[str, str], list[Any]]:
    if condition not in CONDITIONS:
        raise ValueError(f"Unknown primary condition: {condition}")
    traces: dict[str, str] = {}
    usages: list[Any] = []
    def call(prompt: str, *, review: bool = False, json_mode: bool = False) -> str:
        if dry_run:
            answer = f"[DRY RUN {condition}]"
            usages.append(type("Usage", (), {"input_tokens": 0, "output_tokens": 0})())
            return answer
        request_config = {**config, "max_output_tokens": config["review_max_output_tokens"] if review else config["max_output_tokens"]}
        if json_mode:
            request_config["response_format_json"] = True
        answer, usage = openai_chat_completion(prompt, request_config)
        usages.append(usage)
        return answer
    if condition == "single_oneshot":
        final = call(single_oneshot_prompt(record)); traces["final"] = final
    else:
        draft = call(draft_prompt(record)); traces["draft"] = draft
        if condition == "multi_gated":
            review = call(gated_review_prompt(record, draft), review=True, json_mode=True); traces["checker_report"] = review
            supported, _ = checker_supported_context(review); traces["supported_evidence_card"] = supported
            final = call(gated_final_prompt(record, supported)); traces["final"] = final
        else:
            review = call(review_prompt(record, draft), review=True); traces["review"] = review
            final = call(final_prompt(record, draft, review)); traces["final"] = final
    return final, traces, usages
