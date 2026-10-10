"""Leakage-controlled retrieval corpus for one evaluation case.

Rules (from the evaluation brief):
* Every evaluation case (dev and test) and its whole discussion is removed from the
  search base, together with issues the case cards mark as the same recurring family.
* Past issues are included only if created before the case's cutoff, and only with the
  comments that existed at that time. Bot comments are dropped. The issue's final state
  and labels are not included: they were collected later than the cutoff.
* Release notes are included only if published before the cutoff.
* Documentation comes from one pinned docs commit (``docs_meta.json``). The snapshot is
  newer than most cases, so the evaluation is not historical for documentation; this is
  recorded in every run log through ``corpus_policy()``.
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Set

from config import COMMENTS_PATH, DOCS_META_PATH, DOCS_PATH, ISSUES_PATH, RELEASES_PATH
from problem1_part1.evidence_synthesis.evidence_core import SourceDocument

_NO_DATE = "9999-12-31T23:59:59Z"  # undated sources are treated as unknown, i.e. excluded


def _read_jsonl(path: Path) -> Iterator[Dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def _is_bot(comment: Dict[str, Any]) -> bool:
    return (comment.get("user_login") or "").endswith("[bot]")


@dataclass(frozen=True)
class Snapshot:
    """The raw snapshot loaded once and filtered per case."""

    issues: List[Dict[str, Any]]
    comments_by_issue: Dict[str, List[Dict[str, Any]]]
    docs: List[Dict[str, Any]]
    releases: List[Dict[str, Any]]
    docs_commit: str | None

    @classmethod
    def load(cls) -> "Snapshot":
        comments_by_issue: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for comment in _read_jsonl(COMMENTS_PATH):
            if not _is_bot(comment):
                comments_by_issue[str(comment["issue_number"])].append(comment)
        for comments in comments_by_issue.values():
            comments.sort(key=lambda comment: comment.get("created_at") or "")
        meta = json.loads(DOCS_META_PATH.read_text(encoding="utf-8")) if DOCS_META_PATH.exists() else {}
        return cls(
            issues=list(_read_jsonl(ISSUES_PATH)),
            comments_by_issue=dict(comments_by_issue),
            docs=list(_read_jsonl(DOCS_PATH)),
            releases=list(_read_jsonl(RELEASES_PATH)),
            docs_commit=meta.get("docs_commit"),
        )

    def corpus_for(self, cutoff: str, excluded_issue_ids: Set[str]) -> List[SourceDocument]:
        documents = [
            self._issue_document(issue, cutoff)
            for issue in self.issues
            if f"issue-{issue['number']}" not in excluded_issue_ids
            and (issue.get("created_at") or _NO_DATE) <= cutoff
        ]
        documents += [self._doc_document(row) for row in self.docs]
        documents += [
            self._release_document(row) for row in self.releases if (row.get("date") or _NO_DATE) <= cutoff
        ]
        return documents

    def policy(self) -> Dict[str, Any]:
        return {
            "evaluation_cases_excluded": True,
            "issues": "created before cutoff; comments up to cutoff; bots, final state and labels removed",
            "release_notes": "published before cutoff",
            "documentation": f"pinned snapshot {self.docs_commit or 'unknown'} (not historical)",
        }

    def _issue_document(self, issue: Dict[str, Any], cutoff: str) -> SourceDocument:
        visible = [
            comment
            for comment in self.comments_by_issue.get(str(issue["number"]), [])
            if (comment.get("created_at") or _NO_DATE) <= cutoff
        ]
        discussion = "\n\n".join(
            f"[comment by {comment.get('author_association')} @ {comment.get('created_at')}]\n{comment.get('body') or ''}"
            for comment in visible
        )
        return SourceDocument(
            id=f"issue-{issue['number']}",
            source_type="past_report",
            title=issue.get("title") or f"issue-{issue['number']}",
            content=f"Title: {issue.get('title')}\n\n{issue.get('body') or ''}\n\n--- Discussion ---\n{discussion}",
            url_or_path=issue.get("html_url") or "",
            date=issue.get("created_at"),
            metadata={"number": issue["number"], "comments_visible": len(visible)},
        )

    def _doc_document(self, row: Dict[str, Any]) -> SourceDocument:
        return SourceDocument(
            id=row.get("id") or row.get("url_or_path") or row.get("title"),
            source_type="documentation",
            title=row.get("title") or "doc",
            content=row.get("content") or "",
            url_or_path=row.get("url_or_path") or "",
            version=row.get("commit") or self.docs_commit,
            date=None,
            metadata={"section": row.get("section"), "commit": row.get("commit")},
        )

    @staticmethod
    def _release_document(row: Dict[str, Any]) -> SourceDocument:
        return SourceDocument(
            id=row.get("id") or f"release-{row.get('version')}",
            source_type="release_note",
            title=row.get("title") or f"Release {row.get('version')}",
            content=row.get("content") or "",
            url_or_path=row.get("url_or_path") or "",
            version=row.get("version"),
            date=row.get("date"),
        )


def excluded_issue_ids(split: Dict[str, Any], cases: Iterable[Dict[str, Any]]) -> Set[str]:
    """All evaluation cases plus the recurring-issue families recorded on their case cards."""
    excluded = set(split["dev_case_ids"]) | set(split["test_case_ids"])
    for case in cases:
        excluded |= {f"issue-{number}" for number in case.get("recurring_issue_numbers", [])}
    return excluded
