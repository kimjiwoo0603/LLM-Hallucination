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

## Statistical rule

For one complete observation per question across conditions, use Cochran’s Q followed by exact pairwise McNemar tests with Holm correction if appropriate. With repeated trials, preserve the article/question cluster and use the pre-specified repeated-measures model; do not treat repetitions as independent observations. Report Wilson 95% confidence intervals, including when zero events are observed.

## What this automation does not do

It does not bypass robots.txt or source terms, fabricate articles/questions, approve candidates, make human labels, resolve disagreements, or claim results from an unexecuted experiment.
