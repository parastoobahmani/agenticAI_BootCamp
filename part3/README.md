# Problem 1 — Part 3 contribution

This folder is the standalone team contribution. It prepares a user reply and a technical maintainer handoff from **only a `NextStepReport` JSON instance**, using the supplied schema stored locally as `part1_2_output_report.schema.json`. It does not import Part 1, Part 2, a corpus, the original case, a database or a personal API configuration.

The schema describes the format; pass a populated report, not the schema itself. `part1_2_output/example_part1_2_output.json` is an **authored example of Part 2 output**, not a real GitHub case, a teammate-produced result or ground truth. `doc-widget-17` is a fictional evidence ID used to exercise unresolved references.

## Install and run

Run from the shared repository root containing the `part3/` directory. Requires Python 3.12 or 3.13.

```bash
python -m pip install -r part3/requirements.txt
python -m part3 --demo
# Once actual Part 2 reports are present:
python -m part3
python -m unittest discover -s part3/tests -v
```

Defaults are anchored to the project root (the directory containing `part3/`), not the current working directory:

- Input: `part1_2_output/*.json`; schema documents and files prefixed `example_` are skipped during normal runs.
- Output: `part1_3_output/response.json`, `user_response.txt`, `maintainer_summary.md`, and `manifest.json`.

`--demo` uses only the bundled authored example and marks both its response JSON and manifest `artifact_kind="demonstration"`. It does not write fake Part 2 input. A normal run with only the schema fails clearly because no populated report exists. Explicit input files, `--input-dir` and `--output-dir` remain supported. Outputs always go directly into the output directory and each run replaces the previous files. `case_id` remains inside the JSON. If the input folder contains multiple reports, select one explicitly, for example `python -m part3 part1_2_output/case123.json`; no outputs are written until one report is selected.

The offline command never reads credentials or makes API calls. Consumers should check the complete manifest, its response ID and file hashes, and reject demonstration artifacts for real processing. Each file is published atomically and the manifest is written last. This is not a transactional multi-file database; a consumer should retry when hashes do not match during a concurrent update.

## Public interface

```python
from part3 import prepare_next_step_response, markdown_summary

response = prepare_next_step_response(next_step_report)
user_reply = response["user_response"]
maintainer_handoff = markdown_summary(response)
```

`next_step_report` is a Python dictionary parsed from the teammate's JSON. The module validates it against the bundled, unchanged schema. It also checks supported version, finite numbers, payload bounds, duplicate hypothesis IDs and hypothesis cross-references. It does not convert it into the earlier workbench-specific DecisionPacket.

For live prose composition, inject the team's configured model client:

```python
def compose(messages, schema):
    # Adapt this line to your team's gateway. It must return parsed JSON.
    return gateway.complete(messages, run_id, schema=schema)

response = prepare_next_step_response(next_step_report, compose=compose)
```

`gateway` and `run_id` above belong to the calling application; this folder does not provide a credential loader or provider implementation. The callback receives Chat-Completions-style message dictionaries and a JSON Schema, and returns a parsed object with `user_intro`, `case_summary`, and `fact_ids`. The team's adapter must enforce credentials, timeouts, output-token bounds and a shared budget before sending. This module makes at most **one** callback invocation and never retries. A model exception or invalid composition produces a labelled deterministic fallback.

Configuration is not additional case data: the report remains the only investigation input. The example callback is an integration pattern, not an import of another student's implementation.

## How it uses the report

- `decision.type` controls the response framing: a tentative proposed answer, a request for information, or a proposed maintainer handoff.
- `decision.hypothesis_id` selects a hypothesis only when Part 2 explicitly supplies it. No top-score guess is made if it is missing.
- `known_facts` are the current observations. `superseded` entries are retained in the technical handoff, excluded from the current-fact synopsis and not sent to the composer.
- `performed_outcome_unknown` means the action happened but its outcome is unknown. It is never converted into failure or success.
- `next_steps` are assumed to be **selected actions in presentation order**. All are preserved; scores do not cause re-ranking or silent removal. If your teammate actually sends candidates, agree on explicit selection before integration.
- `missing_information`, `skipped_probes`, hypotheses, expectations, conflicts and limitations are retained in structured output. The Markdown handoff highlights the main investigation details; JSON retains the complete supplied records.
- `prior`, `posterior`, evidence strength, information gain and scores remain upstream metadata. They are excluded from the prose prompt and are not presented as calibrated certainty to the user.

All input data is untrusted. Supplied text cannot authorize tools or publication. Input secrets matching the local redaction patterns are removed; redaction is not a comprehensive DLP guarantee. Selected text with detectable unsafe instructions is rejected before a model call.

## What cannot be recovered from this input

The schema includes no original report/title/conversation, actual source text, URLs, sections or revisions. Part 3 therefore:

- Summarizes the supplied facts, not the absent original report.
- Keeps evidence IDs as **unresolved references**, without inventing citations or fetching sources.
- Treats hypotheses as unverified upstream proposals, even when their evidence strength says `strong`.
- Preserves `origin.location` and `origin.quote`, but cannot verify them against the original report.
- Records these limits explicitly and keeps the response a draft with `resolution_confirmed=false`.

This implements the two required outputs using the available input. It does not make the missing source provenance adequate for the assignment's overall evidence requirement. That must be addressed at the team level if independently inspectable citations are required in the final reply.

## Output contract

The returned dictionary has its own `schema_version="1.0"`, `input_contract="NextStepReport/1.0"`, `case_id`, `status="draft"`, `decision_type`, `user_response`, `technical_summary`, `composition`, `input_fingerprint` and a content-derived `id`.

`technical_summary` contains `case_summary`, its scope/method, current facts and corrections, upstream decision, hypotheses, missing information, selected steps, skipped probes, limitations, unresolved evidence IDs, unavailable-information flags and the selection assumption. It does not fabricate an original case object.

`composition.method` is `deterministic`, `model` or `fallback`. Errors expose a fixed category, not provider exception text. The hash covers the actual returned response content; changed prose creates a changed ID. Approval and tracker actions are outside this contribution.

The input schema allows omitted `schema_version`; this module applies its advertised `"1.0"` default. It rejects other versions. Other optional fields remain absent if not supplied. Local service limits are 200 KB input, 20 nesting levels, 100 items per array, 12,000 characters per string and ten selected steps. Inputs are rejected or composition falls back on bounds; no supplied steps are silently truncated. Empty selected-step arrays remain valid and are disclosed instead of invented. A request for an answer with no selected hypothesis is also disclosed.

## Model limitations

The composer writes the introduction and synopsis. Code inserts the selected hypothesis/steps and required provenance caveats. The model cannot change the canonical report records. It must reference current-fact IDs and obey length, reference, detectable-action and sensitive-text checks. These checks do **not** prove semantic faithfulness; a real fact ID can accompany a misleading paraphrase. Review model-written drafts before use.

Tests use authored data and fake model callbacks. They verify schema rejection, correction handling, unknown outcomes, selection order, unresolved evidence, composition failure, sensitive text, prompt bounds and offline execution. They are not a model-quality benchmark.

## Files to submit

Submit `part3/` plus the agreed `part1_2_output/` and `part1_3_output/` scaffolding (schema, README and ignore files). Generated case outputs remain ignored; run `python -m part3 --demo` to reproduce the example. It contains the implementation, schema, dependency declaration, example and tests. It needs none of the personal workspace's `support_workbench/`, corpus, evaluation outputs, runtime database, environment files or virtual environment. The top-level project may wrap this module for local testing; those wrappers are not part of this contribution.
