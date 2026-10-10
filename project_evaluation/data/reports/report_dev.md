# Failure & Metrics Report — DEV

## Decision quality
{
  "by_bucket": {
    "ambiguous": {
      "n": 6,
      "accuracy": 1.0
    },
    "escalation": {
      "n": 5,
      "accuracy": 1.0
    },
    "answerable": {
      "n": 4,
      "accuracy": 0.0
    }
  },
  "overall_accuracy": 0.7333333333333333,
  "n_scored": 15
}

## Evidence quality
{
  "recall@5": {
    "mean": 0.0,
    "n_labeled": 0
  },
  "recall@10": {
    "mean": 0.0,
    "n_labeled": 0
  }
}

## Operational success
{
  "state_transition_accuracy": 0.4444444444444444,
  "n_checked": 27
}

## Cost & time
{
  "mean_latency_sec": 0.18477910668589176,
  "mean_token_estimate": 1845.9333333333334,
  "mean_steps": 1.8,
  "total_token_estimate": 27689
}

## Failures (4)
- **issue-16538** turn 0: got `ask_clarification`, expected `['answer']`
  - excerpt: Ask the user for the exact Streamlit version and a minimal reproducible example.
  - cause tag: decision_mismatch
- **issue-2975** turn 0: got `ask_clarification`, expected `['answer']`
  - excerpt: Ask the user for the exact Streamlit version and a minimal reproducible example.
  - cause tag: decision_mismatch
- **issue-7426** turn 0: got `ask_clarification`, expected `['answer']`
  - excerpt: Ask the user for the exact Streamlit version and a minimal reproducible example.
  - cause tag: decision_mismatch
- **issue-8838** turn 0: got `ask_clarification`, expected `['answer']`
  - excerpt: Ask the user for the exact Streamlit version and a minimal reproducible example.
  - cause tag: decision_mismatch

## Notes for the written report
- TEST numbers must come from a single frozen run after all tuning on DEV.
- Fill relevant_chunk_ids / relevant_source_ids in annotations for real Recall@k.
- If using LLM-as-a-Judge, attach the judge prompt and human agreement sample here.
- Record source snapshot timestamps/versions from problem1_part1/data/*_meta.json.