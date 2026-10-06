# Support Agent — Memory + Human Approval + Safe Execution

This branch combines the team's **Part 1 (state, memory and tools)** with **Part 2 (human approval and correct execution)**.

## Architecture

```text
User report
   |
   v
Orchestrator
   |
   +--> CaseMemory / SQLite       (persistent per-case state)
   |
   +--> EvidenceStore             (read-only evidence)
   |
   +--> propose_action            (creates a PENDING proposal only)
             |
             v
      HumanApprovalManager
        /      |       \
   approve    edit     reject
      |         |         |
      +---------+---------+
                |
        exact approval token
                |
                v
        validate immediately
        before the side effect
                |
                v
          TicketInterceptor
                |
                v
          updated ticket
```

The important boundary is that **memory and retrieved evidence provide context, not authorization**. Only an explicit human approval/edit creates an authorization token that the executor accepts.

## What changed for Part 2

The original memory branch already contained an approval flow. I kept that architecture and strengthened the approval boundary instead of adding a second, competing database/model system.

### 1. Case versioning

`CaseState.version` changes whenever substantive case state changes. A proposal stores the exact version at which it was created.

If a user changes a fact after approval, the old approval becomes stale and execution is refused.

### 2. Exact action binding

Every proposal stores an SHA-256 hash of its canonical:

```text
{action, payload}
```

The approval token is bound to:

```text
case_id + proposal_id + case_version + action_hash
```

Therefore approval of one action cannot authorize a modified action.

### 3. Explicit human decisions

`HumanApprovalManager` supports:

- `approve()`
- `edit()` — edit the proposed action and approve the edited version
- `reject()`
- `validate_before_execution()`
- `execute()`

### 4. Idempotency

Successful executions are recorded using the case, proposal and action hash. Repeating the same approved execution returns the stored result instead of changing the ticket twice.

### 5. Case isolation

Idempotency records are searched only inside the requested case. Approval tokens contain the case ID, so a token from another case is rejected.

### 6. Secret-safe audit logging

Raw user messages are not written to the event log. Tool failures record an error category/type rather than exception text or a stack trace.

## Files relevant to your section

- `support_agent/approval.py` — **main Human Approval / Correct Execution implementation**
- `support_agent/models.py` — proposal, approval and case-version data structures
- `support_agent/memory.py` — persistent state and version tracking
- `support_agent/orchestrator.py` — exposes approve/edit/reject/execute to the rest of the system
- `support_agent/tools.py` — `apply_action` is the only observable-action tool
- `support_agent/interceptor.py` — local ticket side-effect boundary
- `tests.py` — six safety tests

The old standalone root files `data_model.py`, `validation.py` and `executer.py` are intentionally not used. Keeping a second implementation would create two sources of truth. Your contribution now lives inside the team's existing `support_agent` architecture.

## Safety scenarios

Run:

```powershell
python -m support_agent scenarios
```

The scenarios cover:

1. approve → execute
2. reject → no execution
3. repeated execution → idempotent result
4. waiting for approval → no second proposal
5. case changed after approval → stale approval rejected
6. token from another case → rejected
7. missing case/tool failure → structured error
8. two cases → isolated state and actions

Run the automated tests:

```powershell
python -m unittest -v tests.py
```

Expected result:

```text
Ran 6 tests ...
OK
```

## CLI

Examples:

```powershell
python -m support_agent open 10001 --title "Test case"
python -m support_agent message 10001 "Streamlit 1.35.0 on Linux, running locally, app is slow"
python -m support_agent approve 10001 <proposal_id>
python -m support_agent edit 10001 <proposal_id> comment '{"body":"Human-edited reply"}'
python -m support_agent execute 10001 <proposal_id> --token <approval_token>
python -m support_agent reject 10001 <proposal_id>
```

For a real deployment, the approval secret should be supplied through an environment variable/secret manager rather than committed to source.
