#!/usr/bin/env python3
"""Run the frozen HALO 2.1 primary experiment with final-response checkpoints."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from halo_runner.core import read_json, read_jsonl, sha256_text, utc_now, write_json, write_jsonl  # noqa: E402
from halo_runner.v21_budget import TokenUsage, assert_within_budget, call_cost_usd, projected_run_cost_usd  # noqa: E402
from halo_runner.v21_primary import CONDITIONS, run_condition  # noqa: E402


def prior_spend_usd(ledger: Path) -> float:
    return sum(float(row["cost_usd"]) for row in read_jsonl(ledger)) if ledger.exists() else 0.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "halo_v21_primary.json")
    parser.add_argument("--budget-config", type=Path, default=ROOT / "config" / "halo_v21_budget.json")
    parser.add_argument("--ledger-path", type=Path, default=ROOT / "results" / "v2_1" / "api_usage_ledger.jsonl")
    parser.add_argument("--condition", choices=["all", *CONDITIONS], default="all")
    parser.add_argument("--offset", type=int, default=0, help="Zero-based benchmark unit offset for a resumable batch")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    config, budget = read_json(args.config), read_json(args.budget_config)
    records = read_jsonl(args.benchmark)
    if args.offset < 0:
        raise ValueError("--offset must be zero or greater")
    records = records[args.offset:]
    if args.limit is not None:
        records = records[:args.limit]
    conditions = list(config["conditions"] if args.condition == "all" else [args.condition])
    if not records or any(condition not in CONDITIONS for condition in conditions):
        raise ValueError("Invalid benchmark or condition configuration")
    projected = projected_run_cost_usd(((row["candidate"]["source_text"], row["packet_draft"]["question"]) for row in records), budget["pricing"], repetitions=int(config["repetitions"]))
    if len(conditions) != len(CONDITIONS):
        projected *= len(conditions) / len(CONDITIONS)
    ledger = args.ledger_path.resolve(); ledger.parent.mkdir(parents=True, exist_ok=True)
    assert_within_budget(projected_new_cost_usd=projected, spent_live_cost_usd=prior_spend_usd(ledger), budget=budget)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    final_path, trace_path = args.output_dir / "final_responses.pending_auto_audit.jsonl", args.output_dir / "traces.coordinator_only.jsonl"
    finals = read_jsonl(final_path) if args.resume and final_path.exists() else []
    traces = read_jsonl(trace_path) if args.resume and trace_path.exists() else []
    done = {(row["packet_id"], row["condition"], row["repetition"]) for row in finals}
    write_json(args.output_dir / "primary_manifest.json", {"protocol_version": config["protocol_version"], "created_at": utc_now(), "dry_run": args.dry_run, "conditions": conditions, "offset": args.offset, "unit_count": len(records), "projected_new_cost_usd": projected, "benchmark_sha256": sha256_text(args.benchmark.read_text(encoding="utf-8")), "model": config["model"], "temperature": config["temperature"]})
    new_ledger_count = 0
    for record in records:
        for repetition in range(1, int(config["repetitions"]) + 1):
            for condition in conditions:
                key = (record["packet_id"], condition, repetition)
                if key in done:
                    continue
                final, trace, usages = run_condition(record, condition, config, dry_run=args.dry_run)
                final_row = {"packet_id": record["packet_id"], "source_id": record["candidate"]["source_id"], "question_type": record["candidate"]["selected_question_type"], "question": record["packet_draft"]["question"], "condition": condition, "repetition": repetition, "response": final, "response_sha256": sha256_text(final), "status": "PENDING_AUTO_AUDIT"}
                finals.append(final_row); traces.append({"packet_id": record["packet_id"], "condition": condition, "repetition": repetition, "trace": trace})
                write_jsonl(final_path, finals); write_jsonl(trace_path, traces)
                if not args.dry_run:
                    ledger_rows = read_jsonl(ledger) if ledger.exists() else []
                    for usage in usages:
                        ledger_rows.append({"created_at": utc_now(), "phase": "primary_execution", "packet_id": record["packet_id"], "condition": condition, "model": config["model"], "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens, "cost_usd": call_cost_usd(TokenUsage(usage.input_tokens, usage.output_tokens), budget["pricing"])})
                        new_ledger_count += 1
                    write_jsonl(ledger, ledger_rows)
    print(f"Completed {len(finals)} final responses; newly run {new_ledger_count} calls; dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
