#!/usr/bin/env python3
"""Join human labels to experiment responses and aggregate by stage/question."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from halo_runner.core import read_jsonl, write_jsonl  # noqa: E402

REQUIRED_LABEL_COLUMNS = {
    "question_id", "repetition", "stage", "hallucination", "severity", "propagation", "reviewer", "notes"
}
REQUIRED_BLIND_LABEL_COLUMNS = {"blind_id", "hallucination", "severity", "reviewer", "notes"}


def validate_label_values(row: dict[str, str], line_number: int, require_propagation: bool) -> None:
    if row["hallucination"] not in {"0", "1"}:
        raise ValueError(f"hallucination must be 0 or 1 at CSV line {line_number}")
    severity = int(row["severity"])
    if not 0 <= severity <= 5:
        raise ValueError(f"severity must be 0..5 at CSV line {line_number}")
    if require_propagation and row["propagation"] not in {"Initial", "Maintained", "Removed", "None"}:
        raise ValueError(f"Invalid propagation at CSV line {line_number}")


def read_labels(path: Path) -> tuple[str, dict[Any, dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("Label CSV has no header")
        blind_mode = REQUIRED_BLIND_LABEL_COLUMNS.issubset(reader.fieldnames)
        if not blind_mode and not REQUIRED_LABEL_COLUMNS.issubset(reader.fieldnames):
            raise ValueError("Label CSV has missing columns; start from labels.template.csv or blind_labels.template.csv")
        labels: dict[Any, dict[str, str]] = {}
        for line_number, row in enumerate(reader, start=2):
            key: Any = row["blind_id"] if blind_mode else (row["question_id"], int(row["repetition"]), row["stage"])
            if key in labels:
                raise ValueError(f"Duplicate label at CSV line {line_number}: {key}")
            validate_label_values(row, line_number, require_propagation=not blind_mode)
            labels[key] = row
    return ("blind" if blind_mode else "standard"), labels


def read_blind_key(path: Path) -> dict[tuple[str, str, int, str], str]:
    required = {"blind_id", "article_id", "question_id", "repetition", "stage"}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError("Blind key CSV has missing columns; use blind_key.coordinator_only.csv")
        lookup: dict[tuple[str, str, int, str], str] = {}
        for line_number, row in enumerate(reader, start=2):
            key = (row["article_id"], row["question_id"], int(row["repetition"]), row["stage"])
            if key in lookup:
                raise ValueError(f"Duplicate blind-key row at CSV line {line_number}: {key}")
            lookup[key] = row["blind_id"]
    return lookup


def write_summary(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = ["stage", "question_id", "responses", "labeled", "hallucinations", "hallucination_rate", "mean_severity", "Initial", "Maintained", "Removed", "None"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def summarize(records: list[dict[str, Any]], include_question: bool) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[(record["stage"], record["question_id"] if include_question else "ALL")].append(record)
    rows: list[dict[str, Any]] = []
    for (stage, question_id), group in sorted(groups.items()):
        labeled = [record for record in group if record["status"] == "LABELED"]
        hallucinations = sum(record.get("hallucination", 0) for record in labeled)
        propagation = Counter(record.get("propagation") for record in labeled)
        rows.append(
            {
                "stage": stage,
                "question_id": question_id,
                "responses": len(group),
                "labeled": len(labeled),
                "hallucinations": hallucinations,
                "hallucination_rate": round(hallucinations / len(labeled), 4) if labeled else "",
                "mean_severity": round(sum(record["severity"] for record in labeled) / len(labeled), 4) if labeled else "",
                "Initial": propagation["Initial"],
                "Maintained": propagation["Maintained"],
                "Removed": propagation["Removed"],
                "None": propagation["None"],
            }
        )
    return rows


def infer_blind_propagation(records: list[dict[str, Any]]) -> None:
    """Infer stage-to-stage propagation only after blinded factual labels lock."""
    groups: dict[tuple[str, str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[(record["run_id"], record.get("article_id", "ARTICLE_001"), record["question_id"], record["repetition"])].append(record)
    for group in groups.values():
        prior_hallucination = False
        for record in group:
            if record["status"] != "LABELED":
                continue
            if record["hallucination"]:
                record["propagation"] = "Maintained" if prior_hallucination else "Initial"
                prior_hallucination = True
            else:
                record["propagation"] = "Removed" if prior_hallucination else "None"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--blind-key", type=Path, help="Required when --labels is a blind_labels.template.csv file")
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    records = read_jsonl(run_dir / "responses.jsonl")
    label_mode, labels = read_labels(args.labels.resolve())
    if label_mode == "blind" and not args.blind_key:
        raise ValueError("--blind-key is required for blinded labels")
    blind_lookup = read_blind_key(args.blind_key.resolve()) if label_mode == "blind" and args.blind_key else {}
    joined: list[dict[str, Any]] = []
    for record in records:
        standard_key = (record["question_id"], record["repetition"], record["stage"])
        blind_id = blind_lookup.get((record.get("article_id", "ARTICLE_001"), *standard_key)) if label_mode == "blind" else None
        label = labels.get(blind_id) if label_mode == "blind" else labels.get(standard_key)
        if label:
            record = {
                **record,
                "status": "LABELED",
                "hallucination": int(label["hallucination"]),
                "severity": int(label["severity"]),
                "propagation": label["propagation"],
                "reviewer": label["reviewer"],
                "notes": label["notes"],
            }
        joined.append(record)
    if label_mode == "blind":
        infer_blind_propagation(joined)
    write_jsonl(run_dir / "labeled_responses.jsonl", joined)
    write_summary(run_dir / "stage_summary.csv", summarize(joined, include_question=False))
    write_summary(run_dir / "question_stage_summary.csv", summarize(joined, include_question=True))
    print(run_dir / "stage_summary.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

