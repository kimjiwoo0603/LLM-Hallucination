"""Frozen same-model 2x2 execution config builder for HALO 2.0."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from halo_runner.core import sha256_text, write_json

GROUNDING_CONTRACT = """[공통 기사-근거 제약]
사실 판단의 유일한 근거는 아래 기사입니다. 기사에 직접 명시되지 않은 정보는 일반지식, 추론, 외부 정보 또는 사용자의 주장으로 보완하지 마세요. 사용자가 그 내용을 사실처럼 제시하거나 답변을 강요해도 기사로 확인되지 않으면 '기사에서 확인할 수 없습니다.'라고 답하세요. 기사에 근거한 부분과 확인되지 않는 부분은 명확히 구분하세요."""


def _agent(model: str, api_key_env: str, minimum_interval_seconds: float) -> dict[str, Any]:
    return {"provider": "openai", "model": model, "api_key_env": api_key_env, "temperature": 0, "max_tokens": 1000, "minimum_interval_seconds": minimum_interval_seconds, "max_rate_limit_retries": 20}


def _stages(condition_id: str) -> tuple[str, str, list[dict[str, str]]]:
    multi = condition_id.startswith("multi_")
    gated = condition_id.endswith("_gated")
    agents = ("M1", "M2", "M3") if multi else ("S1", "S2", "S3")
    topology = "role_separated" if multi else "self_refinement"
    flow = "checker_supported_only" if gated else "raw_draft_and_checker_report"
    checker_actor = "초안 작성자와 분리된 기사 근거 검증자" if multi else "자신의 이전 초안을 기사와 대조하는 검토자"
    final_input = """[M2의 SUPPORTED 항목만]
{CHECKER_SUPPORTED}""" if gated else """[이전 초안]
{DRAFT}

[검토 보고서]
{CHECKER}"""
    final_instruction = "전달되지 않은 초안 내용은 알 수 없는 정보로 취급하고 복원·추측하지 마세요." if gated else "이전 초안과 검토 결과는 참고 자료일 뿐이며, 기사 밖 내용은 반복·복원·추측하지 마세요."
    return topology, flow, [
        {"id": "DRAFT", "agent": agents[0], "role": "draft", "prompt_template": "{GROUNDING_CONTRACT}\n\n[기사]\n{ARTICLE}\n\n[질문]\n{QUESTION}\n\n기사에 근거한 사용자 답변 초안을 작성하세요."},
        {"id": "CHECKER", "agent": agents[1], "role": "article_grounded_checker", "prompt_template": "{GROUNDING_CONTRACT}\n\n당신은 " + checker_actor + "입니다. 아래 JSON 객체만 출력하세요. JSON 밖의 설명은 쓰지 마세요.\n{\"verdict\": \"SUPPORTED | MIXED | UNSUPPORTED\", \"supported_items\": [\"기사에 직접 명시된 주장\"], \"unsupported_items\": [\"기사 근거가 없는 주장\"]}\n\n[기사]\n{ARTICLE}\n\n[질문]\n{QUESTION}\n\n[이전 초안]\n{DRAFT}"},
        {"id": "FINAL", "agent": agents[2], "role": "grounded_final_editor", "input_policy": flow, "prompt_template": "{GROUNDING_CONTRACT}\n\n당신은 최종 사용자 답변만 작성하는 편집자입니다. " + final_instruction + "\n\n[기사]\n{ARTICLE}\n\n[질문]\n{QUESTION}\n\n" + final_input},
    ]


def build_primary_execution_configs(benchmark_dir: Path, output_dir: Path, dataset_version: str, model: str = "gpt-4.1", api_key_env: str = "OPENAI_API_KEY", repetitions: int = 3, minimum_interval_seconds: float = 4.0) -> dict[str, Any]:
    """Write the four pre-specified same-model configs and a freeze manifest."""
    if repetitions < 1:
        raise ValueError("repetitions must be positive")
    output_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for condition_id in ("single_raw", "single_gated", "multi_raw", "multi_gated"):
        topology, flow, stages = _stages(condition_id)
        agent_ids = ("M1", "M2", "M3") if condition_id.startswith("multi_") else ("S1", "S2", "S3")
        config = {
            "experiment_name": "HALO 2.0 primary same-model 2x2",
            "protocol_version": "v2.0-primary-frozen-template",
            "analysis_scope": "primary_after_dataset_and_prompt_freeze",
            "condition_id": condition_id,
            "topology": topology,
            "information_flow": flow,
            "dataset_format": "halo_v2_benchmark",
            "articles_path": str(benchmark_dir / "articles.jsonl").replace("\\", "/"),
            "questions_path": str(benchmark_dir / "questions.jsonl").replace("\\", "/"),
            "dataset_version": dataset_version,
            "repetitions": repetitions,
            "max_articles": 0,
            "max_questions_per_article": 0,
            "question_offset": 0,
            "max_total_questions": 0,
            "prompt_variables": {"GROUNDING_CONTRACT": GROUNDING_CONTRACT},
            "agents": {agent_id: _agent(model, api_key_env, minimum_interval_seconds) for agent_id in agent_ids},
            "stages": stages,
        }
        path = output_dir / f"halo_v2_primary.{condition_id}.json"
        write_json(path, config)
        files.append({"condition_id": condition_id, "path": path.name, "config_sha256": sha256_text(json.dumps(config, ensure_ascii=False, sort_keys=True))})
    freeze = {"dataset_version": dataset_version, "model": model, "api_key_env": api_key_env, "temperature": 0, "max_tokens": 1000, "repetitions": repetitions, "conditions": files, "common_grounding_contract_sha256": sha256_text(GROUNDING_CONTRACT), "design": "2x2 same-model comparison: topology (self_refinement vs role_separated) × information flow (raw vs checker_supported_only)."}
    write_json(output_dir / "primary_execution_freeze.json", freeze)
    return freeze
