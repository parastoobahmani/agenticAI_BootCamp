# Support Agent — State, Memory and Tools

This branch implements **Part 1 (وضعیت، حافظه و ابزارها)** and
**Part 2 (تأیید انسانی و اجرای درست)** of Problem 2 for the Streamlit
technical-support assistant: the case state, the per-case memory, the tool layer
the agent is allowed to use, and the human-approval plus safe-execution path.

## What the code does

Each case is stored on its own in a SQLite file (`support_agent/storage.py`), and
`CaseMemory` (`support_agent/memory.py`) is the only thing that writes to it.
Memory keeps the known facts, the open unknowns, the checks that were performed,
the retrieved sources, the proposals, the executed actions and the turn counter —
always keyed by `case_id`, so two cases running at the same time cannot read or
write each other's data. State survives a restart because it lives on disk, not
in process memory.

`support_agent/tools.py` declares the tool contract: `read_ticket` and
`search_evidence` are read-only, while `propose_action` and `apply_action` change
the ticket. Every tool has a named input and a validated argument list, and an
unknown tool or a missing argument returns a structured error instead of raising.
`Orchestrator.call_tool` (`support_agent/orchestrator.py`) is the dispatcher: it
counts calls against a hard ceiling, validates the arguments, runs the handler and
returns `{"ok": ...}`. The result of a tool is stored back into case memory, so the
next decision actually depends on it.

No visible ticket change happens without human approval. `propose_action` only
prepares a proposal; `approve` marks it approved and returns a token bound to that
case and that proposal; `apply_action` refuses any token that was not issued for
that exact pair, refuses a rejected proposal, re-checks that newer case facts have
not invalidated the proposal, and skips execution if the same action was already
recorded (idempotency). The visible ticket itself is a local, resettable JSON file
(`support_agent/interceptor.py`) — nothing here touches the real repository.

## Part 2 — human approval and correct execution

Part 2 is the "never change the ticket on your own" half of the task. The rules
that are enforced in code:

1. **A proposal is not an action.** `create_proposal` only appends a record with
   `status="pending"`. Nothing is written to the ticket at that moment.
2. **Approval is explicit and signed.** `Orchestrator.approve` sets
   `status="approved"`, records `decided_by` and `decided_at`, and returns
   `approval_token = appr:<case_id>:<proposal_id>:<sha256(secret|case|proposal)[:16]>`.
   The token is not just a flag: it is bound to one case and one proposal.
3. **Execution demands that exact token.** `execute` → `apply_action` →
   `validate_approval` re-computes the token and compares it. A token from another
   proposal of the same case, or an empty token, is refused. A rejected proposal is
   refused. A still-pending proposal is refused with "has not been approved".
4. **The proposal is re-checked against the current case.** Before dispatching,
   `check_validity` compares the proposal's captured facts against the live case
   (version mismatch, already-closed case, empty comment body, or a case that
   changed after the proposal was created).
5. **Execution is idempotent.** `has_action(case_id, "apply_action", {case_id, proposal_id})`
   runs first, so calling `execute` twice returns
   `{"executed": False, "duplicate": True}` and the ticket keeps exactly one change.
6. **Rejection is terminal.** `approve` after `reject` fails with
   `approval_failed: proposal ... is already rejected`.
7. **While a proposal waits, the agent stops.** `decide` returns
   `WAIT_FOR_APPROVAL` instead of stacking a second proposal.
8. **Everything is bounded.** `max_steps` and `max_tool_calls` raise
   `BudgetExceeded` instead of looping, and every proposal, decision, action and
   tool error is written to the SQLite event log.

## Scenarios and their real output

`python -m support_agent scenarios` runs eight scripted cases
(`support_agent/scenarios.py`) and prints the actual results below.

**1. Normal path — approve then execute.**
`decision: PROPOSE` → `approve` returns `{'ok': True, 'status': 'approved', 'approval_token': 'appr:30001:...:ba464134ab02d4b2'}` → `execute` returns
`{'executed': True, 'duplicate': False}`, ticket comments: 1.

**2. Maintainer rejects.**
`reject` → `{'ok': True, 'status': 'rejected'}`; `approve` after that → `{'ok': False, 'error': 'approval_failed', 'message': "proposal 'PRP_e7b23f94' is already rejected"}`;
ticket comments: 0, labels: [].

**3. Same execute call repeated.**
First call → `{'executed': True, 'duplicate': False}`; second call →
`{'executed': False, 'duplicate': True}`; ticket comments: 1 (not 2).

**4. The agent waits.**
first turn `PROPOSE PRP_dfedda14`; second turn `WAIT_FOR_APPROVAL PRP_dfedda14`;
pending proposals: 1.

**5. A fact changes after approval.**
The user corrects the version to 1.35.0 after approval →
`{'ok': False, 'error': 'proposal_invalidated', 'message': 'streamlit_version in the proposal no longer matches the case'}`;
ticket comments: 0.

**6. Token from another proposal.**
`{'ok': False, 'error': 'tool_error', 'message': 'approval token is not valid for this case and proposal'}`;
with no token: `missing_argument: apply_action requires 'approval_token'`; ticket comments: 0.

**7. Missing case.**
`{'ok': False, 'error': 'tool_error', 'message': "no case with id 'nope'"}` —
a structured error, not a crash.

**8. Two cases at once.**
A executed and has 1 comment; B is still `pending` with 0 comments — the two cases
did not mix state or actions.

## Files

- `support_agent/models.py` — the dataclasses for a case and its records.
- `support_agent/storage.py` — SQLite persistence plus an event log.
- `support_agent/memory.py` — per-case memory and approval tokens.
- `support_agent/tools.py` — tool specifications and argument validation.
- `support_agent/interceptor.py` — the resettable local ticket.
- `support_agent/evidence.py` — the read-only evidence search over `assets/evidence_store.json`.
- `support_agent/orchestrator.py` — the tool dispatcher, decision and approval flow.
- `support_agent/cli.py` — the command line used to inspect and drive a case.
- `support_agent/scenarios.py` — the eight scripted cases for Part 2.

## Running it

```
python -m support_agent reset --ticket
python -m support_agent seed
python -m support_agent show 10001
python -m support_agent message 10001 "Streamlit 1.30.0 on Python 3.11 behind nginx, stuck on loading screen"
python -m support_agent approve 10001 <proposal_id>
python -m support_agent execute 10001 <proposal_id> --token <approval_token>
python -m support_agent reject 10001 <proposal_id>
python -m support_agent events --case_id 10001
python -m support_agent tools
python -m support_agent ticket
python -m support_agent scenarios
```

`reset` clears the case store; `reset --ticket` also resets the interceptor.
