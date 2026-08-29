#!/usr/bin/env python3
"""Freeze balanced base/high-pressure HALO 2.0 execution batches (no API calls)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from halo_runner.v2_batches import build_pair_batches


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark-dir", type=Path, required=True); parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True); parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--conditions", type=int, default=4); parser.add_argument("--stages", type=int, default=3)
    args = parser.parse_args()
    print(json.dumps(build_pair_batches(args.benchmark_dir, args.output_dir, args.seed, args.repetitions, args.conditions, args.stages), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
