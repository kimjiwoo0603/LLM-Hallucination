#!/usr/bin/env python3
"""Run the pre-registered HALO 2.1 Single one-shot development calibration."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from halo_runner.core import read_json, read_jsonl, sha256_text, utc_now, write_json, write_jsonl  # noqa: E402
from halo_runner.v21_budget import TokenUsage, approximate_tokens, assert_within_budget, call_cost_usd  # noqa: E402
from halo_runner.v21_execution import openai_chat_completion, single_oneshot_prompt  # noqa: E402


def prior_spend_usd(ledger: Path) -> float:
    return sum(float(row["cost_usd"]) for row in read_jsonl(ledger)) if ledger.exists() else 0.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "halo_v21_calibration.json")
    parser.add_argument("--budget-config", type=Path, default=ROOT / "config" / "halo_v21_budget.json")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--ledger-path", type=Path, default=ROOT / "results" / "v2_1" / "api_usage_ledger.jsonl")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    config, budget = read_json(args.config), read_json(args.budget_config)
    records = read_jsonl(args.benchmark)
    if args.limit is not None:
        records = records[:args.limit]
    if not records:
        raise ValueError("Frozen development benchmark is empty")
    if config["condition"] != "single_oneshot":
        raise ValueError("Calibration must use the pre-registered single_oneshot condition")
    prompts = [single_oneshot_prompt(record) for record in records]
    projected = sum(call_cost_usd(TokenUsage(approximate_tokens(prompt), config["max_output_tokens"]), budget["pricing"]) for prompt in prompts)
    ledger = args.ledger_path.resolve(); ledger.parent.mkdir(parents=True, exist_ok=True)
    spent = prior_spend_usd(ledger)
    assert_within_budget(projected_new_cost_usd=projected, spent_live_cost_usd=spent, budget=budget)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.output_dir / "calibration_manifest.json", {
        "protocol_version": config["protocol_version"], "created_at": utc_now(), "dry_run": args.dry_run,
        "condition": config["condition"], "model": config["model"], "temperature": config["temperature"],
        "benchmark_sha256": sha256_text(args.benchmark.read_text(encoding="utf-8")), "unit_count": len(records),
        "projected_new_cost_usd": projected, "prior_recorded_spend_usd": spent, "live_run_cap_usd": budget["live_run_cap_usd"],
    })
    outputs: list[dict[str, object]] = []; ledger_rows: list[dict[str, object]] = []
    for record, prompt in zip(records, prompts):
        if args.dry_run:
            response, usage = "[DRY RUN — no API call]", TokenUsage(0, 0)
        else:
            response, usage = openai_chat_completion(prompt, config)
        outputs.append({
            "packet_id": record["packet_id"], "source_id": record["candidate"]["source_id"],
            "question_type": record["candidate"]["selected_question_type"], "condition": "single_oneshot",
            "question": record["packet_draft"]["question"], "response": response,
            "response_sha256": sha256_text(response), "status": "PENDING_BLIND_HUMAN_LABEL",
        })
        if not args.dry_run:
            ledger_rows.append({"created_at": utc_now(), "phase": "development_calibration", "condition": "single_oneshot", "packet_id": record["packet_id"], "model": config["model"], "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens, "cost_usd": call_cost_usd(usage, budget["pricing"])})
    write_jsonl(args.output_dir / "calibration_responses.pending_label.jsonl", outputs)
    if ledger_rows:
        existing = read_jsonl(ledger) if ledger.exists() else []
        write_jsonl(ledger, existing + ledger_rows)
    print(f"Completed {len(outputs)} calibration responses; projected API cost ${projected:.4f}; dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
