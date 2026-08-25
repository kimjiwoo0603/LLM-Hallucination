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


def read_labels(path: Path) -> dict[tuple[str, int, str], dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not REQUIRED_LABEL_COLUMNS.issubset(reader.fieldnames):
            raise ValueError("Label CSV has missing columns; start from labels/labels.template.csv")
        labels: dict[tuple[str, int, str], dict[str, str]] = {}
        for line_number, row in enumerate(reader, start=2):
            key = (row["question_id"], int(row["repetition"]), row["stage"])
            if key in labels:
                raise ValueError(f"Duplicate label at CSV line {line_number}: {key}")
            if row["hallucination"] not in {"0", "1"}:
                raise ValueError(f"hallucination must be 0 or 1 at CSV line {line_number}")
            severity = int(row["severity"])
            if not 0 <= severity <= 5:
                raise ValueError(f"severity must be 0..5 at CSV line {line_number}")
            if row["propagation"] not in {"Initial", "Maintained", "Removed", "None"}:
                raise ValueError(f"Invalid propagation at CSV line {line_number}")
            labels[key] = row
    return labels


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    records = read_jsonl(run_dir / "responses.jsonl")
    labels = read_labels(args.labels.resolve())
    joined: list[dict[str, Any]] = []
    for record in records:
        key = (record["question_id"], record["repetition"], record["stage"])
        label = labels.get(key)
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
    write_jsonl(run_dir / "labeled_responses.jsonl", joined)
    write_summary(run_dir / "stage_summary.csv", summarize(joined, include_question=False))
    write_summary(run_dir / "question_stage_summary.csv", summarize(joined, include_question=True))
    print(run_dir / "stage_summary.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
