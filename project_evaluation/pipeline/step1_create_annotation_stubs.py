"""
Step 1: Create annotation stubs.
YOU must edit the annotation files to add gold labels before trusting decision metrics.
Existing annotation files are never overwritten unless --force is passed, so hand-made
labels survive re-runs.

Fields to fill by hand:
- bucket: answerable | ambiguous | escalation
- acceptable_actions_turn0: subset of answer | ask_clarification | escalate
- missing_information: Part 2 facet ids a good first step would ask about, e.g.
  ["streamlit_version", "widget_has_key"] (see problem1_part2/implementation/facets.py)
- relevant_source_ids / relevant_chunk_ids: gold evidence for Recall@k (a subset is enough)
- ideal_response_notes: what a good first reply should do

Multi-turn behaviour is covered by the Problem 2 Part 3 scenarios, not by these stubs.
"""
from __future__ import annotations

import argparse
import json

from config import ANNOT_DIR, CASES_DIR


def stub(case: dict) -> dict:
    stratum = case.get("stratum_auto", "ambiguous")
    return {
        "case_id": case["case_id"],
        "bucket": stratum,  # automatic guess; correct it by hand
        "relevant_source_ids": [],
        "relevant_chunk_ids": [],
        "missing_information": [],
        "acceptable_actions_turn0": (
            ["ask_clarification"]
            if stratum == "ambiguous"
            else ["answer"]
            if stratum == "answerable"
            else ["escalate", "ask_clarification"]
        ),
        "ideal_response_notes": "TODO: write what a good first reply should do.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="overwrite existing (possibly hand-edited) annotations")
    args = parser.parse_args()
    ANNOT_DIR.mkdir(parents=True, exist_ok=True)

    created, kept = 0, 0
    for case_path in sorted(CASES_DIR.glob("issue-*.json")):
        case = json.loads(case_path.read_text(encoding="utf-8"))
        target = ANNOT_DIR / f"{case['case_id']}.json"
        if target.exists() and not args.force:
            kept += 1
            continue
        target.write_text(json.dumps(stub(case), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        created += 1

    print("Step 1 complete.")
    print(f"  Annotations → {ANNOT_DIR} ({created} written, {kept} existing kept)")
    print(
        "\nACTION REQUIRED: Edit annotation JSON files to set correct bucket, acceptable actions, "
        "missing_information, relevant ids (for Recall@k) and ideal_response_notes. "
        "Decision metrics are only reliable after this."
    )


if __name__ == "__main__":
    main()
