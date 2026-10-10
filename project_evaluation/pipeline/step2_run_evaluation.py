"""
Step 2: Run the compared systems on DEV and/or TEST cases with leakage controls.
- Builds a leakage-controlled corpus per case (see corpus.py).
- Gives every system only the case's visible input (title and body).
- Writes one run log per case and system under project_evaluation/data/runs/{split}/{system}/
Multi-turn behaviour is evaluated by the Problem 2 Part 3 scenarios (see step3).
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List

from config import ANNOT_DIR, CASES_DIR, RUNS_DIR, SPLIT_PATH, SYSTEMS
from corpus import Snapshot, excluded_issue_ids
from problem1_part1.evidence_synthesis import evidence_core as part1_retrieval
from systems import BaselineSystem, IntegratedSystem


def build_systems(names: List[str], live: bool, env_file: str | None) -> list:
    systems = []
    for name in names:
        if name == "baseline":
            systems.append(BaselineSystem())
        elif live:
            from problem1_part3.configuration import GatewayConfig
            from problem1_part3.provider import Gateway

            gateway = Gateway(GatewayConfig.from_env_file(env_file))
            systems.append(IntegratedSystem(compose=gateway.complete, provider_usage=lambda: gateway.last_usage))
        else:
            systems.append(IntegratedSystem())
    return systems


def run_log(case: Dict[str, Any], annot: Dict[str, Any], system, corpus: list, snapshot: Snapshot) -> Dict[str, Any]:
    run = system.run_case(case, corpus)
    return {
        "case_id": case["case_id"],
        "split": case.get("split"),
        "system": system.name,
        "bucket": annot.get("bucket"),
        "cutoff": case["acceptable_source_cutoff"],
        "corpus": dict(Counter(document.source_type for document in corpus)),
        "corpus_policy": snapshot.policy(),
        "retrieval_mode": {
            "embeddings": part1_retrieval.HAS_EMBEDDINGS,
            "bm25": part1_retrieval.HAS_BM25,
        },
        "run": run.to_dict(),
        "ran_at": datetime.now(timezone.utc).isoformat(),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["dev", "test", "both"], default="dev")
    parser.add_argument(
        "--allow-test",
        action="store_true",
        help="required for the test split: run it once, after all development choices are frozen",
    )
    parser.add_argument("--systems", nargs="+", choices=SYSTEMS, default=list(SYSTEMS))
    parser.add_argument("--live", action="store_true", help="compose Part 3 replies with the configured provider")
    parser.add_argument("--env-file", help="provider env file; required with --live")
    args = parser.parse_args()
    if args.split in ("test", "both") and not args.allow_test:
        parser.error("the test split is held out; pass --allow-test only for the final frozen run")
    if args.live and not args.env_file:
        parser.error("--env-file is required with --live")

    split = json.loads(SPLIT_PATH.read_text(encoding="utf-8"))
    cases = {path.stem: json.loads(path.read_text(encoding="utf-8")) for path in CASES_DIR.glob("issue-*.json")}
    snapshot = Snapshot.load()
    excluded = excluded_issue_ids(split, cases.values())
    systems = build_systems(args.systems, args.live, args.env_file)

    targets = []
    if args.split in ("dev", "both"):
        targets.append(("dev", split["dev_case_ids"]))
    if args.split in ("test", "both"):
        targets.append(("test", split["test_case_ids"]))

    for split_name, case_ids in targets:
        print(f"\n=== Running {split_name.upper()} ({len(case_ids)} cases, systems: {', '.join(args.systems)}) ===")
        for cid in case_ids:
            case = cases[cid]
            annot_path = ANNOT_DIR / f"{cid}.json"
            annot = json.loads(annot_path.read_text(encoding="utf-8")) if annot_path.exists() else {}
            corpus = snapshot.corpus_for(case["acceptable_source_cutoff"], excluded)
            for system in systems:
                log = run_log(case, annot, system, corpus, snapshot)
                out_dir = RUNS_DIR / split_name / system.name
                out_dir.mkdir(parents=True, exist_ok=True)
                (out_dir / f"{cid}.json").write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")
                run = log["run"]
                status = f"ERROR {run['error']}" if run["error"] else f"action={run['action']}"
                print(f"  {cid} [{system.name}]: {status} docs={sum(log['corpus'].values())} latency={run['latency_sec']:.2f}s")

    print("\nStep 2 complete. Raw runs in", RUNS_DIR)


if __name__ == "__main__":
    main()
