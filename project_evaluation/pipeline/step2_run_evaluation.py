"""
Step 2: Run the system on DEV and/or TEST cases with leakage controls.
- Builds a time-cutoff corpus per case (no future docs/releases, no seed issue).
- Reveals multi-turn user messages only after the assistant has replied.
- Writes raw run logs under project_evaluation/data/runs/{dev|test}/
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import (
    CASES_DIR,
    ANNOT_DIR,
    MULTI_DIR,
    RUNS_DIR,
    SPLIT_PATH,
    ISSUES_PATH,
    COMMENTS_PATH,
    DOCS_PATH,
    RELEASES_PATH,
)
from evidence_core import SourceDocument
from system_under_test import SupportAssistant


def load_jsonl(path: Path) -> List[Dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def build_full_corpus() -> List[SourceDocument]:
    docs: List[SourceDocument] = []

    # Past reports = issue + comments
    issues = load_jsonl(ISSUES_PATH)
    comments = load_jsonl(COMMENTS_PATH)
    by_issue = {}
    for c in comments:
        by_issue.setdefault(c["issue_number"], []).append(c)

    for iss in issues:
        c_text = "\n\n".join(
            f"[comment {c.get('author_association')} @ {c.get('created_at')}]\n{c.get('body') or ''}"
            for c in sorted(by_issue.get(iss["number"], []), key=lambda x: x.get("created_at") or "")
        )
        content = (
            f"Title: {iss.get('title')}\n"
            f"State: {iss.get('state')}\n"
            f"Labels: {', '.join(iss.get('labels') or [])}\n\n"
            f"{iss.get('body') or ''}\n\n--- Discussion ---\n{c_text}"
        )
        docs.append(
            SourceDocument(
                id=f"issue-{iss['number']}",
                source_type="past_report",
                title=iss.get("title") or f"issue-{iss['number']}",
                content=content,
                url_or_path=iss.get("html_url") or "",
                date=iss.get("created_at"),
                metadata={"number": iss["number"]},
            )
        )

    for row in load_jsonl(DOCS_PATH):
        docs.append(
            SourceDocument(
                id=row.get("id") or row.get("url_or_path") or row.get("title"),
                source_type="documentation",
                title=row.get("title") or "doc",
                content=row.get("content") or "",
                url_or_path=row.get("url_or_path") or "",
                version=row.get("version"),
                date=row.get("date") or row.get("collected_at"),
                metadata={"section": row.get("section"), "commit": row.get("commit")},
            )
        )

    for row in load_jsonl(RELEASES_PATH):
        docs.append(
            SourceDocument(
                id=row.get("id") or f"release-{row.get('version')}",
                source_type="release_note",
                title=row.get("title") or f"Release {row.get('version')}",
                content=row.get("content") or "",
                url_or_path=row.get("url_or_path") or "",
                version=row.get("version"),
                date=row.get("date"),
            )
        )
    return docs


def filter_corpus_for_case(corpus: List[SourceDocument], case: Dict) -> List[SourceDocument]:
    cutoff = case.get("acceptable_source_cutoff") or case.get("seed_created_at") or "9999"
    forbidden = set(case.get("forbidden_source_ids") or [])
    allowed = []
    for d in corpus:
        if d.id in forbidden:
            continue
        # seed issue itself already forbidden via id
        doc_date = d.date or "1970-01-01T00:00:00Z"
        if doc_date <= cutoff:
            allowed.append(d)
    return allowed


def run_single_case(
        case: Dict,
        annot: Dict,
        corpus: List[SourceDocument],
        multi: Optional[Dict],
        assistant: SupportAssistant,
) -> Dict[str, Any]:
    allowed = filter_corpus_for_case(corpus, case)
    assistant.state = {
        "status": "open",
        "waiting_for_user": False,
        "escalated": False,
        "last_action": None,
    }

    if multi and multi.get("turns"):
        turns = multi["turns"]
    else:
        turns = [
            {
                "role": "user",
                "visible": True,
                "text": f"{case['title']}\n\n{case['body']}",
            },
            {
                "role": "assistant",
                "acceptable": annot.get("acceptable_actions_turn0", ["answer"]),
                "expected_state": annot.get("expected_state_after_turn0", {}),
            },
        ]

    conversation: List[Dict[str, str]] = []
    turn_logs = []
    total_latency = 0.0
    total_tokens = 0

    i = 0
    while i < len(turns):
        t = turns[i]
        if t["role"] == "user":
            # only append if visible or previous assistant already replied
            if t.get("visible", True) or conversation:
                conversation.append({"role": "user", "content": t["text"]})
            i += 1
            continue

        # assistant turn
        out = assistant.reply(conversation, allowed)
        total_latency += out["latency_sec"]
        total_tokens += out["token_estimate"]

        expected_actions = t.get("acceptable") or annot.get("acceptable_actions_turn0") or []
        expected_state = t.get("expected_state") or {}

        decision_ok = out["action"] in expected_actions if expected_actions else None
        state_ok = True
        for k, v in expected_state.items():
            if out["state"].get(k) != v:
                state_ok = False
                break

        turn_logs.append(
            {
                "turn_index": len(turn_logs),
                "action": out["action"],
                "decision_ok": decision_ok,
                "state_ok": state_ok,
                "expected_actions": expected_actions,
                "expected_state": expected_state,
                "actual_state": out["state"],
                "response_text": out["text"],
                "retrieved_chunk_ids": out["retrieved_chunk_ids"],
                "latency_sec": out["latency_sec"],
                "token_estimate": out["token_estimate"],
                "gaps": out["result"].remaining_gaps,
                "citations": [
                    {"claim": e.extracted_claim, "citation": e.citation, "source_id": e.chunk.source_id}
                    for e in out["result"].evidence_used
                ],
            }
        )
        conversation.append({"role": "assistant", "content": out["text"]})
        i += 1

        # reveal next hidden user turn (handled by loop when visible flag is false
        # but conversation already has assistant → next user is appended)

    return {
        "case_id": case["case_id"],
        "split": case.get("split"),
        "bucket": annot.get("bucket"),
        "n_allowed_docs": len(allowed),
        "turns": turn_logs,
        "total_latency_sec": total_latency,
        "total_token_estimate": total_tokens,
        "n_turns": len(turn_logs),
        "ran_at": datetime.now(timezone.utc).isoformat(),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--split",
        choices=["dev", "test", "both"],
        default="dev",
        help="Which split to run. Use 'test' only for final numbers.",
    )
    args = parser.parse_args()

    split = json.loads(SPLIT_PATH.read_text(encoding="utf-8"))
    corpus = build_full_corpus()
    print(f"Full corpus size: {len(corpus)}")

    targets = []
    if args.split in ("dev", "both"):
        targets += [("dev", split["dev_case_ids"])]
    if args.split in ("test", "both"):
        targets += [("test", split["test_case_ids"])]

    assistant = SupportAssistant()

    for split_name, case_ids in targets:
        out_dir = RUNS_DIR / split_name
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n=== Running {split_name.upper()} ({len(case_ids)} cases) ===")

        for cid in case_ids:
            case = json.loads((CASES_DIR / f"{cid}.json").read_text(encoding="utf-8"))
            annot_path = ANNOT_DIR / f"{cid}.json"
            annot = json.loads(annot_path.read_text(encoding="utf-8")) if annot_path.exists() else {}
            multi_path = MULTI_DIR / f"{cid}.json"
            multi = json.loads(multi_path.read_text(encoding="utf-8")) if multi_path.exists() else None

            log = run_single_case(case, annot, corpus, multi, assistant)
            (out_dir / f"{cid}.json").write_text(
                json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            print(
                f"  {cid}: action={log['turns'][0]['action'] if log['turns'] else '?'} "
                f"docs={log['n_allowed_docs']} latency={log['total_latency_sec']:.2f}s"
            )

    print("\nStep 2 complete. Raw runs in", RUNS_DIR)


if __name__ == "__main__":
    main()
