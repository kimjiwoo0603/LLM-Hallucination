#!/usr/bin/env python3
"""Create HALO 2.1 RAGTruth source-packet candidates without model calls."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from halo_runner.v21_dataset import build_candidate_artifacts  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-info", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "datasets" / "v2_1" / "candidates")
    parser.add_argument("--seed", type=int, default=20260828)
    args = parser.parse_args()
    manifest = build_candidate_artifacts(args.source_info.resolve(), args.output_dir.resolve(), args.seed)
    print(f"Created {manifest['candidate_records']} candidates in {args.output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
