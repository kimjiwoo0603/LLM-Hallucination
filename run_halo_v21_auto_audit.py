#!/usr/bin/env python3
"""Create condition-blind, AI-assisted audit candidates for final HALO responses."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from halo_runner.core import read_json, read_jsonl, utc_now, write_json, write_jsonl  # noqa: E402
from halo_runner.v21_auto_audit import automatic_audit_prompt, parse_audit_response, projected_audit_cost_usd  # noqa: E402
from halo_runner.v21_budget import TokenUsage, assert_within_budget, call_cost_usd  # noqa: E402
from halo_runner.v21_execution import openai_chat_completion  # noqa: E402


def prior_spend_usd(ledger: Path) -> float:
    return sum(float(row["cost_usd"]) for row in read_jsonl(ledger)) if ledger.exists() else 0.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--responses", type=Path, required=True, help="Final-response JSONL; each row must include packet_id and response.")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "halo_v21_auto_audit.json")
    parser.add_argument("--budget-config", type=Path, default=ROOT / "config" / "halo_v21_budget.json")
    parser.add_argument("--ledger-path", type=Path, default=ROOT / "results" / "v2_1" / "api_usage_ledger.jsonl")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    config, budget = read_json(args.config), read_json(args.budget_config)
    packets = {row["packet_id"]: row for row in read_jsonl(args.benchmark)}
    responses = read_jsonl(args.responses)
    if args.limit is not None:
        responses = responses[:args.limit]
    if not responses:
        raise ValueError("No final responses to audit")
    missing = [row.get("packet_id") for row in responses if row.get("packet_id") not in packets or not row.get("response")]
    if missing:
        raise ValueError(f"Responses are missing a known packet_id or response: {missing[0]}")
    projected = sum(projected_audit_cost_usd(packets[row["packet_id"]], str(row["response"]), config) for row in responses)
    ledger = args.ledger_path.resolve(); ledger.parent.mkdir(parents=True, exist_ok=True)
    spent = prior_spend_usd(ledger)
    assert_within_budget(projected_new_cost_usd=projected, spent_live_cost_usd=spent, budget=budget)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.output_dir / "auto_audit_manifest.json", {
        "protocol_version": config["protocol_version"], "created_at": utc_now(), "dry_run": args.dry_run,
        "auditor_model": config["model"], "response_count": len(responses), "projected_new_cost_usd": projected,
        "prior_recorded_spend_usd": spent, "human_finalization_required": True,
    })
    audits, ledger_rows = [], []
    for response in responses:
        packet = packets[response["packet_id"]]
        if args.dry_run:
            audit, usage = {field: ([] if field == "findings" else 0) for field in ["fact_hallucination_candidate", "numeric_error_candidate", "causal_overreach_candidate", "citation_link_hallucination_candidate", "findings", "confidence"]}, TokenUsage(0, 0)
        else:
            content, usage = openai_chat_completion(automatic_audit_prompt(packet, str(response["response"])), config)
            audit = parse_audit_response(content)
        audits.append({
            "packet_id": response["packet_id"], "response_sha256": response.get("response_sha256"), "question": packet["packet_draft"]["question"],
            "response": response["response"], "question_type": packet["candidate"]["selected_question_type"], "audit": audit,
            "auto_audit_status": "PENDING_HUMAN_CONFIRMATION", "auditor_model": config["model"],
        })
        if not args.dry_run:
            ledger_rows.append({"created_at": utc_now(), "phase": "auto_audit", "packet_id": response["packet_id"], "model": config["model"], "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens, "cost_usd": call_cost_usd(usage, config["pricing"])})
    write_jsonl(args.output_dir / "auto_audit.pending_human_review.jsonl", audits)
    if ledger_rows:
        write_jsonl(ledger, (read_jsonl(ledger) if ledger.exists() else []) + ledger_rows)
    print(f"Created {len(audits)} automatic audit candidates; projected API cost ${projected:.4f}; dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
