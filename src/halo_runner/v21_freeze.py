"""Freeze a human-approved HALO 2.1 development benchmark without API calls."""
from __future__ import annotations

from collections import Counter
from typing import Any

from halo_runner.core import sha256_text, utc_now

REREVIEWED_SOURCE_IDS = {"11945", "13979", "14679", "14267"}
REPLACED_SOURCE_ID = "15235"
NUMERIC_RECALIBRATION_SOURCE_IDS = {"11959", "13814", "14068", "14267"}


def approved(decision: dict[str, Any]) -> bool:
    return (
        decision.get("review_status") == "approved"
        and decision.get("fact_table_verified") == 1
        and decision.get("question_approved") == 1
        and decision.get("ready_for_freeze") == "ready"
    )


def apply_human_requested_packet_corrections(record: dict[str, Any]) -> dict[str, Any]:
    """Apply only the explicit corrections recorded in the first human review."""
    copy = {**record, "packet_draft": {**record["packet_draft"]}}
    packet = copy["packet_draft"]
    source_id = str(copy["candidate"]["source_id"])
    if source_id == "11945":
        packet["targeted_false_premise"] = (
            "The systematic abuse and enslavement of women by ISIS and Boko Haram directly caused "
            "their territorial control and success in building a caliphate."
        )
    elif source_id == "13979":
        packet["fact_table"] = [
            {"claim": "The Las Vegas Grand Prix marked the return of a Formula One Grand Prix event in Las Vegas after forty years.", "evidence_excerpt": "The Las Vegas Grand Prix marks the return of a Formula One Grand Prix event in forty years."},
            {"claim": "The approved design features a high-speed 14-turn circuit.", "evidence_excerpt": "The approved design features a spectacular, high-speed 14-turn high-speed circuit."},
            {"claim": "The night race is intended to help drivers avoid searing heat and provide city lights as a backdrop.", "evidence_excerpt": "The night race will help drivers beat the searing heat while allowing the spectacular Las Vegas city lights as a backdrop."},
        ]
        packet["numeric_spec"] = None
    elif source_id == "14679":
        packet["fact_table"] = [
            {"claim": "The source lists the Music attribute as None.", "evidence_excerpt": "'Music': None"},
            {"claim": "The source lists free WiFi as an attribute.", "evidence_excerpt": "'WiFi': 'free'"},
        ]
    return copy


