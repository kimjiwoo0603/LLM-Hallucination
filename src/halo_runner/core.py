from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if line.strip():
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as error:
                    raise ValueError(f"Invalid JSONL at {path}:{line_number}") from error
    return records


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def resolve_project_path(config_path: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (config_path.parent.parent / path).resolve()


def validate_config(config: dict[str, Any]) -> None:
    required = {"experiment_name", "model", "article_path", "questions_path", "repetitions", "stages"}
    missing = required.difference(config)
    if missing:
        raise ValueError(f"Missing config keys: {', '.join(sorted(missing))}")
    if not isinstance(config["repetitions"], int) or config["repetitions"] < 1:
        raise ValueError("repetitions must be a positive integer")
    if not config["stages"]:
        raise ValueError("At least one stage is required")

    stage_ids = [stage.get("id") for stage in config["stages"]]
    if any(not stage_id for stage_id in stage_ids) or len(stage_ids) != len(set(stage_ids)):
        raise ValueError("Every stage needs a unique id")
    for stage in config["stages"]:
        if not stage.get("prompt_template"):
            raise ValueError(f"Stage {stage.get('id', '<unknown>')} has no prompt_template")


def frozen_config(config: dict[str, Any]) -> dict[str, Any]:
    """Keep reproducibility metadata, but never copy a key value into results."""
    copy = json.loads(json.dumps(config))
    model = copy.get("model", {})
    model.pop("api_key", None)
    return copy


class OpenAICompatibleClient:
    def __init__(self, model: dict[str, Any]):
        self.model = model

    def complete(self, prompt: str) -> str:
        api_key_env = self.model.get("api_key_env")
        if not api_key_env:
            raise ValueError("model.api_key_env is required for a live run")
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise RuntimeError(f"Environment variable {api_key_env} is not set")

        api_base = self.model.get("api_base", "https://api.openai.com/v1").rstrip("/")
        payload: dict[str, Any] = {
            "model": self.model["name"],
            "messages": [{"role": "user", "content": prompt}],
        }
        for key in ("temperature", "top_p", "seed", "max_tokens"):
            if key in self.model:
                payload[key] = self.model[key]
        request = urllib.request.Request(
            f"{api_base}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.model.get("timeout_seconds", 120)) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Model request failed ({error.code}): {detail}") from error
        except urllib.error.URLError as error:
            raise RuntimeError(f"Model request could not be sent: {error.reason}") from error
        try:
            return body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise RuntimeError("Model response did not contain choices[0].message.content") from error


class DryRunClient:
    def complete(self, prompt: str) -> str:
        # Deliberately deterministic: useful only for pipeline verification, never for evaluation.
        return f"[DRY RUN — no model call]\nPrompt SHA-256: {sha256_text(prompt)}"


def render_prompt(template: str, context: dict[str, str], stage_id: str) -> str:
    try:
        return template.format(**context)
    except KeyError as error:
        raise ValueError(f"Stage {stage_id} references an unavailable placeholder: {error.args[0]}") from error


def execute(config_path: Path, output_root: Path, run_id: str, dry_run: bool = False) -> Path:
    config = read_json(config_path)
    validate_config(config)
    article_path = resolve_project_path(config_path, config["article_path"])
    if not article_path.exists():
        raise FileNotFoundError(f"Article file not found: {article_path}")
    article = article_path.read_text(encoding="utf-8").strip()
    if not article or article.startswith("[PASTE THE EXACT ARTICLE"):
        raise ValueError("Paste the exact source article into the configured article file before a live run")
    questions = read_jsonl(resolve_project_path(config_path, config["questions_path"]))
    if not questions:
        raise ValueError("Question dataset is empty")
    if any("question_id" not in question or "question" not in question for question in questions):
        raise ValueError("Every question needs question_id and question")

    run_dir = output_root / run_id
    if run_dir.exists():
        raise FileExistsError(f"Run directory already exists: {run_dir}")
    run_dir.mkdir(parents=True)

    client = DryRunClient() if dry_run else OpenAICompatibleClient(config["model"])
    frozen = frozen_config(config)
    frozen_text = json.dumps(frozen, ensure_ascii=False, sort_keys=True)
    manifest = {
        "experiment_name": config["experiment_name"],
        "run_id": run_id,
        "created_at": utc_now(),
        "dry_run": dry_run,
        "config_sha256": sha256_text(frozen_text),
        "article_sha256": sha256_text(article),
        "question_dataset_sha256": sha256_text(
            resolve_project_path(config_path, config["questions_path"]).read_text(encoding="utf-8")
        ),
        "model": frozen["model"],
        "stage_ids": [stage["id"] for stage in config["stages"]],
    }
    write_json(run_dir / "config.snapshot.json", frozen)
    write_json(run_dir / "manifest.json", manifest)

    records: list[dict[str, Any]] = []
    for repetition in range(1, config["repetitions"] + 1):
        for question in questions:
            context = {"ARTICLE": article, "QUESTION": question["question"]}
            for stage in config["stages"]:
                stage_id = stage["id"]
                prompt = render_prompt(stage["prompt_template"], context, stage_id)
                answer = client.complete(prompt)
                context[stage_id] = answer
                records.append(
                    {
                        "run_id": run_id,
                        "generated_at": utc_now(),
                        "repetition": repetition,
                        "question_id": question["question_id"],
                        "question_type": question.get("type"),
                        "target_error": question.get("target_error"),
                        "question": question["question"],
                        "stage": stage_id,
                        "response": answer,
                        "prompt_sha256": sha256_text(prompt),
                        "response_sha256": sha256_text(answer),
                        "status": "PENDING_MANUAL_LABEL",
                    }
                )
    write_jsonl(run_dir / "responses.jsonl", records)
    return run_dir
