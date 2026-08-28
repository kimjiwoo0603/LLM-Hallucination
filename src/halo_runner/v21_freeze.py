"""Freeze a human-approved HALO 2.1 development benchmark without API calls."""
from __future__ import annotations

from collections import Counter
from typing import Any

from halo_runner.core import sha256_text, utc_now

REREVIEWED_SOURCE_IDS = {"11945", "13979", "14679", "14267"}
REPLACED_SOURCE_ID = "15235"


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
