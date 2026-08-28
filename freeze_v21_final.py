#!/usr/bin/env python3
"""Freeze the user-approved HALO 2.1 final benchmark without API calls."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from halo_runner.core import read_jsonl, write_json, write_jsonl  # noqa: E402
from halo_runner.v21_freeze import freeze_final_packets  # noqa: E402

DEVELOPMENT_SOURCE_IDS = {"11945", "11959", "12033", "12432", "13814", "13979", "14058", "14068", "14267", "14679", "15029", "15209", "15329", "15369", "15566", "15797"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packets", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--approval-basis", choices=["user_confirmed_all"], required=True)
    args = parser.parse_args()
    frozen, manifest = freeze_final_packets(read_jsonl(args.packets), approval_basis=args.approval_basis, excluded_source_ids=DEVELOPMENT_SOURCE_IDS)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.output_dir / "halo_v21_final_frozen.jsonl", frozen)
    write_json(args.output_dir / "halo_v21_final_manifest.json", manifest)
    print(f"Frozen {manifest['unit_count']} final packets in {args.output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
