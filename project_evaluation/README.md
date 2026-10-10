# Project evaluation

This folder owns evaluation across the completed project:

- `pipeline/`: case preparation, execution, metric computation and failure reporting.
- `data/`: evaluation cases, annotations and reports (run logs under `data/runs/` are not committed).
- `tests/`: tests for the corpus rules, metrics and system adapters.

## What is evaluated

Two systems run on the same 30 cases (15 dev, 15 test), each seeing only the case's
visible input (title and body):

| System | What it is |
|---|---|
| `baseline` | the original keyword-overlap stub (`pipeline/system_under_test.py`) with a fixed "ask for version and a reproducible example" policy |
| `integrated` | the real project pipeline `project_app.ProjectPipeline`: Part 1 retrieval and synthesis, Part 2 next-step decision, Part 3 reply, and import as a pending Problem 2 proposal |

Part 2 decisions are mapped to the evaluation's actions:
`propose_answer` → `answer`, `request_information` → `ask_clarification`, `escalate` → `escalate`.
Every integrated case runs against its own temporary SQLite store and tracker.

Multi-turn and operational behaviour (corrections, rejection, edits, restart while waiting,
duplicate execution, case change before execution, tool failures, case isolation) is
evaluated by the ten Problem 2 Part 3 scenarios (five dev, five test). Step 3 runs the
scenarios of the evaluated split and includes them in the report.

## Leakage control (`pipeline/corpus.py`)

For each case the retrieval corpus is rebuilt from `problem1_part1/data/`:

- all 30 evaluation cases, and any recurring issue family listed on their case cards, are removed;
- past issues are included only if created before the case's cutoff, with only the comments
  that existed at that time; bot comments, final state and labels are removed;
- release notes are included only if published before the cutoff;
- documentation comes from the pinned docs commit in `docs_meta.json`. The snapshot is newer
  than most cases, so the evaluation is **not historical for documentation**; every run log
  records this policy.

## Run

From the repository root, in order. The test split is held out: run it once, after all
development choices are frozen.

```bash
python project_evaluation/pipeline/step0_prepare_cases.py            # refuses to overwrite the frozen split
python project_evaluation/pipeline/step1_create_annotation_stubs.py  # keeps existing annotations
python project_evaluation/pipeline/step2_run_evaluation.py --split dev
python project_evaluation/pipeline/step3_compute_metrics.py --split dev
python project_evaluation/pipeline/step4_failure_report.py
```

Final numbers:

```bash
python project_evaluation/pipeline/step2_run_evaluation.py --split test --allow-test
python project_evaluation/pipeline/step3_compute_metrics.py --split test
python project_evaluation/pipeline/step4_failure_report.py
```

Options of step 2: `--systems baseline integrated` (default: both) and
`--live --env-file path/to/private.env` to compose Part 3 replies with the configured
provider; provider requests, tokens and cost are then taken from each run manifest.

## Annotations

`data/annotations/<case>.json` holds the gold labels. They start as automatic stubs and
must be corrected by hand before decision metrics can be trusted:

| Field | Meaning |
|---|---|
| `bucket` | `answerable`, `ambiguous` or `escalation` |
| `acceptable_actions_turn0` | acceptable first actions |
| `missing_information` | Part 2 facet ids a good first step asks about (see `problem1_part2/implementation/facets.py`) |
| `relevant_source_ids` / `relevant_chunk_ids` | gold evidence for Recall@k; a labelled subset is enough |
| `ideal_response_notes` | what a good first reply does |

## Metrics (`data/reports/metrics_<split>.json`, `report_<split>.md`)

Per system, side by side:

- **Decision quality**: accuracy overall and per bucket, with the actions taken per bucket,
  so that asking or escalating on every case cannot pass as success. A system error counts
  as a wrong decision.
- **Evidence quality**: Recall@5 and Recall@10 on labelled cases; `null` when nothing is labelled.
- **Next-step quality** (integrated): share of cases that re-ask information the user already
  gave, share of first steps chosen by information gain rather than fallback, and hits of the
  first step on labelled `missing_information`.
- **Operational success** (integrated), read from the stored state after the run: case
  persisted, exactly one pending proposal, nothing approved or executed, tracker unchanged.
- **Cost and time**: latency, setup time, provider requests, tokens and estimated cost.
- **Failures** (`failures_<split>.json`): each wrong decision with a probable cause
  (`system_error`, `over_escalation`, `unnecessary_question`, `unsupported_answer`).
