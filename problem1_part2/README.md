# Problem 1 Part 2

This folder owns missing-information detection and next-step selection:

- `implementation/`: analyzer and command-line implementation.
- `examples/`: authored inputs and expected example reports.
- `schemas/`: public `AnalysisInput` and `NextStepReport` JSON Schemas.
- `tests/`: component tests.

Run commands from the repository root:

```bash
python -m problem1_part2 analyze problem1_part2/examples/stuck_loading_on_server.json --output report.json
python -m pytest problem1_part2/tests -q
```

The component accepts Problem 1 Part 1 evidence through its public JSON
contract and emits a `NextStepReport` for Problem 1 Part 3.