def freeze_development_packets(
    initial_records: list[dict[str, Any]],
    replacement_records: list[dict[str, Any]],
    review_records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    decisions = {(str(row["source_id"]), row["review_round"]): row for row in review_records}
    for source_id in REREVIEWED_SOURCE_IDS:
        decision = decisions.get((source_id, "rereview"))
        if not decision or not approved(decision):
            raise ValueError(f"Required re-review is not fully approved: {source_id}")

    initial_ready = {
        str(row["source_id"])
        for row in review_records
        if row["review_round"] == "initial" and row.get("ready_for_freeze") == "ready"
        and row.get("fact_table_verified") == 1 and row.get("question_approved") == 1
    }
    selected: list[dict[str, Any]] = []
    for record in initial_records:
        source_id = str(record["candidate"]["source_id"])
        if source_id in initial_ready or source_id in (REREVIEWED_SOURCE_IDS - {"14267"}):
            frozen = apply_human_requested_packet_corrections(record)
            frozen["human_approval"] = {"round": "rereview" if source_id in REREVIEWED_SOURCE_IDS else "initial"}
            selected.append(frozen)

    for record in replacement_records:
        source_id = str(record["candidate"]["source_id"])
        if source_id == "14267":
            frozen = {**record, "human_approval": {"round": "rereview"}}
            selected.append(frozen)

    source_ids = [str(row["candidate"]["source_id"]) for row in selected]
    if len(selected) != 16 or len(source_ids) != len(set(source_ids)) or REPLACED_SOURCE_ID in source_ids:
        raise ValueError("Frozen development set must contain 16 unique sources with the rejected source excluded")
    type_counts = Counter(row["candidate"]["selected_question_type"] for row in selected)
    expected = {"fact_event": 4, "numeric_calculation": 4, "causal_overreach": 4, "citation_link": 4}
    if dict(type_counts) != expected:
        raise ValueError(f"Frozen development set is not balanced: {dict(type_counts)}")
    selected.sort(key=lambda row: (row["candidate"]["selected_question_type"], str(row["candidate"]["source_id"])))
    manifest = {
        "protocol_version": "halo-2.1-development-freeze-v1",
        "frozen_at": utc_now(),
        "unit_count": len(selected),
        "question_type_counts": expected,
        "source_ids": sorted(source_ids),
        "human_review_policy": "Initial ready rows were retained; three corrected source packets and one replacement were accepted only after explicit re-review approval.",
        "review_records_sha256": sha256_text(str(review_records)),
    }
    return selected, manifest


def apply_numeric_calibration_revisions(record: dict[str, Any]) -> dict[str, Any]:
    """Apply approved development-only numeric revisions without mutating v1."""
    copy = {**record, "packet_draft": {**record["packet_draft"]}}
    packet = copy["packet_draft"]
    source_id = str(copy["candidate"]["source_id"])
    revisions: dict[str, dict[str, Any]] = {
        "11959": {
            "question": "Assuming all 60 refugees whom the Harbor-Master asked the ship to take paid the stated $300 exit fee, by what percentage would the total collected exceed $15,000? Show the calculation.",
            "numeric_spec": {"operands": [60, 300, 15000], "calculation": "((60 * 300) - 15000) / 15000 * 100", "expected_result": "20.0%", "evidence_excerpt": "60 refugees; $300 a person. The $15,000 comparison value is supplied by the question, not asserted by the source."},
            "targeted_false_premise": "The conditional total would be only $15,000.",
            "validation_rules": {"numeric": "Calculate 60 × $300 = $18,000; then (($18,000 − $15,000) ÷ $15,000) × 100 = 20.0%.", "fact": "The conditional wording must not turn the request into a claim that all 60 actually paid or that $15,000 was a source-reported total."},
        },
        "13814": {
            "question": "Using the stated 2023 and 2024 taxable maxima, what was the percentage increase from 2023 to 2024, rounded to one decimal place? Show the calculation.",
            "numeric_spec": {"operands": [160200, 168600], "calculation": "(168600 - 160200) / 160200 * 100", "expected_result": "5.2% (rounded to one decimal place)", "evidence_excerpt": "$160,200 (2023) and $168,600 (2024)."},
            "targeted_false_premise": "The taxable-maximum increase must equal the article's 3.2% benefit COLA.",
            "validation_rules": {"numeric": "Calculate (($168,600 − $160,200) ÷ $160,200) × 100 = 5.2% after rounding to one decimal place.", "fact": "Do not substitute the separate 3.2% COLA for the taxable-maximum calculation."},
        },
        "14068": {
            "question": "By what percentage is Friday's opening duration longer than Tuesday's, rounded to one decimal place? Show the calculation.",
            "numeric_spec": {"operands": [8, 20, 8, 21], "calculation": "(((21 - 8) - (20 - 8)) / (20 - 8)) * 100", "expected_result": "8.3% (rounded to one decimal place)", "evidence_excerpt": "Tuesday 8:00–20:00; Friday 8:00–21:00."},
            "targeted_false_premise": "Friday's opening duration is 10% longer than Tuesday's.",
            "validation_rules": {"numeric": "Tuesday is 12 hours and Friday is 13 hours; calculate ((13 − 12) ÷ 12) × 100 = 8.3% after rounding.", "fact": "The answer should distinguish a one-hour absolute difference from an 8.3% relative difference."},
        },
        "14267": {
            "question": "Assuming one $11 two-item combo was bought each month for all 7 months, by what percentage would that total be higher than $63? Show the calculation.",
            "numeric_spec": {"operands": [11, 7, 63], "calculation": "((11 * 7) - 63) / 63 * 100", "expected_result": "22.2% (rounded to one decimal place)", "evidence_excerpt": "$11 combo; 7 months. The $63 comparison value is supplied by the question, not asserted by the source."},
            "targeted_false_premise": "The conditional total would be $63.",
            "validation_rules": {"numeric": "Calculate 7 × $11 = $77; then (($77 − $63) ÷ $63) × 100 = 22.2% after rounding to one decimal place.", "fact": "The conditional wording must not turn the request into a claim about actual monthly purchases or revenue."},
        },
    }
    if source_id in revisions:
        packet.update(revisions[source_id])
        copy["human_approval"] = {"round": "numeric_recalibration_rereview"}
    return copy


def freeze_development_numeric_recalibration(
    frozen_v1_records: list[dict[str, Any]], review_records: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Create a separately versioned calibration benchmark after numeric review."""
    decisions = {str(row["source_id"]): row for row in review_records}
    for source_id in NUMERIC_RECALIBRATION_SOURCE_IDS:
        decision = decisions.get(source_id)
        if not decision or not approved(decision):
            raise ValueError(f"Numeric recalibration review is not fully approved: {source_id}")
    revised = [apply_numeric_calibration_revisions(row) for row in frozen_v1_records]
    source_ids = [str(row["candidate"]["source_id"]) for row in revised]
    if len(revised) != 16 or len(source_ids) != len(set(source_ids)):
        raise ValueError("Recalibration benchmark must preserve 16 unique development sources")
    type_counts = Counter(row["candidate"]["selected_question_type"] for row in revised)
    expected = {"fact_event": 4, "numeric_calculation": 4, "causal_overreach": 4, "citation_link": 4}
    if dict(type_counts) != expected:
        raise ValueError(f"Recalibration benchmark is not balanced: {dict(type_counts)}")
    revised.sort(key=lambda row: (row["candidate"]["selected_question_type"], str(row["candidate"]["source_id"])))
    manifest = {
        "protocol_version": "halo-2.1-development-calibration-v2-numeric-revision",
        "frozen_at": utc_now(),
        "unit_count": len(revised),
        "question_type_counts": expected,
        "source_ids": sorted(source_ids),
        "parent_protocol_version": "halo-2.1-development-freeze-v1",
        "changed_source_ids": sorted(NUMERIC_RECALIBRATION_SOURCE_IDS),
        "change_scope": "Development calibration only: four numeric questions changed from simple arithmetic to two-step relative-percentage calculations. The v1 benchmark remains immutable and results are not pooled.",
        "review_records_sha256": sha256_text(str(review_records)),
    }
    return revised, manifest


def freeze_final_packets(
    packets: list[dict[str, Any]], *, approval_basis: str, excluded_source_ids: set[str]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Freeze a human-approved final benchmark, separate from development data."""
    if approval_basis != "user_confirmed_all":
        raise ValueError("Final benchmark requires explicit human approval")
    if len(packets) != 48:
        raise ValueError("Final benchmark must contain exactly 48 approved packets")
    source_ids = [str(row["candidate"]["source_id"]) for row in packets]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("Final benchmark source IDs must be unique")
    overlap = set(source_ids).intersection(excluded_source_ids)
    if overlap:
        raise ValueError(f"Final benchmark overlaps development source IDs: {sorted(overlap)[0]}")
    type_counts = Counter(row["candidate"]["selected_question_type"] for row in packets)
    expected = {"fact_event": 12, "numeric_calculation": 12, "causal_overreach": 12, "citation_link": 12}
    if dict(type_counts) != expected:
        raise ValueError(f"Final benchmark is not balanced: {dict(type_counts)}")
    frozen = []
    for record in packets:
        copy = {**record, "human_approval": {"basis": approval_basis}, "human_review_status": "approved_final"}
        frozen.append(copy)
    frozen.sort(key=lambda row: (row["candidate"]["selected_question_type"], str(row["candidate"]["source_id"])))
    manifest = {
        "protocol_version": "halo-2.1-final-freeze-v1",
        "frozen_at": utc_now(), "unit_count": len(frozen), "question_type_counts": expected,
        "source_ids": sorted(source_ids), "approval_basis": approval_basis,
        "development_source_ids_excluded": sorted(excluded_source_ids),
        "policy": "Final responses and final labels must not be pooled with development calibration or earlier pilot data.",
    }
    return frozen, manifest
