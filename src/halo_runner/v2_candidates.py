"""Mechanical conversion of the legacy HALO corpus into HALO 2.0 candidates.

This module deliberately preserves the distinction between *candidate* and
*approved benchmark* data.  It makes no factual approval, source verification,
or question-validity decision.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from halo_runner.core import read_json, read_jsonl, sha256_text, write_json, write_jsonl


DIFFICULTY_MAP = {"낮음": "EASY", "중간": "MEDIUM", "높음": "HARD"}
QUESTION_TYPE_MAP = {
    "INFORMATION_ABSENCE": "unsupported_detail",
    "TEMPORAL": "unsupported_date",
    "DOMAIN_SPECIFIC": "unsupported_procedure",
    "USER_INDUCED": "false_number",
    "FALSE_PREMISE": "false_relationship",
    "OVERCONFIDENCE": "unsupported_prediction",
}


def _pending_evidence() -> str:
    return "PENDING HUMAN REVIEW: select the exact article evidence or record that the detail is absent."


def _pending_premise() -> str:
    return "PENDING HUMAN REVIEW: state the exact unsupported or false premise, if any."


def _candidate_article(pack: dict[str, Any], article_text: str, source_snapshot: str) -> dict[str, Any]:
    legacy_id = str(pack["article_id"])
    return {
        "article_id": f"V2C_{legacy_id}",
        "source_article_id": legacy_id,
        # Most legacy packs did not store a title.  A visible review marker is
        # safer than deriving one from the article body.
        "title": pack.get("title") or f"[제목 검토 필요: {legacy_id}]",
        "article_text": article_text,
        "source_name": "user-provided news snapshot (unverified)",
        # A local URI makes the absence of a public URL explicit and avoids
        # accidentally treating a file name as a verified web source.
        "original_url": f"local://user-provided-corpus/{legacy_id}",
        "published_at": "unknown",
        "category": "unassigned",
        "review_status": "pending",
        "article_length_chars": len(article_text.strip()),
        "length_screening": "meets_default_minimum" if len(article_text.strip()) >= 1500 else "below_default_minimum_requires_reviewer_decision",
        "source_snapshot": source_snapshot,
        "provenance_status": "needs_human_source_verification",
        "provenance_note": "Converted from the pre-existing user-provided v1 snapshot. A reviewer must enter the public source URL, publication date, category, and approval decision before selection.",
        "ground_truth_candidates": pack.get("ground_truth", []),
    }


def _candidate_question(source: dict[str, Any], article_id: str, origin: str) -> dict[str, Any]:
    source_type = str(source.get("type", ""))
    return {
        "question_id": f"V2C_{source['question_id']}",
        "article_id": article_id,
        "source_question_id": source["question_id"],
        "question_type": QUESTION_TYPE_MAP.get(source_type, "pending_human_mapping"),
        "source_question_type": source_type,
        "difficulty": "ADVERSARIAL" if origin == "high_pressure" else DIFFICULTY_MAP.get(str(source.get("difficulty", "")), "HARD"),
        "question": source["question"],
        "false_premise": _pending_premise(),
        "target_claim": source.get("target_error", "PENDING HUMAN REVIEW"),
        "evidence_basis": _pending_evidence(),
        "annotation_status": "pending",
        "candidate_origin": origin,
        "question_condition": source.get("condition", "BASELINE"),
        "induction_strategy": source.get("induction_strategy", "none"),
        "review_note": "Mechanical v1-to-v2 candidate conversion only; do not approve until the false premise and evidence basis are checked by a human reviewer.",
    }


def build_candidates(repo_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Read legacy packs and return pending-only v2 candidates plus provenance."""
    article_rows, question_rows, source_digests = [], [], {}
    for manifest_row in read_jsonl(repo_root / "datasets" / "article_packs" / "manifest.jsonl"):
        pack_path = repo_root / manifest_row["dataset_path"]
        pack = read_json(pack_path)
        source_digests[manifest_row["article_id"]] = sha256_text(pack_path.read_text(encoding="utf-8"))
        source_snapshot = str(pack.get("source_snapshot") or pack.get("article_path") or "")
        if "article_text" in pack:
            article_text = str(pack["article_text"])
        elif source_snapshot:
            snapshot_path = repo_root / source_snapshot
            article_text = snapshot_path.read_text(encoding="utf-8")
            source_digests[f"{pack['article_id']}:article_snapshot"] = sha256_text(article_text)
        else:
            raise ValueError(f"Legacy article pack {pack_path} has neither article_text nor article_path")
        article = _candidate_article(pack, article_text, source_snapshot)
        article_rows.append(article)
        question_rows.extend(_candidate_question(row, article["article_id"], "base") for row in pack.get("questions", []))
        hp_path = repo_root / "datasets" / "high_pressure_questions" / f"{pack['article_id']}.jsonl"
        if hp_path.exists():
            source_digests[f"{pack['article_id']}:high_pressure"] = sha256_text(hp_path.read_text(encoding="utf-8"))
            question_rows.extend(_candidate_question(row, article["article_id"], "high_pressure") for row in read_jsonl(hp_path))

    article_rows.sort(key=lambda row: row["article_id"])
    question_rows.sort(key=lambda row: row["question_id"])
    provenance = {
        "conversion": "mechanical v1-to-v2 candidate conversion",
        "candidate_article_count": len(article_rows),
        "candidate_question_count": len(question_rows),
        "all_article_review_status": "pending",
        "all_question_annotation_status": "pending",
        "source_file_sha256": dict(sorted(source_digests.items())),
        "source_digest_sha256": sha256_text(json.dumps(source_digests, ensure_ascii=False, sort_keys=True)),
        "approval_rule": "No candidate is an evaluation item until a human reviewer records source provenance and changes its status to approved.",
    }
    return article_rows, question_rows, provenance


def write_review_templates(output_dir: Path, articles: list[dict[str, Any]], questions: list[dict[str, Any]]) -> None:
    """Write human-facing review sheets without changing any candidate status."""
    review_dir = output_dir / "review_templates"
    review_dir.mkdir(parents=True, exist_ok=True)
    article_fields = ["article_id", "title", "review_status", "source_name", "original_url", "published_at", "category", "reviewer", "notes"]
    question_fields = ["question_id", "article_id", "candidate_origin", "question_type", "difficulty", "annotation_status", "false_premise", "target_claim", "evidence_basis", "reviewer", "notes"]
    for filename, fields, rows in (("article_review.template.csv", article_fields, articles), ("question_review.template.csv", question_fields, questions)):
        with (review_dir / filename).open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def write_candidates(repo_root: Path, output_dir: Path) -> dict[str, Any]:
    articles, questions, provenance = build_candidates(repo_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / "articles.candidates.jsonl", articles)
    write_jsonl(output_dir / "questions.candidates.jsonl", questions)
    write_json(output_dir / "conversion_manifest.json", provenance)
    write_review_templates(output_dir, articles, questions)
    return provenance
