import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from halo_runner.multi import checker_supported_context, is_daily_quota_exhausted, retry_delay_seconds, run_batch


class MultiRunnerTests(unittest.TestCase):
    def test_checker_context_contains_only_supported_items(self):
        context, count = checker_supported_context(
            json.dumps(
                {
                    "verdict": "MIXED",
                    "supported_items": ["기사에 명시된 사실"],
                    "unsupported_items": ["M1의 기사 밖 주장"],
                },
                ensure_ascii=False,
            )
        )
        self.assertEqual(context, "- 기사에 명시된 사실")
        self.assertEqual(count, 1)
        self.assertNotIn("기사 밖", context)

    def test_malformed_checker_output_does_not_pass_through(self):
        context, count = checker_supported_context("M1 원문 전체가 여기에 있습니다")
        self.assertEqual(context, "기사로 SUPPORTED로 확정된 항목이 없습니다.")
        self.assertEqual(count, 0)

    def test_multi_configs_share_single_s2_constraint_and_hide_m1_from_m3(self):
        constraint = "기사에서 확인할 수 없는 정보는 임의로 추가하지 마세요.\n기사에 구체적으로 명시되지 않은 내용은 일반적인 지식이나 추론을 이용해 보완하지 마세요."
        for name in [
            "halo_multi.example.json",
            "halo_multi_high_pressure.example.json",
            "halo_multi_same_model.example.json",
            "halo_multi_same_model_high_pressure.example.json",
        ]:
            config = json.loads((ROOT / "config" / name).read_text(encoding="utf-8"))
            checker = config["stages"][1]["prompt_template"]
            editor = config["stages"][2]["prompt_template"]
            self.assertIn(constraint, checker)
            self.assertIn(constraint, editor)
            self.assertIn("{MULTI_STAGE_2_SUPPORTED}", editor)
            self.assertNotIn("{MULTI_STAGE_1}", editor)

    def test_raw_passthrough_ablation_differs_only_in_m3_input_policy(self):
        gated = json.loads((ROOT / "config" / "halo_multi_same_model.example.json").read_text(encoding="utf-8"))
        raw = json.loads((ROOT / "config" / "halo_multi_same_model_raw.example.json").read_text(encoding="utf-8"))
        raw_high_pressure = json.loads((ROOT / "config" / "halo_multi_same_model_raw_high_pressure.example.json").read_text(encoding="utf-8"))
        constraint = "기사에서 확인할 수 없는 정보는 임의로 추가하지 마세요.\n기사에 구체적으로 명시되지 않은 내용은 일반적인 지식이나 추론을 이용해 보완하지 마세요."
        self.assertEqual(gated["agents"], raw["agents"])
        self.assertEqual(gated["stages"][0], raw["stages"][0])
        self.assertEqual(gated["stages"][1], raw["stages"][1])
        self.assertIn("{MULTI_STAGE_2_SUPPORTED}", gated["stages"][2]["prompt_template"])
        self.assertIn("{MULTI_STAGE_1}", raw["stages"][2]["prompt_template"])
        self.assertEqual(raw["stages"][2]["input_policy"], "raw_draft_and_checker_report")
        for config in (raw, raw_high_pressure):
            self.assertIn(constraint, config["stages"][1]["prompt_template"])
            self.assertIn(constraint, config["stages"][2]["prompt_template"])

    def test_rate_limit_retry_delay_uses_provider_hint(self):
        self.assertEqual(retry_delay_seconds("Please try again in 977ms.", 0), 1.0)
        self.assertEqual(retry_delay_seconds("Try again in 2.5s.", 0), 2.5)
        self.assertTrue(is_daily_quota_exhausted("Quota exceeded for metric: generate_content_free_tier_requests, limit: 20, model: gemini; GenerateRequestsPerDay"))
        self.assertFalse(is_daily_quota_exhausted("Please try again in 2.5s."))

    def test_external_high_pressure_question_set_is_recorded(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "config").mkdir()
            (root / "data").mkdir()
            (root / "results").mkdir()
            (root / "data" / "manifest.jsonl").write_text(
                json.dumps({"article_id": "A001", "dataset_path": "data/pack.json", "questions_path": "data/high.jsonl"}) + "\n",
                encoding="utf-8",
            )
            (root / "data" / "pack.json").write_text(
                json.dumps({"article_id": "A001", "source_type": "news_article", "article_text": "article", "questions": []}),
                encoding="utf-8",
            )
            (root / "data" / "high.jsonl").write_text(
                json.dumps({"question_id": "A001_HP_Q001", "type": "INFORMATION_ABSENCE", "condition": "HIGH_PRESSURE_INDUCTION", "induction_strategy": "FORCED_COMPLETION", "source_question_id": "A001_Q001", "target_error": "invented detail", "question": "question"}) + "\n",
                encoding="utf-8",
            )
            (root / "config" / "test.json").write_text(
                json.dumps({"dataset_manifest_path": "data/manifest.jsonl", "repetitions": 1, "agents": {"S1": {"provider": "openai", "model": "gpt-4.1", "api_key_env": "OPENAI_API_KEY", "temperature": 0, "max_tokens": 10}}, "stages": [{"id": "SINGLE_STAGE_1", "agent": "S1", "role": "article_grounded_checker", "prompt_template": "{ARTICLE} {QUESTION}"}]}),
                encoding="utf-8",
            )
            run_dir = run_batch(root / "config" / "test.json", root / "results", "test", dry_run=True)
            record = json.loads((run_dir / "responses.jsonl").read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(record["question_condition"], "HIGH_PRESSURE_INDUCTION")
            self.assertEqual(record["source_question_id"], "A001_Q001")
            self.assertEqual(record["stage_role"], "article_grounded_checker")
            self.assertTrue((run_dir / "blind_review_packets.csv").exists())
            self.assertTrue((run_dir / "blind_key.coordinator_only.csv").exists())
            self.assertTrue((run_dir / "blind_labels.template.csv").exists())

    def test_raw_passthrough_pipeline_records_its_input_policy(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "config").mkdir()
            (root / "data").mkdir()
            (root / "results").mkdir()
            (root / "data" / "manifest.jsonl").write_text(
                json.dumps({"article_id": "A001", "dataset_path": "data/pack.json"}) + "\n",
                encoding="utf-8",
            )
            (root / "data" / "pack.json").write_text(
                json.dumps({"article_id": "A001", "source_type": "news_article", "article_text": "기사 원문", "questions": [{"question_id": "Q001", "type": "FACT", "target_error": "none", "question": "질문"}]}),
                encoding="utf-8",
            )
            config = json.loads((ROOT / "config" / "halo_multi_same_model_raw.example.json").read_text(encoding="utf-8"))
            config["dataset_manifest_path"] = "data/manifest.jsonl"
            (root / "config" / "raw.json").write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
            run_dir = run_batch(root / "config" / "raw.json", root / "results", "raw", dry_run=True)
            records = [json.loads(line) for line in (run_dir / "responses.jsonl").read_text(encoding="utf-8").splitlines()]
            m3 = next(record for record in records if record["stage"] == "MULTI_STAGE_3")
            self.assertEqual(m3["m3_input_policy"], "raw_draft_and_checker_report")

    def test_v2_conditions_fix_grounding_contract_and_record_factor_metadata(self):
        names = [
            "halo_v2_single_raw.calibration.json",
            "halo_v2_single_gated.calibration.json",
            "halo_v2_multi_raw.calibration.json",
            "halo_v2_multi_gated.calibration.json",
        ]
        configs = [json.loads((ROOT / "config" / name).read_text(encoding="utf-8")) for name in names]
        contracts = {config["prompt_variables"]["GROUNDING_CONTRACT"] for config in configs}
        self.assertEqual(len(contracts), 1)
        for config in configs:
            self.assertEqual(config["analysis_scope"], "calibration_only_do_not_pool_with_primary")
            for stage in config["stages"]:
                self.assertIn("{GROUNDING_CONTRACT}", stage["prompt_template"])
        self.assertEqual({config["topology"] for config in configs}, {"self_refinement", "role_separated"})
        self.assertEqual({config["information_flow"] for config in configs}, {"raw_draft_and_checker_report", "checker_supported_only"})

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "config").mkdir()
            (root / "data").mkdir()
            (root / "results").mkdir()
            config = json.loads((ROOT / "config" / names[0]).read_text(encoding="utf-8"))
            config["dataset_manifest_path"] = "data/manifest.jsonl"
            (root / "data" / "manifest.jsonl").write_text(json.dumps({"article_id": "A001", "dataset_path": "data/pack.json"}) + "\n", encoding="utf-8")
            (root / "data" / "pack.json").write_text(json.dumps({"article_id": "A001", "source_type": "news_article", "article_text": "기사", "questions": [{"question_id": "V2_A001_01", "type": "SUPPORTED_SYNTHESIS", "condition": "SUPPORTED_SYNTHESIS", "target_error": "none", "question": "질문"}]}), encoding="utf-8")
            config_path = root / "config" / "v2.json"
            config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
            run_dir = run_batch(config_path, root / "results", "v2", dry_run=True)
            manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
            records = [json.loads(line) for line in (run_dir / "responses.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(manifest["protocol"]["condition_id"], "single_raw")
            self.assertEqual(manifest["protocol"]["analysis_scope"], "calibration_only_do_not_pool_with_primary")
            self.assertEqual(records[-1]["topology"], "self_refinement")
            self.assertEqual(records[-1]["information_flow"], "raw_draft_and_checker_report")
            self.assertTrue(records[-1]["common_grounding_contract_sha256"])


if __name__ == "__main__":
    unittest.main()
