# Problem 1 to Problem 2 integration contracts

The team components keep their existing native contracts. This folder supplies
deterministic adapters at the boundaries:

```text
finding_synthesizing_evidence
    SynthesisResult + original case
        -> AnalysisInput
ali-moghadasi
    AnalysisInput -> NextStepReport
sina/part1_3
    NextStepReport -> Part3Response
feat/memory_tools
    Part3Response + AnalysisInput -> CaseState-compatible MemorySeed
human_approval_v2
    Part3Response + AnalysisInput -> versioned CaseState with pending Proposal
```

`schemas/analysis_input.schema.json` is copied unchanged from `ali-moghadasi`.
`problem1_part2_output/next_step_report.schema.json` is the unchanged Part 2 to Part 3
contract. The adapters use dictionaries and JSON, so no branch has to import
another branch's Python classes.

The synthesis adapter does not treat retrieval similarity as hypothesis
confidence. The evidence-synthesis output has no calibrated hypothesis score, so
adapted hypotheses use `confidence=0.0`. This causes downstream code to remain
cautious instead of converting a similarity score into false certainty.

The memory adapter should receive both the `AnalysisInput` and Part 3 response.
The Part 3 contract intentionally omits the original title/body and resolved
source text, while Problem 2 needs them for persistent case state. Its output can
be passed directly to `CaseState.from_dict` on `feat/memory_tools`.

The `human_approval_v2` adapter imports the completed Problem 1 state as case
version 1. Its pending comment proposal carries the same version and an SHA-256
hash of the exact canonical `{action, payload}` object. This matches the v2
approval token and stale-proposal checks. The older standalone `human_approval`
branch is intentionally unsupported.

Part 3 response revisions and Problem 2 case versions are separate identifiers.
The immutable `response_id` and `input_fingerprint` are retained in the imported
proposal rationale for provenance. Import creates `CaseState.version=1`; later
facts, edits and actions increment the Problem 2 version without altering the
Part 3 artifact. Approval always binds to the current Problem 2 version.

Use `part3_response_to_human_approval_v2_seed` only when creating the initial
Problem 2 case. For every later immutable Part 3 revision, call
`part3_response_to_action_request` and pass its result to v2 `propose_action`.
The v2 memory layer then assigns the current `case_version` and `action_hash`.
Reject or otherwise resolve an older pending proposal before proposing a newer
response revision, so maintainers see one current draft awaiting review.

Run the compatibility tests from the repository root:

```bash
python -m unittest discover -s problem1_to_problem2/tests -v
```
