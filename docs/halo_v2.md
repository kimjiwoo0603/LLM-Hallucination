# HALO 2.0: staged research protocol

HALO 2.0 is separate from v1 and from the 12-question v2 calibration. It is not allowed to pool those results.

## Fixed outcomes

- Primary: human-labelled article-grounded hallucination (0/1).
- Secondary: accuracy (0/1/2), usefulness (1–5), abstention (0/1), and repetition consistency.
- Excluded from the research outcome set: response latency. API cost and execution failures remain operational records.

## Freeze rule

Pilot data may be used to test executable code and benchmark sensitivity. Before the primary run, freeze the approved dataset version, question set, prompt hashes, model configuration, repetitions, conditions, label rubric, and analysis configuration. Do not select questions after observing condition outcomes.

## Human workflow

Two raters receive only the blind packet and their own template. `run_halo_v2.py adjudicate` creates an agreement file and a separate disagreement file; it never chooses a winner. A coordinator creates final adjudicated labels before running the summary.

When the corpus is supplied directly by the research team and the public article URLs are unavailable, the corpus may instead be frozen as **research-team-provided immutable article snapshots**. This is a provenance category, not a substitute for web verification: record the supplied text hashes and human attestation, do not claim that the corpus was crawled or URL-verified, and retain the limitation in the final report.

## Statistical rule

For one complete observation per question across conditions, use Cochran’s Q followed by exact pairwise McNemar tests with Holm correction if appropriate. With repeated trials, preserve the article/question cluster and use the pre-specified repeated-measures model; do not treat repetitions as independent observations. Report Wilson 95% confidence intervals, including when zero events are observed.

## What this automation does not do

It does not bypass robots.txt or source terms, fabricate articles/questions, approve candidates, make human labels, resolve disagreements, or claim results from an unexecuted experiment.

## Execution after the freeze

After human review, run `select` to create an immutable benchmark directory. Then run `build_v2_primary_configs.py` once. It creates four GPT-4.1, temperature-0 execution configurations:

- `single_raw`: one model performs its own draft, check, and raw-context revision.
- `single_gated`: one model performs its own draft/check, but its final revision receives only checker-supported content.
- `multi_raw`: three separately scoped calls to the same GPT-4.1 model, with raw draft/check context passed to the final editor.
- `multi_gated`: three separately scoped GPT-4.1 calls, with only checker-supported content passed to the final editor.

This is a fixed 2×2 design: **topology** (self-refinement vs role-separated) × **information flow** (raw vs supported-only). The builder stores the configuration hashes in `primary_execution_freeze.json`. It makes no API calls.

## Budget-safe batching

Before any live call, `build_v2_batch_plan.py` freezes base/high-pressure question pairs into execution batches. The first full batch takes one pair from every article, yielding 20 questions across the 10-article corpus. A batch is selected by the pre-recorded seed, not by earlier model outcomes. Budget exhaustion may stop later pre-specified batches, but it must not cause outcome-based removal or replacement of questions.

`Run HALO 2.0 primary experiment` is manual-only. It defaults to a dry run and requires the separate `RUN_FUNDED_PRIMARY` confirmation before it can use `OPENAI_API_KEY`. The full scope contains 66 questions (2,376 model requests for 3 repetitions × 4 conditions × 3 stages); `batch_01` through `batch_03` contain 20 questions each, and `batch_04` contains the remaining 6.
