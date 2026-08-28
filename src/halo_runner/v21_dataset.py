"""Build reviewable HALO 2.1 source-packet candidates from RAGTruth."""
from __future__ import annotations

import csv
import random
import re
from collections import Counter
from pathlib import Path
from typing import Any

from halo_runner.core import read_jsonl, sha256_text, utc_now, write_json, write_jsonl

V21_PROTOCOL_VERSION = "halo-2.1-ragtruth-candidates-v1"
URL_PATTERN = re.compile(r"https?://[^\s)\]}>\"']+|www\.[^\s)\]}>\"']+", re.IGNORECASE)
NUMBER_PATTERN = re.compile(r"(?<![A-Za-z])[-+]?\d[\d,]*(?:\.\d+)?%?(?![A-Za-z])")
CAUSAL_PATTERN = re.compile(
    r"\b(because|due to|caused|causing|resulted in|led to|therefore|as a result|after)\b",
    re.IGNORECASE,
)


def normalize_text(value: str) -> str:
    return " ".join(value.split())


def explicit_urls(text: str) -> list[str]:
    return list(dict.fromkeys(match.rstrip(".,;:") for match in URL_PATTERN.findall(text)))


def numeric_literals(text: str) -> list[str]:
    return NUMBER_PATTERN.findall(text)


def eligible_types(text: str, task_type: str) -> tuple[list[str], list[str]]:
    """Return pre-execution eligibility; this is never based on model outputs."""
    normalized = normalize_text(text)
    reasons: list[str] = []
    eligible: list[str] = []
    numbers = numeric_literals(normalized)
    urls = explicit_urls(normalized)

    if len(normalized) >= 800:
        eligible.append("fact_event")
    else:
        reasons.append("too_short_for_fact_event")

    if len(numbers) >= 2 and len(normalized) >= 250:
        eligible.append("numeric_calculation")
    else:
        reasons.append("insufficient_numeric_operands")

    if len(normalized) >= 800 and CAUSAL_PATTERN.search(normalized):
        eligible.append("causal_overreach")
    else:
        reasons.append("insufficient_explicit_causal_context")

    if urls:
        eligible.append("citation_link")
    else:
        reasons.append("no_explicit_url_for_link_verification")

    if task_type == "Data2txt" and len(normalized) < 500:
        eligible = [kind for kind in eligible if kind == "numeric_calculation"]
        reasons.append("short_structured_source_numeric_only")
    return eligible, reasons


