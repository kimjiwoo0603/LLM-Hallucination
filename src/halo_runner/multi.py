from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from halo_runner.core import DryRunClient, read_json, read_jsonl, render_prompt, sha256_text, utc_now, write_json, write_jsonl, write_label_template


class ProviderClient:
    def __init__(self, spec: dict[str, Any]):
        self.spec = spec

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
        request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=self.spec.get("timeout_seconds", 120)) as response:
            body: Any = json.loads(response.read().decode("utf-8"))
        for part in text_path:
            body = body[part]
        return body


def project_path(config_path: Path, raw: str) -> Path:
    candidate = Path(raw)
    return candidate if candidate.is_absolute() else (config_path.parent.parent / candidate).resolve()


def run_batch(config_path: Path, output_root: Path, run_id: str, dry_run: bool) -> Path:
    config = read_json(config_path)
    packs = read_jsonl(project_path(config_path, config["dataset_manifest_path"]))
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    records: list[dict[str, Any]] = []
    for pack_ref in packs:
        pack = read_json(project_path(config_path, pack_ref["dataset_path"]))
        article = pack["article_text"]
        for repetition in range(1, config["repetitions"] + 1):
            for question in pack["questions"]:
                context = {"ARTICLE": article, "QUESTION": question["question"]}
                for stage in config["stages"]:
                    agent = config["agents"][stage["agent"]]
                    prompt = render_prompt(stage["prompt_template"], context, stage["id"])
                    answer = DryRunClient().complete(prompt) if dry_run else ProviderClient(agent).complete(prompt)
                    context[stage["id"]] = answer
                    records.append({"run_id": run_id, "generated_at": utc_now(), "article_id": pack["article_id"], "source_type": pack["source_type"], "repetition": repetition, "question_id": question["question_id"], "question_type": question["type"], "target_error": question["target_error"], "question": question["question"], "stage": stage["id"], "agent": stage["agent"], "provider": agent["provider"], "model": agent["model"], "response": answer, "prompt_sha256": sha256_text(prompt), "response_sha256": sha256_text(answer), "article_sha256": sha256_text(article), "status": "PENDING_MANUAL_LABEL"})
    write_jsonl(run_dir / "responses.jsonl", records)
    write_label_template(run_dir / "labels.template.csv", records)
    write_json(run_dir / "manifest.json", {"run_id": run_id, "created_at": utc_now(), "dry_run": dry_run, "dataset_manifest_path": config["dataset_manifest_path"], "agents": config["agents"]})
    return run_dir
