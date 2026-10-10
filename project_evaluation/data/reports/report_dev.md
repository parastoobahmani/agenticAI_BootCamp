# Evaluation report — DEV

## Systems compared on the same cases

| Metric | baseline | integrated |
|---|---|---|
| Cases / errors | 15 / 0 | 15 / 0 |
| Decision accuracy (overall) | 0.73 | 0.40 |
| Decision accuracy: ambiguous | 1.00 (n=6) | 0.17 (n=6) |
| Decision accuracy: answerable | 0.00 (n=4) | 0.00 (n=4) |
| Decision accuracy: escalation | 1.00 (n=5) | 1.00 (n=5) |
| Recall@5 | n/a (n=0) | n/a (n=0) |
| Recall@10 | n/a (n=0) | n/a (n=0) |
| Re-asked known information | n/a (n=0) | 0.00 (n=15) |
| First step from information gain | n/a (n=0) | 0.27 (n=15) |
| First step hits labelled missing info | n/a (n=0) | n/a (n=0) |
| All operational checks on stored state | n/a (n=0) | 1.00 (n=15) |
| Mean / max latency (s) | 0.04 / 0.06 | 0.13 / 0.38 |
| API requests / tokens in+out / cost USD | 0 / 0+0 / 0.0 | 0 / 0+0 / 0.0 |

## Actions taken per bucket

Shown next to accuracy so that asking or escalating on every case cannot pass as success.

**baseline**

| Bucket | answer | ask_clarification | escalate | error |
|---|---|---|---|---|
| ambiguous | 0 | 6 | 0 | 0 |
| answerable | 0 | 4 | 0 | 0 |
| escalation | 0 | 5 | 0 | 0 |

**integrated**

| Bucket | answer | ask_clarification | escalate | error |
|---|---|---|---|---|
| ambiguous | 0 | 1 | 5 | 0 |
| answerable | 0 | 2 | 2 | 0 |
| escalation | 0 | 1 | 4 | 0 |

## Multi-turn and operational scenarios (Problem 2 Part 3)

5/5 passed — problem2_part3.scenarios (designed follow-ups, real stored state, no API calls).

- S01 normal multi-turn path: passed
- S02 user correction invalidates old approval: passed
- S03 maintainer rejection: passed
- S04 maintainer edit binds exact action: passed
- S05 restart while waiting for approval: passed

## Corpus policy

- evaluation_cases_excluded: True
- issues: created before cutoff; comments up to cutoff; bots, final state and labels removed
- release_notes: published before cutoff
- documentation: pinned snapshot d97e7bbfa275aca06c65c4e3ed0f51023460fbdd (not historical)

## Failures (13)

- baseline: unnecessary_question × 4
- integrated: over_escalation × 7
- integrated: unnecessary_question × 2

- **baseline / issue-16538** (answerable): got `ask_clarification`, expected `['answer']` — unnecessary_question
- **baseline / issue-2975** (answerable): got `ask_clarification`, expected `['answer']` — unnecessary_question
- **baseline / issue-7426** (answerable): got `ask_clarification`, expected `['answer']` — unnecessary_question
- **baseline / issue-8838** (answerable): got `ask_clarification`, expected `['answer']` — unnecessary_question
- **integrated / issue-10501** (ambiguous): got `escalate`, expected `['ask_clarification']` — over_escalation
- **integrated / issue-16538** (answerable): got `ask_clarification`, expected `['answer']` — unnecessary_question
- **integrated / issue-16721** (ambiguous): got `escalate`, expected `['ask_clarification']` — over_escalation
- **integrated / issue-16827** (ambiguous): got `escalate`, expected `['ask_clarification']` — over_escalation
- **integrated / issue-17107** (ambiguous): got `escalate`, expected `['ask_clarification']` — over_escalation
- **integrated / issue-2975** (answerable): got `escalate`, expected `['answer']` — over_escalation
- **integrated / issue-7426** (answerable): got `ask_clarification`, expected `['answer']` — unnecessary_question
- **integrated / issue-8186** (ambiguous): got `escalate`, expected `['ask_clarification']` — over_escalation
- **integrated / issue-8838** (answerable): got `escalate`, expected `['answer']` — over_escalation

## Notes for the written report
- TEST numbers must come from a single frozen run after all tuning on DEV (step2 needs --allow-test).
- Decision accuracy is only as good as the annotations: fill bucket, acceptable actions, missing_information and relevant ids by hand.
- If using LLM-as-a-Judge, attach the judge prompt and a human agreement sample here.
- Record source snapshot timestamps/versions from problem1_part1/data/*_meta.json.
