# Streamlit support agent

This repository combines the team project into one evidence-grounded support
pipeline and a reliable multi-turn case tracker. The default branch is
`master`. Components exchange JSON contracts rather than importing another
student's internal classes.

## Architecture

```text
GitHub issues, comments, docs and releases
                  |
                  v
        evidence synthesis (source/)
                  |
                  v
            AnalysisInput
                  |
                  v
 missing-information decision (missing_info/)
                  |
                  v
            NextStepReport
                  |
                  v
 response and maintainer handoff (part1_3/)
                  |
                  v
             Part3Response
                  |
                  v
 adapters (part1_3_integration/) -> support_agent/
                  |
                  v
 persistent case state, human approval and local tracker action
```

`support_agent/` implements Problem 2 Parts 1 and 2. Its scenario runner
implements Part 3 with ten multi-turn scenarios: five development scenarios and
five test scenarios. All visible mutations require an approval bound to the
exact case version, proposal and action hash. Tracker operations use durable
operation receipts so retry after a lost response does not publish twice.

## Components

| Assignment area | Location | Primary output |
|---|---|---|
| Problem 1 Part 1 | `source/` and `data/raw/` | synthesized evidence |
| Problem 1 Part 2 | `missing_info/` | `NextStepReport` |
| Problem 1 Part 3 | `part1_3/` | proposed user reply and maintainer summary |
| Stage adapters | `part1_3_integration/` | contract translations for Problem 2 |
| Problem 2 Parts 1–2 | `support_agent/` | durable `CaseState`, approvals and actions |
| Problem 2 Part 3 | `support_agent/scenarios.py` | ten practical scenario results |
| Final evaluation | `eval_pipeline/` and `data/eval/` | retrieval, decision and operational metrics |

Generated Part 3 artifacts are written under
`part1_3_output/cases/<case_id>/<response_id>/`. Immutable response revisions
are content-addressed; live provider usage is stored separately under
`part1_3_output/runs/`.

## Installation

Python 3.11 or newer is required.

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[dev,llm]"
```

The `llm` extra is needed only for live OpenAI-compatible composition. Never
commit provider keys. Use the provider template in
`part1_3/provider.env.example`.

## Main commands

Prepare the raw evidence snapshot:

```bash
python source/collect_streamlit_issues.py
python source/collect_streamlit_docs.py
python source/collect_release_notes.py
python source/evidence_synthesis_streamlit.py
```

Run the missing-information decision component:

```bash
missing-info analyze examples/stuck_loading_on_server.json --output report.json
```

Compose all populated Part 2 reports offline:

```bash
python -m part1_3
```

Run Part 3 with an OpenAI-compatible provider:

```bash
python -m part1_3 part1_2_output/example_part1_2_output.json --live --env-file path/to/private.env
```

Inspect the Problem 2 CLI and run all practical scenarios:

```bash
python -m support_agent --help
python -m support_agent scenarios
```

## Validation

```bash
python -m pytest -q
python -m unittest discover -v
python -m unittest discover -s part1_3/tests -v
python -m unittest discover -s part1_3_integration/tests -v
```

The evaluation pipeline is run in order and the test split is used only after
development choices are frozen:

```bash
python eval_pipeline/step0_prepare_cases.py
python eval_pipeline/step1_create_annotation_stubs.py
python eval_pipeline/step2_run_evaluation.py --split dev
python eval_pipeline/step3_compute_metrics.py --split dev
python eval_pipeline/step4_failure_report.py
```

Annotations and evaluation cases stay separate from the retrieval corpus.
Follow-up messages designed for multi-turn evaluation must remain labelled as
designed inputs rather than historical GitHub comments.

## Detailed guides

- `part1_3/README.md`: Part 1 Part 3 interface, provider configuration and output contract.
- `part1_3_integration/README.md`: adapters between independently developed stages.
- `part1_2_output/README.md`: expected input directory for Part 3.
- `part1_3_output/README.md`: immutable response artifact layout.
- `support_agent/scenarios.py`: executable Problem 2 Part 3 specification.
