from __future__ import annotations
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from halo_runner.multi import run_batch
parser = argparse.ArgumentParser()
parser.add_argument("--config", type=Path, required=True)
parser.add_argument("--output-root", type=Path, default=ROOT / "results")
parser.add_argument("--run-id")
parser.add_argument("--dry-run", action="store_true")
args = parser.parse_args()
run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
print(run_batch(args.config.resolve(), args.output_root.resolve(), run_id, args.dry_run))