def build_candidates(source_info_path: Path, seed: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = read_jsonl(source_info_path)
    candidates: list[dict[str, Any]] = []
    for row in rows:
        source_text = normalize_text(str(row.get("source_info", "")))
        source_id = str(row.get("source_id", ""))
        if not source_id or not source_text:
            continue
        types, reasons = eligible_types(source_text, str(row.get("task_type", "")))
        candidates.append(
            {
                "candidate_id": f"RAGTRUTH_{source_id}",
                "source_dataset": "RAGTruth",
                "source_id": source_id,
                "task_type": row.get("task_type", ""),
                "source_collection": row.get("source", ""),
                "source_text": source_text,
                "source_prompt": row.get("prompt", ""),
                "source_sha256": sha256_text(source_text),
                "source_characters": len(source_text),
                "numeric_literals": numeric_literals(source_text),
                "explicit_urls": explicit_urls(source_text),
                "eligible_question_types": types,
                "eligibility_notes": reasons,
                "candidate_status": "pending_human_review",
            }
        )
    random.Random(seed).shuffle(candidates)
    type_counts = Counter(kind for item in candidates for kind in item["eligible_question_types"])
    manifest = {
        "protocol_version": V21_PROTOCOL_VERSION,
        "created_at": utc_now(),
        "source_info_path": str(source_info_path),
        "source_info_sha256": sha256_text(source_info_path.read_text(encoding="utf-8")),
        "random_seed": seed,
        "source_records": len(rows),
        "candidate_records": len(candidates),
        "eligible_by_question_type": dict(sorted(type_counts.items())),
        "selection_rule": "Candidates are shuffled deterministically before human review; no model response is used for inclusion.",
    }
    return candidates, manifest


def write_reviewer_template(path: Path, candidates: list[dict[str, Any]]) -> None:
    fields = [
        "candidate_id", "source_id", "task_type", "source_collection", "source_characters",
        "eligible_question_types", "review_status", "approved_question_type",
        "fact_table_verified", "numeric_spec_verified", "official_links_verified",
        "question_candidate_approved", "reviewer", "notes",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in candidates:
            writer.writerow(
                {
                    "candidate_id": item["candidate_id"],
                    "source_id": item["source_id"],
                    "task_type": item["task_type"],
                    "source_collection": item["source_collection"],
                    "source_characters": item["source_characters"],
                    "eligible_question_types": ";".join(item["eligible_question_types"]),
                    "review_status": "pending",
                }
            )


def build_candidate_artifacts(source_info_path: Path, output_dir: Path, seed: int = 20260828) -> dict[str, Any]:
    if not source_info_path.exists():
        raise FileNotFoundError(f"RAGTruth source_info file not found: {source_info_path}")
    output_dir.mkdir(parents=True, exist_ok=True)
    candidates, manifest = build_candidates(source_info_path, seed)
    write_jsonl(output_dir / "ragtruth_source_candidates.jsonl", candidates)
    write_json(output_dir / "candidate_manifest.json", manifest)
    write_reviewer_template(output_dir / "candidate_review.template.csv", candidates)
    return manifest


def parse_type_quotas(values: list[str]) -> dict[str, int]:
    """Parse CLI-friendly `type=count` values without silently choosing N."""
    quotas: dict[str, int] = {}
    known = {"fact_event", "numeric_calculation", "causal_overreach", "citation_link"}
    for value in values:
        key, separator, raw_count = value.partition("=")
        if not separator or key not in known:
            raise ValueError(f"Invalid question-type quota: {value}")
        try:
            count = int(raw_count)
        except ValueError as error:
            raise ValueError(f"Quota for {key} must be an integer") from error
        if count < 1:
            raise ValueError(f"Quota for {key} must be positive")
        if key in quotas:
            raise ValueError(f"Duplicate quota for {key}")
        quotas[key] = count
    if not quotas:
        raise ValueError("At least one --quota question_type=count value is required")
    return quotas


def select_balanced_source_pool(
    candidates: list[dict[str, Any]], quotas: dict[str, int], seed: int, excluded_source_ids: set[str] | None = None
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Select unique sources deterministically before question/model generation.

    Scarce link candidates are allocated first so that a broad type cannot use
    a source needed by a later rare type. Selection never reads model outputs.
    """
    excluded_source_ids = excluded_source_ids or set()
    randomizer = random.Random(seed)
    by_type: dict[str, list[dict[str, Any]]] = {}
    for kind in quotas:
        eligible = [
            item for item in candidates
            if kind in item.get("eligible_question_types", []) and item.get("source_id") not in excluded_source_ids
        ]
        randomizer.shuffle(eligible)
        by_type[kind] = eligible

    ordered_types = sorted(quotas, key=lambda kind: (len(by_type[kind]), kind))
    selected_ids: set[str] = set()
    selected: list[dict[str, Any]] = []
    for kind in ordered_types:
        choices = [item for item in by_type[kind] if item["candidate_id"] not in selected_ids]
        if len(choices) < quotas[kind]:
            raise ValueError(
                f"Cannot fulfill {kind}={quotas[kind]} with unique sources; only {len(choices)} remain"
            )
        for rank, item in enumerate(choices[:quotas[kind]], start=1):
            copy = dict(item)
            copy.update(
                {
                    "selected_question_type": kind,
                    "selection_rank_within_type": rank,
                    "selection_seed": seed,
                    "selection_status": "pending_human_packet_validation",
                }
            )
            selected.append(copy)
            selected_ids.add(item["candidate_id"])

    selected.sort(key=lambda item: (item["selected_question_type"], item["selection_rank_within_type"]))
    manifest = {
        "protocol_version": "halo-2.1-source-pool-v1",
        "created_at": utc_now(),
        "selection_seed": seed,
        "excluded_source_ids": sorted(excluded_source_ids),
        "requested_quotas": quotas,
        "selection_order": ordered_types,
        "selected_source_packets": len(selected),
        "unique_source_packets": len(selected_ids),
        "selection_rule": "Unique source-only allocation; scarce eligible types are allocated first; model outputs are never used.",
    }
    return selected, manifest
