# Problem 2 Part 3

This package owns the practical multi-turn scenario evaluation required by
Problem 2 Part 3. It consumes the Problem 2 Parts 1–2 implementation from
`support_agent/`; it does not duplicate that implementation.

Run it from the repository root:

```bash
python -m problem2_part3
python -m unittest discover -s problem2_part3/tests -v
```

The suite contains five development scenarios and five held-out test
scenarios. It uses a local tracker double, performs no network requests, and
writes its generated report to `var/problem2_part3_scenarios.json`.
