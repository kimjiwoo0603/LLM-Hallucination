"""HALO 2.0 dataset, annotation, and analysis utilities.

This module intentionally automates only mechanical, auditable work.  It never
auto-approves candidate articles/questions or auto-resolves human-labeler
disagreements.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from halo_runner.core import read_jsonl, sha256_text, write_json, write_jsonl

TRACKING_PARAMETERS = {"utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "fbclid", "gclid"}
ARTICLE_REQUIRED = {"article_id", "title", "article_text", "source_name", "original_url", "published_at", "category", "review_status"}
QUESTION_REQUIRED = {"question_id", "article_id", "question_type", "difficulty", "question", "false_premise", "target_claim", "evidence_basis", "annotation_status"}
LABEL_FIELDS = ["blind_id", "question_validity", "false_premise_validity", "hallucination", "accuracy", "usefulness", "abstention", "reviewer", "notes"]


def normalize_url(value: str) -> str:
    parts = urlsplit(value.strip())
    query = [(key, item) for key, item in parse_qsl(parts.query, keep_blank_values=True) if key.lower() not in TRACKING_PARAMETERS]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/") or "/", urlencode(query), ""))


def _fail(message: str, problems: list[str]) -> None:
    problems.append(message)


def validate_articles(records: list[dict[str, Any]], min_chars: int, max_chars: int) -> list[str]:
    problems: list[str] = []
    seen_ids, seen_urls, seen_hashes = set(), set(), set()
    for index, article in enumerate(records, start=1):
        missing = ARTICLE_REQUIRED.difference(article)
        if missing:
            _fail(f"article line {index}: missing {sorted(missing)[0]}", problems); continue
        aid, text = str(article["article_id"]), str(article["article_text"]).strip()
        if aid in seen_ids: _fail(f"article line {index}: duplicate article_id {aid}", problems)
        seen_ids.add(aid)
        if not min_chars <= len(text) <= max_chars: _fail(f"article line {index}: body length outside {min_chars}..{max_chars}", problems)
        url = normalize_url(str(article["original_url"]))
        if url in seen_urls: _fail(f"article line {index}: duplicate normalized URL", problems)
        seen_urls.add(url)
        digest = sha256_text(text)
        if digest in seen_hashes: _fail(f"article line {index}: duplicate article text", problems)
        seen_hashes.add(digest)
    return problems


def validate_questions(records: list[dict[str, Any]], article_ids: set[str]) -> list[str]:
    problems, seen_ids = [], set()
    valid_difficulty = {"EASY", "MEDIUM", "HARD", "ADVERSARIAL"}
    for index, question in enumerate(records, start=1):
        missing = QUESTION_REQUIRED.difference(question)
        if missing:
            _fail(f"question line {index}: missing {sorted(missing)[0]}", problems); continue
        qid = str(question["question_id"])
        if qid in seen_ids: _fail(f"question line {index}: duplicate question_id {qid}", problems)
        seen_ids.add(qid)
        if question["article_id"] not in article_ids: _fail(f"question line {index}: unknown article_id", problems)
        if question["difficulty"] not in valid_difficulty: _fail(f"question line {index}: invalid difficulty", problems)
        if question["annotation_status"] not in {"pending", "approved", "rejected"}: _fail(f"question line {index}: invalid annotation_status", problems)
    return problems


def approved_benchmark(articles: list[dict[str, Any]], questions: list[dict[str, Any]], seed: int, target_articles: int | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    approved_articles = [item for item in articles if item.get("review_status") == "approved"]
    rng = random.Random(seed)
    approved_articles.sort(key=lambda item: str(item["article_id"]))
    rng.shuffle(approved_articles)
    selected = approved_articles[:target_articles] if target_articles else approved_articles
    selected.sort(key=lambda item: str(item["article_id"]))
    selected_ids = {item["article_id"] for item in selected}
    approved_questions = [item for item in questions if item.get("annotation_status") == "approved" and item["article_id"] in selected_ids]
    approved_questions.sort(key=lambda item: str(item["question_id"]))
    return selected, approved_questions


def write_dataset_manifest(path: Path, articles: list[dict[str, Any]], questions: list[dict[str, Any]], seed: int, version: str) -> None:
    categories = Counter(str(item["category"]) for item in articles)
    payload = {"dataset_id": "halo-news-benchmark", "dataset_version": version, "selection_seed": seed, "article_count": len(articles), "question_count": len(questions), "category_distribution": dict(sorted(categories.items())), "article_sha256": {item["article_id"]: sha256_text(str(item["article_text"])) for item in articles}}
    payload["manifest_sha256"] = sha256_text(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    write_json(path, payload)


def final_records(run_dirs: list[Path]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for run_dir in run_dirs:
        records = read_jsonl(run_dir / "responses.jsonl")
        finals = [row for row in records if row.get("stage_role") == "grounded_final_editor" or row.get("stage") in {"FINAL", "S3", "M3"}]
        result.extend(finals)
    return result


def write_v2_blind_packet(output_dir: Path, records: list[dict[str, Any]], articles: dict[str, str]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    ordered = sorted(records, key=lambda row: sha256_text("|".join(str(row.get(key, "")) for key in ("run_id", "article_id", "question_id", "repetition", "response_sha256"))))
    with (output_dir / "blind_review_packets.csv").open("w", encoding="utf-8", newline="") as packet, (output_dir / "blind_key.coordinator_only.csv").open("w", encoding="utf-8", newline="") as key, (output_dir / "labels.rater_a.template.csv").open("w", encoding="utf-8", newline="") as labels:
        packet_writer = csv.DictWriter(packet, fieldnames=["blind_id", "article", "question", "response"]); packet_writer.writeheader()
        key_fields = ["blind_id", "run_id", "condition_id", "article_id", "question_id", "repetition", "stage", "provider", "model", "question_type", "difficulty"]
        key_writer = csv.DictWriter(key, fieldnames=key_fields); key_writer.writeheader()
        label_writer = csv.DictWriter(labels, fieldnames=LABEL_FIELDS); label_writer.writeheader()
        for number, row in enumerate(ordered, start=1):
            blind_id = f"B{number:05d}"
            packet_writer.writerow({"blind_id": blind_id, "article": articles.get(row.get("article_id"), ""), "question": row.get("question", ""), "response": row.get("response", "")})
            key_writer.writerow({field: row.get(field, "") for field in key_fields} | {"blind_id": blind_id})
            label_writer.writerow({"blind_id": blind_id})


def read_v2_labels(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not set(LABEL_FIELDS).issubset(reader.fieldnames): raise ValueError("Use the v2 rater label template")
        rows: dict[str, dict[str, str]] = {}
        for line, row in enumerate(reader, start=2):
            blind_id = row["blind_id"]
            if blind_id in rows: raise ValueError(f"duplicate blind_id at line {line}")
            if row["hallucination"] not in {"0", "1"}: raise ValueError(f"hallucination must be 0/1 at line {line}")
            if row["accuracy"] not in {"0", "1", "2"}: raise ValueError(f"accuracy must be 0/1/2 at line {line}")
            if row["usefulness"] not in {"1", "2", "3", "4", "5"}: raise ValueError(f"usefulness must be 1..5 at line {line}")
            if row["abstention"] not in {"0", "1"}: raise ValueError(f"abstention must be 0/1 at line {line}")
            if row["question_validity"] not in {"0", "1"} or row["false_premise_validity"] not in {"0", "1"}: raise ValueError(f"validity must be 0/1 at line {line}")
            rows[blind_id] = row
    return rows


def write_adjudication(output_dir: Path, labels_a: dict[str, dict[str, str]], labels_b: dict[str, dict[str, str]]) -> tuple[int, int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    agreed, disagreements = [], []
    outcomes = ["question_validity", "false_premise_validity", "hallucination", "accuracy", "usefulness", "abstention"]
    for blind_id in sorted(set(labels_a) | set(labels_b)):
        a, b = labels_a.get(blind_id), labels_b.get(blind_id)
        if not a or not b:
            disagreements.append({"blind_id": blind_id, "reason": "missing_rater_row"}); continue
        if all(a[key] == b[key] for key in outcomes): agreed.append({key: a[key] for key in LABEL_FIELDS})
        else: disagreements.append({"blind_id": blind_id, "reason": "label_disagreement", **{f"a_{key}": a[key] for key in outcomes}, **{f"b_{key}": b[key] for key in outcomes}})
    with (output_dir / "agreed_labels.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LABEL_FIELDS); writer.writeheader(); writer.writerows(agreed)
    fields = sorted({key for row in disagreements for key in row} | {"blind_id", "reason"})
    with (output_dir / "adjudication_required.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(disagreements)
    return len(agreed), len(disagreements)


def wilson_interval(events: int, total: int) -> tuple[float | None, float | None]:
    if not total: return None, None
    z, p = 1.959963984540054, events / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denominator
    return round(max(0.0, centre - margin), 4), round(min(1.0, centre + margin), 4)


def exact_mcnemar_pvalue(b: int, c: int) -> float | None:
    n = b + c
    if not n: return None
    tail = sum(math.comb(n, k) for k in range(min(b, c) + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def summarize_final_labels(records: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records: groups[str(row.get("condition_id", "unknown"))].append(row)
    rows = []
    for condition, group in sorted(groups.items()):
        valid = [row for row in group if row.get("question_validity") == "1" and row.get("false_premise_validity") == "1"]
        hallucinations = sum(int(row["hallucination"]) for row in valid)
        low, high = wilson_interval(hallucinations, len(valid))
        rows.append({"condition_id": condition, "n_valid": len(valid), "hallucinations": hallucinations, "hallucination_rate": round(hallucinations / len(valid), 4) if valid else None, "hallucination_ci95": [low, high], "mean_accuracy": round(sum(int(row["accuracy"]) for row in valid) / len(valid), 4) if valid else None, "mean_usefulness": round(sum(int(row["usefulness"]) for row in valid) / len(valid), 4) if valid else None, "abstention_rate": round(sum(int(row["abstention"]) for row in valid) / len(valid), 4) if valid else None})
    return {"analysis_note": "Repeated trials are retained as clustered records. Do not apply independent-sample tests; use a repeated-measures model specified before the primary analysis.", "condition_summary": rows}
