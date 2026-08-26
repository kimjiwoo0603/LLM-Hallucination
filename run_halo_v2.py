#!/usr/bin/env python3
"""HALO 2.0 mechanical workflow: validate → approve/select → annotate → summarize."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from halo_runner.core import read_jsonl, write_jsonl
from halo_runner.v2 import (approved_benchmark, final_records, read_v2_labels, summarize_final_labels,
                            validate_articles, validate_questions, write_adjudication, write_dataset_manifest,
                            write_v2_blind_packet)


def articles_from_manifest(path: Path) -> dict[str, str]:
    return {row["article_id"]: row.get("article_text", "") for row in read_jsonl(path)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--articles", type=Path, required=True); validate.add_argument("--questions", type=Path, required=True)
    validate.add_argument("--min-chars", type=int, default=1500); validate.add_argument("--max-chars", type=int, default=30000)
    select = sub.add_parser("select")
    select.add_argument("--articles", type=Path, required=True); select.add_argument("--questions", type=Path, required=True)
    select.add_argument("--output-dir", type=Path, required=True); select.add_argument("--seed", type=int, required=True)
    select.add_argument("--dataset-version", required=True); select.add_argument("--target-articles", type=int)
    select.add_argument("--min-chars", type=int, default=1500); select.add_argument("--max-chars", type=int, default=30000)
    estimate = sub.add_parser("estimate")
    estimate.add_argument("--questions", type=int, required=True); estimate.add_argument("--repetitions", type=int, required=True)
    estimate.add_argument("--conditions", type=int, required=True); estimate.add_argument("--stages", type=int, required=True)
    estimate.add_argument("--estimated-cost-per-request-usd", type=float)
    estimate.add_argument("--max-requests", type=int); estimate.add_argument("--max-estimated-cost-usd", type=float)
    packet = sub.add_parser("make-blind-packet")
    packet.add_argument("--run-dir", type=Path, action="append", required=True); packet.add_argument("--articles", type=Path, required=True); packet.add_argument("--output-dir", type=Path, required=True)
    adjudicate = sub.add_parser("adjudicate")
    adjudicate.add_argument("--rater-a", type=Path, required=True); adjudicate.add_argument("--rater-b", type=Path, required=True); adjudicate.add_argument("--output-dir", type=Path, required=True)
    summarize = sub.add_parser("summarize")
    summarize.add_argument("--labels", type=Path, required=True); summarize.add_argument("--blind-key", type=Path, required=True); summarize.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "validate":
        articles, questions = read_jsonl(args.articles), read_jsonl(args.questions)
        errors = validate_articles(articles, args.min_chars, args.max_chars) + validate_questions(questions, {row.get("article_id") for row in articles})
        if errors:
            print("\n".join(errors), file=sys.stderr); return 2
        print(json.dumps({"articles": len(articles), "questions": len(questions), "status": "valid"}, ensure_ascii=False)); return 0
    if args.command == "select":
        articles, questions = read_jsonl(args.articles), read_jsonl(args.questions)
        errors = validate_articles(articles, args.min_chars, args.max_chars) + validate_questions(questions, {row.get("article_id") for row in articles})
        if errors: raise ValueError("Refusing selection: " + "; ".join(errors))
        selected_articles, selected_questions = approved_benchmark(articles, questions, args.seed, args.target_articles)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        write_jsonl(args.output_dir / "articles.jsonl", selected_articles); write_jsonl(args.output_dir / "questions.jsonl", selected_questions)
        write_dataset_manifest(args.output_dir / "dataset_manifest.json", selected_articles, selected_questions, args.seed, args.dataset_version)
        print(args.output_dir); return 0
    if args.command == "estimate":
        values = [args.questions, args.repetitions, args.conditions, args.stages]
        if any(value < 1 for value in values): raise ValueError("questions, repetitions, conditions, and stages must all be positive")
        requests = args.questions * args.repetitions * args.conditions * args.stages
        estimated_cost = round(requests * args.estimated_cost_per_request_usd, 6) if args.estimated_cost_per_request_usd is not None else None
        blocked = (args.max_requests is not None and requests > args.max_requests) or (args.max_estimated_cost_usd is not None and estimated_cost is not None and estimated_cost > args.max_estimated_cost_usd)
        print(json.dumps({"estimated_requests": requests, "estimated_cost_usd": estimated_cost, "budget_status": "BLOCKED" if blocked else "WITHIN_LIMIT", "note": "Per-request cost is a user-supplied planning assumption; verify current provider pricing before a live run."}, ensure_ascii=False))
        return 2 if blocked else 0
    if args.command == "make-blind-packet":
        write_v2_blind_packet(args.output_dir, final_records(args.run_dir), articles_from_manifest(args.articles)); print(args.output_dir); return 0
    if args.command == "adjudicate":
        agreed, disagreements = write_adjudication(args.output_dir, read_v2_labels(args.rater_a), read_v2_labels(args.rater_b))
        print(json.dumps({"agreed": agreed, "requires_adjudication": disagreements})); return 0
    if args.command == "summarize":
        labels = read_v2_labels(args.labels)
        with args.blind_key.open(encoding="utf-8-sig", newline="") as handle: key = {row["blind_id"]: row for row in csv.DictReader(handle)}
        joined = [{**key[blind_id], **label} for blind_id, label in labels.items() if blind_id in key]
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(summarize_final_labels(joined), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(args.output); return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
