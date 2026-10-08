"""
Step 0: Load raw data, select ≥30 diverse cases, split into 15 DEV + 15 TEST
at the whole-case level, and write case cards (no gold answers yet).
"""
from __future__ import annotations

import json
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from config import (
    ISSUES_PATH,
    COMMENTS_PATH,
    DOCS_PATH,
    RELEASES_PATH,
    EVAL,
    CASES_DIR,
    SPLIT_PATH,
    N_DEV,
    N_TEST,
    N_TOTAL,
    N_MULTI_TURN,
    SPLIT_SEED,
    MIN_BODY_LEN,
)


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def stratify_label(issue: Dict) -> str:
    labels = [lb.lower() for lb in issue.get("labels", [])]
    body = (issue.get("body") or "").lower()
    title = (issue.get("title") or "").lower()
    text = title + " " + body

    if any("bug" in lb or "regression" in lb for lb in labels) or "error" in text or "traceback" in text:
        if "version" not in text and "streamlit==" not in text:
            return "ambiguous"
        return "answerable"
    if any("enhancement" in lb or "feature" in lb for lb in labels):
        return "escalation"
    if len(body) < 200 or "version" not in text:
        return "ambiguous"
    return "answerable"


def main():
    EVAL.mkdir(parents=True, exist_ok=True)
    CASES_DIR.mkdir(parents=True, exist_ok=True)

    issues = load_jsonl(ISSUES_PATH)
    comments = load_jsonl(COMMENTS_PATH)
    docs = load_jsonl(DOCS_PATH)
    releases = load_jsonl(RELEASES_PATH)

    comments_by_issue = defaultdict(list)
    for c in comments:
        comments_by_issue[c["issue_number"]].append(c)

    # Filter usable issues
    candidates = []
    for iss in issues:
        body = iss.get("body") or ""
        if len(body) < MIN_BODY_LEN:
            continue
        if not iss.get("number") or not iss.get("created_at"):
            continue
        candidates.append(iss)

    if len(candidates) < N_TOTAL:
        raise RuntimeError(
            f"Only {len(candidates)} usable issues; need at least {N_TOTAL}. "
            "Collect more issues or lower MIN_BODY_LEN."
        )

    # Diversify by stratum
    by_stratum: Dict[str, List] = defaultdict(list)
    for iss in candidates:
        by_stratum[stratify_label(iss)].append(iss)

    rng = random.Random(SPLIT_SEED)
    selected = []
    # round-robin from strata
    strata = list(by_stratum.keys()) or ["answerable"]
    while len(selected) < N_TOTAL:
        for s in strata:
            pool = by_stratum[s]
            if not pool:
                continue
            iss = pool.pop(rng.randrange(len(pool)))
            selected.append(iss)
            if len(selected) >= N_TOTAL:
                break

    rng.shuffle(selected)
    dev = selected[:N_DEV]
    test = selected[N_DEV:N_TOTAL]

    # Mark multi-turn candidates (issues with ≥2 comments)
    multi_ids = []
    for iss in selected:
        if len(comments_by_issue.get(iss["number"], [])) >= 2:
            multi_ids.append(f"issue-{iss['number']}")
    rng.shuffle(multi_ids)
    multi_ids = multi_ids[: max(N_MULTI_TURN, 10)]

    split = {
        "dev_case_ids": [f"issue-{i['number']}" for i in dev],
        "test_case_ids": [f"issue-{i['number']}" for i in test],
        "multi_turn_case_ids": multi_ids,
        "split_seed": SPLIT_SEED,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "n_dev": N_DEV,
        "n_test": N_TEST,
        "sampling": "stratified by rough answerable/ambiguous/escalation; whole-case split",
        "source_counts": {
            "issues_total": len(issues),
            "issues_usable": len(candidates),
            "comments": len(comments),
            "docs": len(docs),
            "releases": len(releases),
        },
    }
    SPLIT_PATH.write_text(json.dumps(split, indent=2), encoding="utf-8")

    # Write one case card per selected issue
    for iss in selected:
        cid = f"issue-{iss['number']}"
        case = {
            "case_id": cid,
            "seed_issue_number": iss["number"],
            "seed_created_at": iss["created_at"],
            "seed_html_url": iss["html_url"],
            "title": iss["title"],
            "body": iss.get("body") or "",
            "labels": iss.get("labels", []),
            "state": iss.get("state"),
            "stratum_auto": stratify_label(iss),
            "is_multi_turn": cid in multi_ids,
            "split": "dev" if cid in split["dev_case_ids"] else "test",
            # filled in step1
            "visible_input": {
                "title": iss["title"],
                "body": iss.get("body") or "",
                "conversation_so_far": [],
            },
            "acceptable_source_cutoff": iss["created_at"],
            "forbidden_source_ids": [cid],  # do not retrieve the seed itself as "evidence"
            "missing_information": [],
            "defensible_outcomes": [],
            "recurring_issue_numbers": [],  # optional: fill manually if you cluster
        }
        (CASES_DIR / f"{cid}.json").write_text(
            json.dumps(case, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    print("Step 0 complete.")
    print(f"  Split written → {SPLIT_PATH}")
    print(f"  Cases written → {CASES_DIR} ({len(selected)} files)")
    print(f"  DEV:  {len(split['dev_case_ids'])}")
    print(f"  TEST: {len(split['test_case_ids'])}")
    print(f"  Multi-turn marked: {len(multi_ids)}")


if __name__ == "__main__":
    main()
