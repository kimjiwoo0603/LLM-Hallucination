#!/usr/bin/env python3
"""Create blinded human-review files for an already completed HALO run."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from halo_runner.core import read_json, read_jsonl, write_blind_review_files  # noqa: E402


def project_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (ROOT / path).resolve()


def load_articles(dataset_manifest: Path) -> dict[str, str]:
    articles: dict[str, str] = {}
    for reference in read_jsonl(dataset_manifest):
        pack = read_json(project_path(reference["dataset_path"]))
        article = pack.get("article_text")
        if article is None:
            article = project_path(pack["article_path"]).read_text(encoding="utf-8")
        articles[pack["article_id"]] = article
    return articles


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--run-dir",
        type=Path,
        action="append",
        required=True,
        help="Unzipped results/<run-id> directory; repeat this option to mix multiple conditions",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directory for the combined blinded files; required when mixing multiple run directories",
    )
    parser.add_argument(
        "--dataset-manifest",
        type=Path,
        default=ROOT / "datasets/article_packs/manifest.jsonl",
        help="Article-pack manifest used for the run",
    )
    args = parser.parse_args()
    run_dirs = [run_dir.resolve() for run_dir in args.run_dir]
    output_dir = args.output_dir.resolve() if args.output_dir else run_dirs[0]
    if len(run_dirs) > 1 and not args.output_dir:
        raise ValueError("--output-dir is required when mixing multiple runs")
    output_dir.mkdir(parents=True, exist_ok=True)
    records = [record for run_dir in run_dirs for record in read_jsonl(run_dir / "responses.jsonl")]
    if not records:
        raise ValueError("responses.jsonl is empty")
    write_blind_review_files(output_dir, records, load_articles(args.dataset_manifest.resolve()))
    print(output_dir / "blind_review_packets.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

