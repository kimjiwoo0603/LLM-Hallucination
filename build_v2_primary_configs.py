#!/usr/bin/env python3
"""Create frozen same-model HALO 2.0 primary execution configs (no API calls)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from halo_runner.v2_execution import build_primary_execution_configs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument("--model", default="gpt-4.1")
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--minimum-interval-seconds", type=float, default=4)
    args = parser.parse_args()
    print(json.dumps(build_primary_execution_configs(args.benchmark_dir, args.output_dir, args.dataset_version, args.model, args.api_key_env, args.repetitions, args.minimum_interval_seconds), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
