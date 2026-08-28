#!/usr/bin/env python3
"""Generate HALO 2.1 development packet drafts with an enforced project budget."""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from halo_runner.core import read_json, read_jsonl, utc_now, write_json, write_jsonl  # noqa: E402
from halo_runner.v21_budget import TokenUsage, assert_within_budget, call_cost_usd  # noqa: E402
from halo_runner.v21_packets import packet_prompt, parse_packet_response, projected_packet_cost_usd  # noqa: E402


def prior_spend_usd(ledger_path: Path) -> float:
    if not ledger_path.exists():
        return 0.0
    return sum(float(row["cost_usd"]) for row in read_jsonl(ledger_path))


def request_packet(prompt: str, config: dict[str, Any]) -> tuple[dict[str, Any], TokenUsage]:
    api_key = os.environ.get(config["api_key_env"])
    if not api_key:
        raise RuntimeError(f"Environment variable {config['api_key_env']} is not set")
    payload = {
        "model": config["model"],
        "temperature": config["temperature"],
        "max_tokens": config["max_output_tokens"],
        "response_format": {"type": "json_object"},
        "messages": [{"role": "user", "content": prompt}],
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Packet-generation request failed ({error.code}): {detail}") from error
    content = body["choices"][0]["message"]["content"]
    usage = body.get("usage", {})
    return parse_packet_response(content), TokenUsage(
        input_tokens=int(usage.get("prompt_tokens", 0)),
        output_tokens=int(usage.get("completion_tokens", 0)),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-pool", type=Path, required=True)
    parser.add_argument("--generation-config", type=Path, default=ROOT / "config" / "halo_v21_packet_generation.json")
    parser.add_argument("--budget-config", type=Path, default=ROOT / "config" / "halo_v21_budget.json")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--ledger-path", type=Path, default=ROOT / "results" / "v2_1" / "api_usage_ledger.jsonl",
        help="Project-wide append-only API cost ledger shared across calibration and primary runs.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    candidates = read_jsonl(args.source_pool)
    if args.limit is not None:
        candidates = candidates[:args.limit]
    if not candidates:
        raise ValueError("Source pool is empty")
    config = read_json(args.generation_config)
    budget = read_json(args.budget_config)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = args.ledger_path.resolve()
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    projected = sum(projected_packet_cost_usd(candidate, config, budget["pricing"]) for candidate in candidates)
    spent = prior_spend_usd(ledger_path)
    assert_within_budget(projected_new_cost_usd=projected, spent_live_cost_usd=spent, budget=budget)
    write_json(args.output_dir / "packet_generation_preflight.json", {
        "created_at": utc_now(), "dry_run": args.dry_run, "candidate_count": len(candidates),
        "projected_new_cost_usd": projected, "prior_recorded_spend_usd": spent,
        "live_run_cap_usd": budget["live_run_cap_usd"], "model": config["model"],
        "project_ledger_path": str(ledger_path),
    })
    drafts: list[dict[str, Any]] = []
    ledger_rows: list[dict[str, Any]] = []
    for candidate in candidates:
        prompt = packet_prompt(candidate)
        if args.dry_run:
            packet: dict[str, Any] = {"dry_run": True, "question": "[No API call]"}
            usage = TokenUsage(0, 0)
        else:
            packet, usage = request_packet(prompt, config)
        cost = call_cost_usd(usage, budget["pricing"])
        drafts.append({
            "packet_id": f"HALO21_{candidate['candidate_id']}_{candidate['selected_question_type']}",
            "candidate": candidate, "packet_draft": packet,
            "human_review_status": "pending_human_validation",
        })
        if not args.dry_run:
            ledger_rows.append({
                "created_at": utc_now(), "packet_id": drafts[-1]["packet_id"], "model": config["model"],
                "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens, "cost_usd": cost,
            })
    write_jsonl(args.output_dir / "packet_drafts.pending_review.jsonl", drafts)
    if ledger_rows:
        existing = read_jsonl(ledger_path) if ledger_path.exists() else []
        write_jsonl(ledger_path, existing + ledger_rows)
        write_jsonl(args.output_dir / "packet_generation_usage.jsonl", ledger_rows)
    print(f"Created {len(drafts)} packet drafts; projected API cost ${projected:.4f}; dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
