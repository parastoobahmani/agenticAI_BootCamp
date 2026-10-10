# Problem 1 — Part 3 contribution

This folder is the standalone team contribution. It prepares a user reply and a technical maintainer handoff from **only a `NextStepReport` JSON instance**, using the supplied schema stored locally as `part1_2_output_report.schema.json`. It does not import Part 1, Part 2, a corpus, the original case, a database or a personal API configuration.

Team-level adapters in `part1_3_integration/` connect the evidence-synthesis output to
Part 2 and convert this part's response into the current Problem 2 memory and
human-approval proposal formats.

The schema describes the format; pass a populated report, not the schema itself. `part1_2_output/example_part1_2_output.json` is an **authored example of Part 2 output**, not a real GitHub case, a teammate-produced result or ground truth. `doc-widget-17` is a fictional evidence ID used to exercise unresolved references.

## Install and run

Run from the shared repository root containing the `part1_3/` directory. Requires Python 3.12 or 3.13.

```bash
python -m pip install -r part1_3/requirements.txt
python -m part1_3 --demo
# Once actual Part 2 reports are present:
python -m part1_3
python -m unittest discover -s part1_3/tests -v
```

Defaults are anchored to the project root (the directory containing `part1_3/`), not the current working directory:

- Input: `part1_2_output/*.json`; schema documents and files prefixed `example_` are skipped during normal runs.
- Output: `part1_3_output/cases/<case_id>/<response_id>/` containing `response.json`, `proposed_user_reply.txt`, `maintainer_summary.md`, and `manifest.json`.

`--demo` uses only the bundled authored example and marks both its response JSON and manifest `artifact_kind="demonstration"`. It does not write fake Part 2 input. A normal run with only the schema fails clearly because no populated report exists. Explicit input files, `--input-dir` and `--output-dir` remain supported. A normal folder run processes every populated report after validating the whole batch and rejects duplicate `case_id` values.

Outputs are immutable. `case_id` selects the case directory and the content-derived `response_id` selects a response revision. Replaying identical input verifies the existing bytes. Changed input or composition creates a new `response_id` directory; an existing directory with missing, changed or extra files is rejected rather than repaired silently. The manifest is written in a staging directory before one atomic directory rename.

The offline command never reads credentials or makes API calls. Consumers should check the complete manifest, its response ID, input fingerprint and file hashes, and reject demonstration artifacts for real processing.

## Live composition: OpenAI now, Metis for delivery

Part 3 owns the model-assisted composition of the user introduction and maintainer synopsis. The canonical selected hypothesis and next steps still come from Part 2 and are inserted by validated code. Live mode makes at most one provider call per report; offline mode remains the default.

Create a private environment file from `part1_3/provider.env.example`. For the current OpenAI test setup, the important fields are:

```dotenv
API_KEY=<private key>
API_BASE_URL=https://api.openai.com/v1
API_MODEL=gpt-4.1-mini
API_ALLOWED_HOSTS=api.openai.com
API_STRUCTURED_OUTPUTS=true
API_TOKEN_PARAMETER=max_completion_tokens
```

Run one populated Part 2 report with live composition:

```bash
python -m part1_3 part1_2_output/case.json --live --env-file ../final_project/personal.env
```

For course delivery, keep the variable names and change only the private file's values to the assigned Metis key, base URL, model and allowed host. If the Metis endpoint supports JSON mode but not strict JSON Schema, set `API_STRUCTURED_OUTPUTS=false`. If it expects the older OpenAI-compatible token argument, set `API_TOKEN_PARAMETER=max_tokens`. No Python source change is required.

The command never prints or stores `API_KEY`. Each live invocation writes a separate `part1_3_output/runs/run_<id>.json` record containing the public provider settings, per-response token usage, aggregate token usage and estimated cost. Run records are operational audit data and are separate from immutable response revisions.

`API_INPUT_USD_PER_MILLION` and `API_OUTPUT_USD_PER_MILLION` only calculate the `estimated_cost_usd` field in that run record. They do not set provider prices, change billing, select a model or enforce a monetary limit. Set them to the current provider/model prices when cost estimates matter; leave them at zero when unknown. `API_MAX_CALLS` is the actual local request-count bound.

## Public interface

```python
from part1_3 import prepare_next_step_response, markdown_summary

response = prepare_next_step_response(next_step_report)
user_reply = response["user_response"]
maintainer_handoff = markdown_summary(response)
```

`next_step_report` is a Python dictionary parsed from the teammate's JSON. The module validates it against the bundled, unchanged schema. It also checks supported version, finite numbers, payload bounds, duplicate hypothesis IDs and hypothesis cross-references. It does not convert it into the earlier workbench-specific DecisionPacket.

For programmatic live prose composition, inject the provided gateway:

```python
from part1_3.configuration import GatewayConfig
from part1_3.provider import Gateway

config = GatewayConfig.from_env_file("../final_project/personal.env")
gateway = Gateway(config)

def compose(messages, schema):
    return gateway.complete(messages, schema)

response = prepare_next_step_response(next_step_report, compose=compose)
```

The callback receives Chat-Completions-style message dictionaries and a JSON Schema, and returns a parsed object with `user_intro`, `case_summary`, and `fact_ids`. `Gateway` implements that callback over an OpenAI-compatible Chat Completions endpoint. `GatewayConfig` validates the URL and host allowlist and supplies credentials, timeout, output-token and call bounds. The gateway disables provider-library retries; this module makes at most **one** callback invocation for a report. A provider exception or invalid composition produces a labelled deterministic fallback without exposing exception text.

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

Submit `part1_3/` plus the agreed `part1_2_output/` and `part1_3_output/` scaffolding (schema, README and ignore files). Generated case outputs and private environment files remain ignored; run `python -m part1_3 --demo` to reproduce the example. Commit `part1_3/provider.env.example`, but never commit `personal.env` or a real key. The contribution contains the implementation, provider-neutral configuration, OpenAI-compatible gateway, schema, dependency declaration, example and tests. It needs none of the personal workspace's `support_workbench/`, corpus, evaluation outputs, runtime database, private environment files or virtual environment.
