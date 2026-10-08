evaluation_structure/
├── data/
│   └── raw/
│       ├── issues.jsonl
│       ├── comments.jsonl
│       ├── documentation.jsonl
│       └── release_notes.jsonl
├── eval_pipeline/
│   ├── config.py
│   ├── evidence_core.py          # Part-1 retrieval + synthesis (from earlier)
│   ├── system_under_test.py      # thin wrapper around your assistant
│   ├── step0_prepare_cases.py
│   ├── step1_create_annotation_stubs.py
│   ├── step2_run_evaluation.py
│   ├── step3_compute_metrics.py
│   └── step4_failure_report.py
└── data/eval/                    # created by the scripts
    ├── case_split.json
    ├── cases/
    ├── annotations/
    ├── multi_turn/
    ├── runs/
    └── reports/

Run in the following order:
Order,Script,Typical run config
0: step0_prepare_cases.py,no args
1) step1_create_annotation_stubs.py,no args
1-b "Manually edit data/eval/annotations/*.json (buckets, acceptable actions, optional relevant ids)",—
2) step2_run_evaluation.py,Parameters: --split dev
3) step3_compute_metrics.py,Parameters: --split dev
4) "Iterate on DEV only (prompts, retrieval, thresholds)",—
5) step2_run_evaluation.py,Parameters: --split test (once)
6) step3_compute_metrics.py,Parameters: --split test
7) step4_failure_report.py,no args

Results/Outputs:
data/eval/reports/metrics_dev.json / metrics_test.json
data/eval/reports/failures_*.json
data/eval/reports/report_*.md

## Mapping to the evaluation brief
Requirement,                                         Where it is handled
"≥30 cases, 15/15 whole-case split",                 step0 + case_split.json
"Multi-turn ≥10, half in test via random split",     step0 marks multi-turn; scripts live in multi_turn/
No test for tuning,                                  You only pass --split test at the end
Annotations separate from search DB,                 annotations/ never added to corpus
Time cutoff / no future info,                        filter_corpus_for_case
Seed issue not used as its own answer,               forbidden_source_ids
Evidence Recall@k,                                   step3 when gold ids are filled
Decision quality by bucket,                          step3 decision_by_bucket
Operational state checks,                            expected_state vs assistant.state
Cost / time,                                         latency + token_estimate in run logs
Failure analysis,                                    failures_*.json + step4 report