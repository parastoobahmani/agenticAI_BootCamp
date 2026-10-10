"""
Step 1: Create annotation stubs + multi-turn scripts.
YOU must edit the annotation files to add gold labels before trusting decision metrics.
Evidence-relevance labels can start empty and be filled for a subset (Recall@k).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from config import CASES_DIR, ANNOT_DIR, MULTI_DIR, SPLIT_PATH, COMMENTS_PATH


def load_jsonl(path: Path) -> List[Dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def main():
    ANNOT_DIR.mkdir(parents=True, exist_ok=True)
    MULTI_DIR.mkdir(parents=True, exist_ok=True)

    split = json.loads(SPLIT_PATH.read_text(encoding="utf-8"))
    comments = load_jsonl(COMMENTS_PATH)
    comments_by_issue = {}
    for c in comments:
        comments_by_issue.setdefault(c["issue_number"], []).append(c)

    for case_path in sorted(CASES_DIR.glob("issue-*.json")):
        case = json.loads(case_path.read_text(encoding="utf-8"))
        cid = case["case_id"]
        number = case["seed_issue_number"]

        # --- annotation stub ---
        annot = {
            "case_id": cid,
            "bucket": case.get("stratum_auto", "ambiguous"),  # answerable | ambiguous | escalation
            # Gold relevant chunk/source ids for Recall@k (fill for a subset)
            "relevant_source_ids": [],
            "relevant_chunk_ids": [],
            # Acceptable assistant actions for turn 0
            "acceptable_actions_turn0": (
                ["ask_clarification"]
                if case.get("stratum_auto") == "ambiguous"
                else ["answer"]
                if case.get("stratum_auto") == "answerable"
                else ["escalate", "ask_clarification"]
            ),
            "ideal_response_notes": "TODO: write what a good first reply should do.",
            "expected_state_after_turn0": {
                "waiting_for_user": case.get("stratum_auto") == "ambiguous",
                "escalated": case.get("stratum_auto") == "escalation",
                "status": "escalated" if case.get("stratum_auto") == "escalation" else "open",
            },
        }
        (ANNOT_DIR / f"{cid}.json").write_text(
            json.dumps(annot, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # --- multi-turn script (only for marked cases) ---
        if case.get("is_multi_turn"):
            c_list = sorted(
                comments_by_issue.get(number, []),
                key=lambda x: x.get("created_at") or "",
            )
            turns = [
                {
                    "role": "user",
                    "visible": True,
                    "text": f"{case['title']}\n\n{case['body']}",
                },
                {
                    "role": "assistant",
                    "ideal_action": annot["acceptable_actions_turn0"][0],
                    "acceptable": annot["acceptable_actions_turn0"],
                    "expected_state": annot["expected_state_after_turn0"],
                },
            ]
            # Use up to 2 real comments as subsequent user turns (sanitized)
            for c in c_list[:2]:
                turns.append(
                    {
                        "role": "user",
                        "visible": False,
                        "text": (c.get("body") or "")[:1500],
                    }
                )
                turns.append(
                    {
                        "role": "assistant",
                        "ideal_action": "answer",
                        "acceptable": ["answer", "ask_clarification", "escalate"],
                        "expected_state": {
                            "waiting_for_user": False,
                            "escalated": False,
                            "status": "open",
                        },
                    }
                )

            (MULTI_DIR / f"{cid}.json").write_text(
                json.dumps({"case_id": cid, "turns": turns}, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    print("Step 1 complete.")
    print(f"  Annotations → {ANNOT_DIR}")
    print(f"  Multi-turn  → {MULTI_DIR}")
    print(
        "\nACTION REQUIRED: Edit annotation JSON files to set correct "
        "bucket, acceptable_actions, relevant_source_ids (for Recall@k), "
        "and ideal_response_notes. Decision metrics are only reliable after this."
    )


if __name__ == "__main__":
    main()
