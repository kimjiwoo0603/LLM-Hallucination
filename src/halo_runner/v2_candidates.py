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


def _read_csv_rows(path: Path, required: set[str]) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or [])
        missing = required.difference(fields)
        if missing:
            raise ValueError(f"Review file {path.name} is missing {sorted(missing)[0]}")
        rows = list(reader)
    seen = set()
    for line, row in enumerate(rows, start=2):
        row_id = row.get("article_id") or row.get("question_id")
        if not row_id:
            raise ValueError(f"Review file {path.name} has a blank ID at line {line}")
        if row_id in seen:
            raise ValueError(f"Review file {path.name} has a duplicate ID at line {line}")
        seen.add(row_id)
    return rows


def _require_approved_article_values(row: dict[str, Any]) -> None:
    required = ("source_name", "original_url", "published_at", "category", "reviewer")
    for field in required:
        if not str(row.get(field, "")).strip():
            raise ValueError(f"Cannot approve {row.get('article_id')}: {field} is required")
    if not str(row["original_url"]).startswith(("https://", "http://")):
        raise ValueError(f"Cannot approve {row.get('article_id')}: original_url must be a public http(s) URL")
    if str(row["published_at"]).strip().lower() == "unknown" or str(row["category"]).strip().lower() == "unassigned":
        raise ValueError(f"Cannot approve {row.get('article_id')}: replace the pending source metadata")


def _require_approved_question_values(row: dict[str, Any]) -> None:
    required = ("question_type", "false_premise", "target_claim", "evidence_basis", "reviewer")
    for field in required:
        value = str(row.get(field, "")).strip()
        if not value or value.upper().startswith("PENDING") or value == "pending_human_mapping":
            raise ValueError(f"Cannot approve {row.get('question_id')}: replace pending {field}")


def _apply_rows(records: list[dict[str, Any]], rows: list[dict[str, str]], id_field: str, status_field: str, approval_check: Any) -> list[dict[str, Any]]:
    indexed = {str(record[id_field]): dict(record) for record in records}
    row_index = {str(row[id_field]): row for row in rows}
    unknown = sorted(set(row_index).difference(indexed))
    if unknown:
        raise ValueError(f"Review file contains unknown {id_field}: {unknown[0]}")
    allowed = {"pending", "approved", "rejected"}
    output = []
    for record_id in sorted(indexed):
        record = indexed[record_id]
        review = row_index.get(record_id)
        if review:
            proposed_status = str(review.get(status_field, "")).strip() or record[status_field]
            if proposed_status not in allowed:
                raise ValueError(f"Invalid {status_field} for {record_id}")
            # Copy only values that the reviewer actually supplied.  Candidate
            # provenance remains intact and no status is inferred.
            for key, value in review.items():
                if key not in {id_field, status_field, "reviewer", "notes"} and value is not None and value.strip():
                    record[key] = value.strip()
            record[status_field] = proposed_status
            if review.get("reviewer", "").strip():
                record["reviewed_by"] = review["reviewer"].strip()
            if review.get("notes", "").strip():
                record["review_notes"] = review["notes"].strip()
            if proposed_status == "approved":
                approval_check({**record, "reviewer": review.get("reviewer", "")})
        output.append(record)
    return output


def apply_review_templates(article_candidates: Path, question_candidates: Path, article_reviews: Path, question_reviews: Path, output_dir: Path) -> dict[str, Any]:
    """Apply human review sheets, failing closed on incomplete approvals."""
    articles, questions = read_jsonl(article_candidates), read_jsonl(question_candidates)
    article_rows = _read_csv_rows(article_reviews, {"article_id", "review_status", "reviewer"})
    question_rows = _read_csv_rows(question_reviews, {"question_id", "annotation_status", "reviewer"})
    updated_articles = _apply_rows(articles, article_rows, "article_id", "review_status", _require_approved_article_values)
    updated_questions = _apply_rows(questions, question_rows, "question_id", "annotation_status", _require_approved_question_values)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / "articles.reviewed.jsonl", updated_articles)
    write_jsonl(output_dir / "questions.reviewed.jsonl", updated_questions)
    report = {
        "articles": {status: sum(row["review_status"] == status for row in updated_articles) for status in ("pending", "approved", "rejected")},
        "questions": {status: sum(row["annotation_status"] == status for row in updated_questions) for status in ("pending", "approved", "rejected")},
        "input_sha256": {
            "article_candidates": sha256_text(article_candidates.read_text(encoding="utf-8")),
            "question_candidates": sha256_text(question_candidates.read_text(encoding="utf-8")),
            "article_reviews": sha256_text(article_reviews.read_text(encoding="utf-8-sig")),
            "question_reviews": sha256_text(question_reviews.read_text(encoding="utf-8-sig")),
        },
        "rule": "Only values supplied by a human review sheet were copied. Incomplete approval rows stop the import without writing partial output.",
    }
    write_json(output_dir / "review_import_report.json", report)
    return report
