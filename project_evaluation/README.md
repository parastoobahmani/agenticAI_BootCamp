# Project evaluation

This folder owns evaluation across the completed project:

- `pipeline/`: case preparation, execution, metric computation and failure reporting.
- `data/`: evaluation cases, annotations, multi-turn inputs and reports.

Run the pipeline from the repository root in the documented order:

```bash
python project_evaluation/pipeline/step0_prepare_cases.py
python project_evaluation/pipeline/step1_create_annotation_stubs.py
python project_evaluation/pipeline/step2_run_evaluation.py --split dev
python project_evaluation/pipeline/step3_compute_metrics.py --split dev
python project_evaluation/pipeline/step4_failure_report.py
```

The pipeline reads the immutable evidence snapshot from `problem1_part1/data/`.
