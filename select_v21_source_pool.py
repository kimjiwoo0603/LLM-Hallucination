#!/usr/bin/env python3
"""Create a deterministic HALO 2.1 source-packet shortlist without API calls."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from halo_runner.core import read_jsonl, write_json, write_jsonl  # noqa: E402
from halo_runner.v21_dataset import parse_type_quotas, select_balanced_source_pool  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--quota", action="append", required=True, help="question_type=count; repeat for each type")
    parser.add_argument("--seed", type=int, default=20260828)
    args = parser.parse_args()
    quotas = parse_type_quotas(args.quota)
    selected, manifest = select_balanced_source_pool(read_jsonl(args.candidates), quotas, args.seed)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.output_dir / "source_pool.pending_review.jsonl", selected)
    write_json(args.output_dir / "source_pool.manifest.json", manifest)
    print(f"Selected {len(selected)} unique source packets in {args.output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
