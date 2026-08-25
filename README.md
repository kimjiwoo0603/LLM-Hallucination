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
3. Set one fixed model ID in `config/halo_single.json` and keep its sampling values fixed.
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

Each run creates `results/<run-id>/responses.jsonl`, `manifest.json`, and
`config.snapshot.json`.

## Label and aggregate

The report labels each response manually as `Hallucination (0/1)`, `Severity (0–5)`, and
`Propagation (Initial/Maintained/Removed/None)`. The runner deliberately leaves that
judgment as `PENDING_MANUAL_LABEL`; it does not invent a ground-truth verdict.

Create a label CSV from `labels/labels.template.csv`, with one row per
`question_id × repetition × stage`, then run:

```powershell
python aggregate_results.py --run-dir results/<run-id> --labels labels/<run-id>.csv
```

This creates `labeled_responses.jsonl`, `stage_summary.csv`, and
`question_stage_summary.csv`. Repetitions are preserved, so rates and severity means are
computed across repeated executions.

## Multi-model condition

The pilot report also describes an M1→M2→M3 condition, but it does not provide that
condition's three role prompts or fixed per-stage model settings. It is intentionally not
filled in with guessed prompts. The runner supports any ordered stage IDs in the config;
add the approved M1/M2/M3 prompts and exact model assignment only when they are fixed by
the research design.
