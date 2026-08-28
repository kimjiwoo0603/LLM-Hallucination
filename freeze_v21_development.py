#!/usr/bin/env python3
"""Freeze the human-approved HALO 2.1 development set without calling any model."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from halo_runner.core import read_jsonl, write_json, write_jsonl  # noqa: E402
from halo_runner.v21_freeze import freeze_development_packets  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--initial-packets", type=Path, required=True)
    parser.add_argument("--replacement-packets", type=Path, required=True)
    parser.add_argument("--review-decisions", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    review_records = json.loads(args.review_decisions.read_text(encoding="utf-8"))["records"]
    frozen, manifest = freeze_development_packets(
        read_jsonl(args.initial_packets), read_jsonl(args.replacement_packets), review_records
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.output_dir / "halo_v21_development_frozen.jsonl", frozen)
    write_json(args.output_dir / "halo_v21_development_manifest.json", manifest)
    print(f"Frozen {manifest['unit_count']} development packets in {args.output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
