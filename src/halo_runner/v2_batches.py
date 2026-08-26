"""Pre-register balanced, cost-limited HALO 2.0 execution batches."""
from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any

from halo_runner.core import read_jsonl, sha256_text, write_json, write_jsonl


def build_pair_batches(benchmark_dir: Path, output_dir: Path, seed: int, repetitions: int = 3, conditions: int = 4, stages: int = 3) -> dict[str, Any]:
    """Pair each base question with its pre-existing pressure variant.

    Each full batch takes one pair per article whenever possible.  Thus the
    first batch has ten articles represented and exactly balanced base/high
    pressure questions.  The selection order is frozen before model calls.
    """
    articles = read_jsonl(benchmark_dir / "articles.jsonl")
    questions = read_jsonl(benchmark_dir / "questions.jsonl")
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for question in questions:
        group_id = str(question.get("source_question_id") or question["question_id"])
        groups[group_id].append(question)
    pairs: dict[str, list[list[dict[str, Any]]]] = defaultdict(list)
    for group_id, members in groups.items():
        origins = {row.get("candidate_origin") for row in members}
        article_ids = {row["article_id"] for row in members}
        if len(members) != 2 or origins != {"base", "high_pressure"} or len(article_ids) != 1:
            raise ValueError(f"Cannot form a base/high-pressure pair for {group_id}")
        pairs[next(iter(article_ids))].append(sorted(members, key=lambda row: str(row["question_id"])))
    rng = random.Random(seed)
    for article_id in pairs:
        pairs[article_id].sort(key=lambda pair: pair[0]["question_id"])
        rng.shuffle(pairs[article_id])

    article_order = sorted(pairs)
    batches: list[list[dict[str, Any]]] = []
    while any(pairs.values()):
        batch: list[dict[str, Any]] = []
        active_articles = [article_id for article_id in article_order if pairs[article_id]]
        # Once all but one article are exhausted, keep the remaining matched
        # pairs together instead of creating artificial two-question batches.
        if len(active_articles) == 1:
            article_id = active_articles[0]
            while pairs[article_id]:
                batch.extend(pairs[article_id].pop(0))
        else:
            for article_id in active_articles:
                batch.extend(pairs[article_id].pop(0))
        batches.append(batch)

    output_dir.mkdir(parents=True, exist_ok=True)
    plan_rows = []
    for number, batch in enumerate(batches, start=1):
        batch_dir = output_dir / f"batch_{number:02d}"
        batch_dir.mkdir(parents=True, exist_ok=True)
        write_jsonl(batch_dir / "articles.jsonl", articles)
        write_jsonl(batch_dir / "questions.jsonl", batch)
        plan_rows.append({
            "batch_id": f"batch_{number:02d}",
            "question_count": len(batch),
            "article_count": len({row["article_id"] for row in batch}),
            "base_questions": sum(row.get("candidate_origin") == "base" for row in batch),
            "high_pressure_questions": sum(row.get("candidate_origin") == "high_pressure" for row in batch),
            "question_ids": [row["question_id"] for row in batch],
            "estimated_requests": len(batch) * repetitions * conditions * stages,
        })
    plan = {
        "selection_seed": seed,
        "design": "base/high-pressure question pairs are selected together; each full batch includes one pair per article before any article receives a second pair",
        "repetitions": repetitions,
        "conditions": conditions,
        "stages": stages,
        "batches": plan_rows,
        "source_benchmark_sha256": {
            "articles": sha256_text((benchmark_dir / "articles.jsonl").read_text(encoding="utf-8")),
            "questions": sha256_text((benchmark_dir / "questions.jsonl").read_text(encoding="utf-8")),
        },
    }
    write_json(output_dir / "batch_plan.json", plan)
    return plan
