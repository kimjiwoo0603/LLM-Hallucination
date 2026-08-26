#!/usr/bin/env python3
"""Build pending-only HALO 2.0 candidates from the existing user-provided v1 corpus."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from halo_runner.v2_candidates import write_candidates


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "datasets" / "v2" / "candidates")
    args = parser.parse_args()
    manifest = write_candidates(ROOT, args.output_dir)
    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
