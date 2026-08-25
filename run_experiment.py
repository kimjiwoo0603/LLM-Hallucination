#!/usr/bin/env python3
"""Run a fixed S1 -> S2 -> S3 HALO experiment and save raw responses."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from halo_runner.core import execute  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=ROOT / "results")
    parser.add_argument("--run-id")
    parser.add_argument("--dry-run", action="store_true", help="Validate the pipeline without calling a model API")
    args = parser.parse_args()
    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    try:
        run_dir = execute(args.config.resolve(), args.output_root.resolve(), run_id, args.dry_run)
    except (FileNotFoundError, FileExistsError, RuntimeError, ValueError) as error:
        parser.error(str(error))
    print(run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
