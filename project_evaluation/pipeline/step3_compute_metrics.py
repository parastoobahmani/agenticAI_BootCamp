"""
Step 3: Compute evidence quality, decision quality, next-step quality, operational
success and cost/time for every evaluated system on the same cases, plus the Problem 2
Part 3 multi-turn scenarios of the same split.

Unlabelled metrics are reported as null with n_labeled = 0, never as 0.0.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Optional

from config import ACTIONS, ANNOT_DIR, RECALL_KS, REPORTS_DIR, RUNS_DIR


def recall_at_k(retrieved: List[str], relevant: List[str], k: int) -> float:
    return len(set(retrieved[:k]) & set(relevant)) / len(set(relevant))


def labelled_mean(values: List[float]) -> Dict[str, Any]:
    return {"mean": mean(values) if values else None, "n_labeled": len(values)}


def rate(flags: List[bool]) -> Dict[str, Any]:
    return {"rate": sum(flags) / len(flags) if flags else None, "n": len(flags)}


def probable_cause(action: Optional[str], expected: List[str], error: Optional[str]) -> str:
    if error:
        return "system_error"
    if action == "escalate":
        return "over_escalation"
    if action == "ask_clarification" and "answer" in expected:
        return "unnecessary_question"
    if action == "answer":
        return "unsupported_answer"
    return "decision_mismatch"


def load_annotation(case_id: str) -> Dict[str, Any]:
    path = ANNOT_DIR / f"{case_id}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def system_metrics(logs: List[Dict[str, Any]], failures: List[Dict[str, Any]]) -> Dict[str, Any]:
    decisions_by_bucket: Dict[str, List[bool]] = defaultdict(list)
    actions_by_bucket: Dict[str, Counter] = defaultdict(Counter)
    recalls: Dict[int, List[float]] = {k: [] for k in RECALL_KS}
    re_asked, gain_based, first_hits = [], [], []
    operational: Dict[str, List[bool]] = defaultdict(list)
    errors = []

    for log in logs:
        run, annot = log["run"], load_annotation(log["case_id"])
        bucket = annot.get("bucket") or log.get("bucket") or "unknown"
        expected = annot.get("acceptable_actions_turn0") or []
        action = run["action"]

        if run["error"]:
            errors.append({"case_id": log["case_id"], "error": run["error"]})
        actions_by_bucket[bucket][action or "error"] += 1
        if expected:
            correct = action in expected
            decisions_by_bucket[bucket].append(correct)
            if not correct:
                failures.append({
                    "system": log["system"],
                    "case_id": log["case_id"],
                    "bucket": bucket,
                    "action": action,
                    "expected": expected,
                    "probable_cause": probable_cause(action, expected, run["error"]),
                    "error": run["error"],
                    "response_excerpt": (run["text"] or "")[:300],
                })

        relevant_chunks = annot.get("relevant_chunk_ids") or []
        relevant_sources = annot.get("relevant_source_ids") or []
        if relevant_chunks or relevant_sources:
            retrieved = run["retrieved_chunk_ids"] if relevant_chunks else run["retrieved_source_ids"]
            for k in RECALL_KS:
                recalls[k].append(recall_at_k(retrieved, relevant_chunks or relevant_sources, k))

        next_step = run.get("next_step")
        if next_step:
            asked = next_step["asked"]
            re_asked.append(bool(set(asked) & set(next_step["known"])))
            if asked:
                gain_based.append(next_step["bases"][0] == "information_gain")
            gold_missing = annot.get("missing_information") or []
            if gold_missing and asked:
                first_hits.append(asked[0] in gold_missing)

        for check, passed in (run.get("operational") or {}).items():
            operational[check].append(passed)
        if run.get("operational"):
            operational["all_checks"].append(all(run["operational"].values()))

    all_decisions = [flag for flags in decisions_by_bucket.values() for flag in flags]
    usage = [log["run"]["usage"] for log in logs]
    latencies = [log["run"]["latency_sec"] for log in logs]
    return {
        "n_cases": len(logs),
        "n_errors": len(errors),
        "errors": errors,
        "decision_quality": {
            "overall_accuracy": rate(all_decisions)["rate"],
            "n_scored": len(all_decisions),
            "by_bucket": {bucket: rate(flags) for bucket, flags in sorted(decisions_by_bucket.items())},
            "actions_by_bucket": {
                bucket: {action: counts.get(action, 0) for action in (*ACTIONS, "error")}
                for bucket, counts in sorted(actions_by_bucket.items())
            },
        },
        "evidence_quality": {f"recall@{k}": labelled_mean(values) for k, values in recalls.items()},
        "next_step_quality": None if not re_asked else {
            "re_asked_known_information": rate(re_asked),
            "first_step_from_information_gain": rate(gain_based),
            "first_step_hits_labelled_missing_information": rate(first_hits),
        },
        "operational_success": None if not operational else {
            check: rate(flags) for check, flags in operational.items()
        },
        "cost_time": {
            "mean_latency_sec": mean(latencies) if latencies else None,
            "max_latency_sec": max(latencies) if latencies else None,
            "mean_setup_sec": mean(log["run"]["setup_sec"] for log in logs) if logs else None,
            "api_requests": sum(item.get("api_requests", 0) for item in usage),
            "input_tokens": sum(item.get("input_tokens", 0) for item in usage),
            "output_tokens": sum(item.get("output_tokens", 0) for item in usage),
            "estimated_cost_usd": round(sum(item.get("estimated_cost_usd", 0.0) for item in usage), 6),
            "token_estimate_without_api": sum(item.get("token_estimate", 0) for item in usage) or None,
        },
    }


def problem2_scenarios(split: str) -> Dict[str, Any]:
    """Run the Problem 2 Part 3 scenarios of this split; a failing scenario is recorded, not raised."""
    from problem2_part3.scenarios import SCENARIOS

    results = []
    for scenario_id, name, scenario_split, scenario in SCENARIOS:
        if scenario_split != split:
            continue
        with tempfile.TemporaryDirectory(prefix=f"{scenario_id.lower()}-") as directory:
            try:
                scenario(Path(directory))
                results.append({"scenario_id": scenario_id, "name": name, "passed": True, "error": None})
            except Exception as exc:  # isolation boundary: one failing scenario must not hide the others
                results.append({"scenario_id": scenario_id, "name": name, "passed": False, "error": f"{type(exc).__name__}: {exc}"})
    return {
        "source": "problem2_part3.scenarios (designed follow-ups, real stored state, no API calls)",
        "passed": sum(row["passed"] for row in results),
        "total": len(results),
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["dev", "test"], default="dev")
    args = parser.parse_args()

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    split_dir = RUNS_DIR / args.split
    system_dirs = sorted(path for path in split_dir.iterdir() if path.is_dir()) if split_dir.exists() else []
    if not system_dirs:
        raise SystemExit(f"No runs found for {args.split}. Run step2 first.")

    failures: List[Dict[str, Any]] = []
    systems, corpus_policy = {}, None
    for system_dir in system_dirs:
        logs = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(system_dir.glob("issue-*.json"))]
        corpus_policy = corpus_policy or (logs[0]["corpus_policy"] if logs else None)
        systems[system_dir.name] = system_metrics(logs, failures)

    report = {
        "split": args.split,
        "corpus_policy": corpus_policy,
        "systems": systems,
        "problem2_scenarios": problem2_scenarios(args.split),
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
