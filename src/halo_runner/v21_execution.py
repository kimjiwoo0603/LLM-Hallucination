"""Shared, cost-tracked API execution primitives for HALO 2.1."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from halo_runner.v21_budget import TokenUsage


def single_oneshot_prompt(record: dict[str, Any]) -> str:
    """Minimal shared prompt: no universal refusal or article-only instruction."""
    candidate = record["candidate"]
    question = record["packet_draft"]["question"]
    return f"""You are answering a user's question. Use the provided source material when relevant.
Give a clear, specific, and helpful answer.

SOURCE MATERIAL:
{candidate['source_text']}

USER QUESTION:
{question}
"""


def openai_chat_completion(prompt: str, config: dict[str, Any]) -> tuple[str, TokenUsage]:
    api_key = os.environ.get(config["api_key_env"])
    if not api_key:
        raise RuntimeError(f"Environment variable {config['api_key_env']} is not set")
    payload = {
        "model": config["model"], "temperature": config["temperature"],
        "max_tokens": config["max_output_tokens"],
        "messages": [{"role": "user", "content": prompt}],
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HALO 2.1 model request failed ({error.code}): {detail}") from error
    content = body["choices"][0]["message"]["content"]
    usage = body.get("usage", {})
    return content, TokenUsage(int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0)))
