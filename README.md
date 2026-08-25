# HALO: staged hallucination experiment

This repository automates the pilot's **single-chain** protocol without changing its
research design:

`SINGLE_STAGE_1 → SINGLE_STAGE_2 → SINGLE_STAGE_3`

For every question and repetition it saves the three raw answers, hashes of the exact
prompts and responses, and a snapshot/hash of the model configuration and article. The
pilot question set is Q005, Q009, Q011, Q012, Q013, and Q014.

## What is fixed per run

- the exact article text and question file;
- model identifier and all configured sampling parameters;
- the three supplied stage prompts; and
- the order `S1 → S2 → S3`.

The runner writes a new immutable run folder. It never overwrites a previous run and it
never stores API-key values.

## Before a live run

1. Copy `config/halo_single.example.json` to `config/halo_single.json`.
2. Paste the **complete, original** news article into `datasets/halo_article.txt`.
   The report only contains excerpts, so it is intentionally not reconstructed here.
3. The supplied single-agent configuration fixes GPT-4.1 and its sampling values; keep them unchanged within a run.
4. Set the environment variable named by `model.api_key_env`; do not put a key in a file.

The stage prompts are the user's supplied prompts. The complete article is passed to all
three stages, following the pilot report's recommendation that the same source text be
available at every stage.

## Run

```powershell
python run_experiment.py --config config/halo_single.json
```

For a no-cost pipeline check, use `--dry-run` after pasting the article:

```powershell
python run_experiment.py --config config/halo_single.json --dry-run --run-id smoke-test
```

Each run creates `results/<run-id>/responses.jsonl`, `labels.template.csv`,
`manifest.json`, and `config.snapshot.json`.

## Label and aggregate

The report labels each response manually as `Hallucination (0/1)`, `Severity (0–5)`, and
`Propagation (Initial/Maintained/Removed/None)`. The runner deliberately leaves that
judgment as `PENDING_MANUAL_LABEL`; it does not invent a ground-truth verdict.

The run already creates `labels.template.csv` with one row per
`question_id × repetition × stage`; fill in its five label columns, then run:

```powershell
python aggregate_results.py --run-dir results/<run-id> --labels results/<run-id>/labels.template.csv
```

This creates `labeled_responses.jsonl`, `stage_summary.csv`, and
`question_stage_summary.csv`. Repetitions are preserved, so rates and severity means are
computed across repeated executions.

## Single-agent ChatGPT condition

The single-agent condition fixes all three supplied stages to the same model:
`GPT-4.1 → GPT-4.1 → GPT-4.1`. Its batch configuration uses the complete article-pack
dataset and preserves the original `SINGLE_STAGE_1/2/3` prompt texts. Run it from the
**Run HALO single-agent ChatGPT experiment** GitHub Actions workflow; its default is a
one-question smoke test and it saves one artifact per run.

## High-pressure question condition

The baseline question packs remain unchanged. The separate **Run HALO single-agent
ChatGPT high-pressure experiment** workflow uses a versioned 33-question set with
`condition=HIGH_PRESSURE_INDUCTION`. Each question adds an explicitly false claim of
unseen authoritative supplementary material and requires a concrete answer. This is an
adversarial question condition, not a change to the supplied `SINGLE_STAGE_1/2/3`
prompts or the model settings. Saved response records include the question condition,
the induction strategy, and the baseline question ID from which the high-pressure
question was derived.

## Multi-model condition

`run_multi_experiment.py` runs a separately configured three-provider condition:
`M1 (GPT-4.1) → M2 (Gemini 3.6 Flash) → M3 (GPT-4.1)`. The provided configuration
uses the report's recommended roles—drafting, article-grounded verification, and final
editing—and keeps provider API keys in environment variables.
The free-tier Gemini Flash configuration spaces its Gemini calls 13 seconds apart to stay
within the current per-minute request allowance.
Its daily free allowance is 20 requests, so run the full 33-question dataset in two batches:
first `question_offset=0, max_total_questions=20`, then, on the following daily quota window,
`question_offset=20, max_total_questions=20`.

Article packs contain the article snapshot, its Ground Truth, and questions generated from
that snapshot. `datasets/article_packs/manifest.jsonl` lists the packs to run, so one command
runs every article and keeps `article_id` on every saved response and label.

```powershell
python run_multi_experiment.py --config config/halo_multi.json
```

Do not place an unverified automatically generated pack in the manifest. Article packs are
created from the supplied source text under the dataset protocol before models are evaluated.

