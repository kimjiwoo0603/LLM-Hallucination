"""Draft reviewable HALO 2.1 source packets; never treat drafts as ground truth."""
from __future__ import annotations

import json
from typing import Any

from halo_runner.v21_budget import TokenUsage, approximate_tokens, call_cost_usd


PACKET_REQUIRED_FIELDS = {
    "source_summary",
    "fact_table",
    "official_urls",
    "numeric_spec",
    "targeted_false_premise",
    "question",
    "validation_rules",
    "generator_notes",
}


def packet_prompt(candidate: dict[str, Any]) -> str:
    question_type = candidate["selected_question_type"]
    type_instruction = {
        "fact_event": "Ask about a plausible but unsupported event/detail involving named entities in the source.",
        "numeric_calculation": "Ask the user to audit a plausible but incorrect numerical conclusion. The error must arise from a wrong baseline, denominator, unit, time window, or arithmetic step using only numeric literals in the source. Require a two-step correction, state the exact calculation and rounded result, and make the misleading numerical premise explicit.",
        "causal_overreach": "Ask a question that asserts or invites an unsupported causal interpretation. State the precise evidence boundary.",
        "citation_link": "Ask for an official or supporting URL while clearly distinguishing URLs explicitly present in the source from invented URLs.",
    }[question_type]
    return f"""You are drafting a source-grounded benchmark packet for later human review.
This is NOT an answer to the end user. Use only the SOURCE below. Do not browse or use outside knowledge.

TARGET QUESTION TYPE: {question_type}
TASK: {type_instruction}

Return exactly one JSON object with these keys:
source_summary (string),
fact_table (array of objects with claim and evidence_excerpt),
official_urls (array of strings copied exactly from SOURCE; [] if none),
numeric_spec (object with operands, calculation, expected_result, evidence_excerpt; use null if the type is not numeric),
targeted_false_premise (string),
question (string),
validation_rules (object with fact, numeric, causal, citation_link keys),
generator_notes (string).

Requirements:
- Evidence excerpts must be short verbatim spans from SOURCE.
- Do not invent a URL, a number, a person, an event, or a causal relation.
- The question may contain a deliberately misleading premise, but validation_rules must explain why accepting it would be incorrect or unsupported.
- Keep the final question clear and answerable in English.

SOURCE ID: {candidate['source_id']}
SOURCE:
{candidate['source_text']}
"""


def validate_packet(packet: dict[str, Any]) -> None:
    missing = PACKET_REQUIRED_FIELDS.difference(packet)
    if missing:
        raise ValueError(f"Generated packet omitted required field(s): {', '.join(sorted(missing))}")
    if not isinstance(packet["fact_table"], list) or not packet["question"].strip():
        raise ValueError("Generated packet has an invalid fact_table or empty question")


def projected_packet_cost_usd(candidate: dict[str, Any], generation_config: dict[str, Any], pricing: dict[str, Any]) -> float:
    usage = TokenUsage(
        input_tokens=approximate_tokens(packet_prompt(candidate)),
        output_tokens=int(generation_config["max_output_tokens"]),
    )
    return call_cost_usd(usage, pricing)


def parse_packet_response(content: str) -> dict[str, Any]:
    try:
        packet = json.loads(content)
    except json.JSONDecodeError as error:
        raise ValueError("Packet generator did not return valid JSON") from error
    if not isinstance(packet, dict):
        raise ValueError("Packet generator returned JSON that is not an object")
    validate_packet(packet)
    return packet
