from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from halo_runner.core import DryRunClient, read_json, read_jsonl, render_prompt, sha256_text, utc_now, write_json, write_jsonl, write_label_template


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
        try:
            with urllib.request.urlopen(request, timeout=self.spec.get("timeout_seconds", 120)) as response:
                body: Any = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
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
    if max_articles < 0 or max_questions < 0:
        raise ValueError("max_articles and max_questions_per_article must be zero or greater")
    if max_articles:
        packs = packs[:max_articles]
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    records: list[dict[str, Any]] = []
    clients = {agent_id: ProviderClient(agent) for agent_id, agent in config["agents"].items()}
    for pack_ref in packs:
        pack = read_json(project_path(config_path, pack_ref["dataset_path"]))
        article = pack.get("article_text")
        if article is None:
            article = project_path(config_path, pack["article_path"]).read_text(encoding="utf-8")
        for repetition in range(1, config["repetitions"] + 1):
            questions = pack["questions"]
            if max_questions:
                questions = questions[:max_questions]
            for question in questions:
                context = {"ARTICLE": article, "QUESTION": question["question"]}
                for stage in config["stages"]:
                    agent = config["agents"][stage["agent"]]
                    prompt = render_prompt(stage["prompt_template"], context, stage["id"])
                    answer = DryRunClient().complete(prompt) if dry_run else clients[stage["agent"]].complete(prompt)
                    context[stage["id"]] = answer
                    records.append({"run_id": run_id, "generated_at": utc_now(), "article_id": pack["article_id"], "source_type": pack["source_type"], "repetition": repetition, "question_id": question["question_id"], "question_type": question["type"], "target_error": question["target_error"], "question": question["question"], "stage": stage["id"], "agent": stage["agent"], "provider": agent["provider"], "model": agent["model"], "response": answer, "prompt_sha256": sha256_text(prompt), "response_sha256": sha256_text(answer), "article_sha256": sha256_text(article), "status": "PENDING_MANUAL_LABEL"})
    write_jsonl(run_dir / "responses.jsonl", records)
    write_label_template(run_dir / "labels.template.csv", records)
    write_json(run_dir / "manifest.json", {"run_id": run_id, "created_at": utc_now(), "dry_run": dry_run, "dataset_manifest_path": config["dataset_manifest_path"], "max_articles": max_articles, "max_questions_per_article": max_questions, "agents": config["agents"]})
    return run_dir

