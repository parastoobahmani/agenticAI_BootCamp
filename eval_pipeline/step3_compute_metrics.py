"""
Step 3: Compute Evidence Quality, Decision Quality, Operational Success, Cost/Time.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

from config import RUNS_DIR, ANNOT_DIR, REPORTS_DIR, RECALL_KS, SPLIT_PATH


def safe_div(a, b):
    return a / b if b else 0.0


def recall_at_k(retrieved: List[str], relevant: List[str], k: int) -> float:
    if not relevant:
        return float("nan")
    hit = len(set(retrieved[:k]) & set(relevant))
    return hit / len(set(relevant))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["dev", "test"], default="dev")
    args = parser.parse_args()

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    run_dir = RUNS_DIR / args.split
    if not run_dir.exists():
        raise SystemExit(f"No runs found for {args.split}. Run step2 first.")

    decision_by_bucket = defaultdict(list)
    state_oks = []
    latencies = []
    tokens = []
    steps = []
    recalls = {k: [] for k in RECALL_KS}
    failures = []

    for path in sorted(run_dir.glob("issue-*.json")):
        log = json.loads(path.read_text(encoding="utf-8"))
        cid = log["case_id"]
        annot_path = ANNOT_DIR / f"{cid}.json"
        annot = json.loads(annot_path.read_text(encoding="utf-8")) if annot_path.exists() else {}

        bucket = log.get("bucket") or annot.get("bucket") or "unknown"
        latencies.append(log.get("total_latency_sec") or 0)
        tokens.append(log.get("total_token_estimate") or 0)
        steps.append(log.get("n_turns") or 0)

        # Decision + state: use first turn (and average multi-turn if present)
        turn_decisions = []
        for t in log.get("turns") or []:
            if t.get("decision_ok") is not None:
                turn_decisions.append(bool(t["decision_ok"]))
            if t.get("state_ok") is not None:
                state_oks.append(bool(t["state_ok"]))
            if t.get("decision_ok") is False:
                failures.append(
                    {
                        "case_id": cid,
                        "turn": t.get("turn_index"),
                        "action": t.get("action"),
                        "expected": t.get("expected_actions"),
                        "response_excerpt": (t.get("response_text") or "")[:300],
                        "probable_cause": "decision_mismatch",
                    }
                )

        if turn_decisions:
            decision_by_bucket[bucket].append(all(turn_decisions))

        # Evidence Recall@k (only if gold relevant ids provided)
        relevant = annot.get("relevant_chunk_ids") or annot.get("relevant_source_ids") or []
        if relevant and log.get("turns"):
            retrieved = log["turns"][0].get("retrieved_chunk_ids") or []
            # if gold is source_ids, map roughly via citation source_id field
            if annot.get("relevant_source_ids") and not annot.get("relevant_chunk_ids"):
                retrieved_sources = [
                    c.get("source_id")
                    for c in (log["turns"][0].get("citations") or [])
                    if c.get("source_id")
                ]
                for k in RECALL_KS:
                    recalls[k].append(recall_at_k(retrieved_sources, relevant, k))
            else:
                for k in RECALL_KS:
                    recalls[k].append(recall_at_k(retrieved, relevant, k))

    # Aggregate
    decision_summary = {}
    all_dec = []
    for b, vals in decision_by_bucket.items():
        decision_summary[b] = {
            "n": len(vals),
            "accuracy": safe_div(sum(vals), len(vals)),
        }
        all_dec.extend(vals)

    report = {
        "split": args.split,
        "n_cases": len(list(run_dir.glob("issue-*.json"))),
        "evidence_quality": {
            f"recall@{k}": {
                "mean": safe_div(sum(v for v in vals if v == v), len([v for v in vals if v == v])),
                "n_labeled": len([v for v in vals if v == v]),
            }
            for k, vals in recalls.items()
        },
        "decision_quality": {
            "by_bucket": decision_summary,
            "overall_accuracy": safe_div(sum(all_dec), len(all_dec)),
            "n_scored": len(all_dec),
        },
        "operational_success": {
            "state_transition_accuracy": safe_div(sum(state_oks), len(state_oks)),
            "n_checked": len(state_oks),
        },
        "cost_time": {
            "mean_latency_sec": safe_div(sum(latencies), len(latencies)),
            "mean_token_estimate": safe_div(sum(tokens), len(tokens)),
            "mean_steps": safe_div(sum(steps), len(steps)),
            "total_token_estimate": sum(tokens),
        },
        "n_failures_logged": len(failures),
    }

    out = REPORTS_DIR / f"metrics_{args.split}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    fail_out = REPORTS_DIR / f"failures_{args.split}.json"
    fail_out.write_text(json.dumps(failures, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(report, indent=2))
    print(f"\nWrote {out}")
    print(f"Wrote {fail_out}")


if __name__ == "__main__":
    main()
