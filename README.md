# Streamlit support-agent team project

Commit work to a branch named after the contributor or assigned part. Each
component must document its input, output, behavior, limitations, and commands.

## Shared stage boundaries

The independently developed branches communicate through JSON contracts:

```text
evidence synthesis -> AnalysisInput -> NextStepReport -> Part3Response -> Problem 2
```

`part1_3_integration/` contains deterministic adapters for the current
`finding_synthesizing_evidence`, `ali-moghadasi`, `sina/part1_3`,
`feat/memory_tools`, and `human_approval_v2` formats. Components do not import one
another's Python classes.

See [the Part 1.3 integration contract](part1_3_integration/README.md) and
[the Part 3 guide](part1_3/README.md).
