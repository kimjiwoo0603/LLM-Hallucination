from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from halo_runner.core import DryRunClient, read_json, read_jsonl, render_prompt, sha256_text, utc_now, write_blind_review_files, write_json, write_jsonl, write_label_template


def retry_delay_seconds(detail: str, attempt: int) -> float:
    match = re.search(r"try again in\s+([0-9.]+)\s*(ms|s)(?:\b|$)", detail, flags=re.IGNORECASE)
    if match:
        value = float(match.group(1))
        return max(1.0, value / 1000 if match.group(2) == "ms" else value)
    return min(60.0, 2.0**attempt)


def is_daily_quota_exhausted(detail: str) -> bool:
    return bool(re.search(r"(?:RequestsPerDay|PerDay|daily\s+quota|per\s+day)", detail, flags=re.IGNORECASE))


def checker_supported_context(checker_response: str) -> tuple[str, int]:
    """Return only article-supported checker items for the final editor.

    The checker sees the M1 draft, but its full report must never become an
    upstream shortcut through which M3 can read that draft.  A malformed report
    therefore produces an empty context rather than falling back to raw text.
    """
    candidate = checker_response.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", candidate, flags=re.IGNORECASE)
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        return "기사로 SUPPORTED로 확정된 항목이 없습니다.", 0
    items = payload.get("supported_items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return "기사로 SUPPORTED로 확정된 항목이 없습니다.", 0
    clean_items = [item.strip() for item in items if isinstance(item, str) and item.strip()]
    if not clean_items:
        return "기사로 SUPPORTED로 확정된 항목이 없습니다.", 0
    return "\n".join(f"- {item}" for item in clean_items), len(clean_items)


class ProviderClient:
    def __init__(self, spec: dict[str, Any]):
        self.spec = spec
        self.last_request_started_at = 0.0

    def complete(self, prompt: str) -> str:
        key = os.environ.get(self.spec["api_key_env"])
        if not key:
            raise RuntimeError(f"Environment variable {self.spec['api_key_env']} is not set")
        provider = self.spec["provider"]
        if provider == "openai":
            url = self.spec.get("api_base", "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            payload = {"model": self.spec["model"], "messages": [{"role": "user", "content": prompt}], "temperature": self.spec["temperature"], "max_tokens": self.spec["max_tokens"]}
            text_path = ("choices", 0, "message", "content")
        elif provider == "anthropic":
            url = self.spec.get("api_base", "https://api.anthropic.com/v1") + "/messages"
            headers = {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
            payload = {"model": self.spec["model"], "max_tokens": self.spec["max_tokens"], "temperature": self.spec["temperature"], "messages": [{"role": "user", "content": prompt}]}
            text_path = ("content", 0, "text")
        elif provider == "gemini":
            base = self.spec.get("api_base", "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
            url = f"{base}/models/{self.spec['model']}:generateContent?key={urllib.parse.quote(key)}"
            headers = {"Content-Type": "application/json"}
            payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": self.spec["temperature"], "maxOutputTokens": self.spec["max_tokens"]}}
            text_path = ("candidates", 0, "content", "parts", 0, "text")
        else:
            raise ValueError(f"Unsupported provider: {provider}")
        minimum_interval = float(self.spec.get("minimum_interval_seconds", 0))
        if minimum_interval:
            remaining = minimum_interval - (time.monotonic() - self.last_request_started_at)
            if remaining > 0:
                time.sleep(remaining)
        self.last_request_started_at = time.monotonic()
        request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        max_rate_limit_retries = int(self.spec.get("max_rate_limit_retries", 20))
        for attempt in range(max_rate_limit_retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.spec.get("timeout_seconds", 120)) as response:
                    body: Any = json.loads(response.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as error:
                detail = error.read().decode("utf-8", errors="replace")
                if error.code == 429 and is_daily_quota_exhausted(detail):
                    raise RuntimeError(
                        f"{provider} daily quota is exhausted; save the uploaded partial artifact and resume in the next quota window"
                    ) from error
                if error.code == 429 and attempt < max_rate_limit_retries:
                    time.sleep(retry_delay_seconds(detail, attempt))
                    continue
                raise RuntimeError(f"{provider} API request failed (HTTP {error.code}): {detail}") from error
        for part in text_path:
            body = body[part]
        return body


def project_path(config_path: Path, raw: str) -> Path:
    candidate = Path(raw)
    return candidate if candidate.is_absolute() else (config_path.parent.parent / candidate).resolve()


def run_batch(config_path: Path, output_root: Path, run_id: str, dry_run: bool) -> Path:
    config = read_json(config_path)
    packs = read_jsonl(project_path(config_path, config["dataset_manifest_path"]))
    max_articles = int(config.get("max_articles", 0))
    max_questions = int(config.get("max_questions_per_article", 0))
    question_offset = int(config.get("question_offset", 0))
    max_total_questions = int(config.get("max_total_questions", 0))
    if min(max_articles, max_questions, question_offset, max_total_questions) < 0:
        raise ValueError("run limits and question_offset must be zero or greater")
    if max_articles:
        packs = packs[:max_articles]
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    work_items: list[tuple[dict[str, Any], str, dict[str, Any]]] = []
    articles_by_id: dict[str, str] = {}
    for pack_ref in packs:
        pack = read_json(project_path(config_path, pack_ref["dataset_path"]))
        article = pack.get("article_text")
        if article is None:
            article = project_path(config_path, pack["article_path"]).read_text(encoding="utf-8")
        articles_by_id[pack["article_id"]] = article
        questions = (
            read_jsonl(project_path(config_path, pack_ref["questions_path"]))
            if "questions_path" in pack_ref
            else pack["questions"]
        )
        if max_questions:
            questions = questions[:max_questions]
        work_items.extend((pack, article, question) for question in questions)
    if max_total_questions:
        work_items = work_items[question_offset : question_offset + max_total_questions]
    else:
        work_items = work_items[question_offset:]

    write_json(run_dir / "manifest.json", {"run_id": run_id, "created_at": utc_now(), "dry_run": dry_run, "dataset_manifest_path": config["dataset_manifest_path"], "max_articles": max_articles, "max_questions_per_article": max_questions, "question_offset": question_offset, "max_total_questions": max_total_questions, "selected_question_count": len(work_items), "agents": config["agents"]})
    records: list[dict[str, Any]] = []
    shared_clients: dict[str, ProviderClient] = {}
    clients: dict[str, ProviderClient] = {}
    for agent_id, agent in config["agents"].items():
        client_key = json.dumps(agent, sort_keys=True)
        clients[agent_id] = shared_clients.setdefault(client_key, ProviderClient(agent))
    for pack, article, question in work_items:
        for repetition in range(1, config["repetitions"] + 1):
            context = {"ARTICLE": article, "QUESTION": question["question"]}
            for stage in config["stages"]:
                agent = config["agents"][stage["agent"]]
                prompt = render_prompt(stage["prompt_template"], context, stage["id"])
                answer = DryRunClient().complete(prompt) if dry_run else clients[stage["agent"]].complete(prompt)
                context[stage["id"]] = answer
                if stage.get("role") == "article_grounded_checker":
                    supported_context, supported_item_count = checker_supported_context(answer)
                    context[f"{stage['id']}_SUPPORTED"] = supported_context
                else:
                    supported_item_count = 0
                records.append({"run_id": run_id, "generated_at": utc_now(), "article_id": pack["article_id"], "source_type": pack["source_type"], "repetition": repetition, "question_id": question["question_id"], "question_type": question["type"], "question_condition": question.get("condition", "BASELINE"), "induction_strategy": question.get("induction_strategy"), "source_question_id": question.get("source_question_id"), "target_error": question["target_error"], "question": question["question"], "stage": stage["id"], "stage_role": stage.get("role", "answer_generation"), "agent": stage["agent"], "provider": agent["provider"], "model": agent["model"], "response": answer, "prompt_sha256": sha256_text(prompt), "response_sha256": sha256_text(answer), "article_sha256": sha256_text(article), "checker_supported_item_count": supported_item_count, "m3_input_policy": stage.get("input_policy", "checker_supported_only") if stage.get("role") == "grounded_final_editor" else None, "status": "PENDING_MANUAL_LABEL"})
                write_jsonl(run_dir / "responses.jsonl", records)
                write_label_template(run_dir / "labels.template.csv", records)
                write_blind_review_files(run_dir, records, articles_by_id)
    write_jsonl(run_dir / "responses.jsonl", records)
    write_label_template(run_dir / "labels.template.csv", records)
    write_blind_review_files(run_dir, records, articles_by_id)
    return run_dir

