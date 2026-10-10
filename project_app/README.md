# Integrated project application

`project_app` is the thin runtime that joins the separately owned assignment
parts. It invokes their public Python interfaces and persists every contract; it
does not duplicate their decision logic.

## Input and output

The only runtime input is one case JSON matching `problem1_part2.Case`:

```json
{
  "case_id": "123",
  "title": "App stays on the loading screen",
  "body": "The report body",
  "comments": [{"id": "1", "body": "A follow-up", "author_association": "NONE"}]
}
```

The run uses the committed snapshot in `problem1_part1/data/`. It does not run
the GitHub collectors. It creates immutable artifacts under
`project_app/runtime/runs/`, then imports the Part 3 reply into Problem 2 as a
pending comment proposal. Nothing is published until a maintainer approves and
executes that proposal through the Problem 2 CLI.

## Run

Offline, with deterministic Part 3 prose:

```bash
python -m project_app run project_app/examples/example_case.json
```

Live Part 3 composition through an OpenAI-compatible provider:

```bash
python -m project_app run project_app/examples/example_case.json \
  --live --env-file path/to/private.env
```

The provider file uses the same interchangeable names documented in
`problem1_part3/provider.env.example`: `API_KEY`, `API_BASE_URL`, and
`API_MODEL`, plus optional safety, token, and pricing settings.

## Stage artifacts

Each run writes an immutable directory identified by both the Part 3 response
ID and the normalized case-input fingerprint. This preserves separate user
turns even when two inputs produce the same response text.

Each run writes:

| File | Producer / meaning |
|---|---|
| `input_case.json` | validated application input |
| `problem1_part1_synthesis.json` | retrieved and synthesized evidence |
| `analysis_input.json` | adapter output consumed by Part 1 Part 2 |
| `next_step_report.json` | Part 1 Part 2 decision contract |
| `part3_response.json` | proposed user reply and technical summary |
| `maintainer_summary.md` | readable maintainer handoff |
| `problem2_import.json` | pending proposal identity and import result |
| `manifest.json` | run mode, counts, composition method, and provider usage |

Re-running the same deterministic response reuses its Problem 2 proposal. A new
response revision is rejected while an older proposal is pending; the
maintainer must first approve or reject the old proposal.

## Web application

Start the local server in offline mode:

```bash
python -m project_app serve
```

Or enable live Part 3 composition:

```bash
python -m project_app serve --live --env-file personal.env
```

Open `http://127.0.0.1:8765/`. The server provides two views:

- **User:** submit a case, see replies that were actually published, and add a
  correction, test result, or new symptom.
- **Maintainer:** inspect the evidence synthesis and `NextStepReport`, edit the
  exact proposed reply, reject it with a review note, or approve and publish it
  to the local ticket interceptor.

The state transitions preserve the team boundaries:

```text
user input -> ProjectPipeline -> pending Problem 2 proposal
                                      |
                         maintainer approve / edit / reject
                                      |
                         local ticket publication or wait
                                      |
                          later user input -> new revision
```

A user follow-up supersedes any unreviewed proposal, retains it as rejected
audit history, reruns Problems 1.1–1.3 with the complete conversation, merges
the new revision into Problem 2 memory, and creates a new pending proposal.
After an approval or rejection, the next user message resumes from the stored
case instead of creating a disconnected case.

The server intentionally binds only to loopback addresses because the project
does not include an identity provider. Deploying it beyond one machine requires
real user and maintainer authentication plus TLS at the hosting layer.
